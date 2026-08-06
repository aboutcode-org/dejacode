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
from vulnerabilities.triage.models import TriageDecision
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
    list_display = [
        "name",
        "action",
        "precedence",
        "get_enabled_rules",
        "description",
        "enabled",
        "get_dataspace",
    ]
    list_filter = DataspacedAdmin.list_filter + ("enabled",)
    search_fields = ["name"]

    @admin.display(description="Enabled rules")
    def get_enabled_rules(self, obj):
        lines = []
        for rule_type, config in obj.rules_config.items():
            if rule_type not in RULE_REGISTRY or not config.get("is_active"):
                continue
            handler = RULE_REGISTRY[rule_type]
            params = {key: value for key, value in config.items() if key != "is_active"}
            if params:
                param_str = ", ".join(f"{key}: {value}" for key, value in params.items())
                label = f"{handler.label} ({param_str})"
            else:
                label = handler.label
            lines.append(escape(label))
        if not lines:
            return ""
        return mark_safe("<br>".join(lines))

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
        rule_fieldsets = []
        for rule_type, handler in RULE_REGISTRY.items():
            fields = [f"rule_{rule_type}_enabled"]
            for param_name in handler.parameters_schema:
                fields.append(f"rule_{rule_type}_{param_name}")
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


@admin.register(TriageDecision, site=dejacode_site)
class TriageDecisionAdmin(DataspacedAdmin):
    short_description = (
        "A Triage Decision records the result of evaluating a ruleset against a product."
    )
    long_description = (
        "Triage Decisions are created automatically by the evaluation engine. Each record"
        " stores the recommended action, the rules that matched, and the dates of first"
        " detection and last check. These records are read-only in the admin."
    )

    list_display = [
        "product",
        "ruleset",
        "action",
        "get_matched_rules",
        "detected_date",
        "last_checked",
        "get_dataspace",
    ]
    list_filter = DataspacedAdmin.list_filter + ("action", "ruleset")
    search_fields = ["product__name", "ruleset__name"]
    readonly_fields = DataspacedAdmin.readonly_fields + (
        "product",
        "ruleset",
        "action",
        "matched_rules",
        "detected_date",
        "last_checked",
    )

    @admin.display(description="Matched rules")
    def get_matched_rules(self, obj):
        labels = [
            RULE_REGISTRY[rule_type].label
            for rule_type in obj.matched_rules
            if rule_type in RULE_REGISTRY
        ]
        if not labels:
            return ""
        return mark_safe("<br>".join(escape(label) for label in labels))

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .product_secured(request.user, "view_product")
            .select_related("product", "ruleset")
        )

    def has_add_permission(self, request):
        return False
