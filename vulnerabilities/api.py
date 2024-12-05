#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#


from rest_framework import viewsets

from dje.api import DataspacedAPIFilterSet
from dje.api import DataspacedSerializer
from dje.api import ExtraPermissionsViewSetMixin
from dje.api_custom import TabPermission
from dje.filters import LastModifiedDateFilter
from dje.filters import MultipleUUIDFilter
from vulnerabilities.filters import RISK_SCORE_RANGES
from vulnerabilities.filters import ScoreRangeFilter
from vulnerabilities.models import Vulnerability


class VulnerabilitySerializer(DataspacedSerializer):
    class Meta:
        model = Vulnerability
        fields = (
            "api_url",
            "uuid",
            "vulnerability_id",
            "resource_url",
            "summary",
            "aliases",
            "references",
            "exploitability",
            "weighted_severity",
            "risk_score",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:vulnerability-detail",
                "lookup_field": "uuid",
            },
        }


class VulnerabilityFilterSet(DataspacedAPIFilterSet):
    uuid = MultipleUUIDFilter()
    last_modified_date = LastModifiedDateFilter()
    weighted_severity = ScoreRangeFilter(score_ranges=RISK_SCORE_RANGES)
    risk_score = ScoreRangeFilter(score_ranges=RISK_SCORE_RANGES)

    class Meta:
        model = Vulnerability
        fields = (
            "uuid",
            "exploitability",
            "weighted_severity",
            "risk_score",
            "created_date",
            "last_modified_date",
        )


class VulnerabilityViewSet(ExtraPermissionsViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Vulnerability.objects.all()
    serializer_class = VulnerabilitySerializer
    lookup_field = "uuid"
    filterset_class = VulnerabilityFilterSet
    extra_permissions = (TabPermission,)
    search_fields = ("vulnerability_id", "aliases")
    ordering_fields = (
        "exploitability",
        "weighted_severity",
        "risk_score",
        "created_date",
        "last_modified_date",
    )

    def get_queryset(self):
        return super().get_queryset().scope(self.request.user.dataspace).order_by_risk()
