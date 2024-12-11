#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import uuid
from contextlib import suppress
from urllib.parse import urlparse

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db import models
from django.urls import Resolver404
from django.urls import get_script_prefix
from django.urls import resolve
from django.utils.encoding import uri_to_iri
from django.utils.text import get_text_list
from django.utils.translation import gettext as _

import django_filters
from django_filters.rest_framework import FilterSet
from rest_framework import mixins
from rest_framework import serializers
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import SAFE_METHODS
from rest_framework.relations import ManyRelatedField
from rest_framework.response import Response

from dje import outputs
from dje.api_custom import TabPermission
from dje.copier import copy_object
from dje.fields import ExtendedNullBooleanSelect
from dje.filters import LastModifiedDateFilter
from dje.filters import MultipleUUIDFilter
from dje.models import Dataspace
from dje.models import ExternalReference
from dje.models import History
from dje.models import is_content_type_related
from dje.models import is_secured
from dje.notification import send_notification_email
from dje.permissions import get_authorized_tabs
from dje.permissions import get_protected_fields
from dje.permissions import get_tabset_for_model
from dje.utils import construct_changes_details_message
from dje.utils import extract_name_version
from dje.utils import has_permission
from dje.utils import set_intermediate_explicit_m2m

REFERENCE_VAR = "reference"


class CreateRetrieveUpdateListViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Provide default `create`, `retrieve`, `update`,  `partial_update`, and `list` actions."""

    email_notification_on = []
    allow_reference_access = False

    def get_queryset(self):
        """
        Allow to access the reference data if the `self.allow_reference_access` is True.
        The `REFERENCE_VAR` needs to be provided as a GET parameter `?reference=1` in the URL.
        The special value `combine` can be provided as value for the `reference` parameter,
        `?reference=combine`, to return records from both the user dataspace and the reference
        one.
        The special `merge` value value will include the reference records excluding the
        objects `uuid` already present in the user dataspace.
        The reference data access is only available on `SAFE_METHODS` ('GET', 'HEAD', 'OPTIONS').
        """
        user_dataspace = self.request.user.dataspace
        base_qs = super().get_queryset()
        user_qs = base_qs.scope(user_dataspace)

        reference_params_value = self.request.GET.get(REFERENCE_VAR)
        reference_access = all(
            [
                self.allow_reference_access,
                reference_params_value,
                self.request.method in SAFE_METHODS,
            ]
        )

        if not reference_access:
            return user_qs

        reference_dataspace = Dataspace.objects.get_reference()
        if not reference_dataspace:
            return user_qs

        if reference_params_value not in ["combine", "merge"]:
            reference_qs = base_qs.scope(reference_dataspace)
            return reference_qs

        combined_qs = base_qs.scope(user_dataspace, include_reference=True)

        if reference_params_value == "merge":
            return combined_qs.exclude(
                uuid__in=models.Subquery(user_qs.values("uuid")),
                dataspace=reference_dataspace,
            )

        return combined_qs

    @action(detail=True, methods=["post"])
    def copy_to_my_dataspace(self, request, uuid):
        reference_dataspace = Dataspace.objects.get_reference()
        permission_error = {"error": "You do not have rights to execute this action."}
        reference_access = all(
            [
                self.allow_reference_access,
                reference_dataspace,
            ]
        )

        if not reference_access:
            return Response(permission_error, status=status.HTTP_400_BAD_REQUEST)

        queryset = self.queryset.scope(reference_dataspace)
        reference_object = get_object_or_404(queryset, uuid=uuid)

        user = request.user
        target_dataspace = user.dataspace
        model_class = reference_object.__class__

        if not has_permission(reference_object, user, "add"):
            return Response(permission_error, status=status.HTTP_400_BAD_REQUEST)

        if target_dataspace.is_reference:
            data = {"error": "Target dataspace cannot be the reference one."}
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

        object_exists_in_target_dataspace = (
            model_class._default_manager.scope(target_dataspace)
            .filter(uuid=reference_object.uuid)
            .exists()
        )
        if object_exists_in_target_dataspace:
            data = {"error": "The object already exists in your local Dataspace."}
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

        copied_object = copy_object(reference_object, target_dataspace, user)

        if not copied_object:
            data = {"error": "The object could not be copied."}
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(copied_object)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Add the Addition History."""
        user = self.request.user

        fields_name = [field.name for field in serializer.Meta.model._meta.get_fields()]
        kwargs = {}
        if "created_by" in fields_name:
            kwargs["created_by"] = user
        if "last_modified_by" in fields_name:
            kwargs["last_modified_by"] = user

        serializer.save(**kwargs)

        History.log_addition(user, serializer.instance)
        if History.ADDITION in self.email_notification_on:
            send_notification_email(self.request, serializer.instance, History.ADDITION)

    def perform_update(self, serializer):
        """Add the CHANGE History."""
        changed_data = []
        changes_details = []
        user = self.request.user

        for field_name, new_value in serializer.validated_data.items():
            original_value = getattr(serializer.instance, field_name, None)
            if new_value != original_value:
                changed_data.append(field_name)
                changes_details.append((field_name, original_value, new_value))

        fields_name = [field.name for field in serializer.Meta.model._meta.get_fields()]
        kwargs = {}
        if "last_modified_by" in fields_name:
            kwargs["last_modified_by"] = user

        serialized_data = None
        with suppress(AttributeError):
            serialized_data = serializer.instance.as_json()

        serializer.save(**kwargs)

        if changed_data:
            change_message = [_("Changed {}.").format(get_text_list(changed_data, _("and")))]
            change_message = " ".join(change_message)
        else:
            change_message = _("No fields changed.")

        History.log_change(user, serializer.instance, change_message, serialized_data)

        if History.CHANGE in self.email_notification_on:
            change_message += construct_changes_details_message(
                {serializer.instance: changes_details}
            )
            send_notification_email(
                self.request, serializer.instance, History.CHANGE, change_message
            )


class ExtraPermissionsViewSetMixin:
    def get_permissions(self):
        permission_classes = super().get_permissions()
        extra_permission = [permission() for permission in self.extra_permissions]
        return permission_classes + extra_permission


class DynamicFieldsSerializerMixin:
    """
    A Serializer mixin that takes an additional `fields` or `exclude_fields`
    arguments to customize the field selection.

    Inspired by https://www.django-rest-framework.org/api-guide/serializers/#example
    """

    def __init__(self, *args, **kwargs):
        fields = kwargs.pop("fields", [])
        exclude_fields = kwargs.pop("exclude_fields", [])

        super().__init__(*args, **kwargs)

        if fields:
            self.fields = {
                field_name: field
                for field_name, field in self.fields.items()
                if field_name in fields
            }

        for field_name in exclude_fields:
            self.fields.pop(field_name)


class DataspacedSerializer(DynamicFieldsSerializerMixin, serializers.HyperlinkedModelSerializer):
    def __init__(self, *args, **kwargs):
        """
        Add the `dataspace` attribute from the request User Dataspace.
        Required at save time and for validation.
        """
        super().__init__(*args, **kwargs)
        request = self.context.get("request", None)
        self.dataspace = request.user.dataspace if request else None

    def save(self, **kwargs):
        """
        Add the current user dataspace in the object data and
        Wrap the IntegrityError with proper DRFValidationError.

        Starts by popping the m2m data before the actual save()
        then set the m2m relations post save().
        """
        # Pops the m2m data from the validated_data dict before save()
        m2m_data = {
            f: self._validated_data.pop(f.name)
            for f in self.Meta.model._meta.get_fields()
            if f.many_to_many and not f.auto_created and f.name in self._validated_data
        }

        if "uuid" in self.validated_data and not self.validated_data.get("uuid"):
            kwargs.update({"uuid": uuid.uuid4()})

        # Update the uuid in the view kwargs to allow a proper `get_object()` post update
        updated_uuid = self.validated_data.get("uuid")
        if updated_uuid:
            self.context["view"].kwargs["uuid"] = updated_uuid

        kwargs.update({"dataspace": self.dataspace})
        try:
            instance = super().save(**kwargs)
        except (IntegrityError, DjangoValidationError) as e:
            raise DRFValidationError(str(e))

        for field, data in m2m_data.items():
            set_intermediate_explicit_m2m(instance, field, data)

        return instance

    def validate(self, attrs):
        """Add the uniqueness validation calling the logic from Model.clean()."""
        # Make a copy of the attrs and Remove the m2m values,
        # since those cannot be part of the clean()
        attrs_copy = attrs.copy()

        for f in self.Meta.model._meta.get_fields():
            if f.many_to_many and not f.auto_created:
                attrs_copy.pop(f.name, None)
            if isinstance(f, models.ManyToOneRel):
                attrs_copy.pop(f.get_accessor_name(), None)

        for field_name in getattr(self.Meta, "exclude_from_validate", []):
            attrs_copy.pop(field_name, None)

        instance = self.Meta.model(**attrs_copy)
        instance.dataspace = self.dataspace
        # Set the id from the `instance` to handle create vs. edit in Model.`clean()`
        with suppress(AttributeError):
            instance.id = self.instance.id

        instance.clean(from_api=True)

        return attrs

    def get_fields(self):
        """Enable to override the UUID field. Also enabled the field level permissions."""
        fields = super().get_fields()

        if "uuid" in fields:
            fields["uuid"].read_only = False
            fields["uuid"].allow_null = True

        request = self.context.get("request", None)
        if request:
            fields = self.apply_tabs_permission(fields, request.user)

            protected_fields = get_protected_fields(self.Meta.model, request.user)
            for field_name in protected_fields:
                if field_name in fields:
                    fields[field_name].read_only = True

        # Add the object dataspace name as a read-only field.
        fields["dataspace"] = serializers.StringRelatedField()

        return fields

    def get_absolute_url(self, obj):
        """
        Return the object fully qualified URL including the schema and domain.

        Usage:
            absolute_url = serializers.SerializerMethodField()
        """
        absolute_url = obj.get_absolute_url()

        if request := self.context.get("request", None):
            return request.build_absolute_uri(location=absolute_url)

        return absolute_url

    def apply_tabs_permission(self, fields, user):
        model_tabset = get_tabset_for_model(self.Meta.model)

        if not model_tabset:
            return fields

        authorized_fields = {"api_url", "absolute_url", "uuid"}
        authorized_tabs = get_authorized_tabs(self.Meta.model, user)

        if authorized_tabs:
            for tab in authorized_tabs:
                authorized_fields.update(model_tabset.get(tab, {}).get("fields", []))

            fields = {
                field_name: field
                for field_name, field in fields.items()
                if field_name in authorized_fields
            }

        return fields


class DataspacedAPIFilterSet(FilterSet):
    """
    Override default filters.
    This duplicates the purpose of `Meta.filter_overrides`
    but works better for inheritance.
    """

    @classmethod
    def filter_for_lookup(cls, f, lookup_type):
        if isinstance(f, models.BooleanField):
            params = {
                "help_text": 'Supported values: "yes", "no"',
                "widget": ExtendedNullBooleanSelect,
            }
            return django_filters.BooleanFilter, params
        return super().filter_for_lookup(f, lookup_type)


class DataspacedRelatedFieldMixin:
    """
    Handle the Dataspace scoping and the ContentType scoping if the `scope_content_type`
    if provided.
    """

    def __init__(self, scope_content_type=False, **kwargs):
        self.scope_content_type = scope_content_type
        super().__init__(**kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()

        # Support for `many=True`
        serializer_field = self.parent if isinstance(self.parent, ManyRelatedField) else self

        model_class = serializer_field.parent.Meta.model
        field_name = serializer_field.source
        field = model_class._meta.get_field(field_name)
        user = self.context["request"].user

        if not queryset:
            manager = field.related_model.objects
            if is_secured(manager):
                queryset = manager.get_queryset(user=user)
            else:
                queryset = manager.all()

        queryset = queryset.scope(user.dataspace)

        if self.scope_content_type:
            if not is_content_type_related(field.related_model):
                raise ImproperlyConfigured(f"`{field_name}` is not ContentType related")
            content_type = ContentType.objects.get_for_model(model_class)
            queryset = queryset.filter(content_type=content_type)

        return queryset


class DataspacedSlugRelatedField(DataspacedRelatedFieldMixin, serializers.SlugRelatedField):
    pass


class DataspacedHyperlinkedRelatedField(
    DataspacedRelatedFieldMixin, serializers.HyperlinkedRelatedField
):
    """Add support for a slug value for the lookup if `slug_field` is given."""

    def __init__(self, slug_field=None, **kwargs):
        self.slug_field = slug_field
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if self.slug_field:
            with suppress(ObjectDoesNotExist, TypeError, ValueError, DjangoValidationError):
                return self.get_queryset().get(**{self.slug_field: data})
        return super().to_internal_value(data)


class NameVersionHyperlinkedRelatedField(
    DataspacedRelatedFieldMixin, serializers.HyperlinkedRelatedField
):
    """Add support for submitting a "name:version" value in place of the default identifier."""

    def to_internal_value(self, data):
        try:
            name, version = extract_name_version(data)
            return self.get_queryset().get(name=name, version=version)
        except (ObjectDoesNotExist, SyntaxError):
            return super().to_internal_value(data)


class GenericForeignKeyHyperlinkedField(DataspacedHyperlinkedRelatedField):
    """Add support for GenericForeignKey type fields."""

    view_name = "*"

    def get_url(self, obj, view_name, request, format):
        """Enable dynamic view_name generated using the obj model_name."""
        view_name = f"api_v2:{obj._meta.model_name}-detail"
        return super().get_url(obj, view_name, request, format)

    def to_internal_value(self, data):
        """Return the object using the values from the URL matching."""
        # The first section of the following code is copied as-is from
        # HyperlinkedRelatedField.to_internal_value()
        request = self.context.get("request", None)
        try:
            http_prefix = data.startswith(("http:", "https:"))
        except AttributeError:
            self.fail("incorrect_type", data_type=type(data).__name__)

        if http_prefix:
            # If needed convert absolute URLs to relative path
            data = urlparse(data).path
            prefix = get_script_prefix()
            if data.startswith(prefix):
                len_prefix = len(prefix)
                data = "/" + data[len_prefix:]

        data = uri_to_iri(data)

        try:
            match = resolve(data)
        except Resolver404:
            self.fail("no_match")

        # Additions to HyperlinkedRelatedField.to_internal_value() starts here
        user = request.user

        related_model_class = match.func.cls.serializer_class.Meta.model
        related_opts = related_model_class._meta

        parent_model_opts = self.parent.Meta.model._meta
        field = parent_model_opts.get_field(self.field_name)
        limit_choices_to = parent_model_opts.get_field(field.ct_field).get_limit_choices_to()
        if limit_choices_to:
            try:
                ContentType.objects.complex_filter(limit_choices_to).get(
                    app_label=related_opts.app_label, model=related_opts.model_name
                )
            except ObjectDoesNotExist:
                raise DRFValidationError(_("Invalid Object type."), code="incorrect_content_type")

        lookup_value = match.kwargs[self.lookup_url_kwarg]
        lookup_kwargs = {self.lookup_field: lookup_value}

        manager = related_model_class.objects
        if is_secured(manager):
            queryset = manager.get_queryset(user=user)
        else:
            queryset = manager.all()
        queryset = queryset.scope(user.dataspace)

        try:
            return queryset.get(**lookup_kwargs)
        except (ObjectDoesNotExist, TypeError, ValueError):
            self.fail("does_not_exist")


class ProductRelatedViewSet(ExtraPermissionsViewSetMixin, CreateRetrieveUpdateListViewSet):
    lookup_field = "uuid"
    extra_permissions = (TabPermission,)

    def get_queryset(self):
        perms = ["view_product"]
        if self.request.method not in SAFE_METHODS:
            perms.append("change_product")

        return self.queryset.model.objects.product_secured(self.request.user, perms)


class ExternalReferenceSerializer(DataspacedSerializer):
    external_source = DataspacedSlugRelatedField(slug_field="label")
    content_type = serializers.StringRelatedField(source="content_type.model")
    content_object = GenericForeignKeyHyperlinkedField(lookup_field="uuid")
    content_object_display_name = serializers.StringRelatedField(source="content_object")

    class Meta:
        model = ExternalReference
        fields = (
            "api_url",
            "uuid",
            "content_type",
            "content_object",
            "content_object_display_name",
            "external_source",
            "external_id",
            "external_url",
            "created_date",
            "last_modified_date",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:externalreference-detail",
                "lookup_field": "uuid",
            },
        }


class ExternalReferenceFilterSet(DataspacedAPIFilterSet):
    uuid = MultipleUUIDFilter()
    content_type = django_filters.CharFilter(
        field_name="content_type__model",
        help_text='Exact content type model name. E.g.: "owner".',
    )
    external_source = django_filters.CharFilter(
        field_name="external_source__label",
        help_text="Exact external source label.",
    )
    last_modified_date = LastModifiedDateFilter()

    class Meta:
        model = ExternalReference
        fields = (
            "uuid",
            "content_type",
            "external_source",
            "last_modified_date",
        )


class ExternalReferenceViewSet(ExtraPermissionsViewSetMixin, CreateRetrieveUpdateListViewSet):
    queryset = ExternalReference.objects.all()
    serializer_class = ExternalReferenceSerializer
    lookup_field = "uuid"
    filterset_class = ExternalReferenceFilterSet
    extra_permissions = (TabPermission,)
    search_fields = ("external_id",)
    ordering_fields = (
        "external_source",
        "created_date",
        "last_modified_date",
    )
    allow_reference_access = True

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .scope(self.request.user.dataspace)
            .select_related("content_type")
            .prefetch_related("content_object")
        )


class AboutCodeFilesActionMixin:
    @action(detail=True, name="Download AboutCode files")
    def aboutcode_files(self, request, uuid):
        instance = self.get_object()
        about_files = instance.get_about_files()
        filename = self.get_filename(instance)
        return self.get_zipped_response(about_files, filename)


class SPDXDocumentActionMixin:
    @action(detail=True, name="Download SPDX document")
    def spdx_document(self, request, uuid):
        spdx_document = outputs.get_spdx_document(self.get_object(), self.request.user)

        spdx_document_json = spdx_document.as_json()

        return outputs.get_attachment_response(
            file_content=spdx_document_json,
            filename=outputs.get_spdx_filename(spdx_document),
            content_type="application/json",
        )


class CycloneDXSOMActionMixin:
    @action(detail=True, name="Download CycloneDX SBOM")
    def cyclonedx_sbom(self, request, uuid):
        instance = self.get_object()
        spec_version = request.query_params.get("spec_version")

        cyclonedx_bom = outputs.get_cyclonedx_bom(instance, self.request.user)
        try:
            cyclonedx_bom_json = outputs.get_cyclonedx_bom_json(cyclonedx_bom, spec_version)
        except ValueError:
            error = f"Spec version {spec_version} not supported"
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

        return outputs.get_attachment_response(
            file_content=cyclonedx_bom_json,
            filename=outputs.get_cyclonedx_filename(instance),
            content_type="application/json",
        )
