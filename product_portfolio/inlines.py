#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from dje.admin import DataspacedFKMixin
from dje.admin import ProtectedFieldsMixin
from product_portfolio.models import CodebaseResourceUsage
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductPackage


class ProductComponentInline(
    DataspacedFKMixin,
    ProtectedFieldsMixin,
    admin.TabularInline,
):
    model = ProductComponent
    extra = 0
    can_delete = False
    classes = ("grp-collapse grp-closed",)
    readonly_fields = [
        "get_change_link",
        "license_expression",
        "review_status",
        "purpose",
        "notes",
        "is_deployed",
        "is_modified",
        "extra_attribution_text",
        "package_paths",
        "feature",
        "issue_ref",
    ]
    fieldsets = ((None, {"fields": readonly_fields}),)

    def has_add_permission(self, request, obj):
        return False

    @admin.display(description=_("Component"))
    def get_change_link(self, obj):
        if not obj.product.is_active:
            return f"{obj}"

        opts = self.model._meta
        viewname = f"admin:{opts.app_label}_{opts.model_name}_change"
        changeform_url = reverse(viewname, args=[obj.pk])
        return format_html('<a href="{}" target="_blank">{}</a>', changeform_url, obj)


class ProductPackageInline(
    DataspacedFKMixin,
    ProtectedFieldsMixin,
    admin.TabularInline,
):
    model = ProductPackage
    extra = 0
    can_delete = False
    classes = ("grp-collapse grp-closed",)
    readonly_fields = [
        "get_change_link",
        "license_expression",
        "review_status",
        "purpose",
        "notes",
        "is_deployed",
        "is_modified",
        "extra_attribution_text",
        "package_paths",
        "feature",
        "issue_ref",
    ]
    fieldsets = ((None, {"fields": readonly_fields}),)

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description=_("Package"))
    def get_change_link(self, obj):
        if not obj.product.is_active:
            return f"{obj}"

        opts = self.model._meta
        viewname = f"admin:{opts.app_label}_{opts.model_name}_change"
        changeform_url = reverse(viewname, args=[obj.pk])
        return format_html('<a href="{}" target="_blank">{}</a>', changeform_url, obj)


class CodebaseResourceUsageDeployedFromInline(DataspacedFKMixin, admin.TabularInline):
    verbose_name_plural = "Deployed from"
    model = CodebaseResourceUsage
    fk_name = "deployed_to"
    readonly_fields = ["deployed_from"]
    extra = 0
    can_delete = False
    classes = ("hide-thead",)

    def has_add_permission(self, request, obj=None):
        return False


class CodebaseResourceUsageDeployedToInline(DataspacedFKMixin, admin.TabularInline):
    verbose_name = "Deployed to"
    verbose_name_plural = "Deployed to"
    model = CodebaseResourceUsage
    fk_name = "deployed_from"
    raw_id_fields = ("deployed_to",)
    autocomplete_lookup_fields = {"fk": ["deployed_to"]}
    extra = 0
    classes = ("grp-collapse grp-open hide-thead",)
