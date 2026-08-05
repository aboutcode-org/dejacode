#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import apps

from policy.rules import BaseRule

ACTION_UPGRADE = "upgrade"


class BaseTriageRule(BaseRule):
    """Base class for vulnerability triage rule handlers."""

    action = None
    timeline_days = None


class CriticalVulnerabilityTriageRule(BaseTriageRule):
    rule_type = "critical_vulnerability"
    label = "Critical Vulnerability"
    description = "Packages with at least one critical-severity vulnerability (risk score >= 8.0)."
    severity = "error"
    action = ACTION_UPGRADE
    timeline_days = 1

    def count_violations(self, product, threshold, parameters):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        count = (
            ProductPackage.objects.filter(
                product=product,
                package__affected_by_vulnerabilities__risk_level="critical",
            )
            .distinct()
            .count()
        )
        return count if count > threshold else 0


class ExploitedVulnerabilityTriageRule(BaseTriageRule):
    rule_type = "exploited_vulnerability"
    label = "Exploited Vulnerability"
    description = "Packages with vulnerabilities for which known exploits are available."
    severity = "error"
    action = ACTION_UPGRADE
    timeline_days = 1

    def count_violations(self, product, threshold, parameters):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        # exploitability == 2.0 means known exploits are available (vs 0.5 none, 1.0 potential)
        count = (
            ProductPackage.objects.filter(
                product=product,
                package__affected_by_vulnerabilities__exploitability=2.0,
            )
            .distinct()
            .count()
        )
        return count if count > threshold else 0


RULE_REGISTRY = {
    CriticalVulnerabilityTriageRule.rule_type: CriticalVulnerabilityTriageRule(),
    ExploitedVulnerabilityTriageRule.rule_type: ExploitedVulnerabilityTriageRule(),
}
