#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from component_catalog.tests import make_package
from dje.models import Dataspace
from dje.tests import create_superuser
from dje.tests import create_user
from product_portfolio.models import Product
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_package
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.triage.engine import evaluate_ruleset
from vulnerabilities.triage.models import TriageAction
from vulnerabilities.triage.models import TriageRecord
from vulnerabilities.triage.tests import make_product_triage_ruleset
from vulnerabilities.triage.tests import make_triage_ruleset
from workflow.models import RequestTemplate

RULE_CONFIG_DATA = {
    "rule_risk_score_enabled": "on",
    "rule_risk_score_min_risk_score": "8.0",
}


class TriageRulesetAdminSaveModelTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.client.login(username="nexb_user", password="secret")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        make_product_package(self.product, package=self.package)

    def test_creating_a_ruleset_does_not_evaluate_any_product(self):
        make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        url = reverse("admin:vulnerabilities_triage_triageruleset_add")
        data = {
            "name": "My Ruleset",
            "precedence": 100,
            "enabled": "on",
            **RULE_CONFIG_DATA,
        }

        response = self.client.post(url, data)

        self.assertEqual(302, response.status_code)
        self.assertFalse(TriageRecord.objects.exists())

    def test_updating_an_enabled_assigned_ruleset_reevaluates_its_products(self):
        vulnerability = make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        ruleset = make_triage_ruleset(
            self.dataspace,
            recommended_action=TriageAction.UPGRADE,
            enabled=True,
        )
        make_product_triage_ruleset(self.product, ruleset=ruleset)
        self.assertFalse(TriageRecord.objects.exists())

        url = ruleset.get_admin_url()
        data = {
            "name": ruleset.name,
            "precedence": ruleset.precedence,
            "recommended_action": TriageAction.UPGRADE,
            "enabled": "on",
            **RULE_CONFIG_DATA,
        }

        response = self.client.post(url, data)

        self.assertEqual(302, response.status_code)
        record = TriageRecord.objects.get()
        self.assertEqual(vulnerability, record.vulnerability)

    def test_disabling_a_ruleset_deletes_its_triage_records(self):
        make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        ruleset = make_triage_ruleset(
            self.dataspace,
            recommended_action=TriageAction.UPGRADE,
            enabled=True,
            rules_config={"risk_score": {"is_active": True, "min_risk_score": 8.0}},
        )
        make_product_triage_ruleset(self.product, ruleset=ruleset)
        evaluate_ruleset(ruleset, self.product)
        self.assertTrue(TriageRecord.objects.exists())

        url = ruleset.get_admin_url()
        data = {
            "name": ruleset.name,
            "precedence": ruleset.precedence,
            "recommended_action": TriageAction.UPGRADE,
            # "enabled" omitted: disables the ruleset.
            **RULE_CONFIG_DATA,
        }

        response = self.client.post(url, data)

        self.assertEqual(302, response.status_code)
        self.assertFalse(TriageRecord.objects.exists())

    def test_disabling_a_ruleset_keeps_records_that_have_an_open_request(self):
        vulnerability = make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        requester = create_user("requester", self.dataspace)
        request_template = RequestTemplate.objects.create(
            name="Template",
            description="Header",
            dataspace=self.dataspace,
            content_type=ContentType.objects.get_for_model(Product),
            created_by=requester,
        )
        ruleset = make_triage_ruleset(
            self.dataspace,
            recommended_action=TriageAction.UPGRADE,
            enabled=True,
            request_template=request_template,
            rules_config={"risk_score": {"is_active": True, "min_risk_score": 8.0}},
        )
        make_product_triage_ruleset(self.product, ruleset=ruleset)
        evaluate_ruleset(ruleset, self.product)
        record = TriageRecord.objects.get()
        self.assertIsNotNone(record.request)

        url = ruleset.get_admin_url()
        data = {
            "name": ruleset.name,
            "precedence": ruleset.precedence,
            "recommended_action": TriageAction.UPGRADE,
            # "enabled" omitted: disables the ruleset.
            **RULE_CONFIG_DATA,
        }

        response = self.client.post(url, data)

        self.assertEqual(302, response.status_code)
        record.refresh_from_db()
        self.assertEqual(vulnerability, record.vulnerability)

    def test_disabling_then_reenabling_a_ruleset_reuses_the_existing_request(self):
        # Regression: disabling then re-enabling a ruleset used to reopen a new Request
        # instead of reconnecting to the one already tracking this vulnerability.
        make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        requester = create_user("requester", self.dataspace)
        request_template = RequestTemplate.objects.create(
            name="Template",
            description="Header",
            dataspace=self.dataspace,
            content_type=ContentType.objects.get_for_model(Product),
            created_by=requester,
        )
        ruleset = make_triage_ruleset(
            self.dataspace,
            recommended_action=TriageAction.UPGRADE,
            enabled=True,
            request_template=request_template,
            rules_config={"risk_score": {"is_active": True, "min_risk_score": 8.0}},
        )
        make_product_triage_ruleset(self.product, ruleset=ruleset)
        evaluate_ruleset(ruleset, self.product)
        original_request = TriageRecord.objects.get().request
        self.assertIsNotNone(original_request)

        url = ruleset.get_admin_url()
        base_data = {
            "name": ruleset.name,
            "precedence": ruleset.precedence,
            "recommended_action": TriageAction.UPGRADE,
            **RULE_CONFIG_DATA,
        }
        self.client.post(url, base_data)  # Disable.
        self.client.post(url, {**base_data, "enabled": "on"})  # Re-enable.

        self.assertEqual(1, ruleset.triage_records.count())
        self.assertEqual(original_request, TriageRecord.objects.get().request)
