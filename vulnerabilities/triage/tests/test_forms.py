#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dje.models import Dataspace
from dje.tests import create_user
from product_portfolio.models import Product
from vulnerabilities.triage.forms import AnalysisPresetForm
from vulnerabilities.triage.forms import TriageRulesetForm
from vulnerabilities.triage.models import AnalysisPreset
from vulnerabilities.triage.models import TriageRuleset
from workflow.models import RequestTemplate


class AnalysisPresetFormTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    def test_rejects_a_preset_with_no_content_field_set(self):
        # Mirrors VulnerabilityAnalysisForm.clean: is_reachable alone is not enough content
        # to apply, and must be caught here rather than crash in AnalysisPreset.save().
        data = {"name": "No content", "is_reachable": True}
        form = AnalysisPresetForm(data=data, instance=AnalysisPreset(dataspace=self.dataspace))
        self.assertFalse(form.is_valid())
        msg = "At least one of state, justification, responses or detail must be provided."
        self.assertEqual({"__all__": [msg]}, form.errors)

    def test_accepts_a_preset_with_detail_only(self):
        data = {"name": "Detail only", "detail": "Some detail"}
        form = AnalysisPresetForm(data=data, instance=AnalysisPreset(dataspace=self.dataspace))
        self.assertTrue(form.is_valid(), form.errors)
        preset = form.save()
        self.assertEqual("Some detail", preset.detail)


class TriageRulesetFormTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    def test_adds_a_dynamic_field_pair_for_every_registered_rule(self):
        form = TriageRulesetForm(instance=TriageRuleset(dataspace=self.dataspace))
        self.assertIn("rule_risk_score_enabled", form.fields)
        self.assertIn("rule_risk_score_min_risk_score", form.fields)
        self.assertIn("rule_exploited_vulnerability_enabled", form.fields)
        self.assertNotIn("rule_exploited_vulnerability_min_risk_score", form.fields)

    def test_save_builds_rules_config_from_the_submitted_rule_fields(self):
        data = {
            "name": "My Ruleset",
            "precedence": 100,
            "rule_risk_score_enabled": "on",
            "rule_risk_score_min_risk_score": "7.5",
            "rule_exploited_vulnerability_enabled": "on",
        }
        form = TriageRulesetForm(data=data, instance=TriageRuleset(dataspace=self.dataspace))
        self.assertTrue(form.is_valid(), form.errors)

        ruleset = form.save()

        self.assertEqual(
            {"is_active": True, "min_risk_score": 7.5}, ruleset.rules_config["risk_score"]
        )
        self.assertEqual({"is_active": True}, ruleset.rules_config["exploited_vulnerability"])

    def test_save_drops_an_inactive_rule_that_has_no_parameters(self):
        data = {"name": "My Ruleset", "precedence": 100}
        form = TriageRulesetForm(data=data, instance=TriageRuleset(dataspace=self.dataspace))
        self.assertTrue(form.is_valid(), form.errors)

        ruleset = form.save()

        self.assertNotIn("exploited_vulnerability", ruleset.rules_config)

    def test_save_keeps_an_inactive_rule_that_has_parameters_with_their_defaults(self):
        data = {"name": "My Ruleset", "precedence": 100}
        form = TriageRulesetForm(data=data, instance=TriageRuleset(dataspace=self.dataspace))
        self.assertTrue(form.is_valid(), form.errors)

        ruleset = form.save()

        self.assertEqual(
            {"is_active": False, "min_risk_score": 8.0}, ruleset.rules_config["risk_score"]
        )

    def test_rejects_a_request_template_with_no_creator(self):
        # A RequestTemplate normally always has a creator (the admin form sets it on
        # addition), but nothing at the DB level guarantees it, reject it here rather
        # than let create_triage_requests crash later with an IntegrityError.
        request_template = RequestTemplate.objects.create(
            name="Broken Template",
            description="Header",
            dataspace=self.dataspace,
            content_type=ContentType.objects.get_for_model(Product),
        )
        data = {"name": "My Ruleset", "precedence": 100, "request_template": request_template.pk}
        form = TriageRulesetForm(data=data, instance=TriageRuleset(dataspace=self.dataspace))

        self.assertFalse(form.is_valid())

        msg = "This request template has no creator and cannot be used to open requests."
        self.assertEqual({"request_template": [msg]}, form.errors)

    def test_accepts_a_request_template_with_a_creator(self):
        requester = create_user("requester", self.dataspace)
        request_template = RequestTemplate.objects.create(
            name="Valid Template",
            description="Header",
            dataspace=self.dataspace,
            content_type=ContentType.objects.get_for_model(Product),
            created_by=requester,
        )
        data = {"name": "My Ruleset", "precedence": 100, "request_template": request_template.pk}
        form = TriageRulesetForm(data=data, instance=TriageRuleset(dataspace=self.dataspace))

        self.assertTrue(form.is_valid(), form.errors)
