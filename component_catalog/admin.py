#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.options import IS_POPUP_VAR
from django.db import transaction
from django.forms import Media
from django.http import QueryDict
from django.shortcuts import redirect
from django.urls import path
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _

from component_catalog.filters import HierarchyRelatedLookupListFilter
from component_catalog.filters import ParentRelatedLookupListFilter
from component_catalog.forms import ComponentAdminForm
from component_catalog.forms import ComponentMassUpdateForm
from component_catalog.forms import PackageAdminForm
from component_catalog.forms import PackageMassUpdateForm
from component_catalog.forms import SubcomponentAdminForm
from component_catalog.forms import SubcomponentMassUpdateForm
from component_catalog.importers import ComponentImporter
from component_catalog.importers import PackageImporter
from component_catalog.importers import SubcomponentImporter
from component_catalog.inlines import ComponentAssignedPackageInline
from component_catalog.inlines import ComponentAssignedPackageInline2
from component_catalog.inlines import SubcomponentChildInline
from component_catalog.license_expression_dje import validate_expression_on_relations
from component_catalog.models import AcceptableLinkage
from component_catalog.models import Component
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import ComponentKeyword
from component_catalog.models import ComponentStatus
from component_catalog.models import ComponentType
from component_catalog.models import Package
from component_catalog.models import Subcomponent
from component_catalog.programming_languages import PROGRAMMING_LANGUAGES
from component_catalog.views import ComponentAddToProductAdminView
from component_catalog.views import PackageAddToProductAdminView
from component_catalog.views import SetComponentPolicyView
from component_catalog.views import SetPackagePolicyView
from component_catalog.views import SetSubcomponentPolicyView
from dje.admin import ChangelistPopupPermissionMixin
from dje.admin import DataspacedAdmin
from dje.admin import ExternalReferenceInline
from dje.admin import dejacode_site
from dje.admin import get_additional_information_fieldset
from dje.admin import get_hierarchy_link
from dje.client_data import add_client_data
from dje.filters import DataspaceFilter
from dje.filters import IsNullFieldListFilter
from dje.filters import LevelFieldListFilter
from dje.filters import LimitToDataspaceListFilter
from dje.filters import MissingInFilter
from dje.filters import RelatedLookupListFilter
from dje.list_display import AsJoinList
from dje.list_display import AsLink
from dje.list_display import AsLinkList
from dje.list_display import AsNaturalTime
from dje.list_display import AsURL
from dje.models import History
from dje.tasks import package_collect_data
from dje.templatetags.dje_tags import urlize_target_blank
from dje.utils import CHANGELIST_LINK_TEMPLATE
from dje.utils import get_instance_from_referer
from license_library.models import License
from reporting.filters import ReportingQueryListFilter


class FormDataOutdated(Exception):
    pass


class AwesompleteAdminMixin:
    awesomplete_data = {}

    @property
    def media(self):
        base_media = super().media
        extra_media = Media(
            css={"all": ("awesomplete/awesomplete-1.1.5.css",)},
            js=(
                "awesomplete/awesomplete-1.1.5.min.js",
                "js/awesomplete_fields.js",
            ),
        )
        return base_media + extra_media

    def get_awesomplete_data(self):
        return self.awesomplete_data

    def add_view(self, request, form_url="", extra_context=None):
        add_client_data(request, awesomplete_data=self.get_awesomplete_data())
        return super().add_view(request, form_url, extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        add_client_data(request, awesomplete_data=self.get_awesomplete_data())
        return super().change_view(request, object_id, form_url, extra_context)


class LicenseExpressionBuilderAdminMixin:
    """
    The full set of license keys available in the dataspace context is always returned.
    The limited keys from the related component are collected on the client side
    (AJAX API call) based on the form state and events.
    """

    expression_field_name = "license_expression"

    @property
    def media(self):
        base_media = super().media
        extra_media = Media(
            css={"all": ("awesomplete/awesomplete-1.1.5.css",)},
            js=(
                "awesomplete/awesomplete-1.1.5.min.js",
                "js/license_expression_builder.js",
            ),
        )
        return base_media + extra_media

    @staticmethod
    def get_license_data_for_builder(request, instance=None):
        """
        Return the list of formatted licenses scoped by the instance dataspace, or
        by the request user dataspace, when an instance is not available (Addition).
        """
        dataspace = instance.dataspace if instance else request.user.dataspace
        license_qs = License.objects.scope(dataspace).filter(is_active=True)
        return license_qs.data_for_expression_builder()

    def setup_license_builder(self, request, instance=None):
        add_client_data(
            request,
            license_data=self.get_license_data_for_builder(request, instance),
            expression_field_name=self.expression_field_name,
        )

    def add_view(self, request, form_url="", extra_context=None):
        self.setup_license_builder(request)
        return super().add_view(request, form_url, extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        response = super().change_view(request, object_id, form_url, extra_context)

        context_data = response.context_data if hasattr(response, "context_data") else None
        instance = context_data.get("original") if context_data else None
        self.setup_license_builder(request, instance)

        return response


@admin.register(ComponentType, site=dejacode_site)
class ComponentTypeAdmin(DataspacedAdmin):
    list_display = (
        "label",
        "notes",
        "get_dataspace",
    )
    search_fields = (
        "label",
        "notes",
    )

    short_description = _("A component type provides a label to filter and sort components.")

    long_description = _(
        "Your dataspace has the specific component types that meet the "
        "filtering and sorting requirements of your business."
    )


class BaseStatusAdmin(DataspacedAdmin):
    list_display = (
        "label",
        "text",
        "default_on_addition",
        "get_dataspace",
    )
    search_fields = (
        "label",
        "text",
    )
    fieldsets = (("", {"fields": ("label", "text", "default_on_addition", "dataspace", "uuid")}),)


@admin.register(ComponentStatus, site=dejacode_site)
class ComponentStatusAdmin(BaseStatusAdmin):
    short_description = _(
        "The Component Status allows to indicate the level of review that has been performed on "
        "a Component."
    )

    long_description = _(
        "The Component Status can be used within a Dataspace to communicate the current stage "
        "of the review process and whether additional review is required."
    )


@admin.register(ComponentKeyword, site=dejacode_site)
class ComponentKeywordAdmin(DataspacedAdmin):
    list_display = ("label", "description")
    search_fields = ("label", "description")
    fieldsets = (("", {"fields": ("label", "description", "dataspace", "uuid")}),)
    list_filter = DataspacedAdmin.list_filter + (MissingInFilter,)

    short_description = _(
        "Component Keywords support the classification of components, providing users with "
        "additional component search criteria."
    )

    long_description = _(
        "You can define as many Component Keywords as you need to meet the requirements of "
        "your users. Note that one or more keywords can be assigned to each component."
    )


@admin.register(AcceptableLinkage, site=dejacode_site)
class AcceptableLinkageAdmin(DataspacedAdmin):
    short_description = _(
        "Acceptable linkages identify the different kinds of interactions that "
        "can exist as integrations between third-party software components and "
        "your organization products."
    )
    long_description = _(
        "Common linkages include Dynamic Linkage, Static Linkage, Stand Alone, "
        "etc. but your legal review team can also define specific linkages "
        "that are appropriate for your organization's software platforms."
    )
    list_display = ("label", "description")
    search_fields = ("label", "description")
    fieldsets = (("", {"fields": ("label", "description", "dataspace", "uuid")}),)

    def get_readonly_fields(self, request, obj=None):
        """Force `label` as readonly on edit."""
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj:
            readonly_fields += ("label",)
        return readonly_fields

    def has_delete_permission(self, request, obj=None):
        perm = super().has_delete_permission(request, obj)
        # Not deletable once at least 1 Component reference this entry
        if not perm or (obj and obj.has_references()):
            return False
        return True


@admin.register(Component, site=dejacode_site)
class ComponentAdmin(
    AwesompleteAdminMixin,
    LicenseExpressionBuilderAdminMixin,
    ChangelistPopupPermissionMixin,
    DataspacedAdmin,
):
    list_display = (
        get_hierarchy_link,
        "changelist_view_on_site",
        AsNaturalTime("last_modified_date", short_description="Last modified"),
        "name",
        "version",
        "license_expression",
        "copyright",
        AsURL("homepage_url", short_description="Homepage URL"),
        AsLink("owner"),
        AsJoinList("keywords", "<br>", short_description="Keywords"),
        "configuration_status",
        AsLinkList("packages", "component", qs_limit=5, html_class="width300 word-break"),
        "cpe",
        "project",
        "is_active",
        "usage_policy",
        "completion_level_pct",
        "curation_level",
        "primary_language",
        "type",
        "get_dataspace",
    )
    list_display_links = (
        "name",
        "version",
    )
    list_filter = (
        ("owner", RelatedLookupListFilter),
        ("licenses", RelatedLookupListFilter),
        DataspaceFilter,
        ReportingQueryListFilter,
        ("type", LimitToDataspaceListFilter),
        ("configuration_status", LimitToDataspaceListFilter),
        ("completion_level", LevelFieldListFilter),
        ("curation_level", LevelFieldListFilter),
        "is_active",
        ("usage_policy", LimitToDataspaceListFilter),
        MissingInFilter,
    )
    search_fields = (
        "name",
        "version",
        "owner__name",
        "copyright",
        "homepage_url",
        "owner__alias",
        "primary_language",
        "packages__filename",
        "project",
    )
    ordering = ("-last_modified_date",)
    fieldsets = [
        (
            None,
            {
                "fields": (
                    "name",
                    "version",
                    "owner",
                    "copyright",
                    "holder",
                    "license_expression",
                    "declared_license_expression",
                    "other_license_expression",
                    "reference_notes",
                    "release_date",
                    "description",
                    "keywords",
                    "homepage_url",
                    "vcs_url",
                    "code_view_url",
                    "bug_tracking_url",
                    "primary_language",
                    "cpe",
                    "project",
                    "codescan_identifier",
                    "type",
                )
            },
        ),
        (
            "Notice",
            {
                "classes": ("grp-collapse grp-open",),
                "fields": (
                    "notice_text",
                    "is_license_notice",
                    "is_copyright_notice",
                    "is_notice_in_codebase",
                    "notice_filename",
                    "notice_url",
                    "website_terms_of_use",
                    "dependencies",
                ),
            },
        ),
        (
            "Usage Policy",
            {
                "classes": ("grp-collapse grp-open",),
                "fields": (
                    "usage_policy",
                    "guidance",
                    "legal_reviewed",
                    "approval_reference",
                    "distribution_formats_allowed",
                    "acceptable_linkages",
                    "export_restrictions",
                    "approved_download_location",
                    "approved_community_interaction",
                ),
            },
        ),
        (
            "Configuration",
            {
                "classes": ("grp-collapse grp-open",),
                "fields": (
                    "configuration_status",
                    "is_active",
                    "curation_level",
                    "completion_level",
                    "admin_notes",
                ),
            },
        ),
        (
            "Legal",
            {
                "classes": ("grp-collapse grp-open",),
                "fields": (
                    "ip_sensitivity_approved",
                    "affiliate_obligations",
                    "affiliate_obligation_triggers",
                    "legal_comments",
                    "sublicense_allowed",
                    "express_patent_grant",
                    "covenant_not_to_assert",
                    "indemnification",
                ),
            },
        ),
        ("", {"classes": ("placeholder related_children-group",), "fields": ()}),
        ("", {"classes": ("placeholder componentassignedpackage_set-group",), "fields": ()}),
        (
            "",
            {
                "classes": ("placeholder dje-externalreference-content_type-object_id-group",),
                "fields": (),
            },
        ),
        get_additional_information_fieldset(pre_fields=("urn_link",)),
    ]
    raw_id_fields = ("owner",)
    autocomplete_lookup_fields = {"fk": ["owner"]}
    # We have to use 'completion_level' rather than the 'completion_level_pct'
    # callable to keep the help_text available during render in the template.
    readonly_fields = DataspacedAdmin.readonly_fields + (
        "urn_link",
        "completion_level",
    )
    form = ComponentAdminForm
    inlines = [
        SubcomponentChildInline,
        ComponentAssignedPackageInline2,
        ExternalReferenceInline,
    ]
    change_form_template = "admin/component_catalog/component/change_form.html"
    delete_confirmation_template = "admin/component_catalog/component/delete_confirmation.html"
    delete_selected_confirmation_template = (
        "admin/component_catalog/component/delete_selected_confirmation.html"
    )
    actions = [
        "copy_to",
        "compare_with",
        "check_updates_in_reference",
        "check_newer_version_in_reference",
        "add_to_product",
        "set_policy",
    ]
    importer_class = ComponentImporter
    navigation_buttons = True
    mass_update_form = ComponentMassUpdateForm
    view_on_site = DataspacedAdmin.changeform_view_on_site
    content_type_scope_fields = ["usage_policy"]
    awesomplete_data = {"primary_language": PROGRAMMING_LANGUAGES}

    short_description = _(
        "A component is any software-related object. Any component can contain "
        "one or more subcomponents."
    )

    long_description = _("Component Name + Component Version must be unique.")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "type",
                "owner",
                "configuration_status",
                "usage_policy",
            )
            .prefetch_related(
                "componentassignedlicense_set__license",
                "packages",
                "related_parents",
                "related_children",
            )
        )

    @admin.display(
        ordering="completion_level",
        description="Completion level",
    )
    def completion_level_pct(self, obj):
        return format_html("{}%", obj.completion_level)

    def response_change(self, request, obj):
        """
        Add a warning message in the response including links to the changelist of impacted
        objects in case of license_expression invalidity on relations.
        """
        response = super().response_change(request, obj)
        errors = validate_expression_on_relations(obj)
        changelist_links = []

        for model_class, ids in errors.items():
            opts = model_class._meta
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
            href = "{}?{}".format(url, urlencode({"id__in": ",".join(str(id_) for id_ in ids)}))
            changelist_links.append(
                CHANGELIST_LINK_TEMPLATE.format(href, len(ids), opts.verbose_name_plural)
            )

        if changelist_links:
            msg = (
                "This license change impacts component usage in a Product or in another "
                "Component.<br>{}".format(", ".join(changelist_links))
            )
            self.message_user(request, format_html(msg), messages.WARNING)

        return response

    def save_related(self, request, form, formsets, change):
        """
        Update the completion_level at the end of the saving process, when
        all the m2m and related are saved too.
        """
        super().save_related(request, form, formsets, change)
        # Update the completion_level once everything including m2m were saved
        form.instance.update_completion_level()

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name

        urls = [
            path(
                "add_to_product/",
                self.admin_site.admin_view(ComponentAddToProductAdminView.as_view()),
                name="{}_{}_add_to_product".format(*info),
            ),
            path(
                "set_policy/",
                self.admin_site.admin_view(SetComponentPolicyView.as_view()),
                name="{}_{}_set_policy".format(*info),
            ),
        ]

        return urls + super().get_urls()

    @admin.display(description=_("Add the selected components to a product"))
    def add_to_product(self, request, queryset):
        """Add the selected Component object(s) to a Product."""
        return self.base_action_with_redirect(request, queryset, "add_to_product")

    @admin.display(description=_("Set usage policy from licenses"))
    def set_policy(self, request, queryset):
        return self.base_action_with_redirect(request, queryset, "set_policy")

    def get_actions(self, request):
        actions = super().get_actions(request)
        is_another_dataspace = DataspaceFilter.parameter_name in request.GET
        has_perm = request.user.has_perm("product_portfolio.add_productcomponent")
        if (is_another_dataspace or not has_perm) and "add_to_product" in actions:
            del actions["add_to_product"]
        if is_another_dataspace and "set_policy" in actions:
            del actions["set_policy"]
        return actions

    def log_deletion(self, request, object, object_repr):
        """
        Add the option to delete associated `Package` instances.
        We use this method rather than `self.delete_model()` since we want to support both
        the delete_view and the `delete_selected` action.
        """
        super().log_deletion(request, object, object_repr)
        if request.POST.get("delete_packages"):
            object.packages.all().delete()

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """
        Catch FormDataOutdated exception that may be raised in get_inline_formsets().
        If an issue with the inline_formsets data is detected, for example an inline relation has
        been deleted from another view since this page was opened, the page if refresh to its
        initial state.
        """
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except FormDataOutdated:
            messages.error(
                request, "Form data outdated or inconsistent. " "The form data has been refreshed."
            )
            return redirect(request.path)

    def get_inline_formsets(self, request, formsets, inline_instances, obj=None):
        """
        Ensure that the QuerySet count and the initial_form_count is equal for each
        inline_formset.
        If not, the FormDataOutdated is raised to be catch in the changeform_view.
        """
        inline_formsets = super().get_inline_formsets(request, formsets, inline_instances, obj)

        for inline_formset in inline_formsets:
            if not inline_formset.formset.is_bound:
                continue

            qs_count = inline_formset.formset.get_queryset().count()
            if qs_count != inline_formset.formset.initial_form_count():
                raise FormDataOutdated

        return inline_formsets

    @staticmethod
    def _get_initial_from_related_instance(instance):
        fields = [
            "name",
            "version",
            "description",
            "release_date",
            "primary_language",
            "project",
            "license_expression",
            "copyright",
            "notice_text",
            "homepage_url",
            "reference_notes",
            "dependencies",
        ]

        initial = {}
        for field in fields:
            value = getattr(instance, field, None)
            if value:
                initial[field] = value

        return initial

    def get_changeform_initial_data(self, request):
        """
        Set initial values from the Package instance when adding a Component
        from a Package changeform view.
        """
        initial = super().get_changeform_initial_data(request)

        instance = get_instance_from_referer(request)
        # Limit the feature to get values from Package instance only.
        if instance and isinstance(instance, Package):
            initial.update(self._get_initial_from_related_instance(instance))

        return initial


@admin.register(Subcomponent, site=dejacode_site)
class SubcomponentAdmin(LicenseExpressionBuilderAdminMixin, DataspacedAdmin):
    list_display = (
        "__str__",
        AsLink("parent"),
        AsLink("child"),
        "license_expression",
        "usage_policy",
        "purpose",
        "is_deployed",
        "is_modified",
        "get_dataspace",
    )
    search_fields = (
        "parent__name",
        "child__name",
    )
    list_filter = (
        ("parent", ParentRelatedLookupListFilter),
        DataspaceFilter,
        ("usage_policy", LimitToDataspaceListFilter),
        "purpose",
        ReportingQueryListFilter,
    )
    raw_id_fields = (
        "parent",
        "child",
    )
    autocomplete_lookup_fields = {"fk": ["parent", "child"]}
    fieldsets = (
        (None, {"fields": ["parent"]}),
        (None, {"fields": SubcomponentChildInline.fieldsets[0][1]["fields"]}),
        get_additional_information_fieldset(),
    )
    form = SubcomponentAdminForm
    mass_update_form = SubcomponentMassUpdateForm
    importer_class = SubcomponentImporter
    activity_log = False
    navigation_buttons = True
    identifier_fields_warning = False
    content_type_scope_fields = ["usage_policy"]
    actions = ["set_policy"]
    actions_to_remove = ["copy_to", "compare_with", "delete_selected"]

    short_description = _(
        "A subcomponent relationship identifies the dependency of a Parent "
        "component on another component."
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "parent",
            "child",
            "usage_policy",
        ).prefetch_related(
            "licenses",
        )

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        urls = [
            path(
                "set_policy/",
                self.admin_site.admin_view(SetSubcomponentPolicyView.as_view()),
                name="{}_{}_set_policy".format(*info),
            ),
        ]
        return urls + super().get_urls()

    @admin.display(description=_("Set usage policy from components"))
    def set_policy(self, request, queryset):
        return self.base_action_with_redirect(request, queryset, "set_policy")


class HideInlinesInPopupMixin:
    """
    Mixin class hides inlines when the page is in a popup.

    When creating new objects through a popup in the admin, it can be
    distracting to see inline forms.

    For example if you are on the ``Component`` change page and get to the
    ``Package`` add page via the popup for adding a package to the component, you will
    see an inline form for adding associated components to the package.
    """

    def get_inline_instances(self, request, obj=None):
        is_popup = any(
            [
                IS_POPUP_VAR in request.GET,
                IS_POPUP_VAR in QueryDict(request.GET.get("_changelist_filters")),
            ]
        )

        if is_popup:
            return []

        return super().get_inline_instances(request, obj)


@admin.register(Package, site=dejacode_site)
class PackageAdmin(
    HideInlinesInPopupMixin,
    AwesompleteAdminMixin,
    ChangelistPopupPermissionMixin,
    LicenseExpressionBuilderAdminMixin,
    DataspacedAdmin,
):
    short_description = (
        "A Package is a specific software code archive, identified by a combination "
        "of its filename and a download URL or a package URL (purl) or both."
    )
    long_description = (
        "Multiple Packages can be associated with a Component, usually to identify the "
        "various source and binary formats available from the component project. "
        "Packages can also be associated directly with one of your own Products."
    )
    list_display = (
        "changelist_view_on_site",
        AsNaturalTime("last_modified_date", short_description="Last modified"),
        "identifier",
        "license_expression",
        AsURL("download_url"),
        "filename",
        AsJoinList("keywords", "<br>", short_description="Keywords"),
        "components_links",
        "cpe",
        "project",
        "usage_policy",
        "sha1",
        "md5",
        "size",
        "release_date",
        "package_url",
        "get_dataspace",
    )
    list_display_links = ("identifier",)
    search_fields = ("filename", "download_url", "project")
    ordering = ("-last_modified_date",)
    list_filter = (
        ("component", HierarchyRelatedLookupListFilter),
        ("licenses", RelatedLookupListFilter),
        DataspaceFilter,
        ReportingQueryListFilter,
        "release_date",
        ("component", IsNullFieldListFilter),
        ("usage_policy", LimitToDataspaceListFilter),
        MissingInFilter,
    )
    inlines = [
        ComponentAssignedPackageInline,
        ExternalReferenceInline,
    ]
    fieldsets = [
        (
            None,
            {
                "fields": (
                    "filename",
                    "download_url",
                    "size",
                    "release_date",
                    "primary_language",
                    "cpe",
                    "description",
                    "keywords",
                    "project",
                    "notes",
                    "usage_policy",
                )
            },
        ),
        (
            "Package URL",
            {
                "fields": (
                    "package_url",
                    "type",
                    "namespace",
                    "name",
                    "version",
                    "qualifiers",
                    "subpath",
                    "inferred_url",
                )
            },
        ),
        ("", {"classes": ("placeholder componentassignedpackage_set-group",), "fields": ()}),
        (
            "Terms",
            {
                "fields": (
                    "license_expression",
                    "declared_license_expression",
                    "other_license_expression",
                    "copyright",
                    "holder",
                    "author",
                    "reference_notes",
                    "notice_text",
                    "dependencies",
                )
            },
        ),
        (
            "URLs",
            {
                "fields": (
                    "homepage_url",
                    "vcs_url",
                    "code_view_url",
                    "bug_tracking_url",
                    "repository_homepage_url",
                    "repository_download_url",
                    "api_data_url",
                )
            },
        ),
        (
            "Checksums",
            {
                "fields": (
                    "sha1",
                    "sha256",
                    "sha512",
                    "md5",
                )
            },
        ),
        (
            "Others",
            {
                "fields": (
                    "parties",
                    "datasource_id",
                    "file_references",
                )
            },
        ),
        (
            "",
            {
                "classes": ("placeholder dje-externalreference-content_type-object_id-group",),
                "fields": (),
            },
        ),
        get_additional_information_fieldset(),
    ]
    readonly_fields = DataspacedAdmin.readonly_fields + (
        "package_url",
        "inferred_url",
    )
    form = PackageAdminForm
    importer_class = PackageImporter
    mass_update_form = PackageMassUpdateForm
    actions = [
        "copy_to",
        "compare_with",
        "check_updates_in_reference",
        "add_to_product",
        "set_policy",
        "collect_data_action",
        "set_purl",
    ]
    navigation_buttons = True
    content_type_scope_fields = ["usage_policy"]
    change_form_template = "admin/component_catalog/package/change_form.html"
    change_list_template = "admin/component_catalog/package/change_list.html"
    view_on_site = DataspacedAdmin.changeform_view_on_site
    awesomplete_data = {"primary_language": PROGRAMMING_LANGUAGES}

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "usage_policy",
            )
            .prefetch_related(
                "componentassignedpackage_set__component",
            )
        )

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name

        urls = [
            path(
                "add_to_product/",
                self.admin_site.admin_view(PackageAddToProductAdminView.as_view()),
                name="{}_{}_add_to_product".format(*info),
            ),
            path(
                "set_policy/",
                self.admin_site.admin_view(SetPackagePolicyView.as_view()),
                name="{}_{}_set_policy".format(*info),
            ),
        ]

        return urls + super().get_urls()

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """
        Add the `show_save_and_collect_data` in the context.
        See also dje/templates/admin/submit_line.html
        """
        extra_context = extra_context or {}
        extra_context.update({"show_save_and_collect_data": True})
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        """
        Trigger the `package_collect_data` task right after the `obj.save()`
        when the "Save and collect data" button is used.
        """
        super().save_model(request, obj, form, change)

        if "_collectdata" in request.POST and obj.download_url:
            self.collect_data(request, obj)

    def collect_data(self, request, obj):
        base_msg = "The SHA1, MD5, and Size fields collection"
        if obj.download_url.startswith(("http://", "https://")):
            transaction.on_commit(lambda: package_collect_data.delay(obj.id))
            if IS_POPUP_VAR not in request.POST:
                msg = f"{base_msg} from {obj.download_url} is in progress."
                self.message_user(request, msg, messages.SUCCESS)
        else:
            scheme = obj.download_url.split("://")[0]
            msg = f'{base_msg} is not supported for the "{scheme}" scheme.'
            self.message_user(request, msg, messages.WARNING)

    @admin.display(description=_("Add the selected packages to a product"))
    def add_to_product(self, request, queryset):
        """Add the selected Package object(s) to a Product."""
        return self.base_action_with_redirect(request, queryset, "add_to_product")

    @admin.display(description=_("Set usage policy from licenses"))
    def set_policy(self, request, queryset):
        return self.base_action_with_redirect(request, queryset, "set_policy")

    @admin.display(description=_('Set Package URL "purl" from the Download URL'))
    def set_purl(self, request, queryset):
        update_count = 0
        packages = queryset.exclude(download_url="")

        for package in packages.iterator(chunk_size=2000):
            try:
                updated = package.update_package_url(
                    user=request.user,
                    # Enforced save() in the admin context as using update() will
                    # trigger transaction exceptions on problematic purls.
                    save=True,
                    overwrite=False,
                    history=True,
                )
            except Exception:
                updated = False

            if updated:
                update_count += 1

        msg = f"{update_count} Package(s) updated with a Package URL."
        self.message_user(request, msg, messages.SUCCESS)

    @admin.display(description=_("Collect data for selected packages"))
    def collect_data_action(self, request, queryset):
        count = queryset.count()
        count_limit = 100
        if count > count_limit:
            error_msg = f"Collect data is limited to {count_limit} objects at once"
            self.message_user(request, error_msg, messages.ERROR)
            return

        update_count = 0
        for package in queryset:
            serialized_data = package.as_json()
            # Not running as async to message user on completion.
            update_fields = package.collect_data(save=False)
            if update_fields:
                package.last_modified_by = request.user
                package.save()
                message = f'Data collected for: {", ".join(update_fields)}.'
                History.log_change(request.user, package, message, serialized_data)
                update_count += 1

        not_updated = count - update_count
        msg = "The SHA1, MD5, and Size fields collection completed:"
        if update_count:
            msg += f"<br>{update_count} package(s) updated"
        if not_updated:
            msg += f"<br>{not_updated} package(s) NOT updated (data already set or URL unavailable)"

        self.message_user(request, format_html(msg), messages.SUCCESS)

    @admin.display(
        ordering="component",
        description="Components",
    )
    def components_links(self, obj):
        """
        Return all the Component instances related to a Package as links to their
        admin edit view.
        """
        component_links = [
            assigned_package.component.get_admin_link(target="_blank")
            for assigned_package in obj.componentassignedpackage_set.all()
        ]
        return format_html("<br>".join(component_links))

    @admin.display(description="Inferred URL")
    def inferred_url(self, obj):
        if inferred_url := obj.inferred_url:
            return urlize_target_blank(inferred_url)
        return ""

    def save_formset(self, request, form, formset, change):
        """
        Update the completion_level on the related Component at the end of the saving process.
        Addition, Edition, and Deletion are supported.
        """
        super().save_formset(request, form, formset, change)
        if formset.model == ComponentAssignedPackage:
            for f in formset.forms:
                # In the Edition case we need to update both old and new instances.
                if "component" in f.changed_data:
                    old_instance = f.cleaned_data.get("id")
                    if old_instance and old_instance.component_id:
                        old_instance.component.update_completion_level()

                if f.instance.component_id:  # Required for "Save as" cases.
                    f.instance.component.update_completion_level()
