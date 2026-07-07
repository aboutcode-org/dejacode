#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import apps


class BaseRule:
    """Base class for policy rule handlers."""

    rule_type = None
    label = None
    description = None

    def count_violations(self, policy_rule, product):
        """Count objects violating the rule for the given product."""
        raise NotImplementedError


class ComplianceAlertRule(BaseRule):
    rule_type = "compliance_alert"
    label = "Compliance Alert"
    description = (
        "Detects packages assigned a usage policy with a compliance alert level of 'error'."
    )

    def count_violations(self, policy_rule, product):
        Package = apps.get_model("component_catalog", "package")

        count = Package.objects.filter(
            productpackages__product=product,
            usage_policy__compliance_alert="error",
        ).count()

        return count if count > policy_rule.threshold else 0


RULE_REGISTRY = {
    ComplianceAlertRule.rule_type: ComplianceAlertRule(),
}
