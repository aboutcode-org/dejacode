#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from component_catalog.models import PackageAffectedByVulnerability
from component_catalog.tests import make_package
from dje.models import Dataspace
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_package
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.tests import make_vulnerability_analysis
from vulnerabilities.triage.rules import DevOnlyPackageTriageRule
from vulnerabilities.triage.rules import ExploitedVulnerabilityTriageRule
from vulnerabilities.triage.rules import ReachableVulnerabilityTriageRule
from vulnerabilities.triage.rules import RiskScoreTriageRule
from vulnerabilities.triage.rules import StaleVulnerabilityTriageRule
from vulnerabilities.triage.rules import UnresolvedVulnerabilityTriageRule
from vulnerabilities.triage.rules import WeightedRiskTriageRule
from vulnerabilities.triage.rules import rule_parameters_from_config


class RiskScoreTriageRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_matches_vulnerability_at_or_above_default_threshold(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, risk_score=8.0)
        make_product_package(self.product, package=package)
        matches = RiskScoreTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([vulnerability], list(matches))

    def test_excludes_vulnerability_below_default_threshold(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package, risk_score=7.9)
        make_product_package(self.product, package=package)
        matches = RiskScoreTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))

    def test_custom_min_risk_score_parameter(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, risk_score=5.0)
        make_product_package(self.product, package=package)
        matches = RiskScoreTriageRule().get_matching_vulnerabilities(
            self.product, parameters={"min_risk_score": 5.0}
        )
        self.assertEqual([vulnerability], list(matches))

    def test_ignores_vulnerabilities_affecting_packages_outside_the_product(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package, risk_score=9.0)
        matches = RiskScoreTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))


class WeightedRiskTriageRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_matches_package_at_or_above_default_threshold(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, risk_score=8.0)
        make_product_package(self.product, package=package)
        matches = WeightedRiskTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([vulnerability], list(matches))

    def test_excludes_package_below_default_threshold(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package, risk_score=7.9)
        make_product_package(self.product, package=package)
        matches = WeightedRiskTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))

    def test_custom_min_weighted_risk_score_parameter(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, risk_score=4.0)
        make_product_package(self.product, package=package)
        matches = WeightedRiskTriageRule().get_matching_vulnerabilities(
            self.product, parameters={"min_weighted_risk_score": 4.0}
        )
        self.assertEqual([vulnerability], list(matches))


class ExploitedVulnerabilityTriageRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_matches_vulnerability_with_known_exploits(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, exploitability=2.0)
        make_product_package(self.product, package=package)
        matches = ExploitedVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([vulnerability], list(matches))

    def test_excludes_vulnerability_with_potential_exploits_only(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package, exploitability=1.0)
        make_product_package(self.product, package=package)
        matches = ExploitedVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))

    def test_excludes_vulnerability_with_no_exploitability_set(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package)
        make_product_package(self.product, package=package)
        matches = ExploitedVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))


class ReachableVulnerabilityTriageRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_matches_vulnerability_confirmed_reachable(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        product_package = make_product_package(self.product, package=package)
        make_vulnerability_analysis(product_package, vulnerability, is_reachable=True)
        matches = ReachableVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([vulnerability], list(matches))

    def test_excludes_vulnerability_marked_not_reachable(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        product_package = make_product_package(self.product, package=package)
        make_vulnerability_analysis(product_package, vulnerability, is_reachable=False)
        matches = ReachableVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))

    def test_excludes_vulnerability_with_no_analysis(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package)
        make_product_package(self.product, package=package)
        matches = ReachableVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))


class UnresolvedVulnerabilityTriageRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_matches_vulnerability_with_no_terminal_analysis(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        make_product_package(self.product, package=package)
        matches = UnresolvedVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([vulnerability], list(matches))

    def test_excludes_vulnerability_with_resolved_analysis(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        product_package = make_product_package(self.product, package=package)
        make_vulnerability_analysis(product_package, vulnerability, state="resolved")
        matches = UnresolvedVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))

    def test_excludes_vulnerability_with_not_affected_analysis(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        product_package = make_product_package(self.product, package=package)
        make_vulnerability_analysis(product_package, vulnerability, state="not_affected")
        matches = UnresolvedVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))

    def test_matches_when_at_least_one_package_still_unresolved(self):
        # Two packages in the product carry the same vulnerability: one is resolved, the
        # other isn't. The vulnerability is still considered unresolved for the product.
        package1 = make_package(self.dataspace)
        package2 = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=[package1, package2])
        product_package1 = make_product_package(self.product, package=package1)
        make_product_package(self.product, package=package2)
        make_vulnerability_analysis(product_package1, vulnerability, state="resolved")
        matches = UnresolvedVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([vulnerability], list(matches))


class StaleVulnerabilityTriageRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def _age_detection(self, package, vulnerability, days):
        old_date = timezone.now() - timedelta(days=days)
        PackageAffectedByVulnerability.objects.filter(
            package=package, vulnerability=vulnerability
        ).update(detected_date=old_date)

    def test_matches_old_high_risk_unresolved_vulnerability(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, risk_score=9.0)
        make_product_package(self.product, package=package)
        self._age_detection(package, vulnerability, days=60)
        matches = StaleVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([vulnerability], list(matches))

    def test_excludes_recent_vulnerability(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package, risk_score=9.0)
        make_product_package(self.product, package=package)
        matches = StaleVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))

    def test_excludes_vulnerability_below_min_risk_score(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, risk_score=3.0)
        make_product_package(self.product, package=package)
        self._age_detection(package, vulnerability, days=60)
        matches = StaleVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))

    def test_excludes_vulnerability_with_terminal_analysis(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, risk_score=9.0)
        product_package = make_product_package(self.product, package=package)
        self._age_detection(package, vulnerability, days=60)
        make_vulnerability_analysis(product_package, vulnerability, state="resolved")
        matches = StaleVulnerabilityTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))

    def test_custom_max_days_triggers_for_links_within_window(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package, risk_score=9.0)
        make_product_package(self.product, package=package)
        self._age_detection(package, vulnerability, days=10)
        matches = StaleVulnerabilityTriageRule().get_matching_vulnerabilities(
            self.product, parameters={"max_days": 5}
        )
        self.assertEqual([vulnerability], list(matches))


class DevOnlyPackageTriageRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_matches_vulnerability_affecting_only_a_non_deployed_package(self):
        package = make_package(self.dataspace)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        make_product_package(self.product, package=package, is_deployed=False)
        matches = DevOnlyPackageTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([vulnerability], list(matches))

    def test_excludes_vulnerability_affecting_a_deployed_package(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package)
        make_product_package(self.product, package=package, is_deployed=True)
        matches = DevOnlyPackageTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))

    def test_excludes_vulnerability_when_also_carried_by_a_deployed_package(self):
        # Same vulnerability reaches the product through both a deployed and a non-deployed
        # package: it is still live in production, so it must not be flagged as dev-only.
        dev_package = make_package(self.dataspace)
        deployed_package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=[dev_package, deployed_package])
        make_product_package(self.product, package=dev_package, is_deployed=False)
        make_product_package(self.product, package=deployed_package, is_deployed=True)
        matches = DevOnlyPackageTriageRule().get_matching_vulnerabilities(self.product)
        self.assertEqual([], list(matches))


class RuleParametersFromConfigTestCase(TestCase):
    def test_excludes_is_active_key(self):
        config = {"is_active": True, "min_risk_score": 7.0}
        self.assertEqual({"min_risk_score": 7.0}, rule_parameters_from_config(config))

    def test_returns_empty_dict_when_only_is_active_present(self):
        self.assertEqual({}, rule_parameters_from_config({"is_active": True}))
