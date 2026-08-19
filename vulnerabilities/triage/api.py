#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from rest_framework import mixins
from rest_framework import serializers

from dje.api import CreateRetrieveUpdateListViewSet
from dje.api import DataspacedHyperlinkedRelatedField
from dje.api import DataspacedSerializer
from dje.api import ExtraPermissionsViewSetMixin
from dje.api_custom import TabPermission
from vulnerabilities.triage.models import AnalysisPreset
from vulnerabilities.triage.models import TriageRuleset


class AnalysisPresetSerializer(DataspacedSerializer):
    class Meta:
        model = AnalysisPreset
        fields = (
            "api_url",
            "uuid",
            "name",
            "description",
            "state",
            "justification",
            "responses",
            "detail",
            "is_reachable",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:analysispreset-detail",
                "lookup_field": "uuid",
            },
        }

    def validate(self, data):
        content_fields = ("state", "justification", "responses", "detail")

        def get_value(field_name):
            if field_name in data:
                return data[field_name]
            if self.instance is not None:
                return getattr(self.instance, field_name)
            return None

        if not any(get_value(field_name) for field_name in content_fields):
            raise serializers.ValidationError(
                "At least one of state, justification, responses or detail must be provided."
            )
        return data


class AnalysisPresetViewSet(
    ExtraPermissionsViewSetMixin,
    mixins.DestroyModelMixin,
    CreateRetrieveUpdateListViewSet,
):
    queryset = AnalysisPreset.objects.all()
    serializer_class = AnalysisPresetSerializer
    lookup_field = "uuid"
    extra_permissions = (TabPermission,)
    search_fields = (
        "name",
        "description",
    )
    ordering_fields = ("name",)
    allow_reference_access = True


class TriageRulesetSerializer(DataspacedSerializer):
    analysis_preset = DataspacedHyperlinkedRelatedField(
        view_name="api_v2:analysispreset-detail",
        lookup_field="uuid",
        required=False,
        allow_null=True,
    )
    request_template = DataspacedHyperlinkedRelatedField(
        view_name="api_v2:requesttemplate-detail",
        lookup_field="uuid",
        required=False,
        allow_null=True,
    )

    class Meta:
        model = TriageRuleset
        fields = (
            "api_url",
            "uuid",
            "name",
            "description",
            "recommended_action",
            "precedence",
            "enabled",
            "rules_config",
            "analysis_preset",
            "request_template",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:triageruleset-detail",
                "lookup_field": "uuid",
            },
        }

    def validate_request_template(self, value):
        if value and not value.created_by_id:
            raise serializers.ValidationError(
                "This request template has no creator and cannot be used to open requests."
            )
        return value


class TriageRulesetViewSet(
    ExtraPermissionsViewSetMixin,
    mixins.DestroyModelMixin,
    CreateRetrieveUpdateListViewSet,
):
    queryset = TriageRuleset.objects.all()
    serializer_class = TriageRulesetSerializer
    lookup_field = "uuid"
    extra_permissions = (TabPermission,)
    search_fields = (
        "name",
        "description",
    )
    ordering_fields = (
        "name",
        "precedence",
    )
    allow_reference_access = True

    def get_queryset(self):
        return super().get_queryset().select_related("analysis_preset", "request_template")
