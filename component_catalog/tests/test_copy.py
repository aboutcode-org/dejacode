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
from dje.tests import add_perm
from dje.tests import add_perms
from dje.tests import create_admin
from dje.tests import create_superuser
from policy.models import UsagePolicy
from vulnerabilities.models import Vulnerability


class ComponentCatalogCopyTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.target_dataspace = Dataspace.objects.create(name="Target")
        self.super_user = create_superuser("super_user", self.dataspace)

    def make_matching_packages(self):
        reference_package = make_package(self.dataspace, copyright="Reference copyright")
        target_package = make_package(
            self.target_dataspace,
            uuid=reference_package.uuid,
            filename=reference_package.filename,
            copyright="Local copyright",
        )
        return reference_package, target_package

    def test_component_catalog_admin_copy_view_update_requires_change_permission(self):
        reference_package, target_package = self.make_matching_packages()
        target_user = add_perms(
            create_admin("target_user", self.target_dataspace), ["view_package", "add_package"]
        )
        self.client.login(username=target_user.username, password="secret")
        url = reverse("admin:component_catalog_package_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(Package).pk),
            "source": self.dataspace.id,
            "targets": self.target_dataspace.id,
            "select_for_update": target_package.id,
            "form-TOTAL_FORMS": 0,
            "form-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(403, response.status_code)
        target_package.refresh_from_db()
        self.assertEqual("Local copyright", target_package.copyright)

        add_perm(target_user, "change_package")
        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        target_package.refresh_from_db()
        self.assertEqual("Reference copyright", target_package.copyright)

    def test_component_catalog_admin_copy_view_rejects_other_model_content_type(self):
        reference_package, target_package = self.make_matching_packages()
        self.client.login(username=self.super_user.username, password="secret")
        url = reverse("admin:component_catalog_package_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(UsagePolicy).pk),
            "source": self.dataspace.id,
            "targets": self.target_dataspace.id,
            "select_for_update": target_package.id,
            "form-TOTAL_FORMS": 0,
            "form-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(404, response.status_code)

    def test_component_catalog_admin_compare_view_permissions(self):
        reference_package, target_package = self.make_matching_packages()
        target_user = add_perms(
            create_admin("target_user", self.target_dataspace), ["view_package"]
        )
        self.client.login(username=target_user.username, password="secret")
        url = reverse("admin:component_catalog_package_compare") + f"?ids={reference_package.id}"

        response = self.client.post(url, {"checkbox_select": "copyright"})
        self.assertEqual(403, response.status_code)

        add_perm(target_user, "change_package")
        for field_name in ["usage_policy", "id", "dataspace", "created_by", "notes"]:
            with self.subTest(field_name=field_name):
                response = self.client.post(url, {"checkbox_select": field_name})
                self.assertEqual(403, response.status_code)
        target_package.refresh_from_db()
        self.assertEqual("Local copyright", target_package.copyright)

        response = self.client.post(url, {"checkbox_select": "copyright"})
        self.assertEqual(302, response.status_code)
        target_package.refresh_from_db()
        self.assertEqual("Reference copyright", target_package.copyright)

    def test_component_catalog_admin_compare_view_source_from_other_tenant(self):
        reference_package, target_package = self.make_matching_packages()
        other_dataspace = Dataspace.objects.create(name="Other Tenant")
        other_package = make_package(
            other_dataspace,
            uuid=reference_package.uuid,
            filename=reference_package.filename,
            copyright="Other tenant copyright",
        )
        target_user = add_perms(
            create_admin("target_user", self.target_dataspace), ["view_package", "change_package"]
        )
        self.client.login(username=target_user.username, password="secret")
        url = reverse("admin:component_catalog_package_compare") + f"?ids={other_package.id}"

        response = self.client.get(url)
        self.assertEqual(302, response.status_code)
        self.assertNotIn(b"Other tenant copyright", response.content)

        response = self.client.post(url, {"checkbox_select": "copyright"})
        self.assertEqual(302, response.status_code)
        target_package.refresh_from_db()
        self.assertEqual("Local copyright", target_package.copyright)

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
