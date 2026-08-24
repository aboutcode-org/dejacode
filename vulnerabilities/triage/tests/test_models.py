#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.test import TestCase

from component_catalog.tests import make_package
from dje.models import Dataspace
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_package
from vulnerabilities.models import VulnerabilityAnalysis
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.triage.models import AnalysisPreset
from vulnerabilities.triage.models import ProductTriageRuleset
from vulnerabilities.triage.models import TriageAction
from vulnerabilities.triage.models import TriageRecord
from vulnerabilities.triage.models import TriageRuleset
from vulnerabilities.triage.tests import make_analysis_preset
from vulnerabilities.triage.tests import make_product_triage_ruleset
from vulnerabilities.triage.tests import make_triage_ruleset


class AnalysisPresetModelTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    def test_save_requires_at_least_one_content_field(self):
        # A preset that only sets is_reachable has no content to apply to an analysis
        # and must be rejected. Unlike VulnerabilityAnalysis, is_reachable alone is not
        # sufficient for AnalysisPreset because the preset's purpose is to carry content.
        preset = AnalysisPreset(dataspace=self.dataspace, name="No content", is_reachable=True)
        with self.assertRaises(ValueError):
            preset.save()

    def test_save_accepts_detail_only(self):
        preset = AnalysisPreset(dataspace=self.dataspace, name="Detail only", detail="Some detail")
        preset.save()
        self.assertIsNotNone(preset.pk)

    def test_apply_to_analysis_copies_non_blank_fields_only(self):
        preset = make_analysis_preset(
            self.dataspace,
            state=AnalysisPreset.State.NOT_AFFECTED,
            justification="",
            detail="Not deployed",
        )
        package = make_package(self.dataspace)
        product = make_product(self.dataspace)
        product_package = make_product_package(product, package=package)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        analysis = VulnerabilityAnalysis(
            product_package=product_package,
            vulnerability=vulnerability,
            dataspace=self.dataspace,
            justification=VulnerabilityAnalysis.Justification.CODE_NOT_REACHABLE,
        )

        preset.apply_to_analysis(analysis)

        self.assertEqual(AnalysisPreset.State.NOT_AFFECTED, analysis.state)
        self.assertEqual("Not deployed", analysis.detail)
        # Blank preset field must not overwrite the pre-existing value on the analysis.
        self.assertEqual(
            VulnerabilityAnalysis.Justification.CODE_NOT_REACHABLE, analysis.justification
        )

    def test_apply_to_analysis_leaves_is_reachable_untouched_when_preset_value_is_none(self):
        preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.IN_TRIAGE)
        self.assertIsNone(preset.is_reachable)
        package = make_package(self.dataspace)
        product = make_product(self.dataspace)
        product_package = make_product_package(product, package=package)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        analysis = VulnerabilityAnalysis(
            product_package=product_package,
            vulnerability=vulnerability,
            dataspace=self.dataspace,
            is_reachable=True,
        )

        preset.apply_to_analysis(analysis)

        self.assertTrue(analysis.is_reachable)

    def test_apply_to_analysis_sets_is_reachable_when_preset_value_is_false(self):
        preset = make_analysis_preset(
            self.dataspace, state=AnalysisPreset.State.NOT_AFFECTED, is_reachable=False
        )
        package = make_package(self.dataspace)
        product = make_product(self.dataspace)
        product_package = make_product_package(product, package=package)
        vulnerability = make_vulnerability(self.dataspace, affecting=package)
        analysis = VulnerabilityAnalysis(
            product_package=product_package,
            vulnerability=vulnerability,
            dataspace=self.dataspace,
            is_reachable=True,
        )

        preset.apply_to_analysis(analysis)

        self.assertFalse(analysis.is_reachable)


class TriageRulesetModelTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    def test_str(self):
        ruleset = make_triage_ruleset(self.dataspace, name="My Ruleset")
        self.assertEqual("My Ruleset", str(ruleset))

    def test_default_ordering_is_by_descending_precedence_then_name(self):
        low = make_triage_ruleset(self.dataspace, name="B", precedence=100)
        high = make_triage_ruleset(self.dataspace, name="A", precedence=200)
        self.assertEqual([high, low], list(TriageRuleset.objects.all()))

    def test_precedence_is_unique_per_dataspace(self):
        make_triage_ruleset(self.dataspace, precedence=500)
        with self.assertRaises(Exception):
            make_triage_ruleset(self.dataspace, precedence=500)


class ProductTriageRulesetModelTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.ruleset = make_triage_ruleset(self.dataspace)

    def test_str(self):
        assignment = make_product_triage_ruleset(self.product, ruleset=self.ruleset)
        self.assertEqual(f"{self.product} / {self.ruleset}", str(assignment))

    def test_product_ruleset_pair_is_unique(self):
        make_product_triage_ruleset(self.product, ruleset=self.ruleset)
        with self.assertRaises(Exception):
            ProductTriageRuleset.objects.create(
                product=self.product, ruleset=self.ruleset, dataspace=self.dataspace
            )


class TriageRecordModelTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        make_product_package(self.product, package=self.package)
        self.vulnerability = make_vulnerability(self.dataspace, affecting=self.package)
        self.ruleset = make_triage_ruleset(self.dataspace, recommended_action=TriageAction.NOTIFY)

    def test_str(self):
        record = TriageRecord.objects.create(
            vulnerability=self.vulnerability,
            product=self.product,
            ruleset=self.ruleset,
            recommended_action=self.ruleset.recommended_action,
            dataspace=self.dataspace,
        )
        expected = (
            f"{self.vulnerability} / {self.product} /"
            f" {self.ruleset}: {self.ruleset.recommended_action}"
        )
        self.assertEqual(expected, str(record))


class TriageRecordQuerySetHighestPrecedenceTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        make_product_package(self.product, package=self.package)
        self.vulnerability = make_vulnerability(self.dataspace, affecting=self.package)

    def _make_record(self, ruleset):
        return TriageRecord.objects.create(
            vulnerability=self.vulnerability,
            product=self.product,
            ruleset=ruleset,
            recommended_action=ruleset.recommended_action,
            dataspace=self.dataspace,
        )

    def test_returns_the_record_of_the_highest_precedence_assigned_ruleset(self):
        low_ruleset = make_triage_ruleset(
            self.dataspace, precedence=100, recommended_action=TriageAction.NOTIFY
        )
        high_ruleset = make_triage_ruleset(
            self.dataspace, precedence=900, recommended_action=TriageAction.UPGRADE
        )
        make_product_triage_ruleset(self.product, ruleset=low_ruleset)
        make_product_triage_ruleset(self.product, ruleset=high_ruleset)
        self._make_record(low_ruleset)
        high_record = self._make_record(high_ruleset)

        winning_records = TriageRecord.objects.highest_precedence()

        self.assertEqual([high_record], list(winning_records))

    def test_excludes_records_for_a_ruleset_not_assigned_to_the_product(self):
        assigned_ruleset = make_triage_ruleset(self.dataspace, precedence=100)
        unassigned_ruleset = make_triage_ruleset(self.dataspace, precedence=900)
        make_product_triage_ruleset(self.product, ruleset=assigned_ruleset)
        assigned_record = self._make_record(assigned_ruleset)
        self._make_record(unassigned_ruleset)

        winning_records = TriageRecord.objects.highest_precedence()

        self.assertEqual([assigned_record], list(winning_records))

    def test_excludes_records_for_a_disabled_ruleset(self):
        ruleset = make_triage_ruleset(self.dataspace, enabled=False)
        make_product_triage_ruleset(self.product, ruleset=ruleset)
        self._make_record(ruleset)

        self.assertEqual(0, TriageRecord.objects.highest_precedence().count())

    def test_evaluates_precedence_independently_per_product(self):
        other_product = make_product(self.dataspace)
        make_product_package(other_product, package=self.package)
        low_ruleset = make_triage_ruleset(self.dataspace, precedence=100)
        high_ruleset = make_triage_ruleset(self.dataspace, precedence=900)
        make_product_triage_ruleset(self.product, ruleset=low_ruleset)
        make_product_triage_ruleset(other_product, ruleset=high_ruleset)
        low_record = self._make_record(low_ruleset)
        other_record = TriageRecord.objects.create(
            vulnerability=self.vulnerability,
            product=other_product,
            ruleset=high_ruleset,
            recommended_action=high_ruleset.recommended_action,
            dataspace=self.dataspace,
        )

        winning_records = TriageRecord.objects.highest_precedence()

        self.assertEqual({low_record, other_record}, set(winning_records))
