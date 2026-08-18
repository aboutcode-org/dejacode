#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import uuid

from django.test import TestCase

from component_catalog.tests import make_package
from dje.models import Dataspace
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_package
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.triage.models import TriageRecord
from vulnerabilities.triage.tasks import evaluate_all_products_vulnerability_triage_task
from vulnerabilities.triage.tasks import reevaluate_product_triage_rulesets_task
from vulnerabilities.triage.tests import make_product_triage_ruleset
from vulnerabilities.triage.tests import make_triage_ruleset

RISK_SCORE_RULE_CONFIG = {"risk_score": {"is_active": True, "min_risk_score": 8.0}}


class EvaluateAllProductsVulnerabilityTriageTaskTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        make_product_package(self.product, package=self.package)

    def test_evaluates_every_assignment_of_an_enabled_ruleset(self):
        vulnerability = make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        ruleset = make_triage_ruleset(
            self.dataspace, enabled=True, rules_config=RISK_SCORE_RULE_CONFIG
        )
        make_product_triage_ruleset(self.product, ruleset=ruleset)

        evaluate_all_products_vulnerability_triage_task()

        record = TriageRecord.objects.get()
        self.assertEqual(vulnerability, record.vulnerability)

    def test_skips_assignments_of_a_disabled_ruleset(self):
        make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        ruleset = make_triage_ruleset(
            self.dataspace, enabled=False, rules_config=RISK_SCORE_RULE_CONFIG
        )
        make_product_triage_ruleset(self.product, ruleset=ruleset)

        evaluate_all_products_vulnerability_triage_task()

        self.assertFalse(TriageRecord.objects.exists())

    def test_evaluates_assignments_across_multiple_products(self):
        other_product = make_product(self.dataspace)
        other_package = make_package(self.dataspace)
        make_product_package(other_product, package=other_package)
        make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        make_vulnerability(self.dataspace, affecting=other_package, risk_score=9.0)
        ruleset = make_triage_ruleset(self.dataspace, rules_config=RISK_SCORE_RULE_CONFIG)
        make_product_triage_ruleset(self.product, ruleset=ruleset)
        make_product_triage_ruleset(other_product, ruleset=ruleset)

        evaluate_all_products_vulnerability_triage_task()

        evaluated_product_ids = set(TriageRecord.objects.values_list("product_id", flat=True))
        self.assertEqual({self.product.id, other_product.id}, evaluated_product_ids)


class ReevaluateProductTriageRulesetsTaskTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        make_product_package(self.product, package=self.package)

    def test_evaluates_the_rulesets_assigned_to_the_product(self):
        vulnerability = make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        ruleset = make_triage_ruleset(
            self.dataspace, enabled=True, rules_config=RISK_SCORE_RULE_CONFIG
        )
        make_product_triage_ruleset(self.product, ruleset=ruleset)

        reevaluate_product_triage_rulesets_task(product_uuid=str(self.product.uuid))

        record = TriageRecord.objects.get()
        self.assertEqual(vulnerability, record.vulnerability)

    def test_logs_and_returns_when_the_product_does_not_exist(self):
        missing_uuid = str(uuid.uuid4())
        with self.assertLogs("vulnerabilities.triage.tasks", level="ERROR") as captured:
            reevaluate_product_triage_rulesets_task(product_uuid=missing_uuid)

        self.assertTrue(any("not found" in line for line in captured.output))
