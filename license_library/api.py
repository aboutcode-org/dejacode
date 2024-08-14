#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from contextlib import suppress

import django_filters
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import renderers
from rest_framework import serializers

from dje.api import CreateRetrieveUpdateListViewSet
from dje.api import DataspacedAPIFilterSet
from dje.api import DataspacedHyperlinkedRelatedField
from dje.api import DataspacedSerializer
from dje.api import DataspacedSlugRelatedField
from dje.api import ExternalReferenceSerializer
from dje.api_custom import PageSizePagination
from dje.decorators import test_or_set_dataspace_for_anonymous_users
from dje.filters import LastModifiedDateFilter
from dje.filters import MultipleCharFilter
from dje.filters import MultipleUUIDFilter
from dje.models import History
from dje.models import external_references_prefetch
from dje.utils import normalize_newlines_as_CR_plus_LF
from license_library.admin import LicenseAdmin
from license_library.models import License
from license_library.models import LicenseAnnotation
from license_library.models import LicenseAssignedTag
from organization.api import OwnerEmbeddedSerializer


class LicenseAssignedTagSerializer(serializers.ModelSerializer):
    label = DataspacedSlugRelatedField(
        source="license_tag",
        slug_field="label",
    )

    class Meta:
        model = LicenseAssignedTag
        fields = (
            "label",
            "value",
        )


class LicenseSerializer(DataspacedSerializer):
    display_name = serializers.ReadOnlyField(source="__str__")
    absolute_url = serializers.SerializerMethodField()
    owner = DataspacedHyperlinkedRelatedField(
        view_name="api_v2:owner-detail",
        lookup_field="uuid",
        html_cutoff=10,
        slug_field="name",
    )
    owner_name = serializers.StringRelatedField(source="owner.name")
    owner_abcd = OwnerEmbeddedSerializer(
        source="owner",
        read_only=True,
    )
    category = DataspacedSlugRelatedField(
        slug_field="label",
        allow_null=True,
        required=False,
    )
    license_style = DataspacedSlugRelatedField(
        slug_field="name",
        allow_null=True,
        required=False,
    )
    license_profile = DataspacedSlugRelatedField(
        slug_field="name",
        allow_null=True,
        required=False,
    )
    license_status = DataspacedSlugRelatedField(
        slug_field="code",
        allow_null=True,
        required=False,
    )
    usage_policy = DataspacedSlugRelatedField(
        slug_field="label",
        allow_null=True,
        required=False,
        scope_content_type=True,
    )
    tags = LicenseAssignedTagSerializer(
        many=True,
        source="licenseassignedtag_set",
        required=False,
    )
    external_references = ExternalReferenceSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = License
        fields = (
            "display_name",
            "api_url",
            "absolute_url",
            "uuid",
            "key",
            "name",
            "short_name",
            "reviewed",
            "owner",
            "owner_name",
            "owner_abcd",
            "keywords",
            "homepage_url",
            "full_text",
            "standard_notice",
            "publication_year",
            "language",
            "category",
            "license_style",
            "license_profile",
            "license_status",
            "is_active",
            "usage_policy",
            "is_component_license",
            "is_exception",
            "curation_level",
            "popularity",
            "reference_notes",
            "guidance",
            "guidance_url",
            "special_obligations",
            "admin_notes",
            "faq_url",
            "osi_url",
            "text_urls",
            "other_urls",
            "spdx_license_key",
            "spdx_url",
            "tags",
            "attribution_required",
            "redistribution_required",
            "change_tracking_required",
            "external_references",
            "urn",
            "created_date",
            "last_modified_date",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:license-detail",
                "lookup_field": "uuid",
            },
            "owner": {
                "view_name": "api_v2:owner-detail",
                "lookup_field": "uuid",
            },
        }

    def save(self, **kwargs):
        """Add LicenseAssignedTag create/update support."""
        tags = self.validated_data.pop("licenseassignedtag_set", [])
        instance = super().save(**kwargs)

        for tag in tags:
            LicenseAssignedTag.objects.update_or_create(
                license=instance,
                license_tag=tag["license_tag"],
                dataspace=instance.dataspace,
                defaults={"value": tag["value"]},
            )

        return instance


class LicenseFilterSet(DataspacedAPIFilterSet):
    id = django_filters.NumberFilter(
        help_text="Exact id.",
    )
    uuid = MultipleUUIDFilter()
    key = MultipleCharFilter(
        help_text="Exact key. Multi-value supported.",
    )
    name = django_filters.CharFilter(
        help_text="Exact name.",
    )
    short_name = django_filters.CharFilter(
        help_text="Exact short name.",
    )
    owner = MultipleCharFilter(
        field_name="owner__name",
        help_text="Exact owner name. Multi-value supported.",
    )
    category = django_filters.CharFilter(
        field_name="category__label",
        help_text="Exact category label.",
    )
    license_style = django_filters.CharFilter(
        field_name="license_style__name",
        help_text="Exact license style name.",
    )
    license_profile = django_filters.CharFilter(
        field_name="license_profile__name",
        help_text="Exact license profile name.",
    )
    license_status = django_filters.CharFilter(
        field_name="license_status__code",
        help_text="Exact status code.",
    )
    usage_policy = django_filters.CharFilter(
        field_name="usage_policy__label",
        help_text="Exact usage policy label.",
    )
    last_modified_date = LastModifiedDateFilter()

    class Meta:
        model = License
        fields = (
            "id",
            "uuid",
            "key",
            "name",
            "short_name",
            "owner",
            "category",
            "license_style",
            "license_profile",
            "license_status",
            "usage_policy",
            "reviewed",
            "is_active",
            "is_component_license",
            "is_exception",
            "last_modified_date",
        )


class LicenseViewSet(CreateRetrieveUpdateListViewSet):
    queryset = License.objects.all()
    serializer_class = LicenseSerializer
    filterset_class = LicenseFilterSet
    lookup_field = "uuid"
    search_fields = (
        "key",
        "name",
        "short_name",
        "spdx_license_key",
    )
    ordering_fields = (
        "key",
        "name",
        "short_name",
        "publication_year",
        "category",
        "license_style",
        "license_profile",
        "usage_policy",
        "curation_level",
        "created_date",
        "last_modified_date",
    )
    email_notification_on = LicenseAdmin.email_notification_on
    allow_reference_access = True

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "license_profile",
                "license_style",
                "category",
                "owner__dataspace",
                "license_status",
                "usage_policy",
            )
            .prefetch_related(
                "licenseassignedtag_set__license_tag",
                external_references_prefetch,
            )
        )


class LicenseAnnotationSerializer(DataspacedSerializer):
    quote = serializers.SerializerMethodField()
    ranges = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()

    def get_quote(self, obj):
        return normalize_newlines_as_CR_plus_LF(obj.quote)

    def get_ranges(self, obj):
        return [
            {
                "start": "/pre",
                "end": "/pre",
                "startOffset": obj.range_start_offset,
                "endOffset": obj.range_end_offset,
            }
        ]

    def get_tags(self, obj):
        if obj.assigned_tag:
            return [obj.assigned_tag.license_tag.label]
        return []

    class Meta:
        model = LicenseAnnotation
        fields = (
            "api_url",
            "id",
            "text",
            "quote",
            "ranges",
            "tags",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:licenseannotation-detail",
                "lookup_field": "id",
            },
        }

    def to_internal_value(self, data):
        ret = super().to_internal_value(data)

        ranges = data["ranges"][0]
        ret["range_start_offset"] = ranges["startOffset"]
        ret["range_end_offset"] = ranges["endOffset"]

        ret["quote"] = data["quote"]
        ret["license_id"] = data["license"]

        if data["tags"]:
            # If the tag is not valid, it's ignored
            with suppress(LicenseAssignedTag.DoesNotExist):
                license_assigned_tag = LicenseAssignedTag.objects.get(
                    # We only support 1 tag per Annotation
                    license_tag__label=data["tags"][0],
                    license__id=data["license"],
                )
                ret["assigned_tag_id"] = license_assigned_tag.id

        return ret


class LicenseAnnotationFilterSet(DataspacedAPIFilterSet):
    uuid = MultipleUUIDFilter()
    license = django_filters.NumberFilter(field_name="license__id")

    class Meta:
        model = LicenseAnnotation
        fields = (
            "uuid",
            "license",
        )


class LicenseAnnotationPagination(PageSizePagination):
    # Make sur the size is big enough to return all the annotations of a given license
    page_size = 100

    def get_paginated_response(self, data):
        """Rename the 'results' key to 'rows' to fit Annotator needs."""
        response = super().get_paginated_response(data)
        response.data["rows"] = response.data.pop("results")
        return response


class IsAuthenticatedOrAnonymous(permissions.IsAuthenticatedOrReadOnly):
    """Add the ANONYMOUS_USERS_DATASPACE on the AnonymousUser."""

    def has_permission(self, request, view):
        has_permission = super().has_permission(request, view)
        return has_permission and test_or_set_dataspace_for_anonymous_users(request.user)


class LicenseAnnotationViewSet(mixins.DestroyModelMixin, CreateRetrieveUpdateListViewSet):
    queryset = LicenseAnnotation.objects.all()
    serializer_class = LicenseAnnotationSerializer
    pagination_class = LicenseAnnotationPagination
    filterset_class = LicenseAnnotationFilterSet
    lookup_field = "id"
    renderer_classes = [renderers.JSONRenderer]
    permission_classes = [
        IsAuthenticatedOrAnonymous,
        permissions.DjangoModelPermissionsOrAnonReadOnly,
    ]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "license",
                "assigned_tag",
                "assigned_tag__license_tag",
            )
            .order_by("id")
        )

    @staticmethod
    def log_action(request, obj, message):
        History.log_change(request.user, obj, message)

    @staticmethod
    def construct_change_message(annotation, action):
        """
        Create a message suitable for the LogEntry model.
        Similar to messages from ModelAdmin.construct_change_message()
        """
        if annotation.assigned_tag:
            tag_message = f'for tag: "{annotation.assigned_tag}"'
        else:
            tag_message = "without tag"

        return "{action} a {name} {tag_message}.".format(
            action=action,
            name=str(annotation._meta.verbose_name),
            tag_message=str(tag_message),
        )

    def perform_create(self, serializer):
        # WARNING: bypassing the direct super() on purpose
        super(CreateRetrieveUpdateListViewSet, self).perform_create(serializer)
        message = self.construct_change_message(serializer.instance, "Added")
        self.log_action(self.request, serializer.instance.license, message)

    def perform_update(self, serializer):
        # WARNING: bypassing the direct super() on purpose
        super(CreateRetrieveUpdateListViewSet, self).perform_create(serializer)
        message = self.construct_change_message(serializer.instance, "Changed")
        self.log_action(self.request, serializer.instance.license, message)

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        message = self.construct_change_message(instance, "Deleted")
        self.log_action(self.request, instance.license, message)
