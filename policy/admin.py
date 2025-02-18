#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import apps
from django.contrib import admin
from django.http import HttpResponse
from django.template.defaultfilters import linebreaksbr
from django.urls import path
from django.utils.html import format_html
from django.utils.html import urlize
from django.utils.translation import gettext_lazy as _

import yaml

from dje.admin import ColoredIconAdminMixin
from dje.admin import DataspacedAdmin
from dje.admin import DataspacedFKMixin
from dje.admin import dejacode_site
from dje.list_display import AsColored
from policy.forms import AssociatedPolicyForm
from policy.forms import UsagePolicyForm
from policy.models import AssociatedPolicy
from policy.models import UsagePolicy

License = apps.get_model("license_library", "license")


class AssociatedPolicyInline(DataspacedFKMixin, admin.TabularInline):
    model = AssociatedPolicy
    form = AssociatedPolicyForm
    fk_name = "from_policy"
    extra = 0
    max_num = 2
    verbose_name_plural = _("associated policies")


@admin.register(UsagePolicy, site=dejacode_site)
class UsagePolicyAdmin(ColoredIconAdminMixin, DataspacedAdmin):
    list_display = (
        "label",
        "content_type",
        "icon",
        AsColored("color_code"),
        "colored_icon",
        "compliance_alert",
        "associated_policies",
        "associated_product_relation_status",
        "get_dataspace",
    )
    fieldsets = (
        (
            "",
            {
                "fields": (
                    "label",
                    "content_type",
                    "guidelines",
                    "icon",
                    "color_code",
                    "compliance_alert",
                    "associated_product_relation_status",
                    "dataspace",
                    "uuid",
                )
            },
        ),
    )
    form = UsagePolicyForm
    list_filter = DataspacedAdmin.list_filter + ("content_type",)
    change_list_template = "admin/policy/usagepolicy/change_list.html"
    inlines = [AssociatedPolicyInline]

    short_description = (
        "You can define the Usage Policy choices that may apply to various "
        "application object types such as Licenses, Components, "
        "Subcomponent relationships, and Packages."
    )

    long_description = format_html(
        urlize(
            linebreaksbr(
                "For each application object type, you can specify the Usage Policy "
                "label text, icon, and icon color for each relevant policy position "
                "that you need to communicate to your users. "
                "Examples include Recommended, Approved, Restricted, and Prohibited.\n"
                "You can also export your DejaCode License Usage Policy assignments as "
                "a file to use in other applications by clicking the "
                '"Download License Policies as YAML" button. '
                "For an example of how to use this file in an open source tool, see "
                "https://github.com/nexB/scancode-toolkit/wiki/License-Policy-Plugin "
                "for a detailed explanation."
            )
        )
    )

    def associated_policies(self, obj):
        return format_html(
            "<br>".join(
                association.to_policy.str_with_content_type()
                for association in obj.to_policies.all()
            )
        )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "content_type",
                "associated_product_relation_status",
            )
            .prefetch_related(
                "to_policies",
            )
        )

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name

        urls = [
            path(
                "license_dump/",
                self.admin_site.admin_view(self.download_license_dump_view),
                name="{}_{}_license_dump".format(*info),
            ),
        ]

        return urls + super().get_urls()

    def download_license_dump_view(self, request):
        license_queryset = License.objects.scope(request.user.dataspace).filter(
            usage_policy__isnull=False
        )

        licenses = [
            {"license_key": license.key, **license.usage_policy.as_dict()}
            for license in license_queryset
        ]

        dump_kwargs = {
            "default_flow_style": False,
            "default_style": None,
            "canonical": False,
            "allow_unicode": True,
            "encoding": None,
            "indent": 4,
            "width": 90,
            "line_break": "\n",
            "explicit_start": False,
            "explicit_end": False,
        }

        yaml_dump = yaml.safe_dump({"license_policies": licenses}, **dump_kwargs)

        response = HttpResponse(yaml_dump, content_type="application/x-yaml")
        response["Content-Disposition"] = 'attachment; filename="license_policies.yml"'

        return response
