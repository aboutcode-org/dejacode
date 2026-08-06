#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from datetime import timedelta

from django.apps import apps
from django.db.models import Exists
from django.db.models import OuterRef
from django.utils import timezone

from policy.rules import BaseRule

TERMINAL_VULNERABILITY_STATES = [
    "resolved",
    "resolved_with_pedigree",
    "not_affected",
    "false_positive",
]


class BaseTriageRule(BaseRule):
    """Base class for vulnerability triage rule handlers."""

    parameters_schema = {}

    def count_matches(self, product, parameters=None):
        raise NotImplementedError


class RiskScoreTriageRule(BaseTriageRule):
    rule_type = "risk_score"
    label = "Risk Score"
    description = (
        "Packages with at least one vulnerability at or above the configured risk score threshold."
    )
    parameters_schema = {
        "min_risk_score": {
            "default": 8.0,
            "help_text": "Minimum vulnerability risk score (0.0-10.0). Default: 8.0.",
        },
    }

    def count_matches(self, product, parameters=None):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        min_risk_score = (parameters or {}).get(
            "min_risk_score", self.parameters_schema["min_risk_score"]["default"]
        )
        return (
            ProductPackage.objects.filter(
                product=product,
                package__affected_by_vulnerabilities__risk_score__gte=min_risk_score,
            )
            .distinct()
            .count()
        )


class WeightedRiskTriageRule(BaseTriageRule):
    rule_type = "weighted_risk"
    label = "Weighted Risk"
    description = (
        "Packages whose weighted risk score (risk adjusted by purpose exposure factor)"
        " is at or above the configured threshold."
    )
    parameters_schema = {
        "min_weighted_risk_score": {
            "default": 8.0,
            "help_text": "Minimum weighted risk score (0.0-10.0). Default: 8.0.",
        },
    }

    def count_matches(self, product, parameters=None):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        min_weighted_risk_score = (parameters or {}).get(
            "min_weighted_risk_score",
            self.parameters_schema["min_weighted_risk_score"]["default"],
        )
        return (
            ProductPackage.objects.filter(
                product=product,
                weighted_risk_score__gte=min_weighted_risk_score,
            )
            .distinct()
            .count()
        )


class ExploitedVulnerabilityTriageRule(BaseTriageRule):
    rule_type = "exploited_vulnerability"
    label = "Exploited Vulnerability"
    description = "Packages with vulnerabilities for which known exploits are available."

    def count_matches(self, product, parameters=None):
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


class ReachableVulnerabilityTriageRule(BaseTriageRule):
    rule_type = "reachable_vulnerability"
    label = "Reachable Vulnerability"
    description = (
        "Packages with at least one vulnerability confirmed as reachable in the product context."
    )

    def count_matches(self, product, parameters=None):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        VulnerabilityAnalysis = apps.get_model("vulnerabilities", "vulnerabilityanalysis")
        reachable_analysis = VulnerabilityAnalysis.objects.filter(
            product_package=OuterRef("pk"),
            is_reachable=True,
        )
        return (
            ProductPackage.objects.filter(product=product)
            .filter(Exists(reachable_analysis))
            .distinct()
            .count()
        )


class UnresolvedVulnerabilityTriageRule(BaseTriageRule):
    rule_type = "unresolved_vulnerability"
    label = "Unresolved Vulnerability"
    description = "Packages with known vulnerabilities that have no completed triage analysis."

    def count_matches(self, product, parameters=None):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        PackageAffectedByVulnerability = apps.get_model(
            "component_catalog", "packageaffectedbyvulnerability"
        )
        VulnerabilityAnalysis = apps.get_model("vulnerabilities", "vulnerabilityanalysis")
        terminal_analysis = VulnerabilityAnalysis.objects.filter(
            product_package=OuterRef(OuterRef("pk")),
            state__in=TERMINAL_VULNERABILITY_STATES,
            vulnerability=OuterRef("vulnerability"),
        )
        unresolved_link = (
            PackageAffectedByVulnerability.objects.filter(package=OuterRef("package"))
            .annotate(has_terminal=Exists(terminal_analysis))
            .filter(has_terminal=False)
        )
        return (
            ProductPackage.objects.filter(product=product)
            .filter(Exists(unresolved_link))
            .distinct()
            .count()
        )


class StaleVulnerabilityTriageRule(BaseTriageRule):
    rule_type = "stale_vulnerability"
    label = "Stale Vulnerability"
    description = (
        "Packages with vulnerabilities above the configured risk score threshold unaddressed"
        " beyond the configured number of days."
    )
    parameters_schema = {
        "min_risk_score": {
            "default": 8.0,
            "help_text": "Minimum vulnerability risk score to consider (0.0-10.0). Default: 8.0.",
        },
        "max_days": {
            "default": 30,
            "help_text": (
                "Maximum number of days a vulnerability may remain unaddressed. Default: 30."
            ),
        },
    }

    def count_matches(self, product, parameters=None):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        PackageAffectedByVulnerability = apps.get_model(
            "component_catalog", "packageaffectedbyvulnerability"
        )
        VulnerabilityAnalysis = apps.get_model("vulnerabilities", "vulnerabilityanalysis")
        parameters = parameters or {}
        min_risk_score = parameters.get(
            "min_risk_score", self.parameters_schema["min_risk_score"]["default"]
        )
        max_days = parameters.get("max_days", self.parameters_schema["max_days"]["default"])
        cutoff_date = timezone.now() - timedelta(days=max_days)
        terminal_analysis = VulnerabilityAnalysis.objects.filter(
            product_package=OuterRef(OuterRef("pk")),
            state__in=TERMINAL_VULNERABILITY_STATES,
            vulnerability=OuterRef("vulnerability"),
        )
        stale_link = (
            PackageAffectedByVulnerability.objects.filter(
                package=OuterRef("package"),
                vulnerability__risk_score__gte=min_risk_score,
                detected_date__lte=cutoff_date,
            )
            .annotate(has_terminal=Exists(terminal_analysis))
            .filter(has_terminal=False)
        )
        return (
            ProductPackage.objects.filter(product=product)
            .filter(Exists(stale_link))
            .distinct()
            .count()
        )


class DevOnlyPackageTriageRule(BaseTriageRule):
    rule_type = "dev_only_vulnerable_package"
    label = "Dev-Only Vulnerable Package"
    description = (
        "Packages not deployed in production (is_deployed=False) that are affected"
        " by vulnerabilities."
    )

    def count_matches(self, product, parameters=None):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        return (
            ProductPackage.objects.filter(
                product=product,
                is_deployed=False,
                package__affected_by_vulnerabilities__isnull=False,
            )
            .distinct()
            .count()
        )


RULE_REGISTRY = {
    RiskScoreTriageRule.rule_type: RiskScoreTriageRule(),
    WeightedRiskTriageRule.rule_type: WeightedRiskTriageRule(),
    ExploitedVulnerabilityTriageRule.rule_type: ExploitedVulnerabilityTriageRule(),
    ReachableVulnerabilityTriageRule.rule_type: ReachableVulnerabilityTriageRule(),
    UnresolvedVulnerabilityTriageRule.rule_type: UnresolvedVulnerabilityTriageRule(),
    StaleVulnerabilityTriageRule.rule_type: StaleVulnerabilityTriageRule(),
    DevOnlyPackageTriageRule.rule_type: DevOnlyPackageTriageRule(),
}
