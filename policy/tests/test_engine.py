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
from policy.engine import evaluate_rule
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
