#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import copy
import uuid

from django import forms
from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.contrib.auth import get_permission_codename
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from guardian.admin import GuardedModelAdminMixin
from guardian.shortcuts import get_perms as guardian_get_perms

from component_catalog.admin import AwesompleteAdminMixin
from component_catalog.admin import BaseStatusAdmin
from component_catalog.admin import LicenseExpressionBuilderAdminMixin
from component_catalog.models import Component
from component_catalog.models import Package
from component_catalog.programming_languages import PROGRAMMING_LANGUAGES
from dje.admin import ColoredIconAdminMixin
from dje.admin import DataspacedAdmin
from dje.admin import ProhibitDataspaceLookupMixin
from dje.admin import dejacode_site
from dje.admin import get_additional_information_fieldset
from dje.filters import DataspaceFilter
from dje.filters import LimitToDataspaceListFilter
from dje.filters import RelatedLookupListFilter
from dje.list_display import AsColored
from dje.list_display import AsJoinList
from dje.list_display import AsLink
from dje.list_display import AsNaturalTime
from dje.list_display import AsURL
from dje.permissions import assign_all_object_permissions
from dje.permissions import get_limited_perms_for_model
from product_portfolio.filters import ComponentCompletenessListFilter
from product_portfolio.forms import ProductAdminForm
from product_portfolio.forms import ProductComponentAdminForm
from product_portfolio.forms import ProductComponentMassUpdateForm
from product_portfolio.forms import ProductItemPurposeForm
from product_portfolio.forms import ProductMassUpdateForm
from product_portfolio.forms import ProductPackageAdminForm
from product_portfolio.forms import ProductPackageMassUpdateForm
from product_portfolio.forms import ProductRelatedAdminForm
from product_portfolio.importers import CodebaseResourceImporter
from product_portfolio.importers import ProductComponentImporter
from product_portfolio.importers import ProductPackageImporter
from product_portfolio.inlines import CodebaseResourceUsageDeployedFromInline
from product_portfolio.inlines import CodebaseResourceUsageDeployedToInline
from product_portfolio.inlines import ProductComponentInline
from product_portfolio.inlines import ProductPackageInline
from product_portfolio.models import CodebaseResource
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductDependency
from product_portfolio.models import ProductItemPurpose
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductRelationStatus
from product_portfolio.models import ProductStatus
from reporting.filters import ReportingQueryListFilter


@admin.register(ProductStatus, site=dejacode_site)
class ProductStatusAdmin(BaseStatusAdmin):
    short_description = _(
        "The Product Status indicates the development, review, and availability status "
        "of a Product."
    )
    long_description = _(
        "The Product Status can be used to show the various stages of a Product "
        "lifecycle; for example: Proposal, Design, Prototype, Testing, Legal Review, "
        "Beta Program, General Availability, Discontinued."
    )
    list_display = (
        "label",
        "text",
        "default_on_addition",
        "request_to_generate",
        "get_dataspace",
    )
    fieldsets = (
        (
            "",
            {
                "fields": (
                    "label",
                    "text",
                    "default_on_addition",
                    "request_to_generate",
                    "dataspace",
                    "uuid",
                )
            },
        ),
    )
    activity_log = False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("request_to_generate")


@admin.register(ProductRelationStatus, site=dejacode_site)
class ProductRelationStatusAdmin(BaseStatusAdmin):
    short_description = _(
        "The Product relation status identifies the workflow review stage of a "
        "Component or Package intended for use in a Product."
    )
    long_description = _(
        "By creating appropriate status values, a Dataspace administrator can define "
        "all the review status stages that are necessary to support the Product review "
        "business process."
    )
    activity_log = False


@admin.register(ProductItemPurpose, site=dejacode_site)
class ProductItemPurposeAdmin(ColoredIconAdminMixin, BaseStatusAdmin):
    short_description = _(
        "Indicates how a component/package is used in the product context. "
        "Suggested values are: Core, Test, Tool, Build, Reference, Requirement."
    )
    long_description = _(
        'Alternatively, you may want to align your purpose values with the "facets" used by the '
        "ClearlyDefined project (although note that those may be subject to change): core, data, "
        "dev, docs, examples, tests. Refer to https://docs.clearlydefined.io/clearly#facets for "
        "some discussion and definitions of these facets."
    )
    list_display = (
        "label",
        "text",
        "icon",
        AsColored("color_code"),
        "colored_icon",
        "default_on_addition",
        "get_dataspace",
    )
    fieldsets = (
        (
            "",
            {
                "fields": (
                    "label",
                    "text",
                    "icon",
                    "color_code",
                    "default_on_addition",
                    "dataspace",
                    "uuid",
                )
            },
        ),
    )
    form = ProductItemPurposeForm
    activity_log = False


class DataspacedGuardedModelAdminMixin(ProhibitDataspaceLookupMixin, GuardedModelAdminMixin):
    """Add the Dataspace layer of security around the `GuardedModelAdminMixin`."""

    user_owned_objects_field = "created_by"

    def _obj_perms_manage_views_security_check(self, request, object_pk):
        """
        User must be a superuser or the instance creator to access those views.

        The Dataspace scoping is done in the `get_queryset()`.

        The User and Group scoping is done in forms `UserManageForm` and `GroupManageForm`.
        """
        if not request.user.is_superuser:
            filters = {
                "pk": unquote(object_pk),
                self.user_owned_objects_field: request.user,
            }
            get_object_or_404(self.get_queryset(request), **filters)

    def obj_perms_manage_view(self, request, object_pk):
        self._obj_perms_manage_views_security_check(request, object_pk)
        return super().obj_perms_manage_view(request, object_pk)

    def obj_perms_manage_user_view(self, request, object_pk, user_id):
        self._obj_perms_manage_views_security_check(request, object_pk)
        return super().obj_perms_manage_user_view(request, object_pk, user_id)

    def obj_perms_manage_group_view(self, request, object_pk, group_id):
        self._obj_perms_manage_views_security_check(request, object_pk)
        return super().obj_perms_manage_group_view(request, object_pk, group_id)

    def get_queryset(self, request, include_inactive=False):
        """
        Return a secured QuerySet using the django-guardian filtering.
        Limited to Objects for which the User has the `change` Object permission
        assigned.
        Cross Dataspace lookup is not allowed, see also `lookup_allowed()` method.
        """
        codename = get_permission_codename("change", self.opts)
        return self.model.objects.get_queryset(request.user, codename, include_inactive)

    def has_change_permission(self, request, obj=None):
        if obj:
            codename = get_permission_codename("change", self.opts)
            return codename in guardian_get_perms(request.user, obj)
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj:
            codename = get_permission_codename("delete", self.opts)
            return codename in guardian_get_perms(request.user, obj)
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        """
        Add view/change/delete Object permissions to the Product creator.

        Add the copy of the ProductComponent and ProductPackage during a `save_as` since
        those value are not in the form as inlines.
        """
        super().save_model(request, obj, form, change)
        if not change:
            assign_all_object_permissions(request.user, obj)

        if "_saveasnew" in request.POST:
            old_product_id = request.resolver_match.kwargs.get("object_id")
            old_product = self.get_object(request, old_product_id)
            for model_class in [ProductComponent, ProductPackage]:
                for relationship in model_class.objects.filter(product=old_product):
                    relationship.id = None
                    relationship.uuid = uuid.uuid4()
                    relationship.product = obj
                    relationship.save()

    def get_obj_perms_user_select_form(self, request):
        """
        Return a UserManageForm class using the request object for User Dataspace scoping.
        Using a factory pattern for thread safety.
        """
        User = get_user_model()

        class UserManageForm(forms.Form):
            user = forms.ModelChoiceField(queryset=User.objects.none())

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

                self.fields["user"].queryset = (
                    User.objects.scope(request.user.dataspace).actives().order_by("username")
                )

        return UserManageForm

    def get_obj_perms_group_select_form(self, request):
        class GroupManageForm(forms.Form):
            group = forms.ModelChoiceField(queryset=Group.objects.all())

        return GroupManageForm

    def _get_limited_obj_perms_form(self, form_class):
        class LimitedObjectPermissionsForm(form_class):
            def get_obj_perms_field_choices(self):
                return [(p.codename, p.name) for p in get_limited_perms_for_model(self.obj)]

        return LimitedObjectPermissionsForm

    def get_obj_perms_manage_user_form(self, request):
        form_class = super().get_obj_perms_manage_user_form(request)
        return self._get_limited_obj_perms_form(form_class)

    def get_obj_perms_manage_group_form(self, request):
        form_class = super().get_obj_perms_manage_group_form(request)
        return self._get_limited_obj_perms_form(form_class)

    def get_obj_perms_base_context(self, request, obj):
        context = super().get_obj_perms_base_context(request, obj)
        context["model_perms"] = get_limited_perms_for_model(obj)
        return context


@admin.register(Product, site=dejacode_site)
class ProductAdmin(
    AwesompleteAdminMixin,
    LicenseExpressionBuilderAdminMixin,
    DataspacedGuardedModelAdminMixin,
    DataspacedAdmin,
):
    short_description = _(
        "A Product is an assembly of software Components or Packages that are distributed or "
        "deployed together."
    )
    long_description = _(
        "A Product is identified by its name and version. It can have its own license and other "
        "attributes. Product Components can have specific attributes such as a license that are "
        "valid only in the context of this Product."
    )
    list_display = (
        "changelist_view_on_site",
        AsNaturalTime("last_modified_date", short_description="Last modified"),
        "name",
        "version",
        "license_expression",
        "copyright",
        AsURL("homepage_url", short_description="Homepage URL"),
        AsLink("owner"),
        AsJoinList("keywords", "<br>", short_description="Keywords"),
        "is_active",
        "configuration_status",
        "primary_language",
        "contact",
        "get_dataspace",
    )
    list_display_links = (
        "name",
        "version",
    )
    list_filter = (
        ("owner", RelatedLookupListFilter),
        ("licenses", RelatedLookupListFilter),
        ReportingQueryListFilter,
        ("configuration_status", LimitToDataspaceListFilter),
        "is_active",
    )
    search_fields = (
        "name",
        "version",
        "owner__name",
        "copyright",
        "homepage_url",
        "owner__alias",
        "primary_language",
    )
    ordering = ("-last_modified_date",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "version",
                    "owner",
                    "copyright",
                    "notice_text",
                    "license_expression",
                    "release_date",
                    "description",
                    "keywords",
                    "homepage_url",
                    "vcs_url",
                    "code_view_url",
                    "bug_tracking_url",
                    "primary_language",
                    "admin_notes",
                    "is_active",
                    "configuration_status",
                    "contact",
                    "get_feature_datalist",
                )
            },
        ),
        ("", {"classes": ("placeholder productcomponents-group",), "fields": ()}),
        ("", {"classes": ("placeholder productpackages-group",), "fields": ()}),
        get_additional_information_fieldset(),
    )
    raw_id_fields = ("owner",)
    autocomplete_lookup_fields = {"fk": ["owner"]}
    inlines = [
        ProductComponentInline,
        ProductPackageInline,
    ]
    form = ProductAdminForm
    actions = []
    actions_to_remove = ["copy_to", "compare_with", "delete_selected"]
    navigation_buttons = True
    activity_log = False
    view_on_site = DataspacedAdmin.changeform_view_on_site
    mass_update_form = ProductMassUpdateForm
    change_form_template = "admin/product_portfolio/product/change_form.html"
    email_notification_on = []  # Turned off for security reasons
    awesomplete_data = {"primary_language": PROGRAMMING_LANGUAGES}
    readonly_fields = DataspacedAdmin.readonly_fields + ("get_feature_datalist",)

    def get_feature_datalist(self, obj):
        if obj.pk:
            return obj.get_feature_datalist()
        return format_html('<datalist id="feature_datalist"></datalist>')

    def get_queryset(self, request, include_inactive=False):
        return (
            super()
            .get_queryset(request, include_inactive=True)
            .select_related(
                "owner",
                "configuration_status",
            )
            .prefetch_related(
                "licenses",
            )
        )


class ProductRelatedAdminMixin(
    ProhibitDataspaceLookupMixin,
    DataspacedAdmin,
):
    activity_log = False
    navigation_buttons = True
    actions = []
    actions_to_remove = ["copy_to", "compare_with"]
    identifier_fields_warning = False
    email_notification_on = []  # Turned off for security reasons

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .product_secured(request.user, "change_product")
            .select_related(
                "product",
            )
        )

    def has_delete_permission(self, request, obj=None):
        if obj:
            # We use the `delete` object permission from the product
            codename = get_permission_codename("delete", obj.product._meta)
            return codename in guardian_get_perms(request.user, obj.product)
        return super().has_delete_permission(request, obj)


class ProductRelationshipAdminMixin(
    AwesompleteAdminMixin,
    LicenseExpressionBuilderAdminMixin,
    ProductRelatedAdminMixin,
):
    related_name = None
    awesomplete_data = {"primary_language": PROGRAMMING_LANGUAGES}
    readonly_fields = DataspacedAdmin.readonly_fields + ("get_feature_datalist",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                self.related_name,
                "review_status",
                "purpose",
            )
        )

    def has_delete_permission(self, request, obj=None):
        if obj:
            # We use the `delete` object permission from the product
            codename = get_permission_codename("delete", obj.product._meta)
            return codename in guardian_get_perms(request.user, obj.product)
        return super().has_delete_permission(request, obj)

    def get_feature_datalist(self, obj):
        if obj.id and obj.product:
            return obj.product.get_feature_datalist()
        return format_html('<datalist id="feature_datalist"></datalist>')

    def get_actions(self, request):
        actions = super().get_actions(request)

        is_user_dataspace = DataspaceFilter.parameter_name not in request.GET
        if request.user.dataspace.is_reference or not is_user_dataspace:
            if "check_related_updates_in_reference" in actions:
                del actions["check_related_updates_in_reference"]
            if "check_related_newer_version_in_reference" in actions:
                del actions["check_related_newer_version_in_reference"]

        return actions


@admin.register(ProductComponent, site=dejacode_site)
class ProductComponentAdmin(ProductRelationshipAdminMixin):
    related_name = "component"
    short_description = _(
        "A Product Component identifies a component in the context of its use in a Product. "
        "The referenced component may be new, or may already be defined in the Component Catalog."
    )
    long_description = _(
        "A Product Component exists in two states: It can be validated and point to an existing "
        "Catalog Component; or, it can be a new, non-validated Component with the optional "
        "attribute values that are available. A non-validated Component may be a custom for a "
        "new entry in the Component Catalog, or it may simply need to be associated with an "
        "existing Catalog Component after search and analysis."
    )
    list_display = (
        "__str__",
        AsLink("product"),
        AsLink("component"),
        "license_expression",
        "review_status",
        "purpose",
        "is_deployed",
        "is_modified",
        "feature",
        "get_dataspace",
    )
    raw_id_fields = [
        "product",
        "component",
    ]
    autocomplete_lookup_fields = {"fk": raw_id_fields}
    list_filter = (
        ("product", RelatedLookupListFilter),
        ("licenses", RelatedLookupListFilter),
        ("review_status", LimitToDataspaceListFilter),
        ComponentCompletenessListFilter,
        ("purpose", LimitToDataspaceListFilter),
        "is_deployed",
        "is_modified",
        ReportingQueryListFilter,
    )
    search_fields = (
        "product__name",
        "component__name",
        "name",
    )
    form = ProductComponentAdminForm
    fieldsets = (
        (None, {"fields": ["product"]}),
        (
            None,
            {
                "fields": [
                    "component",
                    "license_expression",
                    "review_status",
                    "purpose",
                    "notes",
                    "is_deployed",
                    "is_modified",
                    "extra_attribution_text",
                    "feature",
                    "reference_notes",
                    "issue_ref",
                    "get_feature_datalist",
                ]
            },
        ),
        (
            "Custom Component",
            {
                "classes": ["grp-collapse", "grp-closed"],
                "fields": [
                    "name",
                    "version",
                    "owner",
                    "copyright",
                    "homepage_url",
                    "download_url",
                    "primary_language",
                ],
            },
        ),
        (
            "Deprecated",
            {
                "classes": ("grp-collapse grp-closed",),
                "fields": ["package_paths"],
            },
        ),
        get_additional_information_fieldset(),
    )
    mass_update_form = ProductComponentMassUpdateForm
    importer_class = ProductComponentImporter
    change_form_template = "admin/product_portfolio/productcomponent/change_form.html"
    actions = [
        "check_related_updates_in_reference",
        "check_related_newer_version_in_reference",
    ]

    def get_fieldsets(self, request, obj=None):
        """
        Open the collapsible "Custom Component" fieldset section if at least
        one custom field value is set on the instance.
        """
        fieldsets = super().get_fieldsets(request, obj)

        fieldsets_copy = copy.deepcopy(fieldsets)
        if obj and obj.has_custom_values:
            fieldsets_copy[2][1]["classes"] = ["grp-collapse", "grp-open"]

        return fieldsets_copy

    # WARNING: Do not change this method name without updating the reference
    # in templates/admin/change_list_extended.html as well
    @admin.display(description=_("Check for component updates in reference data"))
    def check_related_updates_in_reference(self, request, queryset):
        values = queryset.values_list("component__uuid", "component__last_modified_date")

        orm_lookups = [
            models.Q(**{"uuid": uuid, "last_modified_date__gt": last_modified_date})
            for uuid, last_modified_date in values
            if uuid  # Excludes custom components
        ]

        return self.base_check_in_reference_action(request, Component, orm_lookups)

    # WARNING: Do not change this method name without updating the reference
    # in templates/admin/change_list_extended.html as well
    @admin.display(description=_("Check for newer component versions in reference data"))
    def check_related_newer_version_in_reference(self, request, queryset):
        values = queryset.values_list("component__name", "component__version")

        orm_lookups = [
            models.Q(**{"name": name, "version__gt": version})
            for name, version in values
            if name  # Excludes custom components
        ]

        return self.base_check_in_reference_action(request, Component, orm_lookups)


@admin.register(ProductPackage, site=dejacode_site)
class ProductPackageAdmin(ProductRelationshipAdminMixin):
    related_name = "package"
    short_description = _(
        "A Product Package identifies a package in the context of its use in a Product. "
        "The referenced package must already be defined in DejaCode."
    )
    long_description = _(
        "Product Package information is optionally available to be included in the Attribution "
        "generated for a Product. A Product Package is optionally associated with a Component "
        "in the DejaCode Component Catalog."
    )
    list_display = (
        "__str__",
        AsLink("product"),
        AsLink("package"),
        "license_expression",
        "review_status",
        "purpose",
        "is_deployed",
        "is_modified",
        "feature",
        "get_dataspace",
    )
    raw_id_fields = [
        "product",
        "package",
    ]
    autocomplete_lookup_fields = {"fk": raw_id_fields}
    list_filter = (
        ("product", RelatedLookupListFilter),
        ("licenses", RelatedLookupListFilter),
        ("review_status", LimitToDataspaceListFilter),
        ("purpose", LimitToDataspaceListFilter),
        "is_deployed",
        "is_modified",
        ReportingQueryListFilter,
    )
    search_fields = (
        "product__name",
        "package__filename",
    )
    form = ProductPackageAdminForm
    fieldsets = (
        (None, {"fields": ["product"]}),
        (
            None,
            {
                "fields": [
                    "package",
                    "license_expression",
                    "review_status",
                    "purpose",
                    "notes",
                    "is_deployed",
                    "is_modified",
                    "extra_attribution_text",
                    "feature",
                    "reference_notes",
                    "issue_ref",
                    "get_feature_datalist",
                ]
            },
        ),
        (
            "Deprecated",
            {
                "classes": ("grp-collapse grp-closed",),
                "fields": ["package_paths"],
            },
        ),
        get_additional_information_fieldset(),
    )
    mass_update_form = ProductPackageMassUpdateForm
    importer_class = ProductPackageImporter
    actions = [
        "check_related_updates_in_reference",
    ]

    # WARNING: Do not change this method name without updating the reference
    # in templates/admin/change_list_extended.html as well
    @admin.display(description=_("Check for package updates in reference data"))
    def check_related_updates_in_reference(self, request, queryset):
        values = queryset.values_list("package__uuid", "package__last_modified_date")

        orm_lookups = [
            models.Q(**{"uuid": uuid, "last_modified_date__gt": last_modified_date})
            for uuid, last_modified_date in values
        ]

        return self.base_check_in_reference_action(request, Package, orm_lookups)


@admin.register(CodebaseResource, site=dejacode_site)
class CodebaseResourceAdmin(ProductRelatedAdminMixin):
    short_description = _(
        "Product codebase resources identify the elements in the development and deployment "
        "codebases of a product."
    )
    long_description = _(
        "Each codebase resource, identified by a path, represents an item in a detailed Product "
        "Inventory and/or a summarized Product Bill of Materials (BOM)."
    )
    list_display = (
        "path",
        AsLink("product"),
        "is_deployment_path",
        AsLink("product_component"),
        AsLink("product_package"),
        AsJoinList("deployed_from_paths", "<br>", short_description="Deployed from"),
        AsJoinList("deployed_to_paths", "<br>", short_description="Deployed to"),
        "additional_details",
        "get_dataspace",
    )
    fieldsets = (
        (
            None,
            {
                "fields": [
                    "product",
                    "path",
                    "is_deployment_path",
                    "product_component",
                    "product_package",
                    "additional_details",
                    "admin_notes",
                    "dataspace",
                    "uuid",
                ]
            },
        ),
    )
    raw_id_fields = [
        "product",
        "product_component",
        "product_package",
    ]
    autocomplete_lookup_fields = {"fk": raw_id_fields}
    search_fields = ("path",)
    list_filter = (
        ("product", RelatedLookupListFilter),
        "is_deployment_path",
        ("product_component", RelatedLookupListFilter),
        ("product_package", RelatedLookupListFilter),
        ReportingQueryListFilter,
    )
    inlines = [
        CodebaseResourceUsageDeployedFromInline,
        CodebaseResourceUsageDeployedToInline,
    ]
    actions_to_remove = ["copy_to", "compare_with"]
    form = ProductRelatedAdminForm
    importer_class = CodebaseResourceImporter
    change_form_template = "admin/product_portfolio/codebaseresource/change_form.html"

    def get_queryset(self, request):
        return super().get_queryset(request).default_select_prefetch()

    def response_add(self, request, obj, post_url_continue=None):
        """
        Pre-fills the `product` field with the previously saved value when
        using the `Save and add another` button.
        """
        if "_addanother" in request.POST:
            # Injects the Product id in the `request.path` before it is called
            # in the super() to craft the `redirect_url`,
            # so the preserve filters is are properly handled.
            request.path += f"?product={obj.product_id}"
        return super().response_add(request, obj, post_url_continue)


@admin.register(ProductDependency, site=dejacode_site)
class ProductDependencyAdmin(ProductRelatedAdminMixin):
    list_display = (
        "dependency_uid",
        AsLink("product"),
        AsLink("for_package"),
        AsLink("resolved_to_package"),
        "declared_dependency",
        "extracted_requirement",
        "scope",
        "datasource_id",
        "is_runtime",
        "is_optional",
        "is_resolved",
        "is_direct",
        "get_dataspace",
    )
    raw_id_fields = [
        "product",
        "for_package",
        "resolved_to_package",
    ]
    autocomplete_lookup_fields = {"fk": raw_id_fields}
    search_fields = ("path",)
    list_filter = (
        ("product", RelatedLookupListFilter),
        "is_runtime",
        "is_optional",
        "is_resolved",
        "is_direct",
        ("for_package", RelatedLookupListFilter),
        ("resolved_to_package", RelatedLookupListFilter),
        ReportingQueryListFilter,
    )
    actions_to_remove = ["copy_to", "compare_with"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "for_package__dataspace",
                "resolved_to_package__dataspace",
            )
        )
