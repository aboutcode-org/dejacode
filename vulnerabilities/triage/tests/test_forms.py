#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.test import TestCase

from dje.models import Dataspace
from vulnerabilities.triage.forms import TriageRulesetForm
from vulnerabilities.triage.models import TriageRuleset


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
