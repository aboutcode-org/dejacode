#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from component_catalog.models import Package
from component_catalog.tests import make_component
from component_catalog.tests import make_package
from dje.models import Dataspace
from license_library.models import License
from organization.models import Owner
from policy.models import UsagePolicy
from product_portfolio.filters import ProductComponentFilterSet
from product_portfolio.filters import ProductFilterSet
from product_portfolio.filters import ProductPackageFilterSet
from product_portfolio.models import Product
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductPolicyViolation
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_component
from product_portfolio.tests import make_product_package
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.triage.engine import evaluate_ruleset
from vulnerabilities.triage.models import ProductTriageRuleset
from vulnerabilities.triage.models import TriageAction
from vulnerabilities.triage.models import TriageRuleset


class ProductPackageFilterSetTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Reference")
        self.owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        self.license1 = License.objects.create(
            key="mit",
            name="MIT",
            short_name="MIT",
            owner=self.owner,
            dataspace=self.dataspace,
        )
        self.license2 = License.objects.create(
            key="apache-2.0",
            name="Apache 2.0",
            short_name="Apache 2.0",
            owner=self.owner,
            dataspace=self.dataspace,
        )

        self.product = make_product(self.dataspace)
        self.package1 = make_package(self.dataspace)
        self.package2 = make_package(self.dataspace)
        self.package3 = make_package(self.dataspace)

        self.pp1 = ProductPackage.objects.create(
            product=self.product,
            package=self.package1,
            license_expression=self.license1.key,
            dataspace=self.dataspace,
        )
        self.pp2 = ProductPackage.objects.create(
            product=self.product,
            package=self.package2,
            license_expression=self.license2.key,
            dataspace=self.dataspace,
        )
        self.pp3 = ProductPackage.objects.create(
            product=self.product,
            package=self.package3,
            license_expression="",
            dataspace=self.dataspace,
        )

    def test_product_package_filterset_licenses(self):
        data = {"licenses": [self.license1.key]}
        filterset = ProductPackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.pp1])

        data = {"licenses": [self.license2.key]}
        filterset = ProductPackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.pp2])

        data = {"licenses": [self.license1.key, self.license2.key]}
        filterset = ProductPackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.pp1, self.pp2], ordered=False)

    def test_product_package_filterset_has_licenses(self):
        data = {"has_licenses": "yes"}
        filterset = ProductPackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.pp1, self.pp2], ordered=False)

        data = {"has_licenses": "no"}
        filterset = ProductPackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.pp3])


class ProductFilterSetPolicyTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product_with = make_product(self.dataspace)
        self.product_without = make_product(self.dataspace)
        ProductPolicyViolation.objects.create(
            product=self.product_with,
            dataspace=self.dataspace,
            rule_type="usage_policy_error",
            violation_count=1,
        )

    def _make_filterset(self, data):
        return ProductFilterSet(
            dataspace=self.dataspace,
            data=data,
            queryset=Product.unsecured_objects.filter(dataspace=self.dataspace),
        )

    def test_filter_policy_violations_true_returns_products_with_violations(self):
        filterset = self._make_filterset({"policy_violations": "true"})
        self.assertIn(self.product_with, filterset.qs)
        self.assertNotIn(self.product_without, filterset.qs)

    def test_filter_policy_violations_false_returns_products_without_violations(self):
        filterset = self._make_filterset({"policy_violations": "false"})
        self.assertIn(self.product_without, filterset.qs)
        self.assertNotIn(self.product_with, filterset.qs)

    def test_filter_policy_violations_excludes_stale_rule_types(self):
        product_stale = make_product(self.dataspace)
        ProductPolicyViolation.objects.create(
            product=product_stale,
            dataspace=self.dataspace,
            rule_type="removed_rule",
            violation_count=1,
        )
        filterset = self._make_filterset({"policy_violations": "true"})
        self.assertNotIn(product_stale, filterset.qs)


class ProductPackageFilterByRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.owner = Owner.objects.create(name="Owner", dataspace=self.dataspace)
        self.usage_policy = UsagePolicy.objects.create(
            label="Error Policy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Package),
            compliance_alert="error",
            dataspace=self.dataspace,
        )
        self.product = make_product(self.dataspace)
        self.pp_with_policy = make_product_package(
            self.product,
            make_package(self.dataspace, usage_policy=self.usage_policy),
        )
        self.pp_without_policy = make_product_package(self.product, make_package(self.dataspace))

    def test_filter_by_policy_rule_filters_matching_packages(self):
        filterset = ProductPackageFilterSet(
            dataspace=self.dataspace,
            data={"policy_rule": "usage_policy_error"},
        )
        self.assertIn(self.pp_with_policy, filterset.qs)
        self.assertNotIn(self.pp_without_policy, filterset.qs)

    def test_filter_by_unknown_rule_returns_all(self):
        filterset = ProductPackageFilterSet(
            dataspace=self.dataspace,
            data={"policy_rule": "nonexistent_rule"},
        )
        self.assertIn(self.pp_with_policy, filterset.qs)
        self.assertIn(self.pp_without_policy, filterset.qs)


class ProductPackageFilterByRuleDistinctTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_filter_by_vulnerability_rule_returns_distinct_results(self):
        package = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=package)
        make_vulnerability(self.dataspace, affecting=package)
        make_product_package(self.product, package=package)
        filterset = ProductPackageFilterSet(
            dataspace=self.dataspace,
            data={"policy_rule": "vulnerability_detected"},
        )
        self.assertEqual(1, filterset.qs.count())


class ProductPackageFilterByTriageActionTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.pp_with_recommendation = make_product_package(
            self.product, make_package(self.dataspace)
        )
        self.pp_without_recommendation = make_product_package(
            self.product, make_package(self.dataspace)
        )
        make_vulnerability(
            self.dataspace, affecting=self.pp_with_recommendation.package, risk_score=9.0
        )
        ruleset = TriageRuleset.objects.create(
            name="Upgrade Ruleset",
            action=TriageAction.UPGRADE,
            precedence=100,
            dataspace=self.dataspace,
            rules_config={"risk_score": {"is_active": True, "min_risk_score": 8.0}},
        )
        ProductTriageRuleset.objects.create(
            product=self.product, ruleset=ruleset, dataspace=self.dataspace
        )
        evaluate_ruleset(ruleset, self.product)

    def test_filter_by_triage_action_filters_matching_packages(self):
        filterset = ProductPackageFilterSet(
            dataspace=self.dataspace,
            data={"triage_action": "upgrade"},
        )
        self.assertIn(self.pp_with_recommendation, filterset.qs)
        self.assertNotIn(self.pp_without_recommendation, filterset.qs)

    def test_filter_by_triage_action_excludes_non_matching_action(self):
        filterset = ProductPackageFilterSet(
            dataspace=self.dataspace,
            data={"triage_action": "notify"},
        )
        self.assertNotIn(self.pp_with_recommendation, filterset.qs)


class ProductComponentFilterByRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_filter_by_policy_rule_returns_empty_for_components(self):
        component = make_component(self.dataspace)
        make_product_component(self.product, component=component)
        filterset = ProductComponentFilterSet(
            dataspace=self.dataspace,
            data={"policy_rule": "usage_policy_error"},
        )
        self.assertEqual(0, filterset.qs.count())
