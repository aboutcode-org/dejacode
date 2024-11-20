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

RISK_SCORE_RANGES = {
    "low": (0.1, 2.9),
    "medium": (3.0, 5.9),
    "high": (6.0, 7.9),
    "critical": (8.0, 10.0),
}


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


class ScoreRangeFilter(django_filters.ChoiceFilter):
    def __init__(self, *args, **kwargs):
        score_ranges = kwargs.pop("score_ranges", {})
        choices = [
            (key, f"{key.capitalize()} ({value[0]} - {value[1]})")
            for key, value in score_ranges.items()
        ]
        kwargs["choices"] = choices
        super().__init__(*args, **kwargs)
        self.score_ranges = score_ranges

    def filter(self, qs, value):
        if value in self.score_ranges:
            low, high = self.score_ranges[value]
            filters = {
                f"{self.field_name}__gte": low,
                f"{self.field_name}__lte": high,
            }
            return qs.filter(**filters)
        return qs


class VulnerabilityFilterSet(DataspacedFilterSet):
    q = SearchFilter(
        label=_("Search"),
        search_fields=["vulnerability_id", "aliases"],
    )
    sort = NullsLastOrderingFilter(
        label=_("Sort"),
        fields=[
            "exploitability",
            "weighted_severity",
            "risk_score",
            "affected_products_count",
            "affected_packages_count",
            "fixed_packages_count",
            "created_date",
            "last_modified_date",
        ],
        widget=SortDropDownWidget,
    )
    weighted_severity = ScoreRangeFilter(
        label=_("Severity"),
        score_ranges=RISK_SCORE_RANGES,
    )
    risk_score = ScoreRangeFilter(
        label=_("Risk score"),
        score_ranges=RISK_SCORE_RANGES,
    )

    class Meta:
        model = Vulnerability
        fields = [
            "q",
            "vulnerability_analyses__state",
            "exploitability",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dropdown_fields = [
            "exploitability",
            "weighted_severity",
            "risk_score",
            "vulnerability_analyses__state",
        ]
        for field_name in dropdown_fields:
            self.filters[field_name].extra["widget"] = DropDownRightWidget(anchor=self.anchor)
