#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from io import StringIO
from unittest import mock

from django.core import management
from django.core.management.base import CommandError
from django.test import TestCase

from component_catalog.tests import make_package
from dje.models import Dataspace
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_package
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.triage.models import AnalysisPreset
from vulnerabilities.triage.models import TriageRecord
from vulnerabilities.triage.models import TriageRuleset
from vulnerabilities.triage.tests import make_product_triage_ruleset
from vulnerabilities.triage.tests import make_triage_ruleset


class CreateTriageRulesetsCommandTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    def test_raises_for_a_missing_dataspace(self):
        with self.assertRaises(CommandError) as error:
            management.call_command("create_triage_rulesets", "does-not-exist")
        self.assertEqual('Dataspace "does-not-exist" does not exist.', str(error.exception))

    def test_creates_the_reference_rulesets_and_presets(self):
        management.call_command("create_triage_rulesets", self.dataspace.name, stdout=StringIO())

        self.assertEqual(8, TriageRuleset.objects.filter(dataspace=self.dataspace).count())
        self.assertEqual(4, AnalysisPreset.objects.filter(dataspace=self.dataspace).count())

    def test_raises_when_rulesets_already_exist_without_reset(self):
        management.call_command("create_triage_rulesets", self.dataspace.name, stdout=StringIO())

        with self.assertRaises(CommandError) as error:
            management.call_command(
                "create_triage_rulesets", self.dataspace.name, stdout=StringIO()
            )
        expected = (
            f'Dataspace "{self.dataspace.name}" already has triage rulesets.'
            " Use --reset to delete and recreate them."
        )
        self.assertEqual(expected, str(error.exception))

    def test_reset_with_noinput_deletes_and_recreates_without_prompting(self):
        management.call_command("create_triage_rulesets", self.dataspace.name, stdout=StringIO())
        ruleset_count = TriageRuleset.objects.filter(dataspace=self.dataspace).count()

        management.call_command(
            "create_triage_rulesets",
            self.dataspace.name,
            "--reset",
            "--noinput",
            stdout=StringIO(),
        )

        new_count = TriageRuleset.objects.filter(dataspace=self.dataspace).count()
        self.assertEqual(ruleset_count, new_count)

    @mock.patch("builtins.input")
    def test_reset_cancelled_when_prompt_is_declined(self, mock_input):
        mock_input.return_value = "no"
        management.call_command("create_triage_rulesets", self.dataspace.name, stdout=StringIO())

        out = StringIO()
        management.call_command(
            "create_triage_rulesets", self.dataspace.name, "--reset", stdout=out
        )

        self.assertIn("Reset cancelled.", out.getvalue())
        self.assertEqual(8, TriageRuleset.objects.filter(dataspace=self.dataspace).count())

    def test_links_each_preset_to_its_ruleset(self):
        management.call_command("create_triage_rulesets", self.dataspace.name, stdout=StringIO())

        ruleset = TriageRuleset.objects.get(
            dataspace=self.dataspace, name="Dev-Only Vulnerable Package"
        )
        self.assertEqual("Auto-Close - Dev Only", ruleset.analysis_preset.name)


class EvaluateTriageCommandTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        make_product_package(self.product, package=self.package)

    def test_raises_for_a_missing_dataspace(self):
        with self.assertRaises(CommandError) as error:
            management.call_command("evaluate_triage", "does-not-exist")
        self.assertEqual('Dataspace "does-not-exist" does not exist.', str(error.exception))

    def test_reports_no_active_assignments(self):
        out = StringIO()
        management.call_command("evaluate_triage", self.dataspace.name, stdout=out)
        self.assertIn("No active ruleset assignments found.", out.getvalue())

    def test_evaluates_the_active_assignments(self):
        vulnerability = make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        ruleset = make_triage_ruleset(
            self.dataspace,
            enabled=True,
            rules_config={"risk_score": {"is_active": True, "min_risk_score": 8.0}},
        )
        make_product_triage_ruleset(self.product, ruleset=ruleset)

        out = StringIO()
        management.call_command("evaluate_triage", self.dataspace.name, stdout=out)

        record = TriageRecord.objects.get()
        self.assertEqual(vulnerability, record.vulnerability)
        self.assertIn("Evaluated: 1/1", out.getvalue())

    def test_skips_assignments_of_a_disabled_ruleset(self):
        ruleset = make_triage_ruleset(self.dataspace, enabled=False)
        make_product_triage_ruleset(self.product, ruleset=ruleset)

        out = StringIO()
        management.call_command("evaluate_triage", self.dataspace.name, stdout=out)

        self.assertIn("No active ruleset assignments found.", out.getvalue())
