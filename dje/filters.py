#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import datetime
import json
import operator
import uuid
from functools import reduce

from django.contrib import messages
from django.contrib.admin import filters
from django.contrib.admin.options import IncorrectLookupParameters
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchQuery
from django.contrib.postgres.search import SearchRank
from django.contrib.postgres.search import SearchVector
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models import Case
from django.db.models import IntegerField
from django.db.models import Q
from django.db.models import Value
from django.db.models import When
from django.forms import widgets
from django.forms.fields import MultipleChoiceField
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

import django_filters

from dje.models import Dataspace
from dje.models import History
from dje.models import is_dataspace_related
from dje.models import is_secured
from dje.utils import database_re_escape
from dje.utils import extract_name_version
from dje.utils import get_uuids_list_sorted
from dje.utils import remove_field_from_query_dict
from dje.widgets import DropDownRightWidget

IS_FILTER_LOOKUP_VAR = "_filter_lookup"


class FilterSetUtilsMixin:
    def is_active(self):
        """Return True if any of the filter is active, except the 'sort' filter."""
        return bool(
            [field_name for field_name in self.form.changed_data if field_name not in ["sort"]]
        )

    def get_query_no_sort(self):
        sort_field_name = "sort"
        if self.form_prefix:
            sort_field_name = f"{self.form_prefix}-{sort_field_name}"
        return remove_field_from_query_dict(self.data, sort_field_name)

    def get_filter_breadcrumb(self, field_name, data_field_name, value):
        return {
            "label": self.filters[field_name].label,
            "value": value,
            "remove_url": remove_field_from_query_dict(self.data, data_field_name, value),
        }

    def get_filters_breadcrumbs(self):
        breadcrumbs = []

        for field_name in self.form.changed_data:
            data_field_name = f"{self.form_prefix}-{field_name}" if self.form_prefix else field_name
            for value in self.data.getlist(data_field_name):
                breadcrumbs.append(self.get_filter_breadcrumb(field_name, data_field_name, value))

        return breadcrumbs


class DataspacedFilterSet(FilterSetUtilsMixin, django_filters.FilterSet):
    related_only = []
    dropdown_fields = []

    def __init__(self, *args, **kwargs):
        try:
            self.dataspace = kwargs.pop("dataspace")
        except KeyError:
            raise AttributeError("A dataspace needs to be provided to this FilterSet.")

        self.dynamic_qs = kwargs.pop("dynamic_qs", True)
        self.parent_qs_cache = {}
        self.anchor = kwargs.pop("anchor", None)
        self.dropdown_fields = kwargs.pop("dropdown_fields", []) or self.dropdown_fields

        super().__init__(*args, **kwargs)

        for field_name, filter_ in self.filters.items():
            # Dataspace scoping for FKs on DataspaceRelated models.
            if hasattr(filter_, "queryset") and is_dataspace_related(filter_.queryset.model):
                filter_.queryset = filter_.queryset.scope(self.dataspace)

            if field_name in self.related_only:
                self.apply_related_only(field_name, filter_)

        usage_policy = self.filters.get("usage_policy")
        if usage_policy:
            model_name = self._meta.model._meta.model_name
            usage_policy.queryset = usage_policy.queryset.filter(content_type__model=model_name)

        for field_name in self.dropdown_fields:
            self.filters[field_name].extra["widget"] = DropDownRightWidget(anchor=self.anchor)

    def apply_related_only(self, field_name, filter_):
        """
        Limit the filter choices to the values used on the parent queryset.
        This logic emulate a facets logic.
        See also `django.contrib.admin.filters.RelatedOnlyFieldListFilter`.
        """
        parent_qs = self.get_parent_qs_for_related_only(field_name)
        is_related_field = hasattr(filter_, "queryset")

        if is_related_field:  # FK type fields
            filter_.queryset = filter_.queryset.distinct().filter(
                pk__in=parent_qs.values_list(f"{field_name}__pk", flat=True)
            )
        else:  # Choices type fields
            choices_qs = (
                parent_qs.order_by(field_name).distinct().values_list(field_name, flat=True)
            )
            filter_.extra["choices"] = [
                choice for choice in filter_.extra["choices"] if choice[0] in choices_qs
            ]

    def get_parent_qs_for_related_only(self, field_name):
        """
        Return the parent QuerySet with active filters applied
        except for the given `filter_name`.
        The model default manager is used in place of the self.queryset
        since it do not containing the annotations and select/prefetch_related
        that are not needed for that dynamic filtering.
        """
        parent_qs = self._meta.model._default_manager.scope(self.dataspace)

        if not self.dynamic_qs:
            return parent_qs

        data = self.data.copy()

        # `sort` is only used for ordering and does not apply here.
        # Removing it from the queryset improves the performances.
        fields_to_remove = [
            "sort",
            field_name,
        ]

        for name in fields_to_remove:
            data.pop(name, None)

        if not data:
            return parent_qs

        cache_key = json.dumps(data, sort_keys=True)
        cached_qs = self.parent_qs_cache.get(cache_key, None)
        if cached_qs:
            return cached_qs

        filterset = self.__class__(
            data=data,
            dataspace=self.dataspace,
            queryset=parent_qs,
            dynamic_qs=False,
        )
        self.parent_qs_cache[cache_key] = filterset.qs
        return filterset.qs


class SearchFilter(django_filters.CharFilter):
    def __init__(self, search_fields, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.search_fields = search_fields

    def filter(self, qs, value):
        lookup_type = "icontains"

        for bit in value.split():
            or_queries = [
                models.Q(**{f"{field}__{lookup_type}": bit}) for field in self.search_fields
            ]
            qs = qs.filter(reduce(operator.or_, or_queries))

        return qs


class SearchRankFilter(SearchFilter):
    """
    Search on multiple fields using django.contrib.postgres.search module capabilities.
    For better performance, all given `search_fields` should be indexed (db_index=True).
    """

    def __init__(self, min_rank=0.01, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.min_rank = min_rank

    def filter(self, qs, value):
        if not value:
            return qs

        vector = SearchVector(*self.search_fields)
        query = SearchQuery(value)
        default_ordering = qs.model._meta.ordering
        qs = (
            qs.annotate(rank=SearchRank(vector, query))
            .filter(rank__gte=self.min_rank)
            .order_by("-rank", *default_ordering)
        )
        return qs.distinct() if self.distinct else qs


class MatchOrderedSearchFilter(SearchRankFilter):
    """
    Start with a case-insensitive containment search on the `match_order_fields` fields,
    ordering based on the match type using annotations.

    If that simple search Return nothing, fallback to the SearchRankFilter
    searching, this allows "name version" type string to return some results.

    Postgres pattern matching docs available at:
    https://www.postgresql.org/docs/10/static/functions-matching.html#POSIX-CONSTRAINT-ESCAPES-TABLE
    """

    def __init__(self, match_order_fields, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.match_order_fields = match_order_fields

    def get_match_order_lookups(self, lookup_type, value):
        or_queries = [
            models.Q(**{f"{field}__{lookup_type}": value}) for field in self.match_order_fields
        ]
        return reduce(operator.or_, or_queries)

    def filter(self, qs, value):
        if not value:
            return qs

        # \y matches only at the beginning or end of a word
        regex_escaped_value = r"\y{}\y".format(database_re_escape(value))

        # All matching patterns are applied case-insensitive
        match_order = Case(
            # 1. Exact match
            When(self.get_match_order_lookups("iexact", value), then=Value(1)),
            # 2. Contains word with boundaries
            When(self.get_match_order_lookups("iregex", regex_escaped_value), then=Value(2)),
            # 3. Contains word
            default=Value(3),  # default `icontains` clause in `.filter()`
            output_field=IntegerField(),
        )

        default_ordering = self.model._meta.ordering

        simple_search_qs = (
            qs.filter(self.get_match_order_lookups("icontains", value))
            .annotate(match_order=match_order)
            .order_by("match_order", *default_ordering)
        )

        if simple_search_qs.exists():
            if self.distinct:
                simple_search_qs = simple_search_qs.distinct()
            return simple_search_qs

        return super().filter(qs, value)


class ProgressiveTextSearchFilter(SearchRankFilter):
    """Start with a icontains search before falling back on a ranking search."""

    def filter(self, qs, value):
        if not value:
            return qs

        if len(self.search_fields) != 1:
            raise ImproperlyConfigured(f"Only 1 field supported for {self.__class__}")
        search_field = self.search_fields[0]

        contains_search_qs = qs.filter(**{f"{search_field}__icontains": value})
        if list(contains_search_qs):
            return contains_search_qs

        vector = SearchVector(search_field)
        query = SearchQuery(value)

        return (
            qs.annotate(rank=SearchRank(vector, query))
            .filter(rank__gte=self.min_rank)
            .order_by("-rank")
        )


class DefaultOrderingFilter(django_filters.OrderingFilter):
    """Add default ordering from model meta after the provided value."""

    def filter(self, qs, value):
        qs = super().filter(qs, value)

        ordering = qs.query.order_by
        if not ordering:
            return qs

        # Add the default ordering from the model and override the order_by value
        for field_name in self.model._meta.ordering:
            if field_name not in ordering:
                ordering += (field_name,)

        return qs.order_by(*ordering)


class CharMultipleWidget(widgets.TextInput):
    """
    Enable the support for `MultiValueDict` `?field=a&field=b`
    reusing the `SelectMultiple.value_from_datadict()` but render as a `TextInput`.
    """

    def value_from_datadict(self, data, files, name):
        value = widgets.SelectMultiple().value_from_datadict(data, files, name)

        if not value or value == [""]:
            return ""

        return value

    def format_value(self, value):
        """Return a value as it should appear when rendered in a template."""
        return ", ".join(value)


class MultipleCharField(MultipleChoiceField):
    widget = CharMultipleWidget

    def valid_value(self, value):
        return True


class MultipleCharFilter(django_filters.MultipleChoiceFilter):
    """Filter on multiple values for a CharField type using `?field=a&field=b` URL syntax."""

    field_class = MultipleCharField


class MultipleUUIDField(MultipleChoiceField):
    widget = CharMultipleWidget

    def valid_value(self, value):
        try:
            uuid.UUID(value)
        except ValueError:
            return False
        return True


class MultipleUUIDFilter(django_filters.MultipleChoiceFilter):
    """Filter on multiple values for an `UUIDField` type using `?field=a&field=b` URL syntax."""

    help_text = "Exact UUID. Multi-value supported."
    field_class = MultipleUUIDField

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", self.help_text)
        super().__init__(*args, **kwargs)


class LastModifiedDateFilter(django_filters.DateTimeFilter):
    help_text = (
        "Limits to records created or updated since that date. "
        'Supports both "YYYY-MM-DD" date and "YYYY-MM-DD HH:MM" datetime.'
    )

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", self.help_text)
        kwargs["lookup_expr"] = "gte"
        super().__init__(*args, **kwargs)


class NameVersionFilter(MultipleCharFilter):
    """
    Filter by `name:version` syntax.
    Supports multiple values: `?name_version=Name:Version&name_version=Name:Version`
    """

    help_text = (
        'Exact match on name/version using the syntax "name:version". Multi-value supported.'
    )

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", self.help_text)
        self.name_field_name = kwargs.pop("name_field_name", "name")
        self.version_field_name = kwargs.pop("version_field_name", "version")
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        value = value or ()  # Make sure we have an iterable

        # Even though not a noop, no point filtering if empty
        if not value:
            return qs

        q = Q()

        for v in set(value):
            try:
                name, version = extract_name_version(v)
            except SyntaxError:
                pass
            else:
                q |= Q(**{self.name_field_name: name, self.version_field_name: version})

        if self.distinct:
            return self.get_method(qs)(q).distinct()

        return self.get_method(qs)(q)


class BooleanChoiceFilter(django_filters.ChoiceFilter):
    def __init__(self, *args, **kwargs):
        kwargs["empty_label"] = kwargs.pop("empty_label", "All")
        kwargs["choices"] = kwargs.pop(
            "choices",
            (
                ("yes", _("Yes")),
                ("no", _("No")),
            ),
        )
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        boolean_value = {"yes": True, "no": False}.get(value)
        if boolean_value is not None:
            return qs.filter(**{self.field_name: boolean_value}).distinct()
        elif value in ["none", "unknown"]:
            return qs.filter(**{f"{self.field_name}__isnull": True}).distinct()
        return qs


class ChoicesOnlyListFilterMixin:
    """Remove the 'All' choice from SimpleListFilter.choices()"""

    def choices(self, cl):
        for lookup, title in self.lookup_choices:
            yield {
                "selected": str(self.value()) == str(lookup),
                "query_string": cl.get_query_string(
                    {
                        self.parameter_name: lookup,
                    },
                    [],
                ),
                "display": title,
            }


class BaseDataspaceLookupsFilter(filters.SimpleListFilter):
    def lookups(self, request, model_admin):
        user_dataspace = request.user.dataspace

        reference_dataspace = Dataspace.objects.get_reference()

        if user_dataspace == reference_dataspace:
            dataspaces = Dataspace.objects.all()
        else:
            dataspaces = [user_dataspace]
            if reference_dataspace:
                dataspaces.append(reference_dataspace)

        return [(dataspace.id, dataspace.name) for dataspace in dataspaces]


class DataspaceFilter(ChoicesOnlyListFilterMixin, BaseDataspaceLookupsFilter):
    """
    Scope the ChangeList results by a Dataspace.
    Default is the current User Dataspace.
    Anyone can look into reference Dataspace.
    Only Reference User can look into other Dataspaces.
    """

    title = _("dataspace")
    parameter_name = "dataspace__id"

    def lookups(self, request, model_admin):
        """Set the lookup value for the current user dataspace choice to None."""
        lookups = super().lookups(request, model_admin)
        return [(None if name == request.user.dataspace.name else pk, name) for pk, name in lookups]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.scope_by_id(self.value())
        return queryset.scope(request.user.dataspace)


class MissingInFilter(BaseDataspaceLookupsFilter):
    """
    Filter by objects missing in the given dataspace, compared with the
    current `DataspaceFilter.parameter_name` or user dataspace.
    Both values for reference and target Dataspace are validated against the
    self.lookup_choices to make sure the user has the proper access permissions.
    This filter is only available to superusers, this is enforced in
    DataspacedAdmin.get_list_filter()
    """

    title = _("missing in")
    parameter_name = "missing_in"

    def queryset(self, request, queryset):
        if not self.value():
            return

        valid_choices = [str(choice) for choice, _ in self.lookup_choices]
        if str(self.value()) not in valid_choices:
            raise IncorrectLookupParameters()

        return queryset.exclude(uuid__in=get_uuids_list_sorted(self.value(), queryset.model))


class LimitToDataspaceListFilter(filters.RelatedFieldListFilter):
    """
    Limit the choices of a filter on a FK to the currently "filtered" Dataspace.
    The limit_choices_to declared on the model field will be applied too.
    """

    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)

        # The get_limit_choices_to_from_path is broken in 1.7, see code in 1.6
        # limit_choices_to = get_limit_choices_to_from_path(model, field_path)
        limit_choices_to = models.Q(**field.get_limit_choices_to())

        dataspace_id = request.GET.get(DataspaceFilter.parameter_name, request.user.dataspace_id)
        queryset = field.related_model.objects.scope_by_id(dataspace_id).filter(limit_choices_to)

        if field.related_model.__name__ == "UsagePolicy":
            content_type = ContentType.objects.get_for_model(model)
            queryset = queryset.filter(content_type=content_type)

        self.lookup_choices = [(x._get_pk_val(), str(x)) for x in queryset]


class HistoryActionTimeListFilter(filters.SimpleListFilter):
    """
    Filter by the dates of an object's associated History entries.

    Inspired by django.contrib.admin.filters.DateFieldListFilter.
    """

    # The action_flag constant of History to filter by
    action_flag = None

    def __init__(self, request, params, model, model_admin):
        self.model_content_type = ContentType.objects.get_for_model(model)
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return (
            ("any_date", _("Any Date")),
            ("today", _("Today")),
            ("past_7_days", _("Past 7 days")),
            ("past_30_days", _("Past 30 days")),
            ("this_year", _("This year")),
        )

    def get_history_objects(self):
        """
        Return the History objects that match the model's content type and
        the action flag. Return None if self.value() is not valid.
        """
        now = timezone.now()
        # When time zone support is enabled, convert "now" to the user's time
        # zone so Django's definition of "Today" matches what the user expects.
        if now.tzinfo is not None:
            current_tz = timezone.get_current_timezone()
            now = now.astimezone(current_tz)
            if hasattr(current_tz, "normalize"):
                # available for pytz time zones
                now = current_tz.normalize(now)

        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + datetime.timedelta(days=1)

        since_field_lookup = "action_time__gte"
        until_field_lookup = "action_time__lt"

        # filters for the DateTimeField
        filter_map = {
            "today": {
                since_field_lookup: today,
                until_field_lookup: tomorrow,
            },
            "past_7_days": {
                since_field_lookup: today - datetime.timedelta(days=7),
                until_field_lookup: tomorrow,
            },
            "past_30_days": {
                since_field_lookup: today - datetime.timedelta(days=30),
                until_field_lookup: tomorrow,
            },
            "this_year": {
                since_field_lookup: today.replace(month=1, day=1),
                until_field_lookup: tomorrow,
            },
        }

        if self.value() == "any_date":
            return

        if self.value() in filter_map:
            history_filters = filter_map[self.value()]
            return History.objects.filter(
                content_type=self.model_content_type,
                action_flag=self.action_flag,
                **history_filters,
            )

    def queryset(self, request, queryset):
        # Convert the History object_id ValuesQuerySet into a list because
        # History.object_id is a TextField and we don't want the ORM to
        # try to cleverly make a subquery for us that will try to compare
        # the model's primary key (most likely an integer) with text
        history_objects = self.get_history_objects()
        if history_objects is not None:
            pks = list(history_objects.values_list("object_id", flat=True))

            # use .distinct() to remove duplicates (there may be multiple
            # History objects for a model)
            return queryset.filter(pk__in=pks).distinct()

    def choices(self, cl):
        """
        Remove the option 'All' that SimpleListFilter adds by default.
        The functionality of 'All' is handled by 'any_date'.
        """
        for lookup, title in self.lookup_choices:
            yield {
                "selected": self.value() == lookup,
                "query_string": cl.get_query_string(
                    {
                        self.parameter_name: lookup,
                    },
                    [],
                ),
                "display": title,
            }


class HistoryCreatedActionTimeListFilter(HistoryActionTimeListFilter):
    title = _("created date")
    parameter_name = "created_date"
    action_flag = History.ADDITION


class HistoryModifiedActionTimeListFilter(HistoryActionTimeListFilter):
    title = _("modified date")
    parameter_name = "modified_date"
    action_flag = History.CHANGE


class LevelFieldListFilter(filters.FieldListFilter):
    """Filter for 0 to 100 level fields."""

    def __init__(self, field, request, params, model, model_admin, field_path):
        self.lookup_kwarg = field_path
        self.lookup_val = request.GET.get(self.lookup_kwarg)
        super().__init__(field, request, params, model, model_admin, field_path)

    def expected_parameters(self):
        return [self.lookup_kwarg]

    def choices(self, cl):
        choices = (
            (None, _("All")),
            ("20", _("0 to 20")),
            ("40", _("20 to 40")),
            ("60", _("40 to 60")),
            ("80", _("60 to 80")),
            ("100", _("80 to 100")),
        )

        for lookup, title in choices:
            yield {
                "selected": self.lookup_val == lookup,
                "query_string": cl.get_query_string({self.lookup_kwarg: lookup}),
                "display": title,
            }

    def queryset(self, request, queryset):
        if self.lookup_val:
            int_value = int(self.lookup_val)
            return queryset.filter(
                **{
                    f"{self.lookup_kwarg}__gte": int_value - 20,
                    f"{self.lookup_kwarg}__lte": int_value,
                }
            )


class CreatedByListFilter(filters.SimpleListFilter):
    """
    Filter by the user who created an object according to the objects's
    associated History. The value from LimitToDataspaceListFilter is
    used for the Dataspace if it exists.
    """

    title = _("created by")
    parameter_name = "created_by"

    def __init__(self, request, params, model, model_admin):
        self.model_content_type = ContentType.objects.get_for_model(model)
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        dataspace_id = request.GET.get(DataspaceFilter.parameter_name, request.user.dataspace.id)
        # Find users of the selected Dataspace
        users = get_user_model().objects.scope_by_id(dataspace_id)

        # Find users who have created at least 1 object
        users = (
            users.filter(
                history__action_flag=History.ADDITION,
                history__content_type=self.model_content_type,
                history__object_dataspace__id=dataspace_id,
            )
            .distinct()
            .order_by("last_name")
        )
        return [(user.pk, user.get_full_name()) for user in users]

    def queryset(self, request, queryset):
        if self.value() is not None:
            user_pk = self.value()
            history_entries = History.objects.filter(
                content_type=self.model_content_type, action_flag=History.ADDITION, user__pk=user_pk
            )
            pks = list(history_entries.values_list("object_id", flat=True))
            return queryset.filter(pk__in=pks)


class IsNullFieldListFilter(filters.FieldListFilter):
    """
    Filter on direct, ForeignKey, and Many2Many fields using isnull to check
    is a value is assigned.
    On ManyToMany type of fields, checks if at least 1 Related object exists.
    """

    def __init__(self, field, request, params, model, model_admin, field_path):
        self.lookup_kwarg = f"{field_path}__isnull"
        self.lookup_val = request.GET.get(self.lookup_kwarg)
        super().__init__(field, request, params, model, model_admin, field_path)
        self.title = "Has {}".format(getattr(field, "verbose_name", field_path))

    def expected_parameters(self):
        return [self.lookup_kwarg]

    def choices(self, cl):
        choices = ((None, _("All")), ("0", _("Yes")), ("1", _("No")))

        for lookup, title in choices:
            yield {
                "selected": self.lookup_val == lookup,
                "query_string": cl.get_query_string({self.lookup_kwarg: lookup}),
                "display": title,
            }


class RelatedLookupListFilter(filters.FieldListFilter):
    template = "admin/filter_related_lookup.html"

    # List of filters to be added to the lookup_url, for example ['<field>__isnull=False']
    lookup_filters = []

    def __init__(self, field, request, params, model, model_admin, field_path):
        related_model = field.related_model
        remote_field_name = related_model._meta.pk.name

        info = related_model._meta.app_label, related_model._meta.model_name
        self.lookup_url = reverse("admin:{}_{}_changelist".format(*info))

        self.lookup_kwarg = f"{field_path}__{remote_field_name}__exact"
        self.lookup_val = request.GET.get(self.lookup_kwarg)

        lookup_filters = self.lookup_filters[:]

        # Similar to IS_POPUP_VAR, to control items display in templates
        lookup_filters.append(f"{IS_FILTER_LOOKUP_VAR}=1")

        # Propagates the dataspace filtering to the lookup URL
        dataspace_id = request.GET.get(DataspaceFilter.parameter_name)
        if dataspace_id:
            lookup_filters.append(f"{DataspaceFilter.parameter_name}={dataspace_id}")

        if lookup_filters:
            self.lookup_params = "&{}".format("&".join(lookup_filters))

        if self.lookup_val:
            manager = related_model._default_manager
            if is_secured(manager):
                manager = manager.get_queryset(user=request.user)

            try:
                self.lookup_object = manager.scope_by_id(
                    dataspace_id or request.user.dataspace_id
                ).get(pk=self.lookup_val)
            except related_model.DoesNotExist:
                if dataspace_id:
                    msg = "Set the Dataspace filter before using the {} lookup filter".format(
                        getattr(field, "verbose_name", field_path).title()
                    )
                    messages.warning(request, msg)
                raise IncorrectLookupParameters()

        super().__init__(field, request, params, model, model_admin, field_path)

    def expected_parameters(self):
        return [self.lookup_kwarg]

    def has_output(self):
        return True

    def choices(self, cl):
        """
        Inject the href used on the 'remove' link in the filter.
        choices() is the only place where the ChangeList `cl` is available.
        """
        self.removal_href = cl.get_query_string(remove=[self.lookup_kwarg])
        return []


class HasValueFilter(django_filters.ChoiceFilter):
    def __init__(self, *args, **kwargs):
        kwargs["lookup_expr"] = "exact"
        kwargs["empty_label"] = "All"
        if not kwargs.get("choices"):
            kwargs["choices"] = (
                ("yes", _("Yes")),
                ("no", _("No")),
            )
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value == "yes":
            return qs.exclude(**{f"{self.field_name}__{self.lookup_expr}": ""}).distinct()
        elif value == "no":
            return qs.filter(**{f"{self.field_name}__{self.lookup_expr}": ""}).distinct()
        return qs


class HasRelationFilter(django_filters.ChoiceFilter):
    def __init__(self, *args, **kwargs):
        kwargs["lookup_expr"] = "isnull"
        kwargs["empty_label"] = "Any"
        kwargs.setdefault(
            "choices",
            (
                ("with", _("With")),
                ("without", _("Without")),
            ),
        )
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value in ["with", "yes"]:
            return qs.filter(**{f"{self.field_name}__{self.lookup_expr}": False}).distinct()
        elif value in ["without", "no"]:
            return qs.filter(**{f"{self.field_name}__{self.lookup_expr}": True}).distinct()
        return qs


class HasCountFilter(HasRelationFilter):
    """
    Extend `HasRelationFilter` using the `count` annotation for performances.
    Requires the proper `annotate()` on the QuerySet.
    """

    def filter(self, qs, value):
        if value in ["with", "yes"]:
            return qs.filter(**{f"{self.field_name}_count__gt": 0}).distinct()
        elif value in ["without", "no"]:
            return qs.filter(**{f"{self.field_name}_count__exact": 0}).distinct()
        return qs
