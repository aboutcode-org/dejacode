#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json

from django import forms
from django.contrib import admin
from django.contrib.admin import TabularInline
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models.functions import Length
from django.forms.widgets import Select
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.urls import path
from django.urls import reverse
from django.utils.html import escape
from django.utils.html import format_html
from django.utils.html import format_html_join
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from component_catalog.admin import LicenseExpressionBuilderAdminMixin
from dje.admin import ChangelistPopupPermissionMixin
from dje.admin import DataspacedAdmin
from dje.admin import DataspacedFKMixin
from dje.admin import ExternalReferenceInline
from dje.admin import dejacode_site
from dje.admin import get_additional_information_fieldset
from dje.client_data import add_client_data
from dje.filters import DataspaceFilter
from dje.filters import LevelFieldListFilter
from dje.filters import LimitToDataspaceListFilter
from dje.filters import MissingInFilter
from dje.list_display import AsLink
from dje.list_display import AsNaturalTime
from dje.templatetags.dje_tags import as_icon_admin
from dje.utils import pop_from_get_request
from license_library.forms import LicenseAdminForm
from license_library.forms import LicenseChoiceAdminForm
from license_library.forms import LicenseMassUpdateForm
from license_library.models import License
from license_library.models import LicenseAnnotation
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseCategory
from license_library.models import LicenseChoice
from license_library.models import LicenseProfile
from license_library.models import LicenseProfileAssignedTag
from license_library.models import LicenseStatus
from license_library.models import LicenseStyle
from license_library.models import LicenseTag
from license_library.models import LicenseTagGroup
from license_library.models import LicenseTagGroupAssignedTag
from license_library.views import LicenseProfileDetailView
from license_library.views import LicenseStyleDetailView
from reporting.filters import ReportingQueryListFilter


def check_object_pk_exists(request, object_id, model_admin):
    """
    Make sure the object exists before starting processing on it,
    as the original 404 check is only done further in the "super".
    This code is similar to the one at the begin of ModelAdmin.change_view()
    """
    obj = model_admin.get_object(request, unquote(object_id))
    if obj is None:
        model = model_admin.model
        raise Http404(
            f"{model._meta.verbose_name} object with "
            f"primary key {escape(object_id)} does not exist."
        )


class LicenseAssignedTagInline(TabularInline):
    model = LicenseAssignedTag
    fields = ("license_tag", "value", "text", "guidance")
    readonly_fields = ("text", "guidance")
    can_delete = False
    extra = 0

    def text(self, instance):
        if instance:
            return instance.license_tag.text

    def guidance(self, instance):
        if instance:
            return instance.license_tag.guidance

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        if db_field.name == "license_tag":
            # This is only called in the case of an ADDITION, as in CHANGE the
            # FK Field is readonly.
            kwargs["queryset"] = LicenseTag.objects.scope(request.user.dataspace).order_by(
                "licensetaggroup__seq", "licensetaggroupassignedtag__seq"
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        """Force the license_tag field as readonly on CHANGE."""
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj:
            return readonly_fields + ("license_tag",)
        return readonly_fields

    def get_formset(self, request, obj=None, **kwargs):
        dataspace = request.user.dataspace
        if obj:
            for tag in LicenseTag.objects.scope(obj.dataspace):
                self.model.objects.get_or_create(
                    license=obj,
                    license_tag=tag,
                    dataspace=obj.dataspace,
                )
        else:
            kwargs["extra"] = LicenseTag.objects.scope(dataspace).count()

        return super().get_formset(request, obj, **kwargs)


@admin.register(License, site=dejacode_site)
class LicenseAdmin(ChangelistPopupPermissionMixin, DataspacedAdmin):
    @admin.display(description=_(""))
    def annotations_link(self, obj):
        annotation_url = reverse(
            "admin:license_library_license_annotation", args=[obj.pk])

        # See DataspacedChangeList.get_results
        preserved_filters = obj._preserved_filters
        if preserved_filters:
            annotation_url = add_preserved_filters(
                {"preserved_filters": preserved_filters,
                    "opts": obj._meta}, annotation_url
            )

        return format_html('<a href="{}">Annotations</a>', annotation_url)

    annotations_link.short_description = "Annotations"

    @admin.display(description=_(""))
    def get_spdx_link(self, obj):
        spdx_url = obj.spdx_url
        if spdx_url:
            return obj.get_html_link(spdx_url, value=spdx_url, target="_blank")
        return ""

    get_spdx_link.short_description = "SPDX URL"

    list_display = (
        "changelist_view_on_site",
        AsNaturalTime("last_modified_date", short_description="Last modified"),
        "key",
        "name",
        "short_name",
        AsLink("owner"),
        "category",
        "license_style",
        "license_profile",
        "license_status",
        "reviewed",
        "is_active",
        "usage_policy",
        "is_component_license",
        "is_exception",
        "curation_level",
        "popularity",
        "spdx_license_key",
        "annotations_link",
        "get_dataspace",
    )
    list_display_links = ("key",)
    list_select_related = True
    search_fields = ("key", "name", "short_name", "keywords", "owner__name")
    ordering = ("-last_modified_date",)
    # Custom list as we don't want to inherit HistoryCreatedActionTimeListFilter
    # and HistoryModifiedActionTimeListFilter from super().
    # We are using the history fields from the Model.
    list_filter = (
        DataspaceFilter,
        ReportingQueryListFilter,
        "reviewed",
        "is_active",
        "is_component_license",
        "is_exception",
        ("curation_level", LevelFieldListFilter),
        ("category", LimitToDataspaceListFilter),
        ("license_style", LimitToDataspaceListFilter),
        ("license_profile", LimitToDataspaceListFilter),
        ("license_status", LimitToDataspaceListFilter),
        ("usage_policy", LimitToDataspaceListFilter),
        MissingInFilter,
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "key",
                    "reviewed",
                    "name",
                    "short_name",
                    "owner",
                    "keywords",
                    "homepage_url",
                    "full_text",
                    "standard_notice",
                    "publication_year",
                    "language",
                )
            },
        ),
        (
            "Configuration",
            {
                "classes": ("grp-collapse grp-open",),
                "fields": (
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
                ),
            },
        ),
        (
            "Urls",
            {
                "classes": ("grp-collapse grp-closed",),
                "fields": (
                    "faq_url",
                    "osi_url",
                    "text_urls",
                    "other_urls",
                ),
            },
        ),
        (
            "SPDX",
            {
                "classes": ("grp-collapse grp-closed",),
                "fields": (
                    "spdx_license_key",
                    "get_spdx_link",
                ),
            },
        ),
        (
            "",
            {
                "classes": ("placeholder dje-externalreference-content_type-object_id-group",),
                "fields": (),
            },
        ),
        get_additional_information_fieldset(pre_fields=("urn_link",)),
    )
    raw_id_fields = ("owner",)
    autocomplete_lookup_fields = {"fk": ["owner"]}
    readonly_fields = DataspacedAdmin.readonly_fields + \
        ("urn_link", "get_spdx_link")
    form = LicenseAdminForm
    inlines = [
        LicenseAssignedTagInline,
        ExternalReferenceInline,
    ]
    change_form_template = "admin/license_library/license/change_form.html"
    navigation_buttons = True
    mass_update_form = LicenseMassUpdateForm
    view_on_site = DataspacedAdmin.changeform_view_on_site
    content_type_scope_fields = ["usage_policy"]
    actions = [
        "copy_to",
        "compare_with",
        "check_updates_in_reference",
    ]

    short_description = (
        "Licenses include both the facts of a license as provided by its "
        "owner, as well as your organization's interpretation and policy "
        "regarding that license."
    )

    long_description = (
        "Each License has an Owner that identifies the origin (or current "
        "custodian) of the license specification. Each License is also "
        "uniquely identified by a Key (a short abbreviation) and a Name (a "
        "concise title). The license facts include data taken directly from "
        "the published license."
        'The "Configuration" section contains classification and policy as '
        "defined by your organization. When available, the SPDX section "
        "contains related information provided by the SPDX license standards "
        "organization (www.spdx.org)."
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "license_profile",
            "license_style",
            "category",
            "owner",
            "license_status",
            "usage_policy",
        )

    def get_readonly_fields(self, request, obj=None):
        """Make License.key readonly on edit."""
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj:
            readonly_fields += ("key",)
        return readonly_fields

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name

        urls = [
            path(
                "<path:object_id>/annotations/",
                self.admin_site.admin_view(self.license_annotation_view),
                name="{}_{}_annotation".format(*info),
            ),
            path(
                "licenseprofile/<pk>/",
                self.admin_site.admin_view(LicenseProfileDetailView.as_view()),
                name="{}_{}_licenseprofile_detail".format(*info),
            ),
            path(
                "licensestyle/<pk>/",
                self.admin_site.admin_view(LicenseStyleDetailView.as_view()),
                name="{}_{}_licensestyle_detail".format(*info),
            ),
        ]

        return urls + super().get_urls()

    def set_assigned_tags_from_license_profile(self, request, obj):
        obj.set_assigned_tags_from_license_profile()
        msg = format_lazy(
            "The system has updated this License with the License Tag settings of the "
            '{license_profile} "{obj.license_profile.name}".',
            license_profile=_("License Profile"),
            obj=obj,
        )
        self.message_user(request, msg)

    def save_model(self, request, obj, form, change):
        if change:
            obj_before_save = License.objects.get(id=obj.id)
            super().save_model(request, obj, form, change)
            # If a LicenseProfile is set or changed, apply the values of the
            # this Profile to the license assigned tags.
            if obj.license_profile and obj.license_profile != obj_before_save.license_profile:
                self.set_assigned_tags_from_license_profile(request, obj)
        else:
            # In the ADDITION case, the obj need to be saved first,
            # before setting the LicenseAssignedTag values
            # Assigning the tags is done in self.response_add, after the obj
            # and the m2m have been saved
            super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        if obj.license_profile:
            self.set_assigned_tags_from_license_profile(request, obj)
        return super().response_add(request, obj, post_url_continue)

    def _get_extra_context_tags(self, request, object_id=None):
        if object_id:  # In CHANGE cases we use the object dataspace
            obj = self.get_object(request, unquote(object_id))
            dataspace = obj.dataspace
        else:
            dataspace = request.user.dataspace

        queryset = (
            LicenseTag.objects.scope(dataspace)
            .prefetch_related("licensetaggroup_set")
            .order_by(
                "licensetaggroup__seq",
                "licensetaggroupassignedtag__seq",
            )
        )

        # Building a dictionary based on the Tag/Group relation
        group_dict = {}
        no_group = []

        for tag in queryset:
            tag_group_set = tag.licensetaggroup_set.all()
            if tag_group_set:
                group_name = tag_group_set.first().name
                group_seq = tag_group_set.first().seq
                if group_seq not in group_dict:
                    group_dict[group_seq] = (group_name, [tag.label])
                else:
                    group_dict[group_seq][1].append(tag.label)
            else:
                no_group.append(tag.label)
        # If the tag is not assigned in a LicenseGroup, only once, after the
        # loop. Using the length of the groups to make sure the "No Group" the
        # last displayed Group
        if no_group:
            group_dict[len(group_dict) + 1] = ("(No Group)", no_group)

        extra_context = {"tags": queryset, "group_dict": group_dict}
        return extra_context

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self.has_change_permission(request):
            raise PermissionDenied

        # Making sure the object exists before processing the extra context
        check_object_pk_exists(request, object_id, self)
        extra_context = self._get_extra_context_tags(request, object_id)

        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = self._get_extra_context_tags(request)
        return super().add_view(request, form_url, extra_context)

    def license_annotation_view(self, request, object_id):
        """Admin view for the LicenseAnnotation Model."""
        obj = get_object_or_404(License, pk=unquote(
            object_id), dataspace=request.user.dataspace)
        tagset = obj.get_tagset(include_unknown=True, include_no_group=True)

        template = "admin/license_library/license/annotation.html"
        context = {
            "object": obj,
            "tag_labels": json.dumps(list(obj.get_tag_labels())),
            "tagset": tagset,
            "opts": self.model._meta,
            "preserved_filters": self.get_preserved_filters(request),
        }

        return render(request, template, context)


class LicenseTagHolderBaseAdmin(DataspacedAdmin):
    """
    The purpose of this class is to be extended by LicenseProfileAdmin and
    LicenseTagGroupAdmin. It's used to add a LicenseTag queryset in the context
    of the add and changes views, to display special data (added through
    javascript) about tags in the page like text and guidance information.
    """

    change_form_template = "admin/license_library/tag_holder/change_form.html"

    def _get_tags_data(self, request, object_id=None):
        dataspace = request.user.dataspace
        # In CHANGE cases, use the obj owner organization
        if object_id:
            obj = self.get_object(request, unquote(object_id))
            dataspace = obj.dataspace

        tags_dict = {}
        for tag in LicenseTag.objects.scope(dataspace):
            tags_dict[str(tag.id)] = {"text": str(
                tag.text), "guidance": str(tag.guidance)}

        return tags_dict

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self.has_change_permission(request):
            raise PermissionDenied

        # Making sure the object exists before processing the extra context
        check_object_pk_exists(request, object_id, self)
        add_client_data(
            request, tags_dict=self._get_tags_data(request, object_id))

        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        add_client_data(request, tags_dict=self._get_tags_data(request))

        return super().add_view(request, form_url, extra_context)


class LicenseProfileAssignedTagInline(DataspacedFKMixin, TabularInline):
    model = LicenseProfileAssignedTag
    can_delete = True
    extra = 0
    fieldsets = (
        ("", {"fields": ("license_tag", "value", "text", "guidance")}),)
    # Using a 'Select' rather then a 'Checkbox' to render the 'value' field
    formfield_overrides = {
        models.BooleanField: {
            # Warning: Requires empty value for 'No', anything else is evaluate to True
            "widget": Select(choices=(("", "No"), (True, "Yes"))),
        }
    }
    readonly_fields = ("text", "guidance")

    def text(self, instance):
        if instance:
            return instance.license_tag.text

    def guidance(self, instance):
        if instance:
            return instance.license_tag.guidance

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("license_profile", "license_tag")


@admin.register(LicenseProfile, site=dejacode_site)
class LicenseProfileAdmin(LicenseTagHolderBaseAdmin):
    list_display = (
        "name",
        "get_assigned_tags_html",
        "examples",
        "get_dataspace",
    )
    fieldsets = (
        ("", {"fields": ("name",)}),
        ("", {"fields": ("examples", "notes", "dataspace", "uuid")}),
    )
    search_fields = ("name",)
    list_filter = DataspacedAdmin.list_filter + (ReportingQueryListFilter,)
    inlines = (LicenseProfileAssignedTagInline,)

    short_description = format_lazy(
        _("License Profile"),
        ': a selection \
    of license tags and their values, identified by a name, in \
    order to provide a convenient way to assign a set of tag values to a \
    license.\
    A "Tag" identifies a frequently encountered obligation, restriction, \
    or other notable characteristic of license terms. Note that \
    individual tag value assignments may vary by license.',
    )

    long_description = format_lazy(
        "An organization should review the ",
        _("License Profile"),
        " supplied as reference data with the application \
        to determine if any additions or modifications are needed to meet the \
        organization's business requirements. For example, if you always \
        want to review a specific Tag assignment on each License, remove \
        the Tag from the ",
        _("License Profile"),
        " so that its initial value \
        will be Unknown.",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("licenseprofileassignedtag_set__license_tag")


@admin.register(LicenseCategory, site=dejacode_site)
class LicenseCategoryAdmin(DataspacedAdmin):
    list_display = ("label", "text", "license_type", "get_dataspace")
    search_fields = ("label",)

    short_description = """A License Category, identified by a label,
    provides a major grouping for licenses, generally describing the
    relationship between the licensor and licensee."""

    long_description = """An organization should review the License
    Categories provided with the application to determine if the
    descriptions require refinement, or if new Categories need to be
    defined, in order to meet the organization's needs. License Category
    examples include Commercial, Copyleft, Copyleft Limited, Copyleft v3,
    Liberal, Proprietary, and Other."""


@admin.register(LicenseStyle, site=dejacode_site)
class LicenseStyleAdmin(DataspacedAdmin):
    list_display = ("name", "notes", "get_dataspace")
    fieldsets = (
        ("", {"fields": ("name",)}),
        ("", {"fields": ("notes", "dataspace", "uuid")}),
    )
    search_fields = ("name",)

    short_description = """A License Style, identified by a License
    Style Name, describes miscellaneous characteristics of a license that
    are useful for analysis. Common License Styles include Apache 1.1, BSD,
    MIT, and X11."""

    long_description = """An organization should review the License
    Styles supplied with the application to determine if any additions are
    needed, or if the descriptions are pertinent to its business
    requirements. An organization can modify the License Styles supplied
    with the application, and it can also create new License Styles. It is
    also OK to delete License Styles, although it is best to make sure that
    they are not being used before deletion."""


@admin.register(LicenseStatus, site=dejacode_site)
class LicenseStatusAdmin(DataspacedAdmin):
    list_display = ("code", "text", "get_dataspace")
    search_fields = ("code", "text")

    short_description = format_lazy(
        "A License Status is defined by an \
    Organization to assign to a License when it is Configured for that \
    Organization's ",
        _("License Library"),
        " .",
    )

    long_description = """An Organization can use the License Status
    to communicate the current stage of the license configuration review
    process."""


@admin.register(LicenseTag, site=dejacode_site)
class LicenseTagAdmin(DataspacedAdmin):
    short_description = (
        "A License Tag identifies a specific characteristic of a License that "
        "can be expressed as a Yes/No value."
    )
    long_description = (
        'Examples include "Copy of license text required in source" and '
        '"Source code redistribution required". An owner organization can '
        "define the specific license tags that it wants to track to meet "
        "its business requirements."
    )
    list_display = (
        "label",
        "text",
        "default_value",
        "show_in_license_list_view",
        "attribution_required",
        "redistribution_required",
        "change_tracking_required",
        "get_dataspace",
    )
    list_filter = DataspacedAdmin.list_filter + (
        ReportingQueryListFilter,
        "default_value",
        "show_in_license_list_view",
        MissingInFilter,
    )
    search_fields = (
        "label",
        "text",
    )
    change_form_template = "admin/license_library/license_tag/change_form.html"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """
        Add a list of examples based on LicenseAnnotation related to the
        Licenses associated with the given LicenseTag instance in the context,
        to be displayed in the custom change_form.html template.
        """
        model = self.model

        try:
            instance = model.objects.get(id=object_id)
        except model.DoesNotExist:
            raise Http404(
                f"{model._meta.verbose_name} object with "
                f"primary key {escape(object_id)} does not exist."
            )

        extra_context = extra_context or {}
        example_limit = 10

        # Order by the `LicenseAnnotation.quote` length,
        # filtering out the unknown values of the assigned_tags.
        annotation_qs = (
            LicenseAnnotation.objects.filter(
                assigned_tag__license_tag=instance,
                assigned_tag__value__isnull=False,
            )
            .annotate(quote_length=Length("quote"))
            .select_related(
                "assigned_tag",
                "license",
            )
            .order_by("-quote_length")[:example_limit]
        )

        extra_context["examples"] = [
            (
                annotation.license.get_admin_link(target="_blank"),
                as_icon_admin(annotation.assigned_tag.value),
                annotation.quote,
            )
            for annotation in annotation_qs
        ]

        return super().change_view(request, object_id, form_url, extra_context)


class LicenseTagGroupAssignedTagInline(DataspacedFKMixin, TabularInline):
    model = LicenseTagGroupAssignedTag
    can_delete = True
    extra = 0
    fieldsets = (
        (
            "",
            {
                "fields": (
                    "license_tag",  # That field triggers 1 extra query per row
                    "text",
                    "guidance",
                    "seq",
                )
            },
        ),
    )
    readonly_fields = ("text", "guidance")
    sortable_field_name = "seq"
    formfield_overrides = {
        models.PositiveSmallIntegerField: {"widget": forms.HiddenInput},
    }

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "license_tag_group",
            "license_tag",
        )

    def text(self, instance):
        return instance.license_tag.text

    def guidance(self, instance):
        return instance.license_tag.guidance


@admin.register(LicenseTagGroup, site=dejacode_site)
class LicenseTagGroupAdmin(LicenseTagHolderBaseAdmin):
    list_display = ("name", "get_assigned_tags_label",
                    "notes", "seq", "get_dataspace")
    search_fields = ("name",)
    inlines = (LicenseTagGroupAssignedTagInline,)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("licensetaggroupassignedtag_set__license_tag")

    @admin.display(description=_(""))
    def get_assigned_tags_label(self, obj):
        labels = [
            tag.license_tag.label for tag in obj.licensetaggroupassignedtag_set.all()]
        label_list = format_html_join(
            "", "<li>{}</li>", ((label,) for label in labels))
        return format_html("<ul>{}</ul>", label_list)

    get_assigned_tags_label.short_description = "Assigned tags"

    short_description = """A License Tag Group is a logical grouping
    of License Tags from a functional point of view."""

    long_description = """A License Tag Group is a logical grouping
    of License Tags, by dataspace, to support administrator and
    user comprehension of License Tag Assignments from a functional point
    of view, including the order in which the License Tag Groups should be
    presented in the application user interface."""


@admin.register(LicenseChoice, site=dejacode_site)
class LicenseChoiceAdmin(LicenseExpressionBuilderAdminMixin, DataspacedAdmin):
    short_description = (
        "A license choice expresses your interpretation of a license that is actually a "
        "complex choice of possible licenses, and allows you to express the choice(s) "
        "that your users are allowed to make when asserting a component license on a product."
    )
    long_description = (
        "You can use the sequence value to indicate your license choice preference policies "
        "for a particular license expression, using zero (0) as the first and preferred choice, "
        "followed by other sequences that define acceptable choices."
    )
    list_display = ("from_expression", "to_expression", "seq", "notes")
    list_editable = ("seq",)
    search_fields = ("from_expression", "to_expression", "seq", "notes")
    list_filter = DataspacedAdmin.list_filter + (ReportingQueryListFilter,)
    form = LicenseChoiceAdminForm
    change_list_template = "admin/license_library/licensechoice/change_list.html"
    expression_field_name = "expression"  # Expression builder
    activity_log = False
    email_notification_on = ()

    def changelist_view(self, request, extra_context=None):
        """Add an input to test license choices from a given expression."""
        extra_context = extra_context or {}

        is_user_dataspace = DataspaceFilter.parameter_name not in request.GET
        extra_context.update({"is_user_dataspace": is_user_dataspace})

        test_expression = pop_from_get_request(request, "test_expression")
        if test_expression and is_user_dataspace:
            dataspace = request.user.dataspace
            get_choices_expression = self.model.objects.get_choices_expression

            extra_context.update(
                {
                    "test_expression": test_expression,
                    "to_expression": get_choices_expression(test_expression, dataspace),
                }
            )

        return super().changelist_view(request, extra_context)
