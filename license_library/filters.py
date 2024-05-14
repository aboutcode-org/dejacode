#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.utils.translation import gettext_lazy as _

import django_filters

from dje.filters import DataspacedFilterSet
from dje.filters import DefaultOrderingFilter
from dje.filters import HasValueFilter
from dje.filters import MatchOrderedSearchFilter
from dje.filters import ProgressiveTextSearchFilter
from dje.widgets import BootstrapSelectMultipleWidget
from dje.widgets import DropDownRightWidget
from license_library.models import License
from license_library.models import LicenseCategory
from license_library.models import LicenseProfile


class LicenseFilterSet(DataspacedFilterSet):
    related_only = [
        "category",
        "license_profile",
        "usage_policy",
    ]
    q = MatchOrderedSearchFilter(
        label=_("Search"),
        match_order_fields=["short_name", "key", "name"],
        search_fields=[
            "name",
            "short_name",
            "key",
            "keywords",
            "spdx_license_key",
            "owner__name",
            "owner__alias",
        ],
        widget=forms.widgets.HiddenInput,
    )
    text_search = ProgressiveTextSearchFilter(
        label=_("License text search"),
        search_fields=["full_text"],
        widget=forms.widgets.HiddenInput,
    )
    sort = DefaultOrderingFilter(
        label=_("Sort"),
        fields=[
            "name",
            "category",
            "license_profile",
            "owner",
        ],
        empty_label="Relevance",
    )
    in_spdx_list = HasValueFilter(
        label=_("In SPDX list"),
        field_name="spdx_license_key",
        choices=(
            ("yes", _("In SPDX List")),
            ("no", _("Not in SPDX List")),
        ),
        widget=DropDownRightWidget,
    )
    category = django_filters.ModelMultipleChoiceFilter(
        label=_("Category"),
        field_name="category__label",
        to_field_name="label",
        queryset=LicenseCategory.objects.only("label", "dataspace__id"),
        widget=BootstrapSelectMultipleWidget(
            search_placeholder="Search categories",
        ),
    )
    license_profile = django_filters.ModelMultipleChoiceFilter(
        label=_("License profile"),
        field_name="license_profile__name",
        to_field_name="name",
        queryset=LicenseProfile.objects.only("name", "dataspace__id"),
        widget=BootstrapSelectMultipleWidget(
            search_placeholder="Search license profiles",
        ),
    )

    class Meta:
        model = License
        fields = [
            "category",
            "category__license_type",
            "license_profile",
            "usage_policy",
            "in_spdx_list",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["usage_policy"].extra["to_field_name"] = "label"
        self.filters["usage_policy"].label = _("Policy")
        self.filters["category__license_type"].label = _("Type")

        for filter_name in ["category__license_type", "usage_policy"]:
            self.filters[filter_name].extra["widget"] = DropDownRightWidget()
