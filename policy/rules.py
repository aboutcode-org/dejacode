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

# VulnerabilityAnalysis states that indicate a vulnerability has been triaged and addressed.
TERMINAL_VULNERABILITY_STATES = ["resolved", "resolved_with_pedigree", "not_affected"]


class BaseRule:
    """Base class for policy rule handlers."""

    rule_type = None
    label = None
    description = None
    severity = "warning"
    default_threshold = 0
    parameters_schema = {}

    def count_violations(self, product, threshold, parameters):
        """Count objects violating the rule for the given product."""
        raise NotImplementedError

    def get_package_filter(self):
        """Return queryset filter kwargs for ProductPackage to identify violating packages."""
        return {}

    def filter_queryset(self, queryset, parameters=None):
        """Filter a ProductPackage queryset to packages that violate this rule."""
        package_filter = self.get_package_filter()
        if package_filter:
            return queryset.filter(**package_filter)
        return queryset


class PackageBaseRule(BaseRule):
    """Base for rules that count packages matching a fixed filter within a product."""

    package_filter = {}

    def count_violations(self, product, threshold, parameters):
        Package = apps.get_model("component_catalog", "package")

        count = (
            Package.objects.filter(
                productpackages__product=product,
                **self.package_filter,
            )
            .distinct()
            .count()
        )

        return count if count > threshold else 0

    def get_package_filter(self):
        return {f"package__{key}": value for key, value in self.package_filter.items()}


class UsagePolicyErrorRule(PackageBaseRule):
    rule_type = "usage_policy_error"
    label = "Usage Policy Error"
    severity = "error"
    description = "Detects packages assigned a usage policy flagged with an error compliance alert."
    package_filter = {"usage_policy__compliance_alert": "error"}


class UsagePolicyWarningRule(PackageBaseRule):
    rule_type = "usage_policy_warning"
    label = "Usage Policy Warning"
    description = (
        "Detects packages assigned a usage policy flagged with a warning compliance alert."
    )
    package_filter = {"usage_policy__compliance_alert": "warning"}


class LicensePolicyErrorRule(PackageBaseRule):
    rule_type = "license_policy_error"
    label = "License Policy Error"
    severity = "error"
    description = (
        "Detects packages whose licenses are assigned a usage policy"
        " flagged with an error compliance alert."
    )
    package_filter = {"licenses__usage_policy__compliance_alert": "error"}


class LicensePolicyWarningRule(PackageBaseRule):
    rule_type = "license_policy_warning"
    label = "License Policy Warning"
    description = (
        "Detects packages whose licenses are assigned a usage policy"
        " flagged with a warning compliance alert."
    )
    package_filter = {"licenses__usage_policy__compliance_alert": "warning"}


class LicenseCoverageGapRule(PackageBaseRule):
    rule_type = "license_coverage_gap"
    label = "License Coverage Gap"
    description = "Detects packages with no license expression."
    package_filter = {"license_expression": ""}


class VulnerabilityDetectedRule(BaseRule):
    rule_type = "vulnerability_detected"
    label = "Vulnerability Detected"
    severity = "error"
    description = "Detects packages with at least one known vulnerability."
    parameters_schema = {
        "min_risk_score": "Minimum risk score (0.0-10.0). Default: any vulnerability.",
    }

    def filter_queryset(self, queryset, parameters=None):
        parameters = parameters or {}
        min_risk_score = parameters.get("min_risk_score")
        if min_risk_score is not None:
            return queryset.filter(
                package__affected_by_vulnerabilities__risk_score__gte=min_risk_score
            )
        return queryset.filter(package__affected_by_vulnerabilities__isnull=False)

    def count_violations(self, product, threshold, parameters):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        product_packages = ProductPackage.objects.filter(product=product)
        count = self.filter_queryset(product_packages, parameters).distinct().count()
        return count if count > threshold else 0


class UnresolvedVulnerabilityRule(BaseRule):
    rule_type = "vulnerability_unresolved"
    label = "Vulnerability Unresolved"
    severity = "warning"
    description = (
        "Detects packages with known vulnerabilities and no completed vulnerability analysis."
    )

    def filter_queryset(self, queryset, parameters=None):
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
        return queryset.filter(Exists(unresolved_link))

    def count_violations(self, product, threshold, parameters):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        product_packages = ProductPackage.objects.filter(product=product)
        count = self.filter_queryset(product_packages).distinct().count()
        return count if count > threshold else 0


class StaleVulnerabilityRule(BaseRule):
    rule_type = "vulnerability_stale"
    label = "Vulnerability Stale"
    severity = "error"
    description = (
        "Detects packages with high-risk vulnerabilities unaddressed"
        " for more than the configured number of days."
    )
    parameters_schema = {
        "max_days": (
            "Maximum number of days a vulnerability may remain unaddressed before flagging. "
            "Default: 30."
        ),
        "min_risk_score": (
            "Only consider vulnerabilities with at least this risk score. Default: 8.0."
        ),
    }

    def filter_queryset(self, queryset, parameters=None):
        PackageAffectedByVulnerability = apps.get_model(
            "component_catalog", "packageaffectedbyvulnerability"
        )
        VulnerabilityAnalysis = apps.get_model("vulnerabilities", "vulnerabilityanalysis")

        parameters = parameters or {}
        max_days = parameters.get("max_days", 30)
        min_risk_score = parameters.get("min_risk_score", 8.0)
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
        return queryset.filter(Exists(stale_link))

    def count_violations(self, product, threshold, parameters):
        ProductPackage = apps.get_model("product_portfolio", "productpackage")
        product_packages = ProductPackage.objects.filter(product=product)
        count = self.filter_queryset(product_packages, parameters).distinct().count()
        return count if count > threshold else 0


RULE_REGISTRY = {
    UsagePolicyErrorRule.rule_type: UsagePolicyErrorRule(),
    UsagePolicyWarningRule.rule_type: UsagePolicyWarningRule(),
    LicensePolicyErrorRule.rule_type: LicensePolicyErrorRule(),
    LicensePolicyWarningRule.rule_type: LicensePolicyWarningRule(),
    LicenseCoverageGapRule.rule_type: LicenseCoverageGapRule(),
    VulnerabilityDetectedRule.rule_type: VulnerabilityDetectedRule(),
    UnresolvedVulnerabilityRule.rule_type: UnresolvedVulnerabilityRule(),
    StaleVulnerabilityRule.rule_type: StaleVulnerabilityRule(),
}
