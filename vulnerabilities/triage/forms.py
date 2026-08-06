#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms

from dje.forms import DataspacedAdminForm
from vulnerabilities.triage.models import TriageAction
from vulnerabilities.triage.models import TriageRuleset
from vulnerabilities.triage.rules import RULE_REGISTRY


class TriageRulesetForm(DataspacedAdminForm):
    action = forms.ChoiceField(
        choices=[("", "---------")] + list(TriageAction.choices),
        required=False,
    )

    class Meta:
        model = TriageRuleset
        fields = ["name", "description", "action", "precedence", "enabled"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_rule_fields()

    def build_parameter_field(self, param_name, param_spec, initial_value):
        label = param_name.replace("_", " ").capitalize()
        help_text = param_spec["help_text"]
        default = param_spec["default"]
        if isinstance(default, int):
            return forms.IntegerField(
                label=label,
                help_text=help_text,
                required=False,
                initial=initial_value,
                min_value=1,
            )
        return forms.DecimalField(
            label=label,
            help_text=help_text,
            required=False,
            initial=initial_value,
            min_value=0,
            max_value=10,
            decimal_places=1,
        )

    def add_rule_fields(self):
        config = getattr(self.instance, "rules_config", {}) or {}
        for rule_type, handler in RULE_REGISTRY.items():
            rule_config = config.get(rule_type, {})
            enable_key = f"rule_{rule_type}_enabled"
            is_active = rule_config.get("is_active", False)
            self.fields[enable_key] = forms.BooleanField(
                label=f"Enable {handler.label}",
                required=False,
                initial=is_active,
            )
            self.initial[enable_key] = is_active
            for param_name, param_spec in handler.parameters_schema.items():
                default = param_spec["default"]
                initial_value = rule_config.get(param_name, default)
                field = self.build_parameter_field(param_name, param_spec, initial_value)
                param_key = f"rule_{rule_type}_{param_name}"
                self.fields[param_key] = field
                self.initial[param_key] = initial_value

    def build_rules_config(self):
        rules_config = {}
        for rule_type, handler in RULE_REGISTRY.items():
            is_active = bool(self.cleaned_data.get(f"rule_{rule_type}_enabled"))
            if not is_active and not handler.parameters_schema:
                continue
            rule_config = {"is_active": is_active}
            for param_name, param_spec in handler.parameters_schema.items():
                default = param_spec["default"]
                value = self.cleaned_data.get(f"rule_{rule_type}_{param_name}")
                if value is not None:
                    coerced = int(value) if isinstance(default, int) else float(value)
                    rule_config[param_name] = coerced
                else:
                    rule_config[param_name] = default
            rules_config[rule_type] = rule_config
        return rules_config

    def save(self, commit=True):
        self.instance.rules_config = self.build_rules_config()
        return super().save(commit=commit)
