#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib import admin
from django.utils.html import escape
from django.utils.html import mark_safe

from dje.admin import DataspacedAdmin
from dje.admin import dejacode_site
from vulnerabilities.triage.forms import TriageRulesetForm
from vulnerabilities.triage.models import TriageRuleset
from vulnerabilities.triage.rules import RULE_REGISTRY


@admin.register(TriageRuleset, site=dejacode_site)
class TriageRulesetAdmin(DataspacedAdmin):
    short_description = (
        "A Triage Ruleset is a named set of detection rules that, when their conditions"
        " are met for a product, recommends a specific remediation action."
    )

    long_description = (
        "Each ruleset combines one or more rules (such as critical vulnerability detection"
        " or exploited vulnerability detection) with a single action to recommend"
        " (upgrade, apply patch, notify, etc.). Multiple rulesets can be assigned to a"
        " product; when conditions overlap, the ruleset with the highest precedence takes"
        " effect."
    )

    form = TriageRulesetForm
    list_display = ["name", "get_enabled_rules", "precedence", "enabled", "get_dataspace"]
    list_filter = DataspacedAdmin.list_filter + ("enabled",)
    search_fields = ["name"]

    @admin.display(description="Enabled rules")
    def get_enabled_rules(self, obj):
        enabled = [
            RULE_REGISTRY[rule_type].label
            for rule_type, config in obj.rules_config.items()
            if rule_type in RULE_REGISTRY and config.get("is_active")
        ]
        if not enabled:
            return ""
        return mark_safe("<br>".join(escape(label) for label in enabled))

    def get_changes_details(self, form):
        model_field_names = {field.name for field in TriageRuleset._meta.get_fields()}
        form.__dict__["changed_data"] = [f for f in form.changed_data if f in model_field_names]
        return super().get_changes_details(form)

    def get_form(self, request, obj=None, change=False, **kwargs):
        kwargs["fields"] = ["name", "description", "action", "precedence", "enabled"]
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fieldsets(self, request, obj=None):
        base_fieldsets = [
            (
                None,
                {"fields": ["name", "description", "action", "precedence", "enabled"]},
            ),
        ]
        if not obj:
            return base_fieldsets
        rule_fieldsets = [
            (
                handler.label,
                {
                    "fields": [f"rule_{rule_type}_enabled"],
                    "description": handler.description,
                    "classes": ("grp-collapse grp-open",),
                },
            )
            for rule_type, handler in RULE_REGISTRY.items()
        ]
        return base_fieldsets + rule_fieldsets
