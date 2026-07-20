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
    severity = "warning"
    default_threshold = 0
    parameters_schema = {}

    def count_violations(self, product, threshold, parameters):
        """Count objects violating the rule for the given product."""
        raise NotImplementedError

    def get_package_filter(self):
        """Return queryset filter kwargs for ProductPackage to identify violating packages."""
        return {}


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
    description = (
        "Detects packages assigned a usage policy with a compliance alert level of 'error'."
    )
    package_filter = {"usage_policy__compliance_alert": "error"}


class UsagePolicyWarningRule(PackageBaseRule):
    rule_type = "usage_policy_warning"
    label = "Usage Policy Warning"
    description = (
        "Detects packages assigned a usage policy with a compliance alert level of 'warning'."
    )
    package_filter = {"usage_policy__compliance_alert": "warning"}


class LicensePolicyErrorRule(PackageBaseRule):
    rule_type = "license_policy_error"
    label = "License Policy Error"
    severity = "error"
    description = (
        "Detects packages whose licenses are assigned a usage policy"
        " with a compliance alert level of 'error'."
    )
    package_filter = {"licenses__usage_policy__compliance_alert": "error"}


class LicensePolicyWarningRule(PackageBaseRule):
    rule_type = "license_policy_warning"
    label = "License Policy Warning"
    description = (
        "Detects packages whose licenses are assigned a usage policy"
        " with a compliance alert level of 'warning'."
    )
    package_filter = {"licenses__usage_policy__compliance_alert": "warning"}


class LicenseCoverageGapRule(PackageBaseRule):
    rule_type = "license_coverage_gap"
    label = "License Coverage Gap"
    description = (
        "Detects packages with no license expression, indicating a gap in license coverage."
    )
    package_filter = {"license_expression": ""}


RULE_REGISTRY = {
    UsagePolicyErrorRule.rule_type: UsagePolicyErrorRule(),
    UsagePolicyWarningRule.rule_type: UsagePolicyWarningRule(),
    LicensePolicyErrorRule.rule_type: LicensePolicyErrorRule(),
    LicensePolicyWarningRule.rule_type: LicensePolicyWarningRule(),
    LicenseCoverageGapRule.rule_type: LicenseCoverageGapRule(),
}
