#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from component_catalog.models import Component
from dje.api_custom import TabPermission
from dje.models import Dataspace
from dje.tests import create_superuser
from dje.tests import create_user
from license_library.models import License
from policy.api import UsagePolicyViewSet
from policy.models import UsagePolicy


class UsagePolicyAPITestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate = Dataspace.objects.create(name="Alternate")
        self.base_user = create_user("base_user", self.dataspace)
        self.super_user = create_superuser("super_user", self.dataspace)

        self.usagepolicy_list_url = reverse("api_v2:usagepolicy-list")

        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.component1 = self.component_ct.model_class().objects.create(
            name="component1", version="1.0", dataspace=self.dataspace
        )
        self.license_ct = ContentType.objects.get(app_label="license_library", model="license")

        self.license_ct = ContentType.objects.get_for_model(License)
        self.component_ct = ContentType.objects.get_for_model(Component)

        self.license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=self.license_ct,
            dataspace=self.dataspace,
            compliance_alert=UsagePolicy.Compliance.ERROR,
        )

        self.component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=self.component_ct,
            dataspace=self.dataspace,
        )

        self.alternate_component_policy = UsagePolicy.objects.create(
            label="OtherComponent",
            icon="icon",
            content_type=self.component_ct,
            dataspace=self.alternate,
        )

        self.license_policy_detail_url = reverse(
            "api_v2:usagepolicy-detail", args=[self.license_policy.uuid]
        )
        self.component_policy_detail_url = reverse(
            "api_v2:usagepolicy-detail", args=[self.component_policy.uuid]
        )
        self.other_component_policy = reverse(
            "api_v2:usagepolicy-detail", args=[self.alternate_component_policy.uuid]
        )

    def test_api_usagepolicy_list_endpoint_user_available_scope(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.usagepolicy_list_url)

        self.assertContains(response, self.license_policy_detail_url)
        self.assertContains(response, self.component_policy_detail_url)
        self.assertNotContains(response, self.other_component_policy)
        self.assertEqual(2, response.data["count"])
        self.assertEqual(self.license_policy.label, response.data["results"][0]["label"])
        self.assertEqual(self.component_policy.label, response.data["results"][1]["label"])

        # results field only available on details view
        self.assertNotIn("results", response.data["results"][0].keys())

    def test_api_usagepolicy_list_endpoint_search(self):
        self.client.login(username="super_user", password="secret")
        data = {"search": self.license_policy.label}
        response = self.client.get(self.usagepolicy_list_url, data)

        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.license_policy)

    def test_api_usagepolicy_detail_endpoint(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.license_policy_detail_url)

        self.assertContains(response, self.license_policy)
        self.assertIn(self.license_policy_detail_url, response.data["api_url"])
        self.assertEqual(str(self.license_policy.uuid), response.data["uuid"])
        self.assertEqual(self.license_policy.label, response.data["label"])
        self.assertEqual(self.license_policy.guidelines, response.data["guidelines"])
        self.assertEqual(self.license_policy.content_type.model, response.data["content_type"])
        self.assertEqual(self.license_policy.compliance_alert, response.data["compliance_alert"])

    def test_api_usagepolicy_endpoint_tab_permission(self):
        self.assertEqual((TabPermission,), UsagePolicyViewSet.extra_permissions)
