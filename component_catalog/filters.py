#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.contrib.admin.options import IncorrectLookupParameters
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

import django_filters

from component_catalog.models import Component
from component_catalog.models import ComponentKeyword
from component_catalog.models import Package
from component_catalog.models import Vulnerability
from component_catalog.programming_languages import PROGRAMMING_LANGUAGES
from dje.filters import DataspacedFilterSet
from dje.filters import DefaultOrderingFilter
from dje.filters import HasRelationFilter
from dje.filters import MatchOrderedSearchFilter
from dje.filters import RelatedLookupListFilter
from dje.filters import SearchFilter
from dje.widgets import BootstrapSelectMultipleWidget
from dje.widgets import DropDownRightWidget
from dje.widgets import SortDropDownWidget
from license_library.models import License


class IsVulnerableFilter(HasRelationFilter):
    def __init__(self, *args, **kwargs):
        kwargs["lookup_expr"] = "isnull"
        kwargs["empty_label"] = "Any"
        kwargs.setdefault("label", _("Is Vulnerable"))
        kwargs.setdefault(
            "choices",
            (
                ("yes", _("Affected by vulnerabilities")),
                ("no", _("No vulnerabilities found")),
            ),
        )
        super().__init__(*args, **kwargs)


class ComponentFilterSet(DataspacedFilterSet):
    related_only = [
        "licenses",
        "primary_language",
        "usage_policy",
    ]
    q = MatchOrderedSearchFilter(
        label=_("Search"),
        match_order_fields=["name"],
        search_fields=[
            "name",
            "version",
        ],
        widget=forms.widgets.HiddenInput,
    )
    sort = DefaultOrderingFilter(
        label=_("Sort"),
        fields=[
            "name",
            "version",
            "license_expression",
            "primary_language",
            "owner",
            "created_date",
            "last_modified_date",
        ],
        field_labels={
            "primary_language": "Language",
        },
        empty_label="Last modified (default)",
        widget=SortDropDownWidget,
    )
    primary_language = django_filters.MultipleChoiceFilter(
        label=_("Language"),
        choices=[(language, language) for language in PROGRAMMING_LANGUAGES],
        widget=BootstrapSelectMultipleWidget(
            search_placeholder="Search languages",
        ),
    )
    licenses = django_filters.ModelMultipleChoiceFilter(
        label=_("License"),
        field_name="licenses__key",
        to_field_name="key",
        queryset=License.objects.only("key", "short_name", "dataspace__id"),
        widget=BootstrapSelectMultipleWidget(
            search_placeholder="Search licenses",
        ),
    )
    keywords = django_filters.ModelMultipleChoiceFilter(
        label=_("Keyword"),
        to_field_name="label",
        lookup_expr="contains",
        queryset=ComponentKeyword.objects.only("label", "dataspace__id"),
        widget=BootstrapSelectMultipleWidget(
            search_placeholder="Search keywords",
        ),
    )
    is_vulnerable = IsVulnerableFilter(
        field_name="affected_by_vulnerabilities",
        widget=DropDownRightWidget(link_content='<i class="fas fa-bug"></i>'),
    )

    class Meta:
        model = Component
        fields = [
            "usage_policy",
            "type",
            "primary_language",
            "licenses",
            "keywords",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["usage_policy"].extra["to_field_name"] = "label"
        self.filters["usage_policy"].extra["widget"] = DropDownRightWidget()
        self.filters["type"].extra["to_field_name"] = "label"
        self.filters["type"].extra["widget"] = DropDownRightWidget()

    @cached_property
    def sort_value(self):
        return self.form["sort"].value()

    def has_sort_by(self, field_name):
        sort_value = self.sort_value
        if sort_value and (field_name in sort_value or f"-{field_name}" in sort_value):
            return True

    @cached_property
    def show_created_date(self):
        return self.has_sort_by("created_date")

    @cached_property
    def show_last_modified_date(self):
        return not self.sort_value or self.has_sort_by("last_modified_date")


class HierarchyRelatedLookupListFilter(RelatedLookupListFilter):
    """Limit the QuerySet to the current Component and all his direct children."""

    def queryset(self, request, queryset):
        if not self.lookup_val:
            return queryset

        try:
            instance = Component.objects.get(id=self.lookup_val)
        except Component.DoesNotExist as e:
            raise IncorrectLookupParameters(e)

        ids = list(instance.children.values_list("id", flat=True)) + [instance.id]
        return queryset.filter(component__id__in=ids)


class ParentRelatedLookupListFilter(RelatedLookupListFilter):
    """Filter the changelist in the pop-up to only Components that have children."""

    lookup_filters = ["children__isnull=False"]


class PackageSearchFilter(MatchOrderedSearchFilter):
    def filter(self, qs, value):
        """Add searching on provided PackageURL identifier."""
        if not value:
            return qs

        is_purl = "/" in value
        if is_purl:
            return qs.for_package_url(value)

        return super().filter(qs, value)


class PackageFilterSet(DataspacedFilterSet):
    q = PackageSearchFilter(
        label=_("Search"),
        match_order_fields=[
            "type",
            "namespace",
            "name",
            "version",
            "filename",
            "download_url",
            "sha1",
            "md5",
        ],
        search_fields=[
            "type",
            "namespace",
            "name",
            "version",
            "filename",
            "download_url",
            "sha1",
            "md5",
        ],
        widget=forms.widgets.HiddenInput,
    )
    primary_language = django_filters.MultipleChoiceFilter(
        label=_("Language"),
        choices=[(language, language) for language in PROGRAMMING_LANGUAGES],
        widget=BootstrapSelectMultipleWidget(
            search_placeholder="Search languages",
        ),
    )
    licenses = django_filters.ModelMultipleChoiceFilter(
        label=_("License"),
        field_name="licenses__key",
        to_field_name="key",
        queryset=License.objects.only("key", "short_name", "dataspace__id"),
        widget=BootstrapSelectMultipleWidget(
            search_placeholder="Search licenses",
        ),
    )
    component = HasRelationFilter(
        label=_("Components"),
        widget=DropDownRightWidget,
    )
    sort = DefaultOrderingFilter(
        label=_("Sort"),
        fields=[
            "sortable_identifier",
            "filename",
            "download_url",
            "license_expression",
            "primary_language",
            "created_date",
            "last_modified_date",
        ],
        field_labels={
            "sortable_identifier": "Identifier",
            "primary_language": "Language",
        },
        empty_label="Last modified (default)",
        widget=SortDropDownWidget,
    )
    is_vulnerable = IsVulnerableFilter(
        field_name="affected_by_vulnerabilities",
        widget=DropDownRightWidget(link_content='<i class="fas fa-bug"></i>'),
    )
    affected_by = django_filters.CharFilter(
        field_name="affected_by_vulnerabilities__vulnerability_id",
        label=_("Affected by"),
    )

    class Meta:
        model = Package
        fields = [
            "q",
            "component",
            "usage_policy",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["usage_policy"].extra["to_field_name"] = "label"
        self.filters["usage_policy"].extra["widget"] = DropDownRightWidget()

    @cached_property
    def sort_value(self):
        return self.form["sort"].value()

    def has_sort_by(self, field_name):
        sort_value = self.sort_value
        if sort_value and (field_name in sort_value or f"-{field_name}" in sort_value):
            return True

    @cached_property
    def show_created_date(self):
        return self.has_sort_by("created_date")

    @cached_property
    def show_last_modified_date(self):
        return not self.sort_value or self.has_sort_by("last_modified_date")


vulnerability_score_ranges = {
    "low": (0.1, 3),
    "medium": (4.0, 6.9),
    "high": (7.0, 8.9),
    "critical": (9.0, 10.0),
}

SCORE_CHOICES = [
    (key, f"{key.capitalize()} ({value[0]} - {value[1]})")
    for key, value in vulnerability_score_ranges.items()
]


class VulnerabilityFilterSet(DataspacedFilterSet):
    q = SearchFilter(
        label=_("Search"),
        search_fields=["vulnerability_id", "aliases"],
    )
    sort = DefaultOrderingFilter(
        label=_("Sort"),
        fields=[
            "highest_score",
            "lowest_score",
            "priority",
            "vulnerability_id",
            "affected_products_count",
            "affected_packages_count",
            "fixed_packages_length",
            "created_date",
            "last_modified_date",
        ],
        widget=SortDropDownWidget,
    )
    highest_score = django_filters.ChoiceFilter(
        choices=SCORE_CHOICES,
        method="filter_by_score_range",
        label="Score Range",
        help_text="Select a score range to filter.",
    )

    class Meta:
        model = Vulnerability
        fields = [
            "q",
            "priority",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["priority"].extra["widget"] = DropDownRightWidget()
        self.filters["highest_score"].extra["widget"] = DropDownRightWidget()

    def filter_by_score_range(self, queryset, name, value):
        if value in vulnerability_score_ranges:
            low, high = vulnerability_score_ranges[value]
            return queryset.filter(highest_score__gte=low, highest_score__lte=high)
        return queryset
