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
    default_threshold = 0
    parameters_schema = {}

    def count_violations(self, product, threshold, parameters):
        """Count objects violating the rule for the given product."""
        raise NotImplementedError


class PackageBaseRule(BaseRule):
    """Base for rules that count packages matching a fixed filter within a product."""

    package_filter = {}

    def count_violations(self, product, threshold, parameters):
        Package = apps.get_model("component_catalog", "package")

        count = Package.objects.filter(
            productpackages__product=product,
            **self.package_filter,
        ).count()

        return count if count > threshold else 0


class LicensePolicyErrorRule(PackageBaseRule):
    rule_type = "license_policy_error"
    label = "License Policy Error"
    description = (
        "Detects packages assigned a usage policy with a compliance alert level of 'error'."
    )
    package_filter = {"usage_policy__compliance_alert": "error"}


class LicensePolicyWarningRule(PackageBaseRule):
    rule_type = "license_policy_warning"
    label = "License Policy Warning"
    description = (
        "Detects packages assigned a usage policy with a compliance alert level of 'warning'."
    )
    package_filter = {"usage_policy__compliance_alert": "warning"}


class LicenseCoverageGapRule(PackageBaseRule):
    rule_type = "license_coverage_gap"
    label = "License Coverage Gap"
    description = (
        "Detects packages with no license expression, indicating a gap in license coverage."
    )
    package_filter = {"license_expression": ""}


class VulnerabilityDetectedRule(BaseRule):
    rule_type = "vulnerability_detected"
    label = "Vulnerability Detected"
    description = "Detects packages with at least one known vulnerability (non-null risk score)."
    parameters_schema = {
        "min_risk_score": "Minimum risk score (0.0-10.0). Default: any vulnerability.",
    }

    def count_violations(self, product, threshold, parameters):
        Package = apps.get_model("component_catalog", "package")

        packages = Package.objects.filter(
            productpackages__product=product,
            risk_score__isnull=False,
        )

        min_risk_score = parameters.get("min_risk_score")
        if min_risk_score is not None:
            packages = packages.filter(risk_score__gte=min_risk_score)

        count = packages.count()
        return count if count > threshold else 0


RULE_REGISTRY = {
    LicensePolicyErrorRule.rule_type: LicensePolicyErrorRule(),
    LicensePolicyWarningRule.rule_type: LicensePolicyWarningRule(),
    LicenseCoverageGapRule.rule_type: LicenseCoverageGapRule(),
    VulnerabilityDetectedRule.rule_type: VulnerabilityDetectedRule(),
}
