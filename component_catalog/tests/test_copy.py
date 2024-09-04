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

from component_catalog.models import Package
from component_catalog.models import PackageAssignedLicense
from component_catalog.tests import make_package
from dje.models import Dataspace
from dje.tests import create_superuser
from vulnerabilities.models import Vulnerability


class ComponentCatalogCopyTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.target_dataspace = Dataspace.objects.create(name="Target")
        self.super_user = create_superuser("super_user", self.dataspace)

    def test_component_catalog_admin_copy_view_vulnerable_package(self):
        package1 = make_package(self.dataspace, is_vulnerable=True)
        self.assertEqual(1, package1.affected_by_vulnerabilities.count())

        self.client.login(username=self.super_user.username, password="secret")
        url = reverse("admin:component_catalog_package_copy")
        data = {
            "ids": str(package1.id),
            "target": self.target_dataspace.id,
        }
        response = self.client.get(url, data, follow=True)
        self.assertContains(response, "Copy the following Packages")

        data = {
            "ct": str(ContentType.objects.get_for_model(Package).pk),
            "copy_candidates": package1.id,
            "source": self.dataspace.id,
            "targets": self.target_dataspace.id,
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(PackageAssignedLicense).pk,
        }
        self.client.post(url, data)
        response = self.client.post(url, data, follow=True)
        self.assertEqual(200, response.status_code)

        copied_package1 = Package.objects.scope(self.target_dataspace).get()
        self.assertEqual(0, copied_package1.affected_by_vulnerabilities.count())
        self.assertEqual(0, Vulnerability.objects.scope(self.target_dataspace).count())
