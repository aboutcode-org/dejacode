#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import apps

from policy.rules import BaseRule


class BaseTriageRule(BaseRule):
    """Base class for vulnerability triage rule handlers."""

    def count_violations(self, product):
        raise NotImplementedError


class CriticalVulnerabilityTriageRule(BaseTriageRule):
    rule_type = "critical_vulnerability"
    label = "Critical Vulnerability"
    description = "Packages with at least one critical-severity vulnerability (risk score >= 8.0)."

    def count_violations(self, product):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        return (
            ProductPackage.objects.filter(
                product=product,
                package__affected_by_vulnerabilities__risk_level="critical",
            )
            .distinct()
            .count()
        )


class ExploitedVulnerabilityTriageRule(BaseTriageRule):
    rule_type = "exploited_vulnerability"
    label = "Exploited Vulnerability"
    description = "Packages with vulnerabilities for which known exploits are available."

    def count_violations(self, product):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        # exploitability == 2.0 means known exploits are available
        return (
            ProductPackage.objects.filter(
                product=product,
                package__affected_by_vulnerabilities__exploitability=2.0,
            )
            .distinct()
            .count()
        )


RULE_REGISTRY = {
    CriticalVulnerabilityTriageRule.rule_type: CriticalVulnerabilityTriageRule(),
    ExploitedVulnerabilityTriageRule.rule_type: ExploitedVulnerabilityTriageRule(),
}
