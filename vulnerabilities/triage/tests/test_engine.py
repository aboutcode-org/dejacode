#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from component_catalog.tests import make_package
from dje.models import Dataspace
from dje.tests import create_user
from product_portfolio.models import Product
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_package
from vulnerabilities.models import VulnerabilityAnalysis
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.tests import make_vulnerability_analysis
from vulnerabilities.triage.engine import apply_preset_for_vulnerabilities
from vulnerabilities.triage.engine import collect_matches
from vulnerabilities.triage.engine import create_triage_requests
from vulnerabilities.triage.engine import delete_preset_analyses_for_product
from vulnerabilities.triage.engine import evaluate_ruleset
from vulnerabilities.triage.engine import sync_triage_records
from vulnerabilities.triage.models import AnalysisPreset
from vulnerabilities.triage.models import TriageAction
from vulnerabilities.triage.models import TriageRecord
from vulnerabilities.triage.tests import make_analysis_preset
from vulnerabilities.triage.tests import make_triage_ruleset
from workflow.models import Request
from workflow.models import RequestTemplate


class CollectMatchesTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        make_product_package(self.product, package=self.package)

    def test_collects_vulnerabilities_matching_an_active_rule(self):
        vulnerability = make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        ruleset = make_triage_ruleset(
            self.dataspace,
            rules_config={"risk_score": {"is_active": True, "min_risk_score": 8.0}},
        )
        matches = collect_matches(ruleset, self.product)
        self.assertEqual({vulnerability.pk: ["risk_score"]}, matches)

    def test_skips_inactive_rule(self):
        make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        ruleset = make_triage_ruleset(
            self.dataspace,
            rules_config={"risk_score": {"is_active": False, "min_risk_score": 8.0}},
        )
        matches = collect_matches(ruleset, self.product)
        self.assertEqual({}, matches)

    def test_skips_unknown_rule_type(self):
        make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        ruleset = make_triage_ruleset(
            self.dataspace,
            rules_config={"not_a_real_rule": {"is_active": True}},
        )
        matches = collect_matches(ruleset, self.product)
        self.assertEqual({}, matches)

    def test_lists_every_rule_type_that_matches_the_same_vulnerability(self):
        vulnerability = make_vulnerability(
            self.dataspace, affecting=self.package, risk_score=9.0, exploitability=2.0
        )
        ruleset = make_triage_ruleset(
            self.dataspace,
            rules_config={
                "risk_score": {"is_active": True, "min_risk_score": 8.0},
                "exploited_vulnerability": {"is_active": True},
            },
        )
        matches = collect_matches(ruleset, self.product)
        self.assertEqual({"risk_score", "exploited_vulnerability"}, set(matches[vulnerability.pk]))

    def test_passes_rule_specific_parameters_to_the_handler(self):
        vulnerability = make_vulnerability(self.dataspace, affecting=self.package, risk_score=5.0)
        ruleset = make_triage_ruleset(
            self.dataspace,
            rules_config={"risk_score": {"is_active": True, "min_risk_score": 5.0}},
        )
        matches = collect_matches(ruleset, self.product)
        self.assertEqual({vulnerability.pk: ["risk_score"]}, matches)


class ApplyPresetForVulnerabilitiesTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        self.product_package = make_product_package(self.product, package=self.package)
        self.vulnerability = make_vulnerability(self.dataspace, affecting=self.package)

    def test_creates_a_new_analysis_from_the_preset(self):
        preset = make_analysis_preset(
            self.dataspace,
            state=AnalysisPreset.State.NOT_AFFECTED,
            detail="Not deployed",
        )
        apply_preset_for_vulnerabilities(preset, self.product, [self.vulnerability.pk])
        analysis = VulnerabilityAnalysis.objects.get(
            product_package=self.product_package, vulnerability=self.vulnerability
        )
        self.assertEqual(AnalysisPreset.State.NOT_AFFECTED, analysis.state)
        self.assertEqual(preset, analysis.applied_by_preset)

    def test_does_not_overwrite_a_human_owned_analysis(self):
        make_vulnerability_analysis(self.product_package, self.vulnerability, state="exploitable")
        preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.NOT_AFFECTED)
        apply_preset_for_vulnerabilities(preset, self.product, [self.vulnerability.pk])
        analysis = VulnerabilityAnalysis.objects.get(
            product_package=self.product_package, vulnerability=self.vulnerability
        )
        self.assertEqual("exploitable", analysis.state)
        self.assertIsNone(analysis.applied_by_preset)

    def test_updates_an_existing_preset_owned_analysis(self):
        first_preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.IN_TRIAGE)
        apply_preset_for_vulnerabilities(first_preset, self.product, [self.vulnerability.pk])

        second_preset = make_analysis_preset(
            self.dataspace, state=AnalysisPreset.State.NOT_AFFECTED
        )
        apply_preset_for_vulnerabilities(second_preset, self.product, [self.vulnerability.pk])

        analysis = VulnerabilityAnalysis.objects.get(
            product_package=self.product_package, vulnerability=self.vulnerability
        )
        self.assertEqual(AnalysisPreset.State.NOT_AFFECTED, analysis.state)
        self.assertEqual(second_preset, analysis.applied_by_preset)
        self.assertEqual(1, VulnerabilityAnalysis.objects.count())

    def test_skips_creation_when_the_preset_has_no_content_field_set(self):
        # An AnalysisPreset always requires at least one content field to be saved (see
        # VulnerabilityAnalysisContentMixin.save), so this can only happen with an in-memory
        # preset. This exercises the defensive guard against saving a content-less analysis.
        content_less_preset = AnalysisPreset(dataspace=self.dataspace, is_reachable=True)
        apply_preset_for_vulnerabilities(content_less_preset, self.product, [self.vulnerability.pk])
        self.assertFalse(VulnerabilityAnalysis.objects.exists())

    def test_does_nothing_when_no_product_package_carries_the_vulnerability(self):
        other_package = make_package(self.dataspace)
        other_vulnerability = make_vulnerability(self.dataspace, affecting=other_package)
        preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.NOT_AFFECTED)
        apply_preset_for_vulnerabilities(preset, self.product, [other_vulnerability.pk])
        self.assertFalse(VulnerabilityAnalysis.objects.exists())


class DeletePresetAnalysesForProductTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        self.product_package = make_product_package(self.product, package=self.package)
        self.vulnerability = make_vulnerability(self.dataspace, affecting=self.package)
        self.preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.IN_TRIAGE)

    def test_deletes_the_matching_preset_owned_analysis(self):
        apply_preset_for_vulnerabilities(self.preset, self.product, [self.vulnerability.pk])
        delete_preset_analyses_for_product(self.preset.pk, self.product, [self.vulnerability.pk])
        self.assertFalse(VulnerabilityAnalysis.objects.exists())

    def test_does_not_delete_analyses_owned_by_a_different_preset(self):
        other_preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.EXPLOITABLE)
        apply_preset_for_vulnerabilities(other_preset, self.product, [self.vulnerability.pk])
        delete_preset_analyses_for_product(self.preset.pk, self.product, [self.vulnerability.pk])
        self.assertTrue(VulnerabilityAnalysis.objects.exists())

    def test_does_not_delete_analyses_from_another_product(self):
        other_product = make_product(self.dataspace)
        other_product_package = make_product_package(other_product, package=self.package)
        make_vulnerability_analysis(
            other_product_package,
            self.vulnerability,
            state="in_triage",
            applied_by_preset=self.preset,
        )
        delete_preset_analyses_for_product(self.preset.pk, self.product, [self.vulnerability.pk])
        self.assertTrue(VulnerabilityAnalysis.objects.exists())


class SyncTriageRecordsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        self.product_package = make_product_package(self.product, package=self.package)
        self.vulnerability = make_vulnerability(self.dataspace, affecting=self.package)
        self.ruleset = make_triage_ruleset(self.dataspace, action=TriageAction.UPGRADE)

    def test_creates_one_record_per_matching_vulnerability(self):
        sync_triage_records(self.ruleset, self.product, {self.vulnerability.pk: ["risk_score"]})
        record = TriageRecord.objects.get()
        self.assertEqual(self.vulnerability, record.vulnerability)
        self.assertEqual(self.product, record.product)
        self.assertEqual(self.ruleset, record.ruleset)
        self.assertEqual(TriageAction.UPGRADE, record.action)
        self.assertEqual(["risk_score"], record.matched_rules)

    def test_reevaluation_updates_matched_rules_without_duplicating_the_record(self):
        sync_triage_records(self.ruleset, self.product, {self.vulnerability.pk: ["risk_score"]})
        first_detected_date = TriageRecord.objects.get().detected_date

        sync_triage_records(
            self.ruleset,
            self.product,
            {self.vulnerability.pk: ["risk_score", "exploited_vulnerability"]},
        )

        self.assertEqual(1, TriageRecord.objects.count())
        record = TriageRecord.objects.get()
        self.assertEqual(["risk_score", "exploited_vulnerability"], record.matched_rules)
        self.assertEqual(first_detected_date, record.detected_date)

    def test_deletes_records_for_vulnerabilities_that_no_longer_match(self):
        sync_triage_records(self.ruleset, self.product, {self.vulnerability.pk: ["risk_score"]})
        sync_triage_records(self.ruleset, self.product, {})
        self.assertFalse(TriageRecord.objects.exists())

    def test_keeps_a_stale_record_that_has_an_open_request(self):
        # A record with a Request already attached must survive going stale, so a later
        # rematch reconnects to the same Request instead of opening a duplicate.
        sync_triage_records(self.ruleset, self.product, {self.vulnerability.pk: ["risk_score"]})
        record = TriageRecord.objects.get()
        request = Request.objects.create(
            request_template=RequestTemplate.objects.create(
                name="Template",
                description="Header",
                dataspace=self.dataspace,
                content_type=ContentType.objects.get_for_model(Product),
                created_by=create_user("requester", self.dataspace),
            ),
            dataspace=self.dataspace,
            requester=create_user("requester2", self.dataspace),
            title="Vulnerability request",
            product_context=self.product,
        )
        record.request = request
        record.save()

        sync_triage_records(self.ruleset, self.product, {})
        self.assertEqual(1, TriageRecord.objects.count())
        record.refresh_from_db()
        self.assertEqual(request, record.request)

        sync_triage_records(self.ruleset, self.product, {self.vulnerability.pk: ["risk_score"]})
        self.assertEqual(1, TriageRecord.objects.count())
        record.refresh_from_db()
        self.assertEqual(request, record.request)

    def test_does_not_touch_records_from_another_ruleset(self):
        other_ruleset = make_triage_ruleset(self.dataspace, action=TriageAction.NOTIFY)
        sync_triage_records(other_ruleset, self.product, {self.vulnerability.pk: ["risk_score"]})
        sync_triage_records(self.ruleset, self.product, {})
        self.assertEqual(1, TriageRecord.objects.count())
        self.assertEqual(other_ruleset, TriageRecord.objects.get().ruleset)

    def test_applies_preset_for_matching_vulnerabilities_by_default(self):
        preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.NOT_AFFECTED)
        self.ruleset.analysis_preset = preset
        self.ruleset.save()
        sync_triage_records(self.ruleset, self.product, {self.vulnerability.pk: ["risk_score"]})
        analysis = VulnerabilityAnalysis.objects.get()
        self.assertEqual(preset, analysis.applied_by_preset)

    def test_apply_preset_false_skips_preset_application(self):
        preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.NOT_AFFECTED)
        self.ruleset.analysis_preset = preset
        self.ruleset.save()
        sync_triage_records(
            self.ruleset,
            self.product,
            {self.vulnerability.pk: ["risk_score"]},
            apply_preset=False,
        )
        self.assertFalse(VulnerabilityAnalysis.objects.exists())

    def test_deletes_the_preset_analysis_of_a_now_stale_record(self):
        preset = make_analysis_preset(self.dataspace, state=AnalysisPreset.State.NOT_AFFECTED)
        self.ruleset.analysis_preset = preset
        self.ruleset.save()
        sync_triage_records(self.ruleset, self.product, {self.vulnerability.pk: ["risk_score"]})
        self.assertTrue(VulnerabilityAnalysis.objects.exists())

        sync_triage_records(self.ruleset, self.product, {})

        self.assertFalse(VulnerabilityAnalysis.objects.exists())

    def test_opens_a_request_for_a_new_record_when_request_template_is_set(self):
        requester = create_user("requester", self.dataspace)
        request_template = RequestTemplate.objects.create(
            name="Vulnerability Template",
            description="Header",
            dataspace=self.dataspace,
            content_type=ContentType.objects.get_for_model(Product),
            created_by=requester,
        )
        self.ruleset.request_template = request_template
        self.ruleset.save()

        sync_triage_records(self.ruleset, self.product, {self.vulnerability.pk: ["risk_score"]})

        record = TriageRecord.objects.get()
        self.assertIsNotNone(record.request)
        self.assertEqual(1, Request.objects.count())

    def test_does_not_reopen_a_request_for_a_record_that_already_has_one(self):
        requester = create_user("requester", self.dataspace)
        request_template = RequestTemplate.objects.create(
            name="Vulnerability Template",
            description="Header",
            dataspace=self.dataspace,
            content_type=ContentType.objects.get_for_model(Product),
            created_by=requester,
        )
        self.ruleset.request_template = request_template
        self.ruleset.save()

        sync_triage_records(self.ruleset, self.product, {self.vulnerability.pk: ["risk_score"]})
        sync_triage_records(self.ruleset, self.product, {self.vulnerability.pk: ["risk_score"]})

        self.assertEqual(1, Request.objects.count())


class CreateTriageRequestsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        make_product_package(self.product, package=self.package)
        self.vulnerability = make_vulnerability(self.dataspace, affecting=self.package)
        self.ruleset = make_triage_ruleset(self.dataspace, action=TriageAction.UPGRADE)
        self.requester = create_user("requester", self.dataspace)
        self.request_template = RequestTemplate.objects.create(
            name="Vulnerability Template",
            description="Header",
            dataspace=self.dataspace,
            content_type=ContentType.objects.get_for_model(Product),
            created_by=self.requester,
        )

    def test_opens_one_request_per_record_using_the_template_creator_as_requester(self):
        record = TriageRecord.objects.create(
            vulnerability=self.vulnerability,
            product=self.product,
            ruleset=self.ruleset,
            action=self.ruleset.action,
            dataspace=self.dataspace,
        )
        create_triage_requests(self.request_template, self.product, [record])

        request = Request.objects.get()
        self.assertEqual(self.requester, request.requester)
        self.assertEqual(self.product, request.product_context)
        self.assertIn(self.vulnerability.advisory_id, request.title)

    def test_sets_the_request_on_the_triage_record(self):
        record = TriageRecord.objects.create(
            vulnerability=self.vulnerability,
            product=self.product,
            ruleset=self.ruleset,
            action=self.ruleset.action,
            dataspace=self.dataspace,
        )
        create_triage_requests(self.request_template, self.product, [record])
        record.refresh_from_db()
        self.assertEqual(Request.objects.get(), record.request)


class EvaluateRulesetTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)
        self.package = make_package(self.dataspace)
        make_product_package(self.product, package=self.package)

    def test_creates_a_triage_record_end_to_end_for_a_matching_vulnerability(self):
        vulnerability = make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        ruleset = make_triage_ruleset(
            self.dataspace,
            action=TriageAction.UPGRADE,
            rules_config={"risk_score": {"is_active": True, "min_risk_score": 8.0}},
        )
        evaluate_ruleset(ruleset, self.product)
        record = TriageRecord.objects.get()
        self.assertEqual(vulnerability, record.vulnerability)
        self.assertEqual(["risk_score"], record.matched_rules)

    def test_removes_the_record_once_the_vulnerability_no_longer_matches(self):
        vulnerability = make_vulnerability(self.dataspace, affecting=self.package, risk_score=9.0)
        ruleset = make_triage_ruleset(
            self.dataspace,
            action=TriageAction.UPGRADE,
            rules_config={"risk_score": {"is_active": True, "min_risk_score": 8.0}},
        )
        evaluate_ruleset(ruleset, self.product)
        self.assertTrue(TriageRecord.objects.exists())

        vulnerability.risk_score = 2.0
        vulnerability.save()
        evaluate_ruleset(ruleset, self.product)

        self.assertFalse(TriageRecord.objects.exists())
