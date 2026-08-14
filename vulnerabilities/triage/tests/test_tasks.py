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
from product_portfolio.tests import make_product
from vulnerabilities.triage.tasks import evaluate_all_products_vulnerability_triage_task
from vulnerabilities.triage.tests import make_product_triage_ruleset
from vulnerabilities.triage.tests import make_triage_ruleset


class EvaluateAllProductsVulnerabilityTriageTaskTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    @patch("vulnerabilities.triage.tasks.evaluate_ruleset")
    def test_evaluates_every_assignment_of_an_enabled_ruleset(self, mock_evaluate):
        product = make_product(self.dataspace)
        ruleset = make_triage_ruleset(self.dataspace, enabled=True)
        make_product_triage_ruleset(product, ruleset=ruleset)

        evaluate_all_products_vulnerability_triage_task()

        mock_evaluate.assert_called_once_with(ruleset=ruleset, product=product)

    @patch("vulnerabilities.triage.tasks.evaluate_ruleset")
    def test_skips_assignments_of_a_disabled_ruleset(self, mock_evaluate):
        product = make_product(self.dataspace)
        ruleset = make_triage_ruleset(self.dataspace, enabled=False)
        make_product_triage_ruleset(product, ruleset=ruleset)

        evaluate_all_products_vulnerability_triage_task()

        mock_evaluate.assert_not_called()

    @patch("vulnerabilities.triage.tasks.evaluate_ruleset")
    def test_continues_evaluating_remaining_assignments_after_one_raises(self, mock_evaluate):
        failing_product = make_product(self.dataspace, name="a-product")
        ok_product = make_product(self.dataspace, name="b-product")
        ruleset = make_triage_ruleset(self.dataspace)
        make_product_triage_ruleset(failing_product, ruleset=ruleset)
        make_product_triage_ruleset(ok_product, ruleset=ruleset)
        mock_evaluate.side_effect = [Exception("boom"), None]

        with self.assertLogs("vulnerabilities.triage.tasks", level="ERROR") as captured:
            evaluate_all_products_vulnerability_triage_task()

        self.assertEqual(2, mock_evaluate.call_count)
        mock_evaluate.assert_any_call(ruleset=ruleset, product=failing_product)
        mock_evaluate.assert_any_call(ruleset=ruleset, product=ok_product)
        self.assertTrue(any("Triage evaluation failed" in line for line in captured.output))

    @patch("vulnerabilities.triage.tasks.evaluate_ruleset")
    def test_evaluates_assignments_across_multiple_products(self, mock_evaluate):
        product1 = make_product(self.dataspace)
        product2 = make_product(self.dataspace)
        ruleset = make_triage_ruleset(self.dataspace)
        make_product_triage_ruleset(product1, ruleset=ruleset)
        make_product_triage_ruleset(product2, ruleset=ruleset)

        evaluate_all_products_vulnerability_triage_task()

        evaluated_products = [call.kwargs["product"] for call in mock_evaluate.call_args_list]
        self.assertEqual({product1, product2}, set(evaluated_products))
