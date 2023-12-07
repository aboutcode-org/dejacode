#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib import admin
from django.contrib.admin import StackedInline
from django.contrib.admin import TabularInline
from django.utils.translation import gettext_lazy as _

from component_catalog.forms import SubcomponentAdminForm
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import Subcomponent
from dje.admin import ChildRelationshipInline
from dje.admin import DataspacedFKMixin
from dje.admin import ProtectedFieldsMixin
from dje.templatetags.dje_tags import urlize_target_blank


class SubcomponentChildInline(
    StackedInline,
    ProtectedFieldsMixin,
    ChildRelationshipInline,
):
    model = Subcomponent
    form = SubcomponentAdminForm
    verbose_name = ""
    verbose_name_plural = _("Child Components")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "child",
                    "license_expression",
                    "reference_notes",
                    "usage_policy",
                    "purpose",
                    "notes",
                    "is_deployed",
                    "is_modified",
                    "extra_attribution_text",
                    "package_paths",
                )
            },
        ),
    )
    raw_id_fields = ("child",)
    autocomplete_lookup_fields = {"fk": ["child"]}
    content_type_scope_fields = ["usage_policy"]


class ComponentAssignedPackageInline(DataspacedFKMixin, TabularInline):
    model = ComponentAssignedPackage
    extra = 0
    classes = ("grp-collapse grp-open",)
    raw_id_fields = ("component",)
    autocomplete_lookup_fields = {"fk": ["component"]}
    verbose_name_plural = _("Associated Components")
    verbose_name = _("Component")


class ComponentAssignedPackageInline2(ComponentAssignedPackageInline):
    raw_id_fields = ("package",)
    autocomplete_lookup_fields = {"fk": ["package"]}
    verbose_name_plural = _("Associated Packages")
    verbose_name = _("Package")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "package",
                    "get_download_url",
                ),
            },
        ),
    )
    readonly_fields = ("get_download_url",)

    @admin.display(description="Download URL")
    def get_download_url(self, obj):
        return urlize_target_blank(obj.package.download_url)
