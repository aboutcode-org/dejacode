#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from dje.admin import ChangelistPopupPermissionMixin
from dje.admin import ChildRelationshipInline
from dje.admin import DataspacedAdmin
from dje.admin import ExternalReferenceInline
from dje.admin import dejacode_site
from dje.admin import get_additional_information_fieldset
from dje.admin import get_hierarchy_link
from dje.filters import IsNullFieldListFilter
from dje.filters import MissingInFilter
from dje.forms import CleanStartEndDateFormMixin
from dje.list_display import AsLinkList
from dje.list_display import AsNaturalTime
from dje.list_display import AsURL
from organization.importers import OwnerImporter
from organization.models import Owner
from organization.models import Subowner
from reporting.filters import ReportingQueryListFilter


class SubownerForm(CleanStartEndDateFormMixin, forms.ModelForm):
    class Meta:
        model = Subowner
        fields = "__all__"


class SubownerChildInline(ChildRelationshipInline):
    model = Subowner
    form = SubownerForm
    verbose_name_plural = _("Child Owners")


@admin.register(Owner, site=dejacode_site)
class OwnerAdmin(ChangelistPopupPermissionMixin, DataspacedAdmin):
    list_display = (
        get_hierarchy_link,
        "changelist_view_on_site",
        AsNaturalTime("last_modified_date", short_description="Last modified"),
        "name",
        "alias",
        AsURL("homepage_url", short_description="Homepage URL", html_class="word-break"),
        AsURL("contact_info", short_description="Contact information", html_class="word-break"),
        "get_license_links",
        "get_components_links",
        "type_label",
        "get_dataspace",
    )
    list_display_links = ("name",)
    search_fields = ("name", "alias")
    ordering = ("-last_modified_date",)
    fieldsets = (
        (
            "",
            {
                "fields": (
                    "name",
                    "alias",
                    "type",
                    "homepage_url",
                    "contact_info",
                    "notes",
                )
            },
        ),
        (
            "Related objects",
            {
                "fields": (
                    "get_license_links",
                    "get_components_links",
                )
            },
        ),
        ("", {"classes": ("placeholder related_children-group",), "fields": ()}),
        (
            "",
            {
                "classes": ("placeholder dje-externalreference-content_type-object_id-group",),
                "fields": (),
            },
        ),
        get_additional_information_fieldset(pre_fields=("urn_link",)),
    )
    readonly_fields = DataspacedAdmin.readonly_fields + (
        "urn_link",
        "get_license_links",
        "get_components_links",
    )
    list_filter = DataspacedAdmin.list_filter + (
        ReportingQueryListFilter,
        "type",
        ("license", IsNullFieldListFilter),
        ("component", IsNullFieldListFilter),
        MissingInFilter,
    )
    inlines = [
        SubownerChildInline,
        ExternalReferenceInline,
    ]
    importer_class = OwnerImporter
    view_on_site = DataspacedAdmin.changeform_view_on_site
    navigation_buttons = True
    actions = [
        "copy_to",
        "compare_with",
        "check_updates_in_reference",
    ]

    short_description = """An Owner is an entity that is the author, custodian,
    or provider of one or more software objects (licenses, components,
    products)."""

    long_description = """An Owner can be an organization, person, project
    team, or a foundation. An Owner may create and publish software components,
    or it may simply be a standards organization. Any Owner can belong to (be
    the child of) any other Owners."""

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related(
                "license_set",
                "related_parents",
                "related_children",
                "component_set",
            )
        )

    @admin.display(
        ordering="type",
        description="Type",
    )
    def type_label(self, obj):
        return obj.type

    @admin.display(description=_("Licenses"))
    def get_license_links(self, obj):
        return AsLinkList("license_set", "owner", qs_limit=5)(obj)

    @admin.display(description=_("Components"))
    def get_components_links(self, obj):
        return AsLinkList("component_set", "owner", qs_limit=5)(obj)
