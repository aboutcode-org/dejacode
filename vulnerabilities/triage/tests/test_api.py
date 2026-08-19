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

from rest_framework import status

from dje.models import Dataspace
from dje.tests import create_superuser
from product_portfolio.models import Product
from vulnerabilities.triage.models import AnalysisPreset
from vulnerabilities.triage.models import TriageAction
from vulnerabilities.triage.models import TriageRuleset
from vulnerabilities.triage.tests import make_analysis_preset
from vulnerabilities.triage.tests import make_triage_ruleset
from workflow.models import RequestTemplate


class AnalysisPresetAPITestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate = Dataspace.objects.create(name="Alternate")
        self.super_user = create_superuser("super_user", self.dataspace)

        self.list_url = reverse("api_v2:analysispreset-list")
        self.preset = make_analysis_preset(
            self.dataspace, name="Preset1", state=AnalysisPreset.State.NOT_AFFECTED
        )
        self.detail_url = reverse("api_v2:analysispreset-detail", args=[self.preset.uuid])
        make_analysis_preset(self.alternate, name="OtherPreset")

    def test_api_analysispreset_list_endpoint_user_available_scope(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.list_url)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.preset.name)

    def test_api_analysispreset_detail_endpoint(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.detail_url)
        self.assertEqual(self.preset.name, response.data["name"])
        self.assertEqual(AnalysisPreset.State.NOT_AFFECTED, response.data["state"])

    def test_api_analysispreset_endpoint_create(self):
        self.client.login(username="super_user", password="secret")
        data = {"name": "New Preset", "detail": "Some detail"}
        response = self.client.post(self.list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        preset = AnalysisPreset.objects.get(name="New Preset")
        self.assertEqual("Some detail", preset.detail)

    def test_api_analysispreset_endpoint_create_rejects_no_content_field(self):
        self.client.login(username="super_user", password="secret")
        data = {"name": "No content", "is_reachable": True}
        response = self.client.post(self.list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        msg = "At least one of state, justification, responses or detail must be provided."
        self.assertIn(msg, response.data["non_field_errors"])

    def test_api_analysispreset_endpoint_update(self):
        self.client.login(username="super_user", password="secret")
        data = {"detail": "Updated detail"}
        response = self.client.patch(self.detail_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.preset.refresh_from_db()
        self.assertEqual("Updated detail", self.preset.detail)

    def test_api_analysispreset_endpoint_delete(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.delete(self.detail_url)
        self.assertEqual(status.HTTP_204_NO_CONTENT, response.status_code)
        self.assertFalse(AnalysisPreset.objects.filter(pk=self.preset.pk).exists())


class TriageRulesetAPITestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate = Dataspace.objects.create(name="Alternate")
        self.super_user = create_superuser("super_user", self.dataspace)

        self.list_url = reverse("api_v2:triageruleset-list")
        self.ruleset = make_triage_ruleset(
            self.dataspace,
            name="Ruleset1",
            recommended_action=TriageAction.UPGRADE,
            precedence=100,
        )
        self.detail_url = reverse("api_v2:triageruleset-detail", args=[self.ruleset.uuid])
        make_triage_ruleset(self.alternate, name="OtherRuleset")

    def test_api_triageruleset_list_endpoint_user_available_scope(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.list_url)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.ruleset.name)

    def test_api_triageruleset_detail_endpoint(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.detail_url)
        self.assertEqual(self.ruleset.name, response.data["name"])
        self.assertEqual(TriageAction.UPGRADE, response.data["recommended_action"])
        self.assertEqual(100, response.data["precedence"])

    def test_api_triageruleset_endpoint_create(self):
        self.client.login(username="super_user", password="secret")
        data = {
            "name": "New Ruleset",
            "precedence": 200,
            "recommended_action": TriageAction.NOTIFY,
            "rules_config": {"risk_score": {"is_active": True, "min_risk_score": 8.0}},
        }
        response = self.client.post(self.list_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        ruleset = TriageRuleset.objects.get(name="New Ruleset")
        self.assertEqual(
            {"is_active": True, "min_risk_score": 8.0}, ruleset.rules_config["risk_score"]
        )

    def test_api_triageruleset_endpoint_create_rejects_request_template_with_no_creator(self):
        self.client.login(username="super_user", password="secret")
        request_template = RequestTemplate.objects.create(
            name="Broken Template",
            description="Header",
            dataspace=self.dataspace,
            content_type=ContentType.objects.get_for_model(Product),
        )
        request_template_url = reverse(
            "api_v2:requesttemplate-detail", args=[request_template.uuid]
        )
        data = {
            "name": "New Ruleset",
            "precedence": 200,
            "request_template": request_template_url,
        }
        response = self.client.post(self.list_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        msg = "This request template has no creator and cannot be used to open requests."
        self.assertIn(msg, response.data["request_template"])

    def test_api_triageruleset_endpoint_create_rejects_cross_dataspace_analysis_preset(self):
        self.client.login(username="super_user", password="secret")
        other_preset = make_analysis_preset(self.alternate, name="OtherPreset")
        other_preset_url = reverse("api_v2:analysispreset-detail", args=[other_preset.uuid])
        data = {
            "name": "New Ruleset",
            "precedence": 200,
            "analysis_preset": other_preset_url,
        }
        response = self.client.post(self.list_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertIn("analysis_preset", response.data)

    def test_api_triageruleset_endpoint_update(self):
        self.client.login(username="super_user", password="secret")
        data = {"enabled": False}
        response = self.client.patch(self.detail_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.ruleset.refresh_from_db()
        self.assertFalse(self.ruleset.enabled)

    def test_api_triageruleset_endpoint_delete(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.delete(self.detail_url)
        self.assertEqual(status.HTTP_204_NO_CONTENT, response.status_code)
        self.assertFalse(TriageRuleset.objects.filter(pk=self.ruleset.pk).exists())
