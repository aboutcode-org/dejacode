#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from component_catalog.models import Package
from component_catalog.models import PackageAffectedByVulnerability
from component_catalog.tests import make_package
from dje.models import Dataspace
from license_library.models import License
from license_library.tests import make_license
from policy.models import UsagePolicy
from policy.rules import LicenseCoverageGapRule
from policy.rules import LicensePolicyErrorRule
from policy.rules import LicensePolicyWarningRule
from policy.rules import StaleVulnerabilityRule
from policy.rules import UnresolvedVulnerabilityRule
from policy.rules import UsagePolicyErrorRule
from policy.rules import UsagePolicyWarningRule
from policy.rules import VulnerabilityDetectedRule
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_package
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.tests import make_vulnerability_analysis


class UsagePolicyErrorRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.policy = UsagePolicy.objects.create(
            label="Prohibited",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Package),
            compliance_alert=UsagePolicy.Compliance.ERROR,
            dataspace=self.dataspace,
        )

    def test_counts_packages_with_error_usage_policy(self):
        package = make_package(self.dataspace, usage_policy=self.policy)
        make_product_package(self.product, package=package)
        make_product_package(self.product, package=make_package(self.dataspace))
        count = UsagePolicyErrorRule().count_violations(self.product, 0, {})
        self.assertEqual(1, count)

    def test_returns_zero_when_no_matching_packages(self):
        make_product_package(self.product, package=make_package(self.dataspace))
        count = UsagePolicyErrorRule().count_violations(self.product, 0, {})
        self.assertEqual(0, count)


class UsagePolicyWarningRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.policy = UsagePolicy.objects.create(
            label="Restricted",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Package),
            compliance_alert=UsagePolicy.Compliance.WARNING,
            dataspace=self.dataspace,
        )

    def test_counts_packages_with_warning_usage_policy(self):
        package = make_package(self.dataspace, usage_policy=self.policy)
        make_product_package(self.product, package=package)
        count = UsagePolicyWarningRule().count_violations(self.product, 0, {})
        self.assertEqual(1, count)


class LicensePolicyErrorRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.policy = UsagePolicy.objects.create(
            label="Prohibited",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            compliance_alert=UsagePolicy.Compliance.ERROR,
            dataspace=self.dataspace,
        )

    def test_counts_packages_with_license_error_policy(self):
        license_ = make_license(self.dataspace, key="gpl-3.0", usage_policy=self.policy)
        package = make_package(self.dataspace)
        package.licenses.add(license_, through_defaults={"dataspace": self.dataspace})
        make_product_package(self.product, package=package)
        count = LicensePolicyErrorRule().count_violations(self.product, 0, {})
        self.assertEqual(1, count)

    def test_returns_zero_when_license_has_no_policy(self):
        license_ = make_license(self.dataspace, key="mit")
        package = make_package(self.dataspace)
        package.licenses.add(license_, through_defaults={"dataspace": self.dataspace})
        make_product_package(self.product, package=package)
        count = LicensePolicyErrorRule().count_violations(self.product, 0, {})
        self.assertEqual(0, count)


class LicensePolicyWarningRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.policy = UsagePolicy.objects.create(
            label="Restricted",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            compliance_alert=UsagePolicy.Compliance.WARNING,
            dataspace=self.dataspace,
        )

    def test_counts_packages_with_license_warning_policy(self):
        license_ = make_license(self.dataspace, key="lgpl-2.1", usage_policy=self.policy)
        package = make_package(self.dataspace)
        package.licenses.add(license_, through_defaults={"dataspace": self.dataspace})
        make_product_package(self.product, package=package)
        count = LicensePolicyWarningRule().count_violations(self.product, 0, {})
        self.assertEqual(1, count)


class LicenseCoverageGapRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_counts_packages_with_no_license_expression(self):
        make_product_package(
            self.product, package=make_package(self.dataspace, license_expression="")
        )
        make_product_package(
            self.product, package=make_package(self.dataspace, license_expression="mit")
        )
        count = LicenseCoverageGapRule().count_violations(self.product, 0, {})
        self.assertEqual(1, count)

    def test_returns_zero_when_all_packages_have_license(self):
        make_product_package(
            self.product, package=make_package(self.dataspace, license_expression="mit")
        )
        count = LicenseCoverageGapRule().count_violations(self.product, 0, {})
        self.assertEqual(0, count)


class VulnerabilityDetectedRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_counts_packages_with_any_vulnerability(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package)
        make_product_package(self.product, package=package)
        make_product_package(self.product, package=make_package(self.dataspace))
        count = VulnerabilityDetectedRule().count_violations(self.product, 0, {})
        self.assertEqual(1, count)

    def test_min_risk_score_excludes_packages_below_threshold(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package, risk_score=4.0)
        make_product_package(self.product, package=package)
        count = VulnerabilityDetectedRule().count_violations(
            self.product, 0, {"min_risk_score": 7.0}
        )
        self.assertEqual(0, count)

    def test_min_risk_score_includes_packages_at_or_above_threshold(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package, risk_score=9.0)
        make_product_package(self.product, package=package)
        count = VulnerabilityDetectedRule().count_violations(
            self.product, 0, {"min_risk_score": 7.0}
        )
        self.assertEqual(1, count)


class UnresolvedVulnerabilityRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_counts_unanalyzed_package_vulnerability_links(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package)
        make_product_package(self.product, package=package)
        count = UnresolvedVulnerabilityRule().count_violations(self.product, 0, {})
        self.assertEqual(1, count)

    def test_does_not_count_links_with_terminal_analysis(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        product_package = make_product_package(self.product, package=package)
        make_vulnerability_analysis(product_package, vulnerability, state="resolved")
        count = UnresolvedVulnerabilityRule().count_violations(self.product, 0, {})
        self.assertEqual(0, count)

    def test_does_not_count_links_with_resolved_with_pedigree_analysis(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        product_package = make_product_package(self.product, package=package)
        make_vulnerability_analysis(product_package, vulnerability, state="resolved_with_pedigree")
        count = UnresolvedVulnerabilityRule().count_violations(self.product, 0, {})
        self.assertEqual(0, count)

    def test_does_not_count_links_with_not_affected_analysis(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        product_package = make_product_package(self.product, package=package)
        make_vulnerability_analysis(product_package, vulnerability, state="not_affected")
        count = UnresolvedVulnerabilityRule().count_violations(self.product, 0, {})
        self.assertEqual(0, count)


class StaleVulnerabilityRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_counts_old_unresolved_high_risk_links(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, risk_score=9.0)
        make_product_package(self.product, package=package)
        old_date = timezone.now() - timedelta(days=60)
        PackageAffectedByVulnerability.objects.filter(
            package=package, vulnerability=vulnerability
        ).update(detected_date=old_date)
        count = StaleVulnerabilityRule().count_violations(self.product, 0, {})
        self.assertEqual(1, count)

    def test_does_not_count_recent_links(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package, risk_score=9.0)
        make_product_package(self.product, package=package)
        count = StaleVulnerabilityRule().count_violations(self.product, 0, {})
        self.assertEqual(0, count)

    def test_does_not_count_links_below_min_risk_score(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, risk_score=3.0)
        make_product_package(self.product, package=package)
        old_date = timezone.now() - timedelta(days=60)
        PackageAffectedByVulnerability.objects.filter(
            package=package, vulnerability=vulnerability
        ).update(detected_date=old_date)
        count = StaleVulnerabilityRule().count_violations(self.product, 0, {})
        self.assertEqual(0, count)

    def test_custom_max_days_triggers_for_links_within_window(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, risk_score=9.0)
        make_product_package(self.product, package=package)
        recent_date = timezone.now() - timedelta(days=10)
        PackageAffectedByVulnerability.objects.filter(
            package=package, vulnerability=vulnerability
        ).update(detected_date=recent_date)
        count = StaleVulnerabilityRule().count_violations(self.product, 0, {"max_days": 5})
        self.assertEqual(1, count)

    def test_does_not_count_stale_links_with_terminal_analysis(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, risk_score=9.0)
        product_package = make_product_package(self.product, package=package)
        old_date = timezone.now() - timedelta(days=60)
        PackageAffectedByVulnerability.objects.filter(
            package=package, vulnerability=vulnerability
        ).update(detected_date=old_date)
        make_vulnerability_analysis(product_package, vulnerability, state="resolved")
        count = StaleVulnerabilityRule().count_violations(self.product, 0, {})
        self.assertEqual(0, count)
