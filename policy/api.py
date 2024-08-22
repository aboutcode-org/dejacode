#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from rest_framework import serializers

from dje.api import CreateRetrieveUpdateListViewSet
from dje.api import DataspacedSerializer
from dje.api import ExtraPermissionsViewSetMixin
from dje.api_custom import TabPermission
from policy.models import UsagePolicy


class UsagePolicySerializer(DataspacedSerializer):
    content_type = serializers.StringRelatedField(source="content_type.model")
    associated_product_relation_status = serializers.StringRelatedField(
        source="associated_product_relation_status.label",
    )

    class Meta:
        model = UsagePolicy
        fields = (
            "api_url",
            "uuid",
            "label",
            "guidelines",
            "content_type",
            "icon",
            "color_code",
            "compliance_alert",
            "associated_product_relation_status",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:usagepolicy-detail",
                "lookup_field": "uuid",
            },
        }


class UsagePolicyViewSet(ExtraPermissionsViewSetMixin, CreateRetrieveUpdateListViewSet):
    queryset = UsagePolicy.objects.all()
    serializer_class = UsagePolicySerializer
    lookup_field = "uuid"
    extra_permissions = (TabPermission,)
    search_fields = (
        "label",
        "guidelines",
    )
    ordering_fields = ("label",)
    allow_reference_access = True

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "content_type",
                "associated_product_relation_status",
            )
        )
