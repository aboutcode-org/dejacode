#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from collections import OrderedDict

import django_filters
from rest_framework import serializers
from rest_framework import viewsets

from dje.api import DataspacedAPIFilterSet
from dje.api import DataspacedSerializer
from dje.api import ExtraPermissionsViewSetMixin
from dje.api_custom import TabPermission
from dje.filters import LastModifiedDateFilter
from dje.filters import MultipleUUIDFilter
from reporting.models import Report


class ReportSerializer(DataspacedSerializer):
    absolute_url = serializers.SerializerMethodField()
    content_type = serializers.StringRelatedField(source="query.content_type.model")
    query = serializers.StringRelatedField(source="query.name")
    column_template = serializers.StringRelatedField(source="column_template.name")
    results = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = (
            "api_url",
            "absolute_url",
            "uuid",
            "name",
            "description",
            "group",
            "content_type",
            "query",
            "column_template",
            "results",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:report-detail",
                "lookup_field": "uuid",
            },
        }

    def get_field_names(self, declared_fields, info):
        """Remove the 'results' field from all views but the details (retrieve) one."""
        field_names = super().get_field_names(declared_fields, info)

        view = self.context.get("view", None)
        if not view or view.action != "retrieve":
            return tuple(name for name in field_names if name != "results")

        return field_names

    def get_results(self, obj):
        headers = obj.column_template.as_headers()
        request = self.context.get("request")
        output = obj.get_output(user=request.user)
        data = [OrderedDict(zip(headers, values)) for values in output]
        return data


class ReportFilterSet(DataspacedAPIFilterSet):
    uuid = MultipleUUIDFilter()
    content_type = django_filters.CharFilter(
        field_name="query__content_type__model",
        help_text='Exact content type model name. E.g.: "owner".',
    )
    last_modified_date = LastModifiedDateFilter()

    class Meta:
        model = Report
        fields = (
            "uuid",
            "content_type",
        )


class ReportViewSet(ExtraPermissionsViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Report.objects.user_availables()
    serializer_class = ReportSerializer
    lookup_field = "uuid"
    filterset_class = ReportFilterSet
    extra_permissions = (TabPermission,)
    search_fields = ("name",)
    ordering_fields = ("name",)

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .scope(self.request.user.dataspace)
            .select_related(
                "query__content_type",
                "column_template",
            )
        )
