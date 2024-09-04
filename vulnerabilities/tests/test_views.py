#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from component_catalog.tests import make_component
from component_catalog.tests import make_package
from dje.models import Dataspace
from dje.models import DataspaceConfiguration
from dje.tests import create_superuser
from vulnerabilities.models import Vulnerability
from vulnerabilities.tests import make_vulnerability

User = get_user_model()


class VulnerabilityViewsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(
            name="Dataspace",
            enable_vulnerablecodedb_access=True,
        )
        DataspaceConfiguration.objects.create(
            dataspace=self.dataspace,
            vulnerablecode_url="vulnerablecode_url/",
        )
        self.super_user = create_superuser("super_user", self.dataspace)

        self.component1 = make_component(self.dataspace)
        self.component2 = make_component(self.dataspace)
        self.package1 = make_package(self.dataspace)
        self.package2 = make_package(self.dataspace)
        self.vulnerability_p1 = make_vulnerability(self.dataspace, affecting=self.component1)
        self.vulnerability_c1 = make_vulnerability(self.dataspace, affecting=self.package1)
        self.vulnerability1 = make_vulnerability(self.dataspace)

    def test_vulnerability_list_view_num_queries(self):
        self.client.login(username=self.super_user.username, password="secret")
        with self.assertNumQueries(8):
            response = self.client.get(reverse("vulnerabilities:vulnerability_list"))

        vulnerability_count = Vulnerability.objects.count()
        expected = f'<a class="nav-link disabled">{vulnerability_count} results</a>'
        self.assertContains(response, expected, html=True)

    def test_vulnerability_list_view_enable_vulnerablecodedb_access(self):
        self.client.login(username=self.super_user.username, password="secret")
        vulnerability_list_url = reverse("vulnerabilities:vulnerability_list")
        response = self.client.get(vulnerability_list_url)
        self.assertEqual(200, response.status_code)
        vulnerability_header_link = (
            f'<a class="dropdown-item active" href="{vulnerability_list_url}">'
        )
        self.assertContains(response, vulnerability_header_link)

        self.dataspace.enable_vulnerablecodedb_access = False
        self.dataspace.save()
        response = self.client.get(reverse("vulnerabilities:vulnerability_list"))
        self.assertEqual(404, response.status_code)

        response = self.client.get(reverse("component_catalog:package_list"))
        self.assertNotContains(response, vulnerability_header_link)

    def test_vulnerability_list_view_vulnerability_id_link(self):
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(reverse("vulnerabilities:vulnerability_list"))
        expected = f"""
        <a href="vulnerablecode_url/vulnerabilities/{self.vulnerability1.vulnerability_id}"
           target="_blank">
           {self.vulnerability1.vulnerability_id}
           <i class="fa-solid fa-up-right-from-square mini"></i>
        </a>
        """
        self.assertContains(response, expected, html=True)
