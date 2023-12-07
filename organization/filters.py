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
from dje.filters import HasCountFilter
from dje.filters import MatchOrderedSearchFilter
from dje.widgets import DropDownRightWidget
from organization.models import Owner


class OwnerFilterSet(DataspacedFilterSet):
    q = MatchOrderedSearchFilter(
        label=_("Search"),
        match_order_fields=[
            "name",
            "alias",
        ],
        search_fields=[
            "name",
            "alias",
            "homepage_url",
        ],
        widget=forms.widgets.HiddenInput,
    )
    license = HasCountFilter(
        label=_("Licenses"),
        widget=DropDownRightWidget,
    )
    component = HasCountFilter(
        label=_("Components"),
        widget=DropDownRightWidget,
    )
    type = django_filters.ChoiceFilter(
        label=_("Type"),
        choices=[(type_value, type_value) for type_value, _ in Owner.OWNER_TYPE_CHOICES],
        widget=DropDownRightWidget,
    )
    sort = DefaultOrderingFilter(
        label=_("Sort"),
        fields=[
            "name",
            "homepage_url",
            "type",
        ],
        field_labels={
            "homepage_url": "Homepage URL",
        },
        empty_label="Default",
    )

    class Meta:
        model = Owner
        fields = [
            "q",
            "license",
            "component",
            "type",
        ]
