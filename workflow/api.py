#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json

from django.core.exceptions import ValidationError
from django.forms.fields import DateField
from django.utils.translation import gettext_lazy as _

import django_filters
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from dje.api import CreateRetrieveUpdateListViewSet
from dje.api import DataspacedAPIFilterSet
from dje.api import DataspacedHyperlinkedRelatedField
from dje.api import DataspacedSerializer
from dje.api import DataspacedSlugRelatedField
from dje.api import ExtraPermissionsViewSetMixin
from dje.api import GenericForeignKeyHyperlinkedField
from dje.api_custom import TabPermission
from dje.filters import LastModifiedDateFilter
from workflow.models import Question
from workflow.models import Request
from workflow.models import RequestComment
from workflow.models import RequestEvent
from workflow.models import RequestTemplate
from workflow.notification import send_request_notification


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = (
            "label",
            "help_text",
            "input_type",
            "is_required",
            "position",
        )


class RequestTemplateSerializer(DataspacedSerializer):
    content_type = serializers.StringRelatedField(source="content_type.model")
    default_assignee = serializers.StringRelatedField()
    questions = QuestionSerializer(many=True, read_only=True)
    form_data_layout = serializers.SerializerMethodField()

    class Meta:
        model = RequestTemplate
        fields = (
            "api_url",
            "uuid",
            "name",
            "description",
            "content_type",
            "is_active",
            "include_applies_to",
            "include_product",
            "default_assignee",
            "questions",
            "form_data_layout",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:requesttemplate-detail",
                "lookup_field": "uuid",
            },
        }

    def get_form_data_layout(self, obj):
        """Return a layout suitable for the RequestSerializer.form_data field."""
        return {question.label: "" for question in obj.questions.all()}


class RequestTemplateFilterSet(DataspacedAPIFilterSet):
    last_modified_date = LastModifiedDateFilter()

    class Meta:
        model = RequestTemplate
        fields = ("last_modified_date",)


class RequestTemplateViewSet(ExtraPermissionsViewSetMixin, ReadOnlyModelViewSet):
    queryset = RequestTemplate.objects.all()
    serializer_class = RequestTemplateSerializer
    lookup_field = "uuid"
    extra_permissions = (TabPermission,)
    filterset_class = RequestTemplateFilterSet
    search_fields = (
        "name",
        "description",
    )
    ordering_fields = (
        "name",
        "content_type",
    )

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .scope(self.request.user.dataspace)
            .select_related(
                "default_assignee",
                "content_type",
            )
            .prefetch_related(
                "questions",
            )
        )


class JSONCharField(serializers.CharField):
    default_error_messages = {
        "invalid": _("Value must be valid JSON."),
        "invalid_data": _("Invalid data content."),
    }

    def to_internal_value(self, data):
        """Convert into a string to be stored in a CharField."""
        if not isinstance(data, dict):
            self.fail("invalid_data")

        try:
            data = json.dumps(data)
        except (TypeError, ValueError):
            self.fail("invalid")

        return data

    def to_representation(self, value):
        """Convert the string from the CharField into proper JSON."""
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {}


class RequestCommentSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()

    class Meta:
        model = RequestComment
        fields = (
            "uuid",
            "user",
            "text",
            "created_date",
            "last_modified_date",
        )


class RequestSerializer(DataspacedSerializer):
    absolute_url = serializers.SerializerMethodField()
    request_template = DataspacedHyperlinkedRelatedField(
        view_name="api_v2:requesttemplate-detail",
        lookup_field="uuid",
        slug_field="name",
    )
    request_template_name = serializers.StringRelatedField(source="request_template.name")
    requester = serializers.StringRelatedField()
    assignee = DataspacedSlugRelatedField(
        slug_field="username",
        # Not required in the REST API context to simplify external integrations.
        allow_null=True,
        required=False,
    )
    priority = DataspacedSlugRelatedField(
        slug_field="label",
        allow_null=True,
        required=False,
    )
    product_context = DataspacedHyperlinkedRelatedField(
        view_name="api_v2:product-detail",
        lookup_field="uuid",
        allow_null=True,
        required=False,
        html_cutoff=10,
    )
    serialized_data = JSONCharField(
        allow_blank=True,
        required=False,
    )
    content_type = serializers.StringRelatedField(source="content_type.model")
    content_object = GenericForeignKeyHyperlinkedField(
        lookup_field="uuid",
        allow_null=True,
        required=False,
    )
    content_object_display_name = serializers.StringRelatedField(source="content_object")
    last_modified_by = serializers.StringRelatedField()
    comments = RequestCommentSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Request
        fields = (
            "api_url",
            "absolute_url",
            "uuid",
            "title",
            "request_template",
            "request_template_name",
            "status",
            "priority",
            "assignee",
            "product_context",
            "notes",
            "serialized_data",
            "is_private",
            "requester",
            "content_type",
            "content_object",
            "content_object_display_name",
            "cc_emails",
            "last_modified_by",
            "created_date",
            "last_modified_date",
            "comments",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:request-detail",
                "lookup_field": "uuid",
            },
        }

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request", None)

        # Only available on creation (POST), not edition (PUT, PATCH)
        if request and request.method in ["PUT", "PATCH"]:
            fields["request_template"].read_only = True

        return fields

    def _validate_serialized_data(self, serialized_data, request_template):
        questions = {question.label: question for question in request_template.questions.all()}

        for label in serialized_data.keys():
            if not questions.get(label):
                raise serializers.ValidationError(
                    {
                        "serialized_data": f'"{label}" is not a valid label.',
                    }
                )

        for label, question in questions.items():
            if question.is_required and not serialized_data.get(label):
                raise serializers.ValidationError(
                    {
                        "serialized_data": f'"{label}" is required.',
                    }
                )

            if question.input_type == "DateField":
                value = serialized_data.get(label)
                try:
                    DateField().to_python(value)
                except ValidationError:  # Not raised for empty string or None
                    raise serializers.ValidationError(
                        {
                            "serialized_data": f'Invalid date for "{label}", use: YYYY-MM-DD.',
                        }
                    )

            elif question.input_type == "BooleanField":
                value = serialized_data.get(label)
                if value not in (True, False, "1", "0"):
                    raise serializers.ValidationError(
                        {
                            "serialized_data": f'"{label}" only accept: true, false, "1", "0".',
                        }
                    )

    def validate(self, data):
        # Value as submitted, since the values in `data` have been through to_internal_value
        serialized_data = self.initial_data.get("serialized_data")

        # WARNING: data['request_template'] is not always present, PUT/PATCH
        request_template = data.get("request_template") or self.instance.request_template

        content_object = data.get("content_object")
        if content_object and request_template:
            if not request_template.include_applies_to:
                raise serializers.ValidationError(
                    {
                        "content_object": "Content object not available on this RequestTemplate.",
                    }
                )
            if request_template.content_type.model_class() != content_object.__class__:
                raise serializers.ValidationError({"content_object": "Invalid Object type."})

        if serialized_data and request_template:
            self._validate_serialized_data(serialized_data, request_template)
        return data

    def save(self, **kwargs):
        user = self.context["request"].user

        if not self.instance:
            kwargs.update({"requester_id": user.id})
            kwargs.pop("last_modified_by")

        return super().save(**kwargs)


class RequestFilterSet(DataspacedAPIFilterSet):
    request_template = django_filters.CharFilter(
        field_name="request_template__name",
        help_text="Exact request template name.",
    )
    requester = django_filters.CharFilter(
        field_name="requester__username",
        help_text="Exact requester username.",
    )
    assignee = django_filters.CharFilter(
        field_name="assignee__username",
        help_text="Exact assignee username.",
    )
    priority = django_filters.CharFilter(
        field_name="priority__label",
        help_text="Exact priority label.",
    )
    content_type = django_filters.CharFilter(
        field_name="content_type__model",
        help_text='Exact content type model name. E.g.: "owner".',
    )
    last_modified_date = LastModifiedDateFilter()

    class Meta:
        model = Request
        fields = (
            "request_template",
            "status",
            "requester",
            "assignee",
            "priority",
            "content_type",
            "last_modified_date",
        )


class RequestViewSet(ExtraPermissionsViewSetMixin, CreateRetrieveUpdateListViewSet):
    queryset = Request.objects.all()
    serializer_class = RequestSerializer
    lookup_field = "uuid"
    filterset_class = RequestFilterSet
    extra_permissions = (TabPermission,)
    search_fields = (
        "title",
        "serialized_data",
    )
    search_fields_autocomplete = ("title",)
    ordering_fields = (
        "title",
        "request_template",
        "status",
        "priority",
        "assignee",
        "requester",
        "created_date",
        "last_modified_date",
    )

    def get_queryset(self):
        user = self.request.user
        qs = (
            super()
            .get_queryset()
            .product_secured(user)
            .select_related(
                "request_template",
                "requester",
                "assignee",
                "priority",
                "product_context",
                "content_type",
            )
            .prefetch_related(  # one extra query per content_type
                "content_object",
            )
        )
        if not user.is_staff:
            qs = qs.filter(is_private=False)
        return qs

    def perform_create(self, serializer):
        super().perform_create(serializer)
        send_request_notification(self.request, serializer.instance, created=True)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        send_request_notification(self.request, serializer.instance, created=False)
        serializer.instance.events.create(
            user=self.request.user,
            text="Request edited.",
            event_type=RequestEvent.EDIT,
            dataspace=self.request.user.dataspace,
        )

    @action(
        detail=True,
        methods=["post"],
        serializer_class=RequestCommentSerializer,
    )
    def add_comment(self, request, *args, **kwargs):
        """Add a comment to this request."""
        request_instance = self.get_object()

        serializer = RequestCommentSerializer(data=request.data)
        if serializer.is_valid():
            request_instance.add_comment(self.request.user, **serializer.validated_data)
            return Response({"status": "Comment added."}, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
