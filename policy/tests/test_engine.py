#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest.mock import patch

from django.test import TestCase

from dje.models import Dataspace
from dje.models import DataspaceConfiguration
from policy.engine import evaluate_rule
from policy.engine import evaluate_rules
from policy.engine import get_effective_config
from product_portfolio.models import ProductPolicyViolation
from product_portfolio.tests import make_product

RULE_TYPE = "usage_policy_error"


class EvaluateRuleTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def _count_violations(self, count):
        """Patch count_violations for RULE_TYPE to return a fixed count."""
        return patch(
            "policy.rules.UsagePolicyErrorRule.count_violations",
            return_value=count,
        )

    def test_evaluate_rule_creates_violation_on_first_trigger(self):
        with self._count_violations(3):
            violation, created, resolved_count = evaluate_rule(RULE_TYPE, self.product, 0, {})
        self.assertTrue(created)
        self.assertEqual(0, resolved_count)
        self.assertEqual(3, violation.violation_count)
        self.assertFalse(violation.resolved)
        self.assertEqual(1, ProductPolicyViolation.objects.count())

    def test_evaluate_rule_resolves_violation_when_count_drops_to_zero(self):
        with self._count_violations(3):
            evaluate_rule(RULE_TYPE, self.product, 0, {})
        with self._count_violations(0):
            violation, created, resolved_count = evaluate_rule(RULE_TYPE, self.product, 0, {})
        self.assertIsNone(violation)
        self.assertFalse(created)
        self.assertEqual(1, resolved_count)
        db_violation = ProductPolicyViolation.objects.get()
        self.assertTrue(db_violation.resolved)
        self.assertIsNotNone(db_violation.resolved_date)

    def test_evaluate_rule_retrigger_after_resolution_does_not_raise(self):
        with self._count_violations(3):
            evaluate_rule(RULE_TYPE, self.product, 0, {})
        with self._count_violations(0):
            evaluate_rule(RULE_TYPE, self.product, 0, {})
        with self._count_violations(5):
            violation, created, resolved_count = evaluate_rule(RULE_TYPE, self.product, 0, {})
        self.assertFalse(violation.resolved)
        self.assertIsNone(violation.resolved_date)
        self.assertEqual(5, violation.violation_count)
        self.assertEqual(1, ProductPolicyViolation.objects.count())

    def test_evaluate_rule_updates_count_on_existing_active_violation(self):
        with self._count_violations(2):
            evaluate_rule(RULE_TYPE, self.product, 0, {})
        with self._count_violations(7):
            violation, created, resolved_count = evaluate_rule(RULE_TYPE, self.product, 0, {})
        self.assertFalse(created)
        self.assertEqual(7, violation.violation_count)
        self.assertEqual(1, ProductPolicyViolation.objects.count())


class GetEffectiveConfigTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    def test_returns_defaults_when_no_dataspace_configuration(self):
        config = get_effective_config("usage_policy_error", self.dataspace)
        self.assertFalse(config["is_active"])
        self.assertEqual(0, config["threshold"])
        self.assertEqual({}, config["parameters"])

    def test_reads_dataspace_override(self):
        DataspaceConfiguration.objects.create(
            dataspace=self.dataspace,
            policy_rules_config={"usage_policy_error": {"is_active": True, "threshold": 5}},
        )
        self.dataspace.refresh_from_db()
        config = get_effective_config("usage_policy_error", self.dataspace)
        self.assertTrue(config["is_active"])
        self.assertEqual(5, config["threshold"])

    def test_falls_back_to_code_defaults_for_partial_config(self):
        DataspaceConfiguration.objects.create(
            dataspace=self.dataspace,
            policy_rules_config={"usage_policy_error": {"is_active": True}},
        )
        self.dataspace.refresh_from_db()
        config = get_effective_config("usage_policy_error", self.dataspace)
        self.assertTrue(config["is_active"])
        self.assertEqual(0, config["threshold"])


class EvaluateRulesTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        DataspaceConfiguration.objects.create(
            dataspace=self.dataspace,
            policy_rules_config={"usage_policy_error": {"is_active": True}},
        )
        self.product = make_product(self.dataspace)

    @patch("policy.engine.fire_policy_webhooks")
    @patch("policy.rules.UsagePolicyErrorRule.count_violations", return_value=3)
    def test_evaluate_rules_creates_violation_for_active_rule(self, _mock_count, mock_fire):
        new_violations, resolved_count = evaluate_rules(self.product)
        self.assertEqual(1, len(new_violations))
        self.assertEqual(0, resolved_count)
        self.assertEqual(1, ProductPolicyViolation.objects.filter(resolved=False).count())
        mock_fire.assert_called_once()

    @patch("policy.engine.fire_policy_webhooks")
    def test_evaluate_rules_resolves_violation_when_rule_inactive(self, _mock_fire):
        ProductPolicyViolation.objects.create(
            product=self.product,
            dataspace=self.dataspace,
            rule_type="license_coverage_gap",
            violation_count=2,
        )
        new_violations, resolved_count = evaluate_rules(self.product)
        self.assertEqual(0, len(new_violations))
        self.assertGreater(resolved_count, 0)
        self.assertTrue(
            ProductPolicyViolation.objects.get(rule_type="license_coverage_gap").resolved
        )
