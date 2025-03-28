#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.contrib import admin
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

import django_filters
from packageurl.contrib.django.utils import purl_to_lookups

from component_catalog.filters import IsVulnerableBooleanFilter
from component_catalog.filters import IsVulnerableFilter
from component_catalog.models import ComponentKeyword
from component_catalog.programming_languages import PROGRAMMING_LANGUAGES
from dje.filters import BooleanChoiceFilter
from dje.filters import DataspacedFilterSet
from dje.filters import DefaultOrderingFilter
from dje.filters import HasRelationFilter
from dje.filters import MatchOrderedSearchFilter
from dje.filters import SearchFilter
from dje.widgets import BootstrapSelectMultipleWidget
from dje.widgets import DropDownRightWidget
from dje.widgets import DropDownWidget
from license_library.models import License
from product_portfolio.models import CodebaseResource
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductDependency
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductStatus
from vulnerabilities.filters import RISK_SCORE_RANGES
from vulnerabilities.filters import ScoreRangeFilter
from vulnerabilities.models import Vulnerability
from vulnerabilities.models import VulnerabilityAnalysisMixin


class ProductFilterSet(DataspacedFilterSet):
    q = MatchOrderedSearchFilter(
        label=_("Search"),
        match_order_fields=[
            "name",
            "components__name",
            "packages__filename",
        ],
        search_fields=[
            "name",
            "version",
            "components__name",
            "packages__filename",
        ],
        distinct=True,
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
            "configuration_status",
            "productinventoryitem_count",
        ],
        field_labels={
            "primary_language": "Language",
            "configuration_status": "Configuration Status",
        },
        empty_label="Default",
    )
    configuration_status = django_filters.ModelMultipleChoiceFilter(
        label=_("Configuration status"),
        field_name="configuration_status__label",
        to_field_name="label",
        queryset=ProductStatus.objects.only("label", "dataspace__id"),
        widget=BootstrapSelectMultipleWidget(
            search=False,
            search_placeholder="Search configuration status",
        ),
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
    is_vulnerable = IsVulnerableBooleanFilter(
        label=_("Is Vulnerable"),
        widget=DropDownRightWidget(link_content='<i class="fas fa-bug"></i>'),
    )
    affected_by = django_filters.CharFilter(
        field_name="packages__affected_by_vulnerabilities__vulnerability_id",
        label=_("Affected by"),
    )

    class Meta:
        model = Product
        fields = [
            "q",
            "licenses",
            "primary_language",
            "configuration_status",
            "keywords",
        ]


class BaseProductRelationFilterSet(DataspacedFilterSet):
    field_name_prefix = None
    dropdown_fields = [
        "is_modified",
        "weighted_risk_score",
    ]
    is_deployed = BooleanChoiceFilter(
        empty_label="All (Inventory)",
        choices=(
            ("yes", _("Yes (BOM)")),
            ("no", _("No (Internal Use Only)")),
        ),
        widget=DropDownWidget(
            anchor="#inventory",
            right_align=True,
        ),
    )
    is_modified = BooleanChoiceFilter()
    object_type = django_filters.CharFilter(
        method="filter_object_type",
        widget=DropDownWidget(
            anchor="#inventory",
            choices=(
                ("", _("All")),
                ("catalog", _("Catalog Components")),
                ("custom", _("Custom Components")),
                ("package", _("Packages")),
            ),
        ),
    )
    exploitability = django_filters.ChoiceFilter(
        label=_("Exploitability"),
        choices=Vulnerability.EXPLOITABILITY_CHOICES,
    )
    weighted_severity = ScoreRangeFilter(
        label=_("Severity"),
        score_ranges=RISK_SCORE_RANGES,
    )
    weighted_risk_score = ScoreRangeFilter(
        label=_("Risk score"),
        score_ranges=RISK_SCORE_RANGES,
    )

    @staticmethod
    def filter_object_type(queryset, name, value):
        if not value:
            return queryset

        if queryset.model is ProductComponent:
            if value == "catalog":
                return queryset.catalogs()
            elif value == "custom":
                return queryset.customs()

        elif queryset.model is ProductPackage:
            if value == "package":
                return queryset

        return queryset.none()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.filters["review_status"].extra["to_field_name"] = "label"
        self.filters["review_status"].extra["widget"] = DropDownWidget(anchor=self.anchor)

        self.filters["purpose"].extra["to_field_name"] = "label"
        self.filters["purpose"].extra["widget"] = DropDownWidget(anchor=self.anchor)

        field_name_prefix = self.field_name_prefix
        for field_name in ["exploitability", "weighted_severity"]:
            field = self.filters[field_name]
            field.extra["widget"] = DropDownWidget(anchor=self.anchor)
            field.field_name = f"{field_name_prefix}__{field_name}"


class ProductComponentFilterSet(BaseProductRelationFilterSet):
    field_name_prefix = "component"
    q = SearchFilter(
        label=_("Search"),
        search_fields=[
            "component__name",
            "component__version",
            "license_expression",
            "notes",
            "extra_attribution_text",
            "feature",
            "issue_ref",
        ],
    )
    sort = DefaultOrderingFilter(
        label=_("Sort"),
        fields=[
            "component",
            "license_expression",
            "review_status",
            "purpose",
            "feature",
            "is_deployed",
            "is_modified",
        ],
    )
    is_vulnerable = IsVulnerableFilter(
        field_name="component__affected_by_vulnerabilities",
        widget=DropDownWidget(
            anchor="#inventory", right_align=True, link_content='<i class="fas fa-bug"></i>'
        ),
    )

    class Meta:
        model = ProductComponent
        fields = [
            "review_status",
            "purpose",
            "object_type",
            "is_deployed",
            "is_modified",
        ]


class ProductPackageFilterSet(BaseProductRelationFilterSet):
    field_name_prefix = "package"
    dropdown_fields = [
        "is_modified",
        "weighted_risk_score",
        "vulnerability_analyses__state",
        "vulnerability_analyses__justification",
        "responses",
        "is_reachable",
    ]
    q = SearchFilter(
        label=_("Search"),
        search_fields=[
            "package__filename",
            "package__type",
            "package__namespace",
            "package__name",
            "package__version",
            "license_expression",
            "notes",
            "extra_attribution_text",
            "feature",
            "issue_ref",
        ],
    )
    sort = DefaultOrderingFilter(
        label=_("Sort"),
        fields=[
            "package",
            "license_expression",
            "review_status",
            "purpose",
            "feature",
            "is_deployed",
            "is_modified",
            "weighted_risk_score",
        ],
    )
    is_vulnerable = IsVulnerableFilter(
        field_name="package__affected_by_vulnerabilities",
        widget=DropDownWidget(
            anchor="#inventory", right_align=True, link_content='<i class="fas fa-bug"></i>'
        ),
    )
    responses = django_filters.ChoiceFilter(
        field_name="vulnerability_analyses__responses",
        lookup_expr="icontains",
        choices=VulnerabilityAnalysisMixin.Response.choices,
    )
    is_reachable = BooleanChoiceFilter(
        field_name="vulnerability_analyses__is_reachable",
        empty_label="All",
        choices=(
            ("yes", _("Reachable")),
            ("no", _("Not reachable")),
            ("unknown", _("Reachability not known")),
        ),
    )

    class Meta:
        model = ProductPackage
        fields = [
            "review_status",
            "purpose",
            "object_type",
            "is_deployed",
            "is_modified",
            "vulnerability_analyses__state",
            "vulnerability_analyses__justification",
            "is_reachable",
            "exploitability",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["vulnerability_analyses__state"].extra["null_label"] = "(No values)"
        self.filters["vulnerability_analyses__justification"].extra["null_label"] = "(No values)"


class ComponentCompletenessListFilter(admin.SimpleListFilter):
    """
    Scope the ChangeList results by valid ProductComponent.
    A valid ProductComponent references a Component by its ForeignKey.
    """

    title = _("Component completeness")
    parameter_name = "completeness"

    def lookups(self, request, model_admin):
        return (
            ("catalog", _("Catalog Components")),
            ("custom", _("Custom Components")),
        )

    def queryset(self, request, queryset):
        if self.value() == "catalog":
            return queryset.catalogs()
        if self.value() == "custom":
            return queryset.customs()


class ComponentCompletenessAPIFilter(django_filters.ChoiceFilter):
    def filter(self, qs, value):
        if value == "catalog":
            return qs.catalogs()
        if value == "custom":
            return qs.customs()
        return qs


class CodebaseResourceFilterSet(DataspacedFilterSet):
    q = SearchFilter(
        label=_("Search"),
        search_fields=["path"],
    )
    is_deployment_path = BooleanChoiceFilter(
        widget=DropDownWidget(anchor="#codebase"),
    )
    product_component = HasRelationFilter(
        widget=DropDownWidget(anchor="#codebase"),
    )
    product_package = HasRelationFilter(
        widget=DropDownWidget(anchor="#codebase"),
    )
    related_deployed_from = HasRelationFilter(
        widget=DropDownWidget(anchor="#codebase"),
    )
    related_deployed_to = HasRelationFilter(
        widget=DropDownWidget(anchor="#codebase", right_align=True),
    )

    class Meta:
        model = CodebaseResource
        fields = [
            "is_deployment_path",
            "product_component",
            "product_package",
            "related_deployed_from",
            "related_deployed_to",
        ]


class PackageURLSearchFilter(SearchFilter):
    def filter(self, qs, value):
        if value and value.startswith("pkg:"):
            base_lookups = purl_to_lookups(value)
            packages_fk_fields = ["for_package", "resolved_to_package"]

            combined_q = Q()
            for package_fk in packages_fk_fields:
                fk_lookups = {
                    f"{package_fk}__{field}": value for field, value in base_lookups.items()
                }
                combined_q |= Q(**fk_lookups)

            if combined_q:
                return qs.filter(combined_q)

        return super().filter(qs, value)


class DependencyFilterSet(DataspacedFilterSet):
    q = PackageURLSearchFilter(
        label=_("Search"),
        search_fields=[
            "dependency_uid",
            "for_package__filename",
            "for_package__type",
            "for_package__namespace",
            "for_package__name",
            "for_package__version",
            "resolved_to_package__filename",
            "resolved_to_package__type",
            "resolved_to_package__namespace",
            "resolved_to_package__name",
            "resolved_to_package__version",
        ],
    )
    sort = DefaultOrderingFilter(
        label=_("Sort"),
        fields=[
            "dependency_uid",
            "for_package",
            "resolved_to_package",
        ],
    )
    for_package = HasRelationFilter(
        widget=DropDownWidget(anchor="#dependencies"),
    )
    resolved_to_package = HasRelationFilter(
        widget=DropDownWidget(anchor="#dependencies"),
    )
    is_runtime = BooleanChoiceFilter(
        widget=DropDownWidget(anchor="#dependencies"),
    )
    is_optional = BooleanChoiceFilter(
        widget=DropDownWidget(anchor="#dependencies"),
    )
    is_pinned = BooleanChoiceFilter(
        widget=DropDownWidget(anchor="#dependencies"),
    )
    is_direct = BooleanChoiceFilter(
        widget=DropDownWidget(anchor="#dependencies"),
    )

    class Meta:
        model = ProductDependency
        fields = [
            "for_package",
            "for_package__uuid",
            "resolved_to_package",
            "resolved_to_package__uuid",
            "scope",
            "datasource_id",
            "is_runtime",
            "is_optional",
            "is_pinned",
            "is_direct",
        ]
