#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.utils.translation import gettext_lazy as _

from dje.forms import DataspacedAdminForm
from vulnerabilities.triage.models import TriageRuleset
from vulnerabilities.triage.rules import RULE_REGISTRY


class TriageRulesetForm(DataspacedAdminForm):
    class Meta:
        model = TriageRuleset
        fields = ["name", "description", "precedence", "enabled"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_rule_fields()

    def add_rule_fields(self):
        if not self.instance.pk:
            return
        config = getattr(self.instance, "rules_config", {}) or {}
        for rule_type, handler in RULE_REGISTRY.items():
            rule_config = config.get(rule_type, {})
            self.fields[f"rule_{rule_type}_enabled"] = forms.BooleanField(
                label=f"Enable {handler.label}",
                required=False,
                initial=rule_config.get("is_active", False),
            )
            self.fields[f"rule_{rule_type}_threshold"] = forms.IntegerField(
                label="Threshold",
                required=False,
                min_value=0,
                initial=rule_config.get("threshold"),
                widget=forms.NumberInput(
                    attrs={"placeholder": f"Default: {handler.default_threshold}"}
                ),
                help_text=_(
                    "Minimum violations to trigger the rule. Leave blank to use the default."
                ),
            )
            for param_name, param_desc in handler.parameters_schema.items():
                self.fields[f"rule_{rule_type}_param_{param_name}"] = forms.FloatField(
                    label=param_name.replace("_", " ").title(),
                    required=False,
                    initial=(rule_config.get("parameters") or {}).get(param_name),
                    help_text=param_desc,
                )

    def build_rules_config(self):
        rules_config = {}
        for rule_type, handler in RULE_REGISTRY.items():
            rule_config = {}
            if self.cleaned_data.get(f"rule_{rule_type}_enabled"):
                rule_config["is_active"] = True
            threshold = self.cleaned_data.get(f"rule_{rule_type}_threshold")
            if threshold is not None:
                rule_config["threshold"] = threshold
            parameters = {}
            for param_name in handler.parameters_schema:
                param_value = self.cleaned_data.get(f"rule_{rule_type}_param_{param_name}")
                if param_value is not None:
                    parameters[param_name] = param_value
            if parameters:
                rule_config["parameters"] = parameters
            if rule_config:
                rules_config[rule_type] = rule_config
        return rules_config

    def save(self, commit=True):
        self.instance.rules_config = self.build_rules_config()
        return super().save(commit=commit)
