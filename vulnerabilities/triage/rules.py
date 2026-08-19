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

TRIAGE_TERMINAL_VULNERABILITY_STATES = [
    "resolved",
    "resolved_with_pedigree",
    "not_affected",
    "false_positive",
]


class BaseTriageRule(BaseRule):
    """Base class for vulnerability triage rule handlers."""

    parameters_schema = {}

    def get_matching_vulnerabilities(self, product, parameters=None):
        raise NotImplementedError


class RiskScoreTriageRule(BaseTriageRule):
    rule_type = "risk_score"
    label = "Risk Score"
    description = "Vulnerabilities at or above the configured risk score affecting the product."
    parameters_schema = {
        "min_risk_score": {
            "default": 8.0,
            "help_text": "Minimum vulnerability risk score (0.0-10.0). Default: 8.0.",
        },
    }

    def get_matching_vulnerabilities(self, product, parameters=None):
        Vulnerability = apps.get_model("vulnerabilities", "Vulnerability")
        min_risk_score = (parameters or {}).get(
            "min_risk_score", self.parameters_schema["min_risk_score"]["default"]
        )
        return Vulnerability.objects.filter(
            affected_packages__productpackages__product=product,
            risk_score__gte=min_risk_score,
        ).distinct()


class WeightedRiskTriageRule(BaseTriageRule):
    rule_type = "weighted_risk"
    label = "Weighted Risk"
    description = (
        "Vulnerabilities affecting at least one package whose weighted risk score"
        " in this product meets the threshold."
    )
    parameters_schema = {
        "min_weighted_risk_score": {
            "default": 8.0,
            "help_text": "Minimum weighted risk score (0.0-10.0). Default: 8.0.",
        },
    }

    def get_matching_vulnerabilities(self, product, parameters=None):
        Vulnerability = apps.get_model("vulnerabilities", "Vulnerability")
        min_weighted_risk_score = (parameters or {}).get(
            "min_weighted_risk_score",
            self.parameters_schema["min_weighted_risk_score"]["default"],
        )
        return Vulnerability.objects.filter(
            affected_packages__productpackages__product=product,
            affected_packages__productpackages__weighted_risk_score__gte=min_weighted_risk_score,
        ).distinct()


class ExploitedVulnerabilityTriageRule(BaseTriageRule):
    rule_type = "exploited_vulnerability"
    label = "Exploited Vulnerability"
    description = "Vulnerabilities for which a known exploit is available."

    def get_matching_vulnerabilities(self, product, parameters=None):
        Vulnerability = apps.get_model("vulnerabilities", "Vulnerability")
        # exploitability == 2.0 means known exploits are available
        return Vulnerability.objects.filter(
            affected_packages__productpackages__product=product,
            exploitability=2.0,
        ).distinct()


class ReachableVulnerabilityTriageRule(BaseTriageRule):
    rule_type = "reachable_vulnerability"
    label = "Reachable Vulnerability"
    description = "Vulnerabilities confirmed as reachable in the product context."

    def get_matching_vulnerabilities(self, product, parameters=None):
        Vulnerability = apps.get_model("vulnerabilities", "Vulnerability")
        VulnerabilityAnalysis = apps.get_model("vulnerabilities", "vulnerabilityanalysis")
        reachable_analysis = VulnerabilityAnalysis.objects.filter(
            product_package__product=product,
            vulnerability=OuterRef("pk"),
            is_reachable=True,
        )
        return (
            Vulnerability.objects.filter(affected_packages__productpackages__product=product)
            .filter(Exists(reachable_analysis))
            .distinct()
        )


class UnresolvedVulnerabilityTriageRule(BaseTriageRule):
    rule_type = "unresolved_vulnerability"
    label = "Unresolved Vulnerability"
    description = (
        "Vulnerabilities affecting the product where at least one package"
        " has no completed triage analysis."
    )

    def get_matching_vulnerabilities(self, product, parameters=None):
        Vulnerability = apps.get_model("vulnerabilities", "Vulnerability")
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        VulnerabilityAnalysis = apps.get_model("vulnerabilities", "vulnerabilityanalysis")
        # A terminal analysis for the (product_package, vulnerability) pair
        terminal_analysis = VulnerabilityAnalysis.objects.filter(
            product_package=OuterRef("pk"),
            vulnerability=OuterRef(OuterRef("pk")),
            state__in=TRIAGE_TERMINAL_VULNERABILITY_STATES,
        )
        # A package in the product that carries this vulnerability but has no terminal analysis
        unresolved_package = ProductPackage.objects.filter(
            product=product,
            package__affected_by_vulnerabilities=OuterRef("pk"),
        ).filter(~Exists(terminal_analysis))
        return (
            Vulnerability.objects.filter(
                affected_packages__productpackages__product=product,
            )
            .filter(Exists(unresolved_package))
            .distinct()
        )


class StaleVulnerabilityTriageRule(BaseTriageRule):
    rule_type = "stale_vulnerability"
    label = "Stale Vulnerability"
    description = (
        "Vulnerabilities above the configured risk score,"
        " unaddressed beyond the configured number of days."
    )
    parameters_schema = {
        "min_risk_score": {
            "default": 8.0,
            "help_text": "Minimum vulnerability risk score (0.0-10.0). Default: 8.0.",
        },
        "max_days": {
            "default": 30,
            "help_text": (
                "Maximum number of days a vulnerability may remain unaddressed. Default: 30."
            ),
        },
    }

    def get_matching_vulnerabilities(self, product, parameters=None):
        Vulnerability = apps.get_model("vulnerabilities", "Vulnerability")
        PackageAffectedByVulnerability = apps.get_model(
            "component_catalog", "packageaffectedbyvulnerability"
        )
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        VulnerabilityAnalysis = apps.get_model("vulnerabilities", "vulnerabilityanalysis")
        parameters = parameters or {}
        min_risk_score = parameters.get(
            "min_risk_score", self.parameters_schema["min_risk_score"]["default"]
        )
        max_days = parameters.get("max_days", self.parameters_schema["max_days"]["default"])
        cutoff_date = timezone.now() - timedelta(days=max_days)
        stale_detection_vuln_ids = PackageAffectedByVulnerability.objects.filter(
            package__productpackages__product=product,
            detected_date__lte=cutoff_date,
        ).values_list("vulnerability_id", flat=True)
        terminal_analysis = VulnerabilityAnalysis.objects.filter(
            product_package=OuterRef("pk"),
            vulnerability=OuterRef(OuterRef("pk")),
            state__in=TRIAGE_TERMINAL_VULNERABILITY_STATES,
        )
        unresolved_package = ProductPackage.objects.filter(
            product=product,
            package__affected_by_vulnerabilities=OuterRef("pk"),
        ).filter(~Exists(terminal_analysis))

        return (
            Vulnerability.objects.filter(
                affected_packages__productpackages__product=product,
                risk_score__gte=min_risk_score,
                id__in=stale_detection_vuln_ids,
            )
            .filter(Exists(unresolved_package))
            .distinct()
        )


class DevOnlyPackageTriageRule(BaseTriageRule):
    rule_type = "dev_only_vulnerable_package"
    label = "Dev-Only Vulnerable Package"
    description = "Vulnerabilities affecting only non-deployed packages in the product."

    def get_matching_vulnerabilities(self, product, parameters=None):
        Vulnerability = apps.get_model("vulnerabilities", "Vulnerability")
        deployed_vuln_ids = Vulnerability.objects.filter(
            affected_packages__productpackages__product=product,
            affected_packages__productpackages__is_deployed=True,
        ).values_list("id", flat=True)
        return (
            Vulnerability.objects.filter(
                affected_packages__productpackages__product=product,
                affected_packages__productpackages__is_deployed=False,
            )
            .exclude(id__in=deployed_vuln_ids)
            .distinct()
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


def rule_parameters_from_config(config):
    """Extract rule-specific parameters from a rule config dict, excluding is_active."""
    return {key: value for key, value in config.items() if key != "is_active"}
