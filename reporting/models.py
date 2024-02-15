#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import ast
import logging
import operator
from contextlib import suppress
from functools import reduce

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import ManyToOneRel
from django.db.models import Q
from django.db.models import QuerySet
from django.db.models.fields.related import ForeignKey
from django.db.models.fields.related import RelatedField
from django.forms import fields_for_model
from django.urls import NoReverseMatch
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _

from dje.models import DataspacedManager
from dje.models import DataspacedModel
from dje.models import DataspacedQuerySet
from dje.models import HistoryFieldsMixin
from dje.models import is_secured
from dje.models import secure_queryset_relational_fields
from dje.utils import extract_name_version
from reporting.fields import DATE_FILTER_CHOICES
from reporting.fields import BooleanSelect
from reporting.fields import DateFieldFilterSelect
from reporting.introspection import introspector
from reporting.utils import get_changelist_list_display
from reporting.utils import get_ordering_field

logger = logging.getLogger("dje")

# When adding a new model to the following list:
# - add the model in reporting.forms.MODEL_WHITELIST
# - add ReportingQueryListFilter in the corresponding ModelAdmin.list_filter
CT_LIMIT = (
    models.Q(app_label="license_library", model="license")
    | models.Q(app_label="component_catalog", model="component")
    | models.Q(app_label="component_catalog", model="subcomponent")
    | models.Q(app_label="component_catalog", model="package")
    | models.Q(app_label="organization", model="owner")
    | models.Q(app_label="workflow", model="request")
    | models.Q(app_label="license_library", model="licensetag")
    | models.Q(app_label="license_library", model="licenseprofile")
    | models.Q(app_label="license_library", model="licensechoice")
    | models.Q(app_label="product_portfolio", model="product")
    | models.Q(app_label="product_portfolio", model="productcomponent")
    | models.Q(app_label="product_portfolio", model="productpackage")
    | models.Q(app_label="product_portfolio", model="productinventoryitem")
    | models.Q(app_label="product_portfolio", model="codebaseresource")
)

LICENSE_TAG_PREFIX = "tag: "

MULTIVALUE_SEPARATOR = ", "

ERROR_STR = "Error"

EMPTY_STR = ""

# Similar to .fields.BooleanSelect values
ISNULL_LOOKUP_CHOICES = {
    "2": True,
    True: True,
    "True": True,
    "3": False,
    "False": False,
    False: False,
}


def get_reportable_models():
    return [
        apps.get_model(
            app_label=dict(q_object.children)["app_label"],
            model_name=dict(q_object.children)["model"],
        )
        for q_object in CT_LIMIT.children
    ]


def get_by_reporting_key(model_class, dataspace, value):
    """Return the instance for a given model_class using reporting_key name:version or id."""
    value = str(value)

    try:
        name, version = extract_name_version(value)
    except SyntaxError:
        filters = {"id": value}
    else:
        filters = {"name": name, "version": version}

    if isinstance(model_class, QuerySet):
        queryset = model_class
    else:
        queryset = model_class._default_manager

    try:
        return queryset.scope(dataspace).get(**filters)
    except ObjectDoesNotExist:
        return


class QueryQuerySet(DataspacedQuerySet):
    def get_for_model(self, model_class):
        return self.filter(content_type=ContentType.objects.get_for_model(model_class))


class Query(HistoryFieldsMixin, DataspacedModel):
    name = models.CharField(
        max_length=100,
        help_text=_("A unique, descriptive title for your query."),
    )

    description = models.TextField(
        blank=True,
        help_text=_("The purpose of your query."),
    )

    content_type = models.ForeignKey(
        to=ContentType,
        on_delete=models.PROTECT,
        limit_choices_to=CT_LIMIT,
        verbose_name=_("object type"),
        help_text=_(
            "Choose the primary data source for your query: licenses, components, " "or owners."
        ),
    )

    OPERATOR_CHOICES = (
        ("and", "and"),
        ("or", "or"),
    )

    operator = models.CharField(
        max_length=5,
        choices=OPERATOR_CHOICES,
        default="and",
        help_text=_(
            "If you define more that one Filter for your query, indicate "
            'if all ("and") or any ("or") of the Filter conditions must be true.'
        ),
    )

    objects = DataspacedManager.from_queryset(QueryQuerySet)()

    class Meta:
        unique_together = (("dataspace", "name"), ("dataspace", "uuid"))
        ordering = ("name",)
        verbose_name_plural = _("queries")

    def __str__(self):
        return f"{self.name} ({self.content_type.model})"

    def get_model(self):
        return self.content_type.model_class()

    def get_qs(self, runtime_value_map=None, user=None):
        """
        Return a QuerySet created using the assigned Filters.
        The returned QuerySet is not yet evaluated.
        Providing `user` is required for "secured" Model Managers.
        """
        if runtime_value_map is None:
            runtime_value_map = {}

        model = self.get_model()
        manager = model._default_manager

        q_objects = []
        for filter_ in self.filters.all():
            runtime_value = runtime_value_map.get(filter_, {}).get("value", None)
            q_object = filter_.get_q(runtime_value, user)
            if q_object:
                q_objects.append(q_object)

        if not q_objects:  # Return nothing rather than everything when no valid filters
            return manager.none()

        order_fields = []
        for order_field in self.order_fields.all():
            prefix = "-" if order_field.sort == "descending" else ""
            order_fields.append(f"{prefix}{order_field.field_name}")

        if not order_fields:  # Force order by primary_key to prevent UnorderedObjectListWarning
            order_fields = [model._meta.pk.name]

        if is_secured(manager):
            qs = manager.get_queryset(user)
        elif hasattr(manager, "product_secured"):  # Special case for the Request manager
            qs = manager.product_secured(user)
        else:
            qs = manager.scope(self.dataspace)

        qs = secure_queryset_relational_fields(qs, user)

        operator_type = operator.or_ if self.operator == "or" else operator.and_
        return qs.filter(reduce(operator_type, q_objects)).order_by(*order_fields).distinct()

    def is_valid(self):
        """Return True if the Query can be executed without any Exceptions."""
        # Warning: do not use count() or exists() since it bypass the validation for order_by()
        # Forcing evaluation with len() but slicing with [:1] for performance
        try:
            len(self.get_qs()[:1])
        except Exception:
            return False
        return True

    @staticmethod
    def get_extra_relational_fields():
        return ["filters", "order_fields"]

    def get_order_list_for_url(self, request, model_admin):
        """
        Use the order_fields set on the Query instance with the list_display
        of the Query.content_type ModelAdmin class to generate Order
        parameters in the changelist link. If an order_field is not part of
        the list_display of the target changelist, it will be ignored.
        """
        list_display = get_changelist_list_display(request, model_admin)
        list_display_order_fields = [
            get_ordering_field(model_admin, field_name) for field_name in list_display
        ]

        order_list = []
        for order_field in self.order_fields.all():
            if order_field.field_name in list_display_order_fields:
                index = list_display_order_fields.index(order_field.field_name)
                prefix = "-" if order_field.sort == "descending" else ""
                order_list.append(f"{prefix}{index}")

        return order_list

    def get_changelist_url(self):
        """Return the changelist URL of the related Model."""
        opts = self.get_model()._meta
        with suppress(NoReverseMatch):
            return reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")

    def get_changelist_url_with_filters(self):
        """Return the changelist URL of the related Model including a filter for this Query."""
        from reporting.filters import ReportingQueryListFilter

        params = {ReportingQueryListFilter.parameter_name: self.id}
        url = self.get_changelist_url()
        if url:
            return f"{url}?{urlencode(params)}"


class Filter(DataspacedModel):
    query = models.ForeignKey(
        to="reporting.Query",
        on_delete=models.CASCADE,
        related_name="filters",
    )

    field_name = models.TextField()

    LOOKUP_CHOICES = (
        ("exact", "Exact match. (e.g.: apache-2.0)"),
        ("iexact", "Case-insensitive exact match. (e.g.: APACHE-2.0)"),
        ("contains", "Case-sensitive containment test. (e.g.: apache)"),
        ("icontains", "Case-insensitive containment test. (e.g.: Apache)"),
        ("in", 'In a given list. (e.g.: ["apache-1.1", "apache-2.0"])'),
        ("startswith", "Case-sensitive starts-with."),
        ("istartswith", "Case-insensitive starts-with."),
        ("endswith", "Case-sensitive ends-with."),
        ("iendswith", "Case-insensitive ends-with."),
        ("gt", "Greater than."),
        ("gte", "Greater than or equal to."),
        ("lt", "Less than."),
        ("lte", "Less than or equal to."),
        ("year", "Exact year match."),
        ("month", "Exact month match."),
        ("day", "Exact day match."),
        ("isnull", "IS NULL. Takes either True or False."),
        ("isempty", "IS EMPTY. Takes either True or False."),
        ("regex", 'Case-sensitive regular expression match. (e.g.: r"^(A?)+")'),
        ("descendant", "Hierarchy traversal: Descendant of (id). (e.g.: 1337)"),
        (
            "product_descendant",
            "Product Hierarchy traversal. Takes product identifier name:version or id",
        ),
    )

    lookup = models.CharField(
        max_length=30,
        choices=LOOKUP_CHOICES,
    )

    value = models.TextField(
        blank=True,
    )

    runtime_parameter = models.BooleanField(
        default=False,
    )

    negate = models.BooleanField(
        default=False,
        help_text=(
            'Check to negate this lookup, as in "does NOT match". '
            "This can be combined with regular lookups."
        ),
    )

    class Meta:
        unique_together = ("dataspace", "uuid")
        ordering = ("pk",)

    def __str__(self):
        return f"{self.field_name} {self.lookup} {self.value}"

    def save(self, *args, **kwargs):
        self.dataspace = self.query.dataspace
        super().save(*args, **kwargs)

    def get_coerced_value(self, value):
        """
        Return a Python object that corresponds to ``value``.  This is
        accomplished by introspecting fields of models and using their
        corresponding form fields to convert strings to Python objects.

        For example, the value 'True' for a ``BooleanField`` is coerced to True.
        """
        field_parts = self.field_name.split("__")  # Split field into list

        # Use the field parts to derive the model field instance
        model = self.query.get_model()
        query_name_map = introspector.get_query_name_map(
            model_class=model,
            get_fields=True,
            get_m2m=True,
            get_related_m2m=True,
            get_related=True,
            get_generic_relation=True,
        )
        for index, part in enumerate(field_parts):
            if index == len(field_parts) - 1:
                final_part = field_parts[-1]
                model_field_instance = model._meta.get_field(final_part)

                # For non-RelatedFields use the model field's form field to
                # coerce the value to a Python object
                if not isinstance(model_field_instance, RelatedField):
                    # Skip validation for containment filters since the value may not be valid.
                    if self.lookup in ["contains", "icontains"]:
                        return value
                    # Runs the Field.clean() method to validate the value, this
                    # is required to run the custom validators declared on the
                    # Model field.
                    model_field_instance.clean(value, model)
                    # We must check if ``fields_for_model()`` Return the field
                    # we are considering.  For example ``AutoField`` returns
                    # None for its form field and thus will not be in the
                    # dictionary returned by ``fields_for_model()``.
                    form_field_instance = fields_for_model(model).get(final_part)
                    if form_field_instance:
                        widget_value = form_field_instance.widget.value_from_datadict(
                            data={final_part: value}, files={}, name=final_part
                        )
                        # Set ``required`` to False to allow empty values
                        form_field_instance.required = False
                        return form_field_instance.clean(widget_value)
                    else:
                        return value
            elif part in query_name_map:
                # Set the next model and query name map to work with
                model = query_name_map[part]
                query_name_map = introspector.get_query_name_map(
                    model_class=model,
                    get_fields=True,
                    get_m2m=True,
                    get_related_m2m=True,
                    get_related=True,
                    get_generic_relation=True,
                )
        return value

    def get_value_as_list(self, value):
        try:
            # `ast.literal_eval()` allows to safely evaluate Python expressions
            return ast.literal_eval(value)
        except SyntaxError:
            return []

    def get_q(self, runtime_value=None, user=None):
        value = runtime_value or self.value
        if not value:
            return

        if value == BooleanSelect.ALL_CHOICE_VALUE:
            return

        # Hack to support special values for date filtering, see #9049
        if value in [choice[0] for choice in DATE_FILTER_CHOICES]:
            value = DateFieldFilterSelect().value_from_datadict(
                data={"value": value}, files=None, name="value"
            )

        left_hand_side = f"{self.field_name}__{self.lookup}"

        # The in lookup is special because it must parse a comma-separated string
        if self.lookup == "in":
            right_hand_side = self.get_value_as_list(value)

        elif self.lookup == "descendant":
            model_class = self.query.content_type.model_class()
            root_instance = get_by_reporting_key(model_class, self.dataspace, value)
            if not root_instance:
                return
            left_hand_side = "id__in"
            right_hand_side = root_instance.get_descendant_ids()

        elif self.lookup == "product_descendant":
            from product_portfolio.models import Product

            # Requires a `user` to be provided for secured Product scoping
            product_secured_qs = Product.objects.get_queryset(user)
            product = get_by_reporting_key(product_secured_qs, self.dataspace, value)
            if not product:
                return
            left_hand_side = "id__in"
            right_hand_side = product.get_merged_descendant_ids()

        elif self.lookup == "isnull":
            right_hand_side = ISNULL_LOOKUP_CHOICES.get(value, None)
            # WARNING '== None' matters as False is a valid value!
            if right_hand_side is None:
                return

        elif self.lookup == "isempty":
            if bool(ISNULL_LOOKUP_CHOICES.get(value, False)):
                left_hand_side = f"{self.field_name}__in"
                right_hand_side = ["", [], {}]  # Support for JSONfield
            else:
                # Using "greater than" as a workaround to filter by non-empty values.
                left_hand_side = f"{self.field_name}__gt"
                right_hand_side = ""

        elif value == "None":
            right_hand_side = None

        else:
            right_hand_side = self.get_coerced_value(value)

        q_object = Q(**{left_hand_side: right_hand_side})

        return ~q_object if self.negate else q_object


class OrderField(DataspacedModel):
    query = models.ForeignKey(
        to="reporting.Query",
        on_delete=models.CASCADE,
        related_name="order_fields",
    )

    field_name = models.TextField()

    SORT_CHOICES = (
        ("ascending", "ascending"),
        ("descending", "descending"),
    )

    sort = models.TextField(
        choices=SORT_CHOICES,
        default="ascending",
    )

    seq = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ("dataspace", "uuid")
        ordering = ("seq",)

    def __str__(self):
        return f"<{self.query.name}>: ({self.seq}) {self.field_name} {self.sort}"

    def save(self, *args, **kwargs):
        self.dataspace = self.query.dataspace
        super().save(*args, **kwargs)


class ColumnTemplate(HistoryFieldsMixin, DataspacedModel):
    name = models.CharField(
        max_length=100,
        help_text=_("A unique, descriptive title for your column template."),
    )

    description = models.TextField(
        blank=True,
        help_text=_("The purpose of your column template."),
    )

    content_type = models.ForeignKey(
        to=ContentType,
        limit_choices_to=CT_LIMIT,
        on_delete=models.PROTECT,
        verbose_name=_("object type"),
        help_text=_(
            "Choose the primary data source for your column template: "
            "licenses, components, or owners."
        ),
    )

    class Meta:
        unique_together = (
            ("dataspace", "name"),
            ("dataspace", "uuid"),
        )
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.content_type.model})"

    def is_valid(self):
        """Return True each fields of the ColumnTemplate is valid."""
        return all(field.is_valid() for field in self.fields.all())

    def get_model_class(self):
        return self.content_type.model_class()

    @staticmethod
    def get_extra_relational_fields():
        return ["fields"]

    def as_headers(self, include_view_link=False):
        """Return a list of field name, usable as Report results headers."""
        headers = [field.display_name or field.field_name for field in self.fields.all()]
        if include_view_link:
            headers.insert(0, format_html("&nbsp;"))
        return headers


class ColumnTemplateAssignedField(DataspacedModel):
    column_template = models.ForeignKey(
        to="reporting.ColumnTemplate",
        on_delete=models.CASCADE,
        related_name="fields",
    )

    field_name = models.TextField()

    display_name = models.CharField(
        max_length=70,
        blank=True,
    )

    seq = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ("dataspace", "uuid")
        ordering = ("seq",)

    def __str__(self):
        return f"<{self.column_template.name}>: {self.field_name}"

    def save(self, *args, **kwargs):
        self.dataspace = self.column_template.dataspace
        super().save(*args, **kwargs)

    def get_model_class(self):
        return self.column_template.get_model_class()

    def is_valid(self):
        """Return True if the ColumnTemplateAssignedField field_name is valid."""
        from reporting.forms import get_model_data_for_column_template

        try:
            introspector.validate_field_traversal_of_model_data(
                fields=self.field_name.split("__"),
                starting_model=self.get_model_class(),
                model_data=get_model_data_for_column_template(self.dataspace),
            )
        except ValidationError:
            return False
        return True

    @staticmethod
    def get_value_for_field(instance, field_name, user):
        """
        Return the value on the given instance for the given field_name.
        This support direct field, special field, choice field, properties,
        foreign keys, m2m, related m2m.
        """
        if not field_name:
            return ERROR_STR

        if not instance:  # null FK
            return EMPTY_STR

        if field_name.startswith(LICENSE_TAG_PREFIX):
            label = field_name.replace(LICENSE_TAG_PREFIX, "")
            return instance.get_tag_value_from_label(label)

        if field_name == "license_expression" and hasattr(instance, "get_license_expression"):
            return instance.get_license_expression()

        try:
            field = instance._meta.get_field(field_name)
        except (FieldDoesNotExist, AttributeError):
            field = None

        # ChoiceField
        # Set `FIELD.report_with_db_value = True` on the model to use the choices
        # database value instead of the `get_FIELD_display`.
        report_with_db_value = getattr(field, "report_with_db_value", False)
        if field and getattr(field, "choices", None) and not report_with_db_value:
            return getattr(instance, f"get_{field_name}_display")()

        if isinstance(field, ManyToOneRel):
            field_name = field.get_accessor_name()

        # Direct field, fk, properties, m2m, related m2m
        try:
            value = getattr(instance, field_name)
        except AttributeError:
            return ERROR_STR

        # Method that required the current `user` to compute, such as `where_used`.
        if field_name == "where_used" and callable(value):
            return value(user)

        if isinstance(field, ForeignKey):
            related_manager = field.related_model._default_manager
            if is_secured(related_manager):
                if value not in related_manager.get_queryset(user):
                    return EMPTY_STR

        # 'ManyRelatedManager' and 'RelatedManager' are not importable since generated by factory
        if value.__class__.__name__ in [
            "ManyRelatedManager",
            "RelatedManager",
            "GenericRelatedObjectManager",
        ]:
            value = list(secure_queryset_relational_fields(value.all(), user))

        return value

    def _get_objects_for_field_name(self, objects, field_name, user):
        result = []
        for obj in objects:
            value = self.get_value_for_field(obj, field_name, user)
            result.extend(value if isinstance(value, list) else [value])
        return result

    def get_value_for_instance(self, instance, user=None):
        """
        Return the value to be display in the row, given an instance
        and the current self.field_name value of this assigned field.
        """
        if self.get_model_class() != instance.__class__:
            raise AssertionError("content types do not match")

        objects = [instance]
        for field_name in self.field_name.split("__"):
            objects = self._get_objects_for_field_name(objects, field_name, user)

        results = [str(val) for val in objects if not (len(objects) < 2 and val is None)]
        return MULTIVALUE_SEPARATOR.join(results)


class ReportQuerySet(DataspacedQuerySet):
    def user_availables(self):
        return self.filter(user_available=True)


class Report(HistoryFieldsMixin, DataspacedModel):
    name = models.CharField(
        max_length=100,
        help_text=_("The title of your Report."),
    )

    description = models.TextField(
        blank=True,
        help_text=_(
            "Provide a description of the report to explain its purpose " "to DejaCode users."
        ),
    )

    query = models.ForeignKey(
        to="reporting.Query",
        on_delete=models.PROTECT,
        help_text=_("Choose one of your Queries to select the data for your report."),
    )

    column_template = models.ForeignKey(
        to="reporting.ColumnTemplate",
        on_delete=models.PROTECT,
        help_text=_(
            "Choose one of your Column templates to define the data " "columns for your report."
        ),
    )

    user_available = models.BooleanField(
        default=False,
        help_text=_("Check this to provide access to non-administrative application users."),
    )

    report_context = models.TextField(
        blank=True,
        default="This DejaCode report was generated from Dataspace "
        "{{dataspace}} on {{date-time}} by {{user}}.",
        help_text=_(
            "The text in this field will appear at the top of your generated "
            "report. You may want to describe the purpose of the report in this field."
        ),
    )

    group = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Use this field to group reports."),
    )

    objects = DataspacedManager.from_queryset(ReportQuerySet)()

    class Meta:
        unique_together = (("dataspace", "name"), ("dataspace", "uuid"))
        ordering = ("name",)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.dataspace = self.query.dataspace
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("reporting:report_details", args=[self.uuid])

    def get_output(self, queryset=None, user=None, include_view_link=False):
        # Checking if the parameter is given rather than the boolean value of the QuerySet
        if queryset is None:
            queryset = self.query.get_qs(user=user)

        icon = format_html('<i class="fas fa-external-link-alt"></i>')
        rows = []

        for instance in queryset:
            cells = []
            if include_view_link:
                view_link = instance.get_absolute_link(value=icon, title="View", target="_blank")
                cells.append(view_link)

            for field in self.column_template.fields.all():
                cells.append(field.get_value_for_instance(instance, user=user))

            rows.append(cells)

        return rows


class Card(HistoryFieldsMixin, DataspacedModel):
    title = models.CharField(
        max_length=1024,
        help_text=_("A concise and unique description of your Card."),
    )
    query = models.ForeignKey(
        to="reporting.Query",
        on_delete=models.CASCADE,
        related_name="cards",
        help_text=_(
            "The Query that obtains the data to show in the Card. "
            "The best kind of Query for this purpose is one that filters by a "
            "status or a modification date, in order to alert the user to "
            "recent activity that may need reviewing."
        ),
    )
    number_of_results = models.PositiveSmallIntegerField(
        default=5,
        help_text=_("The number of results to display in the Card."),
    )
    display_changelist_link = models.BooleanField(
        default=False,
        help_text=_("Display a link to the filtered changelist for admin users."),
    )

    class Meta:
        unique_together = ("dataspace", "title")
        ordering = ["title"]

    def __str__(self):
        return self.title

    def get_object_list(self, user):
        qs = self.query.get_qs(user=user)[: self.number_of_results]
        return [obj.get_absolute_link() or obj for obj in qs]


class CardLayout(HistoryFieldsMixin, DataspacedModel):
    name = models.CharField(
        max_length=100,
        help_text=_(
            "A concise and unique description of the Card layout that indicates "
            "the theme or purpose of the layout."
        ),
    )
    cards = models.ManyToManyField(
        to="reporting.Card",
        through="reporting.LayoutAssignedCard",
    )

    class Meta:
        unique_together = ("dataspace", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_ordered_cards(self):
        """Return the Cards of this Layout ordered by sequence."""
        return self.cards.all().order_by("layoutassignedcard__seq")

    @property
    def cards_title(self):
        return [card.title for card in self.get_ordered_cards()]

    def cards_with_objects(self, user):
        cards = self.get_ordered_cards()
        for card in cards:
            card.object_list = card.get_object_list(user=user)

        return cards


class LayoutAssignedCard(DataspacedModel):
    layout = models.ForeignKey(
        "reporting.CardLayout",
        on_delete=models.CASCADE,
    )
    card = models.ForeignKey(
        "reporting.Card",
        on_delete=models.CASCADE,
    )
    seq = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
    )

    class Meta:
        unique_together = ("dataspace", "uuid")
        ordering = ["seq"]
