#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import django_filters
from rest_framework import serializers

from dje.api import CreateRetrieveUpdateListViewSet
from dje.api import DataspacedAPIFilterSet
from dje.api import DataspacedSerializer
from dje.api import ExternalReferenceSerializer
from dje.filters import LastModifiedDateFilter
from dje.filters import MultipleCharFilter
from dje.filters import MultipleUUIDFilter
from dje.models import external_references_prefetch
from organization.admin import OwnerAdmin
from organization.models import Owner


class OwnerSerializer(DataspacedSerializer):
    absolute_url = serializers.SerializerMethodField()
    licenses = serializers.HyperlinkedRelatedField(
        source="license_set",
        many=True,
        read_only=True,
        view_name="api_v2:license-detail",
        lookup_field="uuid",
    )
    components = serializers.HyperlinkedRelatedField(
        source="component_set",
        many=True,
        read_only=True,
        view_name="api_v2:component-detail",
        lookup_field="uuid",
    )
    external_references = ExternalReferenceSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Owner
        fields = (
            "api_url",
            "absolute_url",
            "uuid",
            "name",
            "homepage_url",
            "contact_info",
            "notes",
            "alias",
            "type",
            "licenses",
            "components",
            "external_references",
            "urn",
            "created_date",
            "last_modified_date",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:owner-detail",
                "lookup_field": "uuid",
            },
        }


class OwnerEmbeddedSerializer(OwnerSerializer):
    class Meta(OwnerSerializer.Meta):
        fields = (
            "api_url",
            "absolute_url",
            "uuid",
            "name",
            "homepage_url",
            "contact_info",
            "notes",
            "alias",
            "type",
            "urn",
            "created_date",
            "last_modified_date",
        )


class OwnerFilterSet(DataspacedAPIFilterSet):
    uuid = MultipleUUIDFilter()
    name = MultipleCharFilter(
        help_text="Exact name. Multi-value supported.",
    )
    type = django_filters.ChoiceFilter(
        choices=Owner.OWNER_TYPE_CHOICES,
        help_text=f"Exact owner type. Supported values: "
        f'{", ".join(type[0] for type in Owner.OWNER_TYPE_CHOICES)}',
    )
    last_modified_date = LastModifiedDateFilter()

    class Meta:
        model = Owner
        fields = (
            "uuid",
            "name",
            "type",
            "last_modified_date",
        )


class OwnerViewSet(CreateRetrieveUpdateListViewSet):
    queryset = Owner.objects.all()
    serializer_class = OwnerSerializer
    lookup_field = "uuid"
    filterset_class = OwnerFilterSet
    search_fields = (
        "name",
        "alias",
        "notes",
    )
    search_fields_autocomplete = ("name",)
    ordering_fields = (
        "name",
        "alias",
        "created_date",
        "last_modified_date",
    )
    email_notification_on = OwnerAdmin.email_notification_on
    allow_reference_access = True

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .prefetch_related(
                "license_set",
                "component_set",
                external_references_prefetch,
            )
        )
