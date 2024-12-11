#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#


from django.test import TestCase
from django.urls import reverse

from rest_framework import status

from component_catalog.tests import make_package
from dje.models import Dataspace
from dje.tests import MaxQueryMixin
from dje.tests import create_superuser
from product_portfolio.tests import make_product
from vulnerabilities.models import VulnerabilityAnalysis
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.tests import make_vulnerability_analysis


class VulnerabilitiesAPITestCase(MaxQueryMixin, TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("super_user", self.dataspace)

        self.vulnerabilities_list_url = reverse("api_v2:vulnerability-list")
        self.analysis_list_url = reverse("api_v2:vulnerabilityanalysis-list")

        self.package1 = make_package(self.dataspace)
        self.package2 = make_package(self.dataspace)
        self.product1 = make_product(self.dataspace, inventory=[self.package1, self.package2])
        self.product2 = make_product(self.dataspace, inventory=[self.package2])
        self.product_package1 = self.product1.productpackages.get(package=self.package1)

        self.vulnerability1 = make_vulnerability(
            dataspace=self.dataspace,
            affecting=self.package1,
            risk_score=0.0,
        )
        self.vulnerability2 = make_vulnerability(
            dataspace=self.dataspace,
            affecting=self.package2,
            risk_score=5.0,
        )
        self.vulnerability3 = make_vulnerability(
            dataspace=self.dataspace,
            affecting=[self.package1, self.package2],
            risk_score=10.0,
        )

    def test_api_vulnerabilities_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")

        with self.assertMaxQueries(9):
            response = self.client.get(self.vulnerabilities_list_url)

        self.assertEqual(3, response.data["count"])
        results = response.data["results"]

        # Ordered by risk_score
        expected = [
            self.vulnerability3.vulnerability_id,
            self.vulnerability2.vulnerability_id,
            self.vulnerability1.vulnerability_id,
        ]
        self.assertEqual(expected, [entry["vulnerability_id"] for entry in results])

        self.assertEqual(str(self.package1), results[2]["affected_packages"][0]["display_name"])
        self.assertEqual(str(self.product1), results[2]["affected_products"][0]["display_name"])

    def test_api_vulnerabilities_list_endpoint_search(self):
        self.client.login(username="super_user", password="secret")

        data = {"search": self.vulnerability1.vulnerability_id}
        response = self.client.get(self.vulnerabilities_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.vulnerability1.vulnerability_id)
        self.assertNotContains(response, self.vulnerability2.vulnerability_id)
        self.assertNotContains(response, self.vulnerability3.vulnerability_id)

    def test_api_vulnerabilities_list_endpoint_filters(self):
        self.client.login(username="super_user", password="secret")

        data = {"risk_score": "critical"}
        response = self.client.get(self.vulnerabilities_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertNotContains(response, self.vulnerability1.vulnerability_id)
        self.assertNotContains(response, self.vulnerability2.vulnerability_id)
        self.assertContains(response, self.vulnerability3.vulnerability_id)

    def test_api_vulnerabilities_detail_endpoint(self):
        detail_url = reverse("api_v2:vulnerability-detail", args=[self.vulnerability1.uuid])
        self.client.login(username="super_user", password="secret")

        with self.assertNumQueries(8):
            response = self.client.get(detail_url)

        self.assertContains(response, detail_url)
        self.assertIn(detail_url, response.data["api_url"])
        self.assertEqual(self.vulnerability1.vulnerability_id, response.data["vulnerability_id"])
        self.assertEqual(str(self.vulnerability1.uuid), response.data["uuid"])
        self.assertEqual("0.0", response.data["risk_score"])
        self.assertEqual(1, len(response.data["affected_packages"]))
        self.assertEqual(1, len(response.data["affected_products"]))

    def test_api_vulnerability_analysis_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")
        make_vulnerability_analysis(self.product_package1, self.vulnerability1)
        make_vulnerability_analysis(self.product_package1, self.vulnerability2)
        make_vulnerability_analysis(self.product_package1, self.vulnerability3)

        with self.assertMaxQueries(9):
            response = self.client.get(self.analysis_list_url)

        self.assertEqual(3, response.data["count"])

    def test_api_vulnerability_analysis_list_endpoint_filters(self):
        self.client.login(username="super_user", password="secret")
        make_vulnerability_analysis(self.product_package1, self.vulnerability1, is_reachable=True)
        make_vulnerability_analysis(self.product_package1, self.vulnerability2)

        data = {"is_reachable": "yes"}
        response = self.client.get(self.analysis_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.vulnerability1.vulnerability_id)
        self.assertNotContains(response, self.vulnerability2.vulnerability_id)

        data = {"is_reachable": "no"}
        response = self.client.get(self.analysis_list_url, data)
        self.assertEqual(0, response.data["count"])
        self.assertNotContains(response, self.vulnerability1.vulnerability_id)
        self.assertNotContains(response, self.vulnerability2.vulnerability_id)

    def test_api_vulnerability_analysis_detail_endpoint(self):
        self.client.login(username="super_user", password="secret")

        analysis1 = make_vulnerability_analysis(
            self.product_package1, self.vulnerability1, is_reachable=True
        )
        detail_url = reverse("api_v2:vulnerabilityanalysis-detail", args=[analysis1.uuid])
        make_vulnerability_analysis(self.product_package1, self.vulnerability2)
        make_vulnerability_analysis(self.product_package1, self.vulnerability3)

        with self.assertNumQueries(6):
            response = self.client.get(detail_url)

        self.assertContains(response, detail_url)
        self.assertIn(detail_url, response.data["api_url"])
        self.assertEqual(self.vulnerability1.vulnerability_id, response.data["vulnerability_id"])
        self.assertEqual(str(analysis1.uuid), response.data["uuid"])
        self.assertTrue(response.data["is_reachable"])

    def test_api_vulnerability_analysis_endpoint_create(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.post(self.analysis_list_url)
        expected = {
            "product_package": ["This field is required."],
            "vulnerability": ["This field is required."],
        }
        self.assertEqual(expected, response.data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)

        product_package1_detail_url = reverse(
            "api_v2:productpackage-detail", args=[self.product_package1.uuid]
        )
        vulnerability1_detail_url = reverse(
            "api_v2:vulnerability-detail", args=[self.vulnerability1.uuid]
        )

        data = {
            "product_package": product_package1_detail_url,
            "vulnerability": vulnerability1_detail_url,
            "state": VulnerabilityAnalysis.State.RESOLVED,
            "justification": VulnerabilityAnalysis.Justification.CODE_NOT_PRESENT,
            "responses": [VulnerabilityAnalysis.Response.CAN_NOT_FIX],
            "detail": "detail",
            "is_reachable": True,
        }

        response = self.client.post(self.analysis_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertIn(product_package1_detail_url, response.data["product_package"])
        self.assertIn(vulnerability1_detail_url, response.data["vulnerability"])
        self.assertEqual(self.vulnerability1.vulnerability_id, response.data["vulnerability_id"])
        self.assertEqual("resolved", response.data["state"])
        self.assertEqual("code_not_present", response.data["justification"])
        self.assertEqual("detail", response.data["detail"])
        self.assertEqual(["can_not_fix"], response.data["responses"])
        self.assertTrue(response.data["is_reachable"])
