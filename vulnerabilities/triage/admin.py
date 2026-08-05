#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib import admin

from dje.admin import DataspacedAdmin
from dje.admin import dejacode_site
from vulnerabilities.triage.forms import TriageRulesetForm
from vulnerabilities.triage.models import TriageRuleset
from vulnerabilities.triage.rules import RULE_REGISTRY


@admin.register(TriageRuleset, site=dejacode_site)
class TriageRulesetAdmin(DataspacedAdmin):
    form = TriageRulesetForm
    list_display = ["name", "precedence", "enabled", "get_dataspace"]
    list_filter = DataspacedAdmin.list_filter + ("enabled",)
    search_fields = ["name"]

    def get_form(self, request, obj=None, change=False, **kwargs):
        kwargs["fields"] = ["name", "description", "precedence", "enabled"]
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fieldsets(self, request, obj=None):
        base_fieldsets = [
            (
                None,
                {"fields": ["name", "description", "precedence", "enabled"]},
            ),
        ]
        if not obj:
            return base_fieldsets
        rule_fieldsets = []
        for rule_type, handler in RULE_REGISTRY.items():
            fields = [f"rule_{rule_type}_enabled", f"rule_{rule_type}_threshold"]
            for param_name in handler.parameters_schema:
                fields.append(f"rule_{rule_type}_param_{param_name}")
            rule_fieldsets.append(
                (
                    handler.label,
                    {
                        "fields": fields,
                        "description": handler.description,
                        "classes": ("grp-collapse grp-open",),
                    },
                )
            )
        return base_fieldsets + rule_fieldsets
