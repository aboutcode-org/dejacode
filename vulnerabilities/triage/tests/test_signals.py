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
from vulnerabilities.triage.models import AnalysisPreset
from vulnerabilities.triage.tests import make_analysis_preset


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
    def test_deleting_a_preset_owned_analysis_does_not_reevaluate(self, mock_reevaluate):
        # A write or delete made by the engine itself always happens inside an evaluation
        # pass that already covers every ruleset assigned to the product, so re-triggering
        # here would recursively re-run that same pass.
        preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.NOT_AFFECTED)
        apply_preset_for_vulnerabilities(preset, self.product, [self.vulnerability.pk])
        analysis = VulnerabilityAnalysis.objects.get()
        mock_reevaluate.reset_mock()

        analysis.delete()

        mock_reevaluate.assert_not_called()


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
