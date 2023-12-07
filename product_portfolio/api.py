#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.exceptions import ValidationError

import django_filters
from rest_framework import permissions
from rest_framework import serializers
from rest_framework.permissions import SAFE_METHODS

from component_catalog.api import KeywordsField
from component_catalog.api import PackageEmbeddedSerializer
from component_catalog.api import ValidateLicenseExpressionMixin
from component_catalog.license_expression_dje import clean_related_expression
from dje.api import CreateRetrieveUpdateListViewSet
from dje.api import DataspacedAPIFilterSet
from dje.api import DataspacedHyperlinkedRelatedField
from dje.api import DataspacedSerializer
from dje.api import DataspacedSlugRelatedField
from dje.api import ExtraPermissionsViewSetMixin
from dje.api import NameVersionHyperlinkedRelatedField
from dje.api_custom import TabPermission
from dje.filters import LastModifiedDateFilter
from dje.filters import MultipleCharFilter
from dje.filters import MultipleUUIDFilter
from dje.filters import NameVersionFilter
from dje.permissions import assign_all_object_permissions
from product_portfolio.filters import ComponentCompletenessAPIFilter
from product_portfolio.models import CodebaseResource
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductPackage

base_extra_kwargs = {
    "licenses": {
        "view_name": "api_v2:license-detail",
        "lookup_field": "uuid",
    },
    "component": {
        "view_name": "api_v2:component-detail",
        "lookup_field": "uuid",
    },
    "components": {
        "view_name": "api_v2:component-detail",
        "lookup_field": "uuid",
    },
    "package": {
        "view_name": "api_v2:package-detail",
        "lookup_field": "uuid",
    },
    "packages": {
        "view_name": "api_v2:package-detail",
        "lookup_field": "uuid",
    },
    "product": {
        "view_name": "api_v2:product-detail",
        "lookup_field": "uuid",
    },
    "product_component": {
        "view_name": "api_v2:productcomponent-detail",
        "lookup_field": "uuid",
    },
    "product_package": {
        "view_name": "api_v2:productpackage-detail",
        "lookup_field": "uuid",
    },
}


class ProductSerializer(ValidateLicenseExpressionMixin, DataspacedSerializer):
    display_name = serializers.ReadOnlyField(source="__str__")
    absolute_url = serializers.SerializerMethodField()
    owner = DataspacedHyperlinkedRelatedField(
        view_name="api_v2:owner-detail",
        lookup_field="uuid",
        allow_null=True,
        required=False,
        html_cutoff=10,
        slug_field="name",
    )
    configuration_status = DataspacedSlugRelatedField(
        slug_field="label",
        allow_null=True,
        required=False,
    )
    keywords = KeywordsField(
        required=False,
    )

    class Meta:
        model = Product
        fields = (
            "display_name",
            "api_url",
            "absolute_url",
            "uuid",
            "name",
            "version",
            "owner",
            "configuration_status",
            "license_expression",
            "licenses",
            "components",
            "packages",
            "keywords",
            "release_date",
            "description",
            "copyright",
            "contact",
            "homepage_url",
            "vcs_url",
            "code_view_url",
            "bug_tracking_url",
            "primary_language",
            "admin_notes",
            "notice_text",
            "created_date",
            "last_modified_date",
        )
        extra_kwargs = {
            **base_extra_kwargs,
            "api_url": {
                "view_name": "api_v2:product-detail",
                "lookup_field": "uuid",
            },
        }


class ProductFilterSet(DataspacedAPIFilterSet):
    id = django_filters.NumberFilter(
        help_text="Exact id.",
    )
    uuid = MultipleUUIDFilter()
    name = MultipleCharFilter(
        help_text="Exact name. Multi-value supported.",
    )
    version = django_filters.CharFilter(
        help_text="Exact version.",
    )
    version__lt = django_filters.CharFilter(
        field_name="version",
        lookup_expr="lt",
        help_text="Version is lower than.",
    )
    version__gt = django_filters.CharFilter(
        field_name="version",
        lookup_expr="gt",
        help_text="Version is greater than.",
    )
    primary_language = django_filters.CharFilter(
        help_text="Exact primary language.",
    )
    owner = MultipleCharFilter(
        field_name="owner__name",
        help_text="Exact owner name. Multi-value supported.",
    )
    configuration_status = django_filters.CharFilter(
        field_name="configuration_status__label",
        help_text="Exact configuration status label.",
    )
    license_expression = django_filters.CharFilter(
        lookup_expr="icontains",
        help_text="License expression contains (case-insensitive).",
    )
    keywords = django_filters.CharFilter(
        lookup_expr="icontains",
        help_text="Keyword label contains (case-insensitive)",
    )
    last_modified_date = LastModifiedDateFilter()

    class Meta:
        model = Product
        fields = (
            # id is required for the add_to_product feature
            "id",
            "uuid",
            "name",
            "version",
            "version__lt",
            "version__gt",
            "primary_language",
            "owner",
            "configuration_status",
            "license_expression",
            "last_modified_date",
        )


class ProductViewSet(CreateRetrieveUpdateListViewSet):
    queryset = Product.objects.none()
    serializer_class = ProductSerializer
    filterset_class = ProductFilterSet
    lookup_field = "uuid"
    # `IsAuthenticated` and `DjangoModelPermissions` are the default values
    # set in the `DEFAULT_PERMISSION_CLASSES` settings.
    # See http://www.django-rest-framework.org/api-guide/permissions/#djangoobjectpermissions
    extra_permissions = (permissions.DjangoObjectPermissions,)
    search_fields = (
        "name",
        "version",
        "copyright",
        "homepage_url",
    )
    search_fields_autocomplete = (
        "name",
        "version",
    )
    ordering_fields = (
        "name",
        "version",
        "configuration_status",
        "license_expression",
        "release_date",
        "copyright",
        "created_date",
        "last_modified_date",
    )

    def get_queryset(self):
        return (
            Product.objects.get_queryset(self.request.user)
            .select_related(
                "owner",
                "configuration_status",
            )
            .prefetch_related(
                "components",
                "packages",
                "licenses",
            )
        )

    def perform_create(self, serializer):
        """Add view/change/delete Object permissions to the Product creator."""
        super().perform_create(serializer)
        assign_all_object_permissions(self.request.user, serializer.instance)


class BaseProductRelationSerializer(ValidateLicenseExpressionMixin, DataspacedSerializer):
    product = NameVersionHyperlinkedRelatedField(
        view_name="api_v2:product-detail",
        lookup_field="uuid",
        allow_null=False,
    )
    review_status = DataspacedSlugRelatedField(
        slug_field="label",
        allow_null=True,
        required=False,
    )
    purpose = DataspacedSlugRelatedField(
        slug_field="label",
        allow_null=True,
        required=False,
    )

    def validate(self, attrs):
        """Add support for LicenseChoice to the `license_expression` field validation."""
        attrs = super().validate(attrs)

        related_field = self.Meta.relation_fk_field
        license_expression = attrs.get("license_expression")
        related_object = attrs.get(related_field)

        if license_expression and related_object and related_object.license_expression:
            try:
                expression = clean_related_expression(license_expression, related_object)
            except ValidationError as e:
                errors = {"license_expression": [e.message]}
                raise serializers.ValidationError(errors, code="invalid")
            attrs["license_expression"] = expression

        return attrs


class ProductComponentSerializer(BaseProductRelationSerializer):
    component = NameVersionHyperlinkedRelatedField(
        view_name="api_v2:component-detail",
        lookup_field="uuid",
        allow_null=True,
        required=False,
        # Required to bypass the ('product', 'component') unique_together validation
        # when component value is not provided (custom component)
        default=None,
    )

    class Meta:
        model = ProductComponent
        relation_fk_field = "component"
        fields = (
            "api_url",
            "uuid",
            "product",
            "component",
            "review_status",
            "license_expression",
            "licenses",
            "purpose",
            "notes",
            "is_deployed",
            "is_modified",
            "extra_attribution_text",
            "feature",
            "package_paths",
            "name",
            "version",
            "owner",
            "copyright",
            "homepage_url",
            "download_url",
            "primary_language",
            "reference_notes",
            "issue_ref",
            "created_date",
            "last_modified_date",
        )
        extra_kwargs = {
            **base_extra_kwargs,
            # The `default` value set on the model field is not accounted by DRF
            # https://github.com/encode/django-rest-framework/issues/7469
            "is_deployed": {"default": True},
            "api_url": {
                "view_name": "api_v2:productcomponent-detail",
                "lookup_field": "uuid",
            },
        }


class ProductComponentFilterSet(DataspacedAPIFilterSet):
    uuid = MultipleUUIDFilter()
    product = NameVersionFilter(
        name_field_name="product__name",
        version_field_name="product__version",
    )
    component = NameVersionFilter(
        name_field_name="component__name",
        version_field_name="component__version",
    )
    review_status = django_filters.CharFilter(
        field_name="review_status__label",
        help_text="Exact review status label.",
    )
    purpose = django_filters.CharFilter(
        field_name="purpose__label",
        help_text="Exact purpose label.",
    )
    feature = django_filters.CharFilter(
        help_text="Exact feature label.",
    )
    completeness = ComponentCompletenessAPIFilter(
        label="Component completeness",
        choices=[("catalog", "Catalog"), ("custom", "Custom")],
        help_text='Supported values: "catalog", "custom".',
    )
    last_modified_date = LastModifiedDateFilter()

    class Meta:
        model = ProductComponent
        fields = (
            "uuid",
            "product",
            "component",
            "review_status",
            "purpose",
            "feature",
            "completeness",
            "last_modified_date",
        )


class ProductRelatedViewSet(ExtraPermissionsViewSetMixin, CreateRetrieveUpdateListViewSet):
    lookup_field = "uuid"
    extra_permissions = (TabPermission,)

    def get_queryset(self):
        perms = ["view_product"]
        if self.request.method not in SAFE_METHODS:
            perms.append("change_product")

        return self.queryset.model.objects.product_secured(self.request.user, perms)


class ProductRelationViewSet(ProductRelatedViewSet):
    relation_fk_field = None

    def get_queryset(self):
        perms = ["view_product"]
        if self.request.method not in SAFE_METHODS:
            perms.append("change_product")

        return (
            super()
            .get_queryset()
            .select_related(
                f"{self.relation_fk_field}__dataspace",
                "review_status",
                "purpose",
            )
            .prefetch_related(
                "licenses",
                "product",
            )
        )


class ProductComponentViewSet(ProductRelationViewSet):
    relation_fk_field = "component"
    queryset = ProductComponent.objects.none()
    serializer_class = ProductComponentSerializer
    filterset_class = ProductComponentFilterSet
    search_fields = ("notes",)
    ordering_fields = (
        "component",
        "review_status",
        "license_expression",
        "created_date",
        "last_modified_date",
    )


class ProductPackageSerializer(BaseProductRelationSerializer):
    package = DataspacedHyperlinkedRelatedField(
        view_name="api_v2:package-detail",
        lookup_field="uuid",
        allow_null=False,
        required=True,
        html_cutoff=10,
        slug_field="filename",
    )
    package_abcd = PackageEmbeddedSerializer(
        source="package",
        read_only=True,
    )

    class Meta:
        model = ProductPackage
        relation_fk_field = "package"
        fields = (
            "api_url",
            "uuid",
            "product",
            "package",
            "package_abcd",
            "review_status",
            "license_expression",
            "licenses",
            "purpose",
            "notes",
            "is_deployed",
            "is_modified",
            "extra_attribution_text",
            "feature",
            "package_paths",
            "reference_notes",
            "issue_ref",
            "created_date",
            "last_modified_date",
        )
        extra_kwargs = {
            **base_extra_kwargs,
            # The `default` value set on the model field is not accounted by DRF
            # https://github.com/encode/django-rest-framework/issues/7469
            "is_deployed": {"default": True},
            "api_url": {
                "view_name": "api_v2:productpackage-detail",
                "lookup_field": "uuid",
            },
        }


class ProductPackageFilterSet(DataspacedAPIFilterSet):
    uuid = MultipleUUIDFilter()
    product = NameVersionFilter(
        name_field_name="product__name",
        version_field_name="product__version",
    )
    package = MultipleUUIDFilter(
        field_name="package__uuid",
    )
    review_status = django_filters.CharFilter(
        field_name="review_status__label",
        help_text="Exact review status label.",
    )
    purpose = django_filters.CharFilter(
        field_name="purpose__label",
        help_text="Exact purpose label.",
    )
    feature = django_filters.CharFilter(
        help_text="Exact feature label.",
    )
    last_modified_date = LastModifiedDateFilter()

    class Meta:
        model = ProductPackage
        fields = (
            "uuid",
            "product",
            "package",
            "review_status",
            "purpose",
            "feature",
            "last_modified_date",
        )


class ProductPackageViewSet(ProductRelationViewSet):
    relation_fk_field = "package"
    queryset = ProductPackage.objects.none()
    serializer_class = ProductPackageSerializer
    filterset_class = ProductPackageFilterSet
    search_fields = ("notes",)
    ordering_fields = (
        "package",
        "review_status",
        "license_expression",
        "created_date",
        "last_modified_date",
    )


class CodebaseResourceSerializer(DataspacedSerializer):
    product = NameVersionHyperlinkedRelatedField(
        view_name="api_v2:product-detail",
        lookup_field="uuid",
        allow_null=False,
    )
    deployed_to = DataspacedSlugRelatedField(
        many=True,
        slug_field="path",
        required=False,
    )
    deployed_from = serializers.SerializerMethodField()

    class Meta:
        model = CodebaseResource
        fields = (
            "api_url",
            "uuid",
            "product",
            "path",
            "is_deployment_path",
            "product_component",
            "product_package",
            "additional_details",
            "admin_notes",
            "deployed_to",
            "deployed_from",
            "created_date",
            "last_modified_date",
        )
        extra_kwargs = {
            **base_extra_kwargs,
            "api_url": {
                "view_name": "api_v2:codebaseresource-detail",
                "lookup_field": "uuid",
            },
        }

    def get_deployed_from(self, obj):
        return obj.deployed_from_paths


class CodebaseResourceFilterSet(DataspacedAPIFilterSet):
    uuid = MultipleUUIDFilter()
    product = NameVersionFilter(
        name_field_name="product__name",
        version_field_name="product__version",
    )
    last_modified_date = LastModifiedDateFilter()

    class Meta:
        model = CodebaseResource
        fields = (
            "uuid",
            "product",
            "is_deployment_path",
            "last_modified_date",
        )


class CodebaseResourceViewSet(ProductRelatedViewSet):
    queryset = CodebaseResource.objects.none()
    serializer_class = CodebaseResourceSerializer
    filterset_class = CodebaseResourceFilterSet
    search_fields = ("path",)
    ordering_fields = (
        "path",
        "is_deployment_path",
        "created_date",
        "last_modified_date",
    )

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "product_component__component",
                "product_package__package",
            )
            .prefetch_related(
                "related_deployed_from__deployed_from",
                # This one is different from the `default_select_prefetch` as its using the m2m
                "deployed_to__deployed_to",
                "product",
            )
        )
