#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import uuid
from unittest.mock import MagicMock
from unittest.mock import patch

from django.test import TestCase

from dje.models import Dataspace
from policy.engine import fire_policy_webhooks
from policy.tasks import evaluate_all_products_rules_task
from policy.tasks import evaluate_product_rules_task
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_status


class FirePolicyWebhooksTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    @patch("policy.engine.fire_webhooks")
    def test_fire_policy_webhooks_dispatches_violation_detected(self, mock_fire):
        violation = MagicMock()
        violation.rule_label = "Usage Policy Error"
        violation.violation_count = 3
        fire_policy_webhooks(self.product, new_violations=[violation], resolved_count=0)
        mock_fire.assert_called_once()
        event_name, kwargs = mock_fire.call_args[0][0], mock_fire.call_args[1]
        self.assertEqual("policy.violation_detected", event_name)
        self.assertIn("Policy violations detected", kwargs["payload_override"]["text"])
        self.assertIn("Usage Policy Error", kwargs["payload_override"]["text"])

    @patch("policy.engine.fire_webhooks")
    def test_fire_policy_webhooks_dispatches_violation_resolved(self, mock_fire):
        fire_policy_webhooks(self.product, new_violations=[], resolved_count=2)
        mock_fire.assert_called_once()
        event_name, kwargs = mock_fire.call_args[0][0], mock_fire.call_args[1]
        self.assertEqual("policy.violation_resolved", event_name)
        self.assertIn("2 policy violation(s) resolved", kwargs["payload_override"]["text"])

    @patch("policy.engine.fire_webhooks")
    def test_fire_policy_webhooks_dispatches_both_events(self, mock_fire):
        violation = MagicMock()
        violation.rule_label = "License Coverage Gap"
        violation.violation_count = 1
        fire_policy_webhooks(self.product, new_violations=[violation], resolved_count=1)
        self.assertEqual(2, mock_fire.call_count)
        events_fired = [c[0][0] for c in mock_fire.call_args_list]
        self.assertIn("policy.violation_detected", events_fired)
        self.assertIn("policy.violation_resolved", events_fired)

    @patch("policy.engine.fire_webhooks")
    def test_fire_policy_webhooks_silent_when_no_changes(self, mock_fire):
        fire_policy_webhooks(self.product, new_violations=[], resolved_count=0)
        mock_fire.assert_not_called()


class EvaluateProductRulesTaskTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    @patch("policy.tasks.evaluate_rules")
    def test_evaluate_product_rules_task_runs_evaluation(self, mock_evaluate):
        mock_evaluate.return_value = ([], 0)
        evaluate_product_rules_task(product_uuid=self.product.uuid)
        mock_evaluate.assert_called_once_with(self.product)

    @patch("policy.tasks.evaluate_rules")
    def test_evaluate_product_rules_task_unknown_uuid_logs_error(self, mock_evaluate):
        with self.assertLogs("policy.tasks", level="ERROR") as captured:
            evaluate_product_rules_task(product_uuid=uuid.uuid4())
        mock_evaluate.assert_not_called()
        self.assertTrue(any("not found" in line for line in captured.output))


class EvaluateAllProductsRulesTaskTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    @patch("policy.tasks.evaluate_rules")
    def test_evaluate_all_products_excludes_locked_by_default(self, mock_evaluate):
        # Regression: previously called .exclude_locked() on DataspacedQuerySet which lacks that
        # method. Now uses .exclude(configuration_status__is_locked=True) inline.
        mock_evaluate.return_value = ([], 0)
        active_product = make_product(self.dataspace)
        locked_status = make_product_status(self.dataspace, is_locked=True)
        locked_product = make_product(self.dataspace, configuration_status=locked_status)
        mock_evaluate.reset_mock()

        evaluate_all_products_rules_task()

        evaluated_products = [c[0][0] for c in mock_evaluate.call_args_list]
        self.assertIn(active_product, evaluated_products)
        self.assertNotIn(locked_product, evaluated_products)

    @patch("policy.tasks.evaluate_rules")
    def test_evaluate_all_products_includes_locked_when_requested(self, mock_evaluate):
        mock_evaluate.return_value = ([], 0)
        locked_status = make_product_status(self.dataspace, is_locked=True)
        locked_product = make_product(self.dataspace, configuration_status=locked_status)
        mock_evaluate.reset_mock()

        evaluate_all_products_rules_task(include_locked=True)

        evaluated_products = [c[0][0] for c in mock_evaluate.call_args_list]
        self.assertIn(locked_product, evaluated_products)

    @patch("policy.tasks.evaluate_rules")
    def test_evaluate_all_products_filters_by_uuids(self, mock_evaluate):
        mock_evaluate.return_value = ([], 0)
        product_a = make_product(self.dataspace)
        product_b = make_product(self.dataspace)
        mock_evaluate.reset_mock()

        evaluate_all_products_rules_task(product_uuids=[product_a.uuid])

        evaluated_products = [c[0][0] for c in mock_evaluate.call_args_list]
        self.assertIn(product_a, evaluated_products)
        self.assertNotIn(product_b, evaluated_products)

    @patch("policy.tasks.evaluate_rules")
    def test_evaluate_all_products_uuid_filter_still_excludes_locked(self, mock_evaluate):
        mock_evaluate.return_value = ([], 0)
        locked_status = make_product_status(self.dataspace, is_locked=True)
        locked_product = make_product(self.dataspace, configuration_status=locked_status)
        mock_evaluate.reset_mock()

        evaluate_all_products_rules_task(product_uuids=[locked_product.uuid])

        evaluated_products = [c[0][0] for c in mock_evaluate.call_args_list]
        self.assertNotIn(locked_product, evaluated_products)
