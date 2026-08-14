#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest.mock import patch

from django.test import TestCase

from component_catalog.tests import make_package
from dje.models import Dataspace
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_package
from vulnerabilities.models import VulnerabilityAnalysis
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.tests import make_vulnerability_analysis
from vulnerabilities.triage.engine import apply_preset_for_vulnerabilities
from vulnerabilities.triage.engine import evaluate_ruleset
from vulnerabilities.triage.models import AnalysisPreset
from vulnerabilities.triage.models import TriageAction
from vulnerabilities.triage.models import TriageRecord
from vulnerabilities.triage.signals import reevaluate_product_rulesets
from vulnerabilities.triage.tests import make_analysis_preset
from vulnerabilities.triage.tests import make_product_triage_ruleset
from vulnerabilities.triage.tests import make_triage_ruleset


class ReevaluateProductRulesetsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    @patch("vulnerabilities.triage.signals.evaluate_ruleset")
    def test_evaluates_every_enabled_ruleset_assigned_to_the_product(self, mock_evaluate):
        ruleset = make_triage_ruleset(self.dataspace, enabled=True)
        make_product_triage_ruleset(self.product, ruleset=ruleset)

        reevaluate_product_rulesets(self.product)

        mock_evaluate.assert_called_once_with(
            ruleset=ruleset, product=self.product, apply_preset=True
        )

    @patch("vulnerabilities.triage.signals.evaluate_ruleset")
    def test_skips_disabled_ruleset_assignments(self, mock_evaluate):
        ruleset = make_triage_ruleset(self.dataspace, enabled=False)
        make_product_triage_ruleset(self.product, ruleset=ruleset)

        reevaluate_product_rulesets(self.product)

        mock_evaluate.assert_not_called()

    @patch("vulnerabilities.triage.signals.evaluate_ruleset")
    def test_apply_preset_flag_is_forwarded(self, mock_evaluate):
        ruleset = make_triage_ruleset(self.dataspace, enabled=True)
        make_product_triage_ruleset(self.product, ruleset=ruleset)

        reevaluate_product_rulesets(self.product, apply_preset=False)

        mock_evaluate.assert_called_once_with(
            ruleset=ruleset, product=self.product, apply_preset=False
        )


class TriageRulesetSaveSignalTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    @patch("vulnerabilities.triage.signals.evaluate_ruleset")
    def test_creating_a_ruleset_does_not_trigger_evaluation(self, mock_evaluate):
        make_triage_ruleset(self.dataspace)
        mock_evaluate.assert_not_called()

    @patch("vulnerabilities.triage.signals.evaluate_ruleset")
    def test_updating_an_enabled_assigned_ruleset_reevaluates_its_products(self, mock_evaluate):
        ruleset = make_triage_ruleset(self.dataspace)
        make_product_triage_ruleset(self.product, ruleset=ruleset)
        mock_evaluate.reset_mock()

        ruleset.description = "updated"
        ruleset.save()

        mock_evaluate.assert_called_once_with(ruleset=ruleset, product=self.product)

    @patch("vulnerabilities.triage.signals.evaluate_ruleset")
    def test_updating_an_unassigned_ruleset_does_not_trigger_evaluation(self, mock_evaluate):
        ruleset = make_triage_ruleset(self.dataspace)
        mock_evaluate.reset_mock()

        ruleset.description = "updated"
        ruleset.save()

        mock_evaluate.assert_not_called()

    @patch("vulnerabilities.triage.signals.evaluate_ruleset")
    def test_disabling_a_ruleset_deletes_its_triage_records_instead_of_evaluating(
        self, mock_evaluate
    ):
        package = make_package(self.dataspace)
        make_product_package(self.product, package=package)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        ruleset = make_triage_ruleset(self.dataspace, action=TriageAction.NOTIFY)
        make_product_triage_ruleset(self.product, ruleset=ruleset)
        TriageRecord.objects.create(
            vulnerability=vulnerability,
            product=self.product,
            ruleset=ruleset,
            action=ruleset.action,
            dataspace=self.dataspace,
        )
        mock_evaluate.reset_mock()

        ruleset.enabled = False
        ruleset.save()

        self.assertFalse(TriageRecord.objects.exists())
        mock_evaluate.assert_not_called()


class DeleteTriageRecordsOnUnassignSignalTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        self.product_package = make_product_package(self.product, package=self.package)
        self.vulnerability = make_vulnerability(
            self.dataspace, affecting=self.package, risk_score=9.0
        )
        self.ruleset = make_triage_ruleset(
            self.dataspace,
            action=TriageAction.NOTIFY,
            rules_config={"risk_score": {"is_active": True, "min_risk_score": 8.0}},
        )
        self.assignment = make_product_triage_ruleset(self.product, ruleset=self.ruleset)
        evaluate_ruleset(self.ruleset, self.product)
        self.assertTrue(TriageRecord.objects.exists())

    def test_unassigning_the_ruleset_deletes_its_triage_records_for_the_product(self):
        self.assignment.delete()
        self.assertFalse(TriageRecord.objects.exists())

    def test_does_not_delete_records_belonging_to_another_product(self):
        other_product = make_product(self.dataspace)
        make_product_package(other_product, package=self.package)
        make_product_triage_ruleset(other_product, ruleset=self.ruleset)
        evaluate_ruleset(self.ruleset, other_product)
        other_record = TriageRecord.objects.get(product=other_product)

        self.assignment.delete()

        self.assertEqual([other_record], list(TriageRecord.objects.all()))

    def test_deletes_the_preset_analyses_tied_to_the_deleted_records(self):
        preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.NOT_AFFECTED)
        self.ruleset.analysis_preset = preset
        self.ruleset.save()  # Re-evaluates the assigned product and auto-applies the preset.
        self.assertTrue(VulnerabilityAnalysis.objects.exists())

        self.assignment.delete()

        self.assertFalse(VulnerabilityAnalysis.objects.exists())

    def test_does_not_delete_human_owned_analyses(self):
        # A human analysis set before the preset exists is never auto-applied over, so it
        # keeps applied_by_preset=None and must survive the preset cleanup below.
        make_vulnerability_analysis(self.product_package, self.vulnerability, state="exploitable")
        preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.NOT_AFFECTED)
        self.ruleset.analysis_preset = preset
        self.ruleset.save()

        self.assignment.delete()

        analysis = VulnerabilityAnalysis.objects.get()
        self.assertEqual("exploitable", analysis.state)
        self.assertIsNone(analysis.applied_by_preset)


class ReevaluateOnAnalysisChangeSignalTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        self.product_package = make_product_package(self.product, package=self.package)
        self.vulnerability = make_vulnerability(self.dataspace, affecting=self.package)

    @patch("vulnerabilities.triage.signals.reevaluate_product_rulesets")
    def test_saving_a_human_owned_analysis_reevaluates_with_preset_application_enabled(
        self, mock_reevaluate
    ):
        make_vulnerability_analysis(self.product_package, self.vulnerability, state="exploitable")
        mock_reevaluate.assert_called_once_with(self.product, apply_preset=True)

    @patch("vulnerabilities.triage.signals.reevaluate_product_rulesets")
    def test_saving_a_preset_applied_analysis_does_not_reevaluate(self, mock_reevaluate):
        preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.NOT_AFFECTED)
        apply_preset_for_vulnerabilities(preset, self.product, [self.vulnerability.pk])
        mock_reevaluate.assert_not_called()

    @patch("vulnerabilities.triage.signals.reevaluate_product_rulesets")
    def test_deleting_a_human_owned_analysis_reevaluates_with_preset_application_disabled(
        self, mock_reevaluate
    ):
        analysis = make_vulnerability_analysis(
            self.product_package, self.vulnerability, state="exploitable"
        )
        mock_reevaluate.reset_mock()

        analysis.delete()

        mock_reevaluate.assert_called_once_with(self.product, apply_preset=False)

    @patch("vulnerabilities.triage.signals.reevaluate_product_rulesets")
    def test_deleting_a_preset_owned_analysis_reevaluates_with_preset_application_enabled(
        self, mock_reevaluate
    ):
        preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.NOT_AFFECTED)
        apply_preset_for_vulnerabilities(preset, self.product, [self.vulnerability.pk])
        analysis = VulnerabilityAnalysis.objects.get()
        mock_reevaluate.reset_mock()

        analysis.delete()

        mock_reevaluate.assert_called_once_with(self.product, apply_preset=True)


class ReevaluateOnProductPackageChangeSignalTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    @patch("vulnerabilities.triage.signals.reevaluate_product_rulesets")
    def test_adding_a_product_package_reevaluates_the_product(self, mock_reevaluate):
        make_product_package(self.product)
        mock_reevaluate.assert_called_once_with(self.product)

    @patch("vulnerabilities.triage.signals.reevaluate_product_rulesets")
    def test_removing_a_product_package_reevaluates_the_product(self, mock_reevaluate):
        product_package = make_product_package(self.product)
        mock_reevaluate.reset_mock()

        product_package.delete()

        mock_reevaluate.assert_called_once_with(self.product)
