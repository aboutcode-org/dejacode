#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.db.models import F
from django.utils.translation import gettext_lazy as _

import django_filters

from dje.filters import DataspacedFilterSet
from dje.filters import SearchFilter
from dje.widgets import DropDownRightWidget
from dje.widgets import SortDropDownWidget
from vulnerabilities.models import Vulnerability


class NullsLastOrderingFilter(django_filters.OrderingFilter):
    """
    A custom ordering filter that ensures null values are sorted last.

    When sorting by fields with potential null values, this filter modifies the
    ordering to use Django's `nulls_last` clause for better handling of null values,
    whether in ascending or descending order.
    """

    def filter(self, qs, value):
        if not value:
            return qs

        ordering = []
        for field in value:
            if field.startswith("-"):
                field_name = field[1:]
                ordering.append(F(field_name).desc(nulls_last=True))
            else:
                ordering.append(F(field).asc(nulls_last=True))

        return qs.order_by(*ordering)


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
    sort = NullsLastOrderingFilter(
        label=_("Sort"),
        fields=[
            "max_score",
            "min_score",
            "affected_products_count",
            "affected_packages_count",
            "fixed_packages_count",
            "created_date",
            "last_modified_date",
        ],
        widget=SortDropDownWidget,
    )
    max_score = django_filters.ChoiceFilter(
        choices=SCORE_CHOICES,
        method="filter_by_score_range",
        label="Score Range",
        help_text="Select a score range to filter.",
    )

    class Meta:
        model = Vulnerability
        fields = [
            "q",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["max_score"].extra["widget"] = DropDownRightWidget(anchor=self.anchor)

    def filter_by_score_range(self, queryset, name, value):
        if value in vulnerability_score_ranges:
            low, high = vulnerability_score_ranges[value]
            return queryset.filter(max_score__gte=low, max_score__lte=high)
        return queryset
