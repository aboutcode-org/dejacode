#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#


from django.db.models import Prefetch

from rest_framework import serializers
from rest_framework import viewsets

from component_catalog.models import Package
from dje.api import DataspacedAPIFilterSet
from dje.api import DataspacedSerializer
from dje.api import ExtraPermissionsViewSetMixin
from dje.api_custom import TabPermission
from dje.filters import LastModifiedDateFilter
from dje.filters import MultipleUUIDFilter
from vulnerabilities.filters import RISK_SCORE_RANGES
from vulnerabilities.filters import ScoreRangeFilter
from vulnerabilities.models import Vulnerability
from vulnerabilities.models import VulnerabilityAnalysis


class VulnerabilitySerializer(DataspacedSerializer):
    # Using SerializerMethodField to workaround circular imports
    affected_packages = serializers.SerializerMethodField()
    affected_products = serializers.SerializerMethodField()

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
            "affected_packages",
            "affected_products",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:vulnerability-detail",
                "lookup_field": "uuid",
            },
        }

    def get_affected_packages(self, obj):
        from component_catalog.api import PackageSerializer

        packages = obj.affected_packages.all()
        fields = [
            "display_name",
            "api_url",
            "uuid",
        ]
        return PackageSerializer(packages, many=True, context=self.context, fields=fields).data

    def get_affected_products(self, obj):
        from product_portfolio.api import ProductSerializer

        products = (
            product_package.product
            for package in obj.affected_packages.all()
            for product_package in package.productpackages.all()
        )
        fields = [
            "display_name",
            "api_url",
            "uuid",
        ]
        return ProductSerializer(products, many=True, context=self.context, fields=fields).data


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
        package_qs = Package.objects.only_rendering_fields()

        return (
            super()
            .get_queryset()
            .scope(self.request.user.dataspace)
            .prefetch_related(
                Prefetch("affected_packages", queryset=package_qs),
                Prefetch("affected_packages__productpackages__product"),
            )
            .order_by_risk()
        )


class VulnerabilityAnalysisSerializer(DataspacedSerializer, serializers.ModelSerializer):
    vulnerability_id = serializers.ReadOnlyField(source="vulnerability.vulnerability_id")

    class Meta:
        model = VulnerabilityAnalysis
        fields = (
            "uuid",
            "product_package",
            "vulnerability",
            "vulnerability_id",
            "state",
            "justification",
            "responses",
            "detail",
            "is_reachable",
        )
        extra_kwargs = {
            "product_package": {
                "view_name": "api_v2:productpackage-detail",
                "lookup_field": "uuid",
            },
            "vulnerability": {
                "view_name": "api_v2:vulnerability-detail",
                "lookup_field": "uuid",
            },
        }
