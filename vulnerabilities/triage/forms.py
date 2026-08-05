#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms

from dje.forms import DataspacedAdminForm
from vulnerabilities.triage.models import TriageRuleset
from vulnerabilities.triage.rules import RULE_REGISTRY


class TriageRulesetForm(DataspacedAdminForm):
    class Meta:
        model = TriageRuleset
        fields = ["name", "description", "action", "precedence", "enabled"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_rule_fields()

    def add_rule_fields(self):
        config = getattr(self.instance, "rules_config", {}) or {}
        for rule_type, handler in RULE_REGISTRY.items():
            rule_config = config.get(rule_type, {})
            self.fields[f"rule_{rule_type}_enabled"] = forms.BooleanField(
                label=f"Enable {handler.label}",
                required=False,
                initial=rule_config.get("is_active", False),
            )

    def build_rules_config(self):
        rules_config = {}
        for rule_type in RULE_REGISTRY:
            if self.cleaned_data.get(f"rule_{rule_type}_enabled"):
                rules_config[rule_type] = {"is_active": True}
        return rules_config

    def save(self, commit=True):
        self.instance.rules_config = self.build_rules_config()
        return super().save(commit=commit)
