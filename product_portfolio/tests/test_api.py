#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import uuid
from pathlib import Path
from unittest import mock

from django.core import mail
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse

from guardian.shortcuts import assign_perm
from guardian.shortcuts import get_perms
from rest_framework import status
from rest_framework.exceptions import ErrorDetail

from component_catalog.models import Component
from component_catalog.models import ComponentKeyword
from component_catalog.models import Package
from dje.models import Dataspace
from dje.models import History
from dje.tests import MaxQueryMixin
from dje.tests import add_perm
from dje.tests import create_admin
from dje.tests import create_superuser
from dje.tests import create_user
from license_library.models import License
from license_library.models import LicenseChoice
from organization.models import Owner
from product_portfolio.api import CodebaseResourceViewSet
from product_portfolio.api import ProductComponentViewSet
from product_portfolio.api import ProductPackageViewSet
from product_portfolio.models import CodebaseResource
from product_portfolio.models import CodebaseResourceUsage
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductItemPurpose
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductRelationStatus
from product_portfolio.models import ProductStatus
from product_portfolio.models import ScanCodeProject
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.tests import make_vulnerability_analysis


class ProductAPITestCase(MaxQueryMixin, TestCase):
    testfiles_path = Path(__file__).parent / "testfiles"

    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="Alternate")

        self.base_user = create_user("base_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)
        self.super_user = create_superuser("super_user", self.dataspace)

        self.product_list_url = reverse("api_v2:product-list")

        self.product1 = Product.objects.create(name="p1", dataspace=self.dataspace)
        self.product1_detail_url = reverse("api_v2:product-detail", args=[self.product1.uuid])

        self.product2 = Product.objects.create(name="p2", dataspace=self.dataspace)
        self.product2_detail_url = reverse("api_v2:product-detail", args=[self.product2.uuid])

    def test_api_product_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")
        with self.assertMaxQueries(12):
            response = self.client.get(self.product_list_url)

        self.assertContains(response, '"count":2,')
        self.assertContains(response, self.product1_detail_url)
        self.assertContains(response, self.product2_detail_url)
        self.assertEqual(2, response.data["count"])

    def test_api_secured_product_list_endpoint_results(self):
        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.product_list_url)
        self.assertContains(response, '"count":0,')
        self.assertNotContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)
        self.assertEqual(0, response.data["count"])

        assign_perm("view_product", self.base_user, self.product1)
        response = self.client.get(self.product_list_url)
        self.assertContains(response, '"count":1,')
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)
        self.assertEqual(1, response.data["count"])

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.product_list_url)
        self.assertContains(response, '"count":0,')
        self.assertNotContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)
        self.assertEqual(0, response.data["count"])

        assign_perm("view_product", self.admin_user, self.product1)
        response = self.client.get(self.product_list_url)
        self.assertContains(response, '"count":1,')
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)
        self.assertEqual(1, response.data["count"])

    def test_api_product_list_endpoint_search(self):
        self.client.login(username="super_user", password="secret")
        data = {"search": self.product1.name}
        response = self.client.get(self.product_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        # Search is case in-sensitive
        data = {"search": self.product1.name.upper()}
        response = self.client.get(self.product_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

    def test_api_product_detail_endpoint(self):
        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        self.product1.owner = owner
        self.product1.save()
        owner_detail_url = reverse("api_v2:owner-detail", args=[owner.uuid])
        self.client.login(username="super_user", password="secret")

        # with self.assertNumQueries(7):
        response = self.client.get(self.product1_detail_url)

        self.assertContains(response, self.product1_detail_url)
        self.assertIn(self.product1_detail_url, response.data["api_url"])
        self.assertEqual(str(self.product1), response.data["display_name"])
        self.assertEqual(str(self.product1.uuid), response.data["uuid"])
        self.assertEqual(self.product1.name, response.data["name"])
        self.assertIn(owner_detail_url, response.data["owner"])

    def test_api_secured_product_detail_endpoint(self):
        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.product1_detail_url)
        self.assertEqual(404, response.status_code)

        assign_perm("view_product", self.base_user, self.product1)
        response = self.client.get(self.product1_detail_url)
        self.assertContains(response, self.product1_detail_url)
        self.assertIn(self.product1_detail_url, response.data["api_url"])
        self.assertEqual(str(self.product1.uuid), response.data["uuid"])
        self.assertEqual(self.product1.name, response.data["name"])

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.product1_detail_url)
        self.assertEqual(404, response.status_code)

        assign_perm("view_product", self.admin_user, self.product1)
        response = self.client.get(self.product1_detail_url)
        self.assertContains(response, self.product1_detail_url)
        self.assertIn(self.product1_detail_url, response.data["api_url"])
        self.assertEqual(str(self.product1.uuid), response.data["uuid"])
        self.assertEqual(self.product1.name, response.data["name"])

    def test_api_product_endpoint_create_minimal(self):
        self.client.login(username=self.super_user.username, password="secret")
        data = {"name": "Product"}
        response = self.client.post(self.product_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        p1 = Product.unsecured_objects.latest("id")
        self.assertTrue(p1.created_date)
        self.assertTrue(p1.last_modified_date)
        self.assertEqual(self.super_user, p1.created_by)
        self.assertEqual(self.super_user, p1.last_modified_by)

    def test_api_product_endpoint_create_update_keywords(self):
        keyword1 = ComponentKeyword.objects.create(label="Keyword1", dataspace=self.dataspace)
        keyword2 = ComponentKeyword.objects.create(label="Keyword2", dataspace=self.dataspace)
        # For scoping sanity check
        ComponentKeyword.objects.create(label=keyword1.label, dataspace=self.alternate_dataspace)

        self.client.login(username="super_user", password="secret")
        data = {
            "name": "Prod1",
            "keywords": [keyword1.label, keyword2.label],
        }
        response = self.client.post(self.product_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        p1 = Product.unsecured_objects.get(name="Prod1")
        self.assertEqual([keyword1.label, keyword2.label], p1.keywords)

        data = {
            "name": "Prod2",
            "keywords": ["non-existing"],
        }
        response = self.client.post(self.product_list_url, data)
        self.assertEqual(201, response.status_code)
        new_keyword = ComponentKeyword.objects.get(label="non-existing")
        self.assertTrue(new_keyword)
        self.assertEqual([new_keyword.label], Product.unsecured_objects.get(name="Prod2").keywords)

        # No keywords
        data = {
            "name": "Prod3",
            "keywords": [],
        }
        response = self.client.post(self.product_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        p3 = Product.unsecured_objects.get(name="Prod3")
        self.assertEqual([], p3.keywords)

        data = {
            "name": "Prod4",
            "keywords": "",
        }
        response = self.client.post(self.product_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertEqual([], Product.unsecured_objects.get(name=data["name"]).keywords)

        # Update
        data = json.dumps({"keywords": [keyword1.label]})
        p3_api_url = reverse("api_v2:product-detail", args=[p3.uuid])
        response = self.client.patch(p3_api_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        p3 = Product.unsecured_objects.get(name="Prod3")
        self.assertEqual([keyword1.label], p3.keywords)

        data = json.dumps({"keywords": [keyword2.label]})
        response = self.client.patch(p3_api_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        p3 = Product.unsecured_objects.get(name="Prod3")
        self.assertEqual([keyword2.label], p3.keywords)

        data = json.dumps({"keywords": [keyword1.label, keyword2.label]})
        response = self.client.patch(p3_api_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        p3 = Product.unsecured_objects.get(name="Prod3")
        self.assertEqual([keyword1.label, keyword2.label], p3.keywords)

    def test_api_product_endpoint_create_permissions(self):
        data = {"name": "Product"}

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.post(self.product_list_url, data)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.post(self.product_list_url, data)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        add_perm(self.admin_user, "add_product")
        response = self.client.post(self.product_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        # Object permissions are added for the creator at save time
        added_product = Product.unsecured_objects.latest("id")
        expected = sorted(["change_product", "view_product", "delete_product"])
        self.assertEqual(expected, sorted(get_perms(self.admin_user, added_product)))

    def test_api_product_endpoint_create_full(self):
        self.client.login(username="super_user", password="secret")

        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="license1", name="License1", short_name="L1", owner=owner, dataspace=self.dataspace
        )
        license2 = License.objects.create(
            key="license2", name="License2", short_name="L2", owner=owner, dataspace=self.dataspace
        )
        self.pc_status1 = ProductStatus.objects.create(
            label="S1", text="Status1", default_on_addition=True, dataspace=self.dataspace
        )

        data = {
            "name": "Product",
            "version": "1.0",
            "owner": owner.name,
            "configuration_status": self.pc_status1.label,
            "license_expression": "{} AND {}".format(license1.key, license2.key),
            "release_date": "1984-10-10",
            "description": "Description",
            "copyright": "Copyright (C)",
            "contact": "contact",
            "homepage_url": "http://nexb.com",
            "vcs_url": "http://nexb.com",
            "code_view_url": "http://nexb.com",
            "bug_tracking_url": "http://nexb.com",
            "primary_language": "Python",
            "admin_notes": "Notes for admins",
            "notice_text": "notice",
        }

        response = self.client.post(self.product_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        product = Product.unsecured_objects.latest("id")

        self.assertFalse(History.objects.get_for_object(product).exists())
        self.assertEqual(self.super_user, product.created_by)
        self.assertTrue(product.created_date)

        for field_name, value in data.items():
            self.assertEqual(str(value), str(getattr(product, field_name)), msg=field_name)

        # No email notifications on Product.
        self.assertEqual(0, len(mail.outbox))

    def test_api_product_endpoint_update_put(self):
        self.client.login(username="super_user", password="secret")

        put_data = json.dumps({"name": "Updated Name"})
        response = self.client.put(
            self.product1_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        history = History.objects.get_for_object(self.product1, action_flag=History.CHANGE).latest(
            "id"
        )
        self.assertEqual("Changed name.", history.get_change_message())

        # No email notifications on Product.
        self.assertEqual(0, len(mail.outbox))

        product1 = Product.unsecured_objects.get(pk=self.product1.pk)
        self.assertEqual("Updated Name", product1.name)

    def test_api_product_endpoint_update_permissions(self):
        put_data = json.dumps({"name": "Updated Name"})

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.put(
            self.product1_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.put(
            self.product1_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        add_perm(self.admin_user, "change_product")
        assign_perm("view_product", self.admin_user, self.product1)
        assign_perm("change_product", self.admin_user, self.product1)
        response = self.client.put(
            self.product1_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        product1 = Product.unsecured_objects.get(pk=self.product1.pk)
        self.assertEqual("Updated Name", product1.name)

    def test_api_product_endpoint_load_sboms_action(self):
        url = reverse("api_v2:product-load-sboms", args=[self.product1.uuid])

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(status.HTTP_405_METHOD_NOT_ALLOWED, response.status_code)
        response = self.client.post(url, data={})
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        # Required permissions
        add_perm(self.base_user, "add_product")
        assign_perm("view_product", self.base_user, self.product1)

        response = self.client.post(url, data={})
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"input_file": ["This field is required."]}
        self.assertEqual(expected, response.data)

        data = {
            "input_file": ContentFile("{}", name="sbom.json"),
            "update_existing_packages": False,
            "scan_all_packages": False,
        }
        response = self.client.post(url, data)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        expected = {"status": "SBOM file submitted to ScanCode.io for inspection."}
        self.assertEqual(expected, response.data)
        self.assertEqual(1, ScanCodeProject.objects.count())

    def test_api_product_endpoint_import_manifests_action(self):
        url = reverse("api_v2:product-import-manifests", args=[self.product1.uuid])

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(status.HTTP_405_METHOD_NOT_ALLOWED, response.status_code)
        response = self.client.post(url, data={})
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        # Required permissions
        add_perm(self.base_user, "add_product")
        assign_perm("view_product", self.base_user, self.product1)

        response = self.client.post(url, data={})
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"input_file": ["This field is required."]}
        self.assertEqual(expected, response.data)

        data = {
            "input_file": ContentFile("Content", name="requirements.txt"),
            "update_existing_packages": False,
            "scan_all_packages": False,
        }
        response = self.client.post(url, data)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        expected = {"status": "Manifest file submitted to ScanCode.io for inspection."}
        self.assertEqual(expected, response.data)
        self.assertEqual(1, ScanCodeProject.objects.count())

    def test_api_product_endpoint_import_from_scan_action(self):
        url = reverse("api_v2:product-import-from-scan", args=[self.product1.uuid])

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(status.HTTP_405_METHOD_NOT_ALLOWED, response.status_code)
        response = self.client.post(url, data={})
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        # Required permissions
        add_perm(self.base_user, "add_product")
        assign_perm("view_product", self.base_user, self.product1)

        response = self.client.post(url, data={})
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"upload_file": ["This field is required."]}
        self.assertEqual(expected, response.data)

        data = {
            "upload_file": ContentFile("Content", name="scan_results.json"),
            "create_codebase_resources": False,
            "stop_on_error": False,
        }
        response = self.client.post(url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = ["The file content is not proper JSON."]
        self.assertEqual(expected, response.data)

        scan_input_location = self.testfiles_path / "import_from_scan.json"
        data = {
            "upload_file": scan_input_location.open(),
            "create_codebase_resources": True,
            "stop_on_error": False,
        }
        response = self.client.post(url, data)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        expected = {
            "status": "Imported from Scan: 1 Packages, 1 Product Packages, 3 Codebase Resources"
        }
        self.assertEqual(1, self.product1.productpackages.count())
        self.assertEqual(1, self.product1.packages.count())
        self.assertEqual(3, self.product1.codebaseresources.count())

    @mock.patch("product_portfolio.forms.PullProjectDataForm.get_project_data")
    def test_api_product_endpoint_pull_scancodeio_project_data_action(self, mock_get_project_data):
        url = reverse("api_v2:product-pull-scancodeio-project-data", args=[self.product1.uuid])

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(status.HTTP_405_METHOD_NOT_ALLOWED, response.status_code)
        response = self.client.post(url, data={})
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        # Required permissions
        add_perm(self.base_user, "add_product")
        assign_perm("view_product", self.base_user, self.product1)

        response = self.client.post(url, data={})
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"project_name_or_uuid": ["This field is required."]}
        self.assertEqual(expected, response.data)

        mock_get_project_data.return_value = None
        data = {
            "project_name_or_uuid": "project_name",
            "update_existing_packages": False,
        }
        response = self.client.post(url, data)
        expected = ['Project "project_name" not found on ScanCode.io.']
        self.assertEqual(expected, response.data)

        mock_get_project_data.return_value = {"uuid": uuid.uuid4()}
        response = self.client.post(url, data)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        expected = {"status": "Packages import from ScanCode.io in progress..."}
        self.assertEqual(expected, response.data)
        self.assertEqual(1, ScanCodeProject.objects.count())

    def test_api_product_endpoint_aboutcode_files_action(self):
        url = reverse("api_v2:product-aboutcode-files", args=[self.product1.uuid])

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(status.HTTP_404_NOT_FOUND, response.status_code)

        # Required permissions
        add_perm(self.base_user, "add_product")
        assign_perm("view_product", self.base_user, self.product1)

        response = self.client.get(url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        expected = 'attachment; filename="p1_about.zip"'
        self.assertEqual(expected, response["Content-Disposition"])
        self.assertEqual("application/zip", response["Content-Type"])

    def test_api_product_endpoint_spdx_document_action(self):
        url = reverse("api_v2:product-spdx-document", args=[self.product1.uuid])

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(status.HTTP_404_NOT_FOUND, response.status_code)

        # Required permissions
        add_perm(self.base_user, "add_product")
        assign_perm("view_product", self.base_user, self.product1)

        response = self.client.get(url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        expected = 'attachment; filename="dejacode_nexb_product_p1.spdx.json"'
        self.assertEqual(expected, response["Content-Disposition"])
        self.assertEqual("application/json", response["Content-Type"])

    def test_api_product_endpoint_cyclonedx_sbom_action(self):
        url = reverse("api_v2:product-cyclonedx-sbom", args=[self.product1.uuid])

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(status.HTTP_404_NOT_FOUND, response.status_code)

        # Required permissions
        add_perm(self.base_user, "add_product")
        assign_perm("view_product", self.base_user, self.product1)

        response = self.client.get(url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        expected = 'attachment; filename="dejacode_nexb_product_p1.cdx.json"'
        self.assertEqual(expected, response["Content-Disposition"])
        self.assertEqual("application/json", response["Content-Type"])
        self.assertIn('"specVersion": "1.6"', str(response.getvalue()))

        # Old spec version
        response = self.client.get(url, data={"spec_version": "1.5"})
        self.assertIn('"specVersion": "1.5"', str(response.getvalue()))

        response = self.client.get(url, data={"spec_version": "10.10"})
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual("Spec version 10.10 not supported", response.data)


class ProductRelatedAPITestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="Alternate")

        self.base_user = create_user("base_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)
        self.super_user = create_superuser("super_user", self.dataspace)

        self.product_list_url = reverse("api_v2:product-list")
        self.productcomponent_list_url = reverse("api_v2:productcomponent-list")
        self.productpackage_list_url = reverse("api_v2:productpackage-list")

        self.product1 = Product.objects.create(
            name="Starship Widget Framework", dataspace=self.dataspace
        )
        self.product1_detail_url = reverse("api_v2:product-detail", args=[self.product1.uuid])

        self.product2 = Product.objects.create(name="p2", dataspace=self.dataspace)
        self.product2_detail_url = reverse("api_v2:product-detail", args=[self.product2.uuid])

        self.component1 = Component.objects.create(
            name="c1", version="1.0", dataspace=self.dataspace
        )
        self.component1_detail_url = reverse("api_v2:component-detail", args=[self.component1.uuid])
        self.component2 = Component.objects.create(
            name="c2", version="2.0", dataspace=self.dataspace
        )
        self.component2_detail_url = reverse("api_v2:component-detail", args=[self.component2.uuid])

        self.pc_status1 = ProductRelationStatus.objects.create(
            label="S1", text="Status1", dataspace=self.dataspace
        )

        self.pc1_valid = ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )
        self.pc1_valid_detail_url = reverse(
            "api_v2:productcomponent-detail", args=[self.pc1_valid.uuid]
        )

        self.pc_custom = ProductComponent.objects.create(
            product=self.product1, name="CustomComponent", dataspace=self.dataspace
        )
        self.pc_custom_detail_url = reverse(
            "api_v2:productcomponent-detail", args=[self.pc_custom.uuid]
        )

        self.pc2_valid = ProductComponent.objects.create(
            product=self.product2, component=self.component1, dataspace=self.dataspace
        )
        self.pc2_valid_detail_url = reverse(
            "api_v2:productcomponent-detail", args=[self.pc2_valid.uuid]
        )

        self.package1 = Package.objects.create(filename="package1", dataspace=self.dataspace)
        self.package1_detail_url = reverse("api_v2:package-detail", args=[self.package1.uuid])

        self.pp1 = ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        self.pp1_detail_url = reverse("api_v2:productpackage-detail", args=[self.pp1.uuid])

        self.owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        self.license1 = License.objects.create(
            key="license1",
            name="License1",
            short_name="L1",
            owner=self.owner,
            dataspace=self.dataspace,
        )
        self.license2 = License.objects.create(
            key="license2",
            name="License2",
            short_name="L2",
            owner=self.owner,
            dataspace=self.dataspace,
        )

        self.codebase_resource_list_url = reverse("api_v2:codebaseresource-list")
        self.codebase_resource1 = CodebaseResource.objects.create(
            path="/path1/", product=self.product1, dataspace=self.dataspace
        )
        self.codebase_resource2 = CodebaseResource.objects.create(
            path="/path2/", product=self.product1, dataspace=self.dataspace
        )
        self.codebase_resource1_detail_url = reverse(
            "api_v2:codebaseresource-detail", args=[self.codebase_resource1.uuid]
        )
        self.codebase_resource2_detail_url = reverse(
            "api_v2:codebaseresource-detail", args=[self.codebase_resource2.uuid]
        )

    def test_api_productcomponent_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")
        # with self.assertNumQueries():
        response = self.client.get(self.productcomponent_list_url)

        self.assertEqual(3, response.data["count"])
        self.assertContains(response, self.pc1_valid_detail_url)
        self.assertContains(response, self.pc_custom_detail_url)

    def test_api_secured_productcomponent_list_endpoint_results(self):
        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.productcomponent_list_url)
        self.assertEqual(0, response.data["count"])
        self.assertNotContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        assign_perm("view_product", self.base_user, self.product1)
        response = self.client.get(self.productcomponent_list_url)
        self.assertEqual(2, response.data["count"])
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.productcomponent_list_url)
        self.assertEqual(0, response.data["count"])
        self.assertNotContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        assign_perm("view_product", self.admin_user, self.product1)
        response = self.client.get(self.productcomponent_list_url)
        self.assertEqual(2, response.data["count"])
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

    def test_api_productcomponent_list_endpoint_filters(self):
        self.client.login(username="super_user", password="secret")
        self.assertEqual(3, ProductComponent.objects.count())

        data = {"product": "{}:{}".format(self.product2.name, self.product2.version)}
        response = self.client.get(self.productcomponent_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.product2_detail_url)
        self.assertNotContains(response, self.product1_detail_url)

        p1_c2 = ProductComponent.objects.create(
            product=self.product1, component=self.component2, dataspace=self.dataspace
        )
        data = {"component": "{}:{}".format(self.component2.name, self.component2.version)}
        response = self.client.get(self.productcomponent_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        # Syntax error in name:version value, filters ignored
        data = {"product": "wrongvalue"}
        response = self.client.get(self.productcomponent_list_url, data)
        self.assertEqual(4, response.data["count"])

        # Empty value, filters ignored
        data = {"product": ""}
        response = self.client.get(self.productcomponent_list_url, data)
        self.assertEqual(4, response.data["count"])

        p1_c2.review_status = self.pc_status1
        p1_c2.save()
        data = {"review_status": self.pc_status1.label}
        response = self.client.get(self.productcomponent_list_url, data)
        self.assertEqual(1, response.data["count"])

        data = {"completeness": "catalog"}
        response = self.client.get(self.productcomponent_list_url, data)
        self.assertEqual(3, response.data["count"])
        data = {"completeness": "custom"}
        response = self.client.get(self.productcomponent_list_url, data)
        self.assertEqual(1, response.data["count"])
        data = {"completeness": "wrong_value"}
        response = self.client.get(self.productcomponent_list_url, data)
        expected = {
            "completeness": [
                ErrorDetail(
                    string="Select a valid choice."
                    " wrong_value is not one of the available choices.",
                    code="invalid_choice",
                )
            ]
        }
        self.assertEqual(expected, response.data)

        purpose1 = ProductItemPurpose.objects.create(
            label="Core", text="t", dataspace=self.dataspace
        )
        p1_c2.purpose = purpose1
        p1_c2.save()
        data = {"purpose": purpose1}
        response = self.client.get(self.productcomponent_list_url, data)
        self.assertEqual(1, response.data["count"])

    def test_api_productcomponent_detail_endpoint(self):
        self.client.login(username="super_user", password="secret")

        # with self.assertNumQueries():
        response = self.client.get(self.pc1_valid_detail_url)

        self.assertContains(response, self.product1_detail_url)
        self.assertIn(self.pc1_valid_detail_url, response.data["api_url"])
        self.assertIn(self.product1_detail_url, response.data["product"])
        self.assertIn(self.component1_detail_url, response.data["component"])
        self.assertEqual(str(self.pc1_valid.uuid), response.data["uuid"])

    def test_api_secured_productcomponent_detail_endpoint(self):
        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.pc1_valid_detail_url)
        self.assertEqual(404, response.status_code)

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.pc1_valid_detail_url)
        self.assertEqual(404, response.status_code)

        assign_perm("view_product", self.admin_user, self.product1)
        response = self.client.get(self.pc1_valid_detail_url)
        self.assertContains(response, self.product1_detail_url)
        self.assertIn(self.pc1_valid_detail_url, response.data["api_url"])
        self.assertEqual(str(self.pc1_valid.uuid), response.data["uuid"])

    def test_api_productcomponent_endpoint_create_minimal(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.post(self.productcomponent_list_url)
        expected = {
            "product": ["This field is required."],
        }
        self.assertEqual(expected, response.data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)

        data = {
            "product": self.product1_detail_url,
        }

        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertIn(self.product1_detail_url, response.data["product"])
        self.assertTrue(response.data["is_deployed"])
        self.assertFalse(response.data["is_modified"])

    def test_api_productcomponent_endpoint_create_name_version_support(self):
        self.client.login(username="super_user", password="secret")
        self.assertFalse(self.product1.version)
        self.assertTrue(self.component2.version)

        data = {
            "product": "{}:{}".format(self.product1.name, self.product1.version),
            "component": "{}:{}".format(self.component2.name, self.component2.version),
        }

        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertIn(self.product1_detail_url, response.data["product"])
        self.assertIn(self.component2_detail_url, response.data["component"])

    def test_api_productcomponent_endpoint_create_license_expression_from_choice(self):
        self.client.login(username="super_user", password="secret")

        data = {
            "product": self.product1_detail_url,
            "component": self.component2_detail_url,
            "license_expression": "non-existing-license",
        }
        expected = {"license_expression": ["Unknown license key(s): non-existing-license"]}
        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected, response.data)

        self.assertFalse(self.component2.licenses.exists())
        data["license_expression"] = self.license2.key
        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        ProductComponent.objects.latest("id").delete()
        self.component2.license_expression = self.license1.key
        self.component2.save()
        license_choice = LicenseChoice.objects.create(
            from_expression=self.license1.key,
            to_expression=self.license2.key,
            dataspace=self.dataspace,
        )

        data["license_expression"] = self.license1.key
        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        productcomponent = ProductComponent.objects.latest("id")
        self.assertEqual(1, productcomponent.licenses.count())
        self.assertEqual(self.license1, productcomponent.licenses.get())

        ProductComponent.objects.latest("id").delete()
        license_choice.delete()
        data["license_expression"] = self.license2.key
        expected = {
            "license_expression": [
                "Unknown license key(s): license2<br>Available licenses: license1"
            ]
        }
        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected, response.data)

    def test_api_productcomponent_endpoint_create_permissions(self):
        data = {"product": self.product1_detail_url}

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        add_perm(self.admin_user, "add_productcomponent")
        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)

        assign_perm("view_product", self.admin_user, self.product1)
        add_perm(self.admin_user, "add_productcomponent")
        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

    def test_api_productcomponent_endpoint_create_full(self):
        self.client.login(username="super_user", password="secret")

        self.component2.license_expression = self.license1.key
        self.component2.save()

        purpose = ProductItemPurpose.objects.create(
            label="Core", text="t", dataspace=self.dataspace
        )

        data = {
            "product": self.product2_detail_url,
            "component": self.component2_detail_url,
            "review_status": self.pc_status1.label,
            "license_expression": self.license1.key,
            "purpose": purpose.label,
            "notes": "Notes",
            "is_deployed": False,
            "is_modified": False,
            "extra_attribution_text": "Attrib",
            "feature": "Feature1",
            "package_paths": "Paths",
            "name": "Component",
            "version": "1.0",
            "owner": "Owner",
            "copyright": "Copyright (C)",
            "homepage_url": "http://nexb.com",
            "download_url": "http://nexb.com",
            "primary_language": "Java",
            "reference_notes": "Reference notes",
            "issue_ref": "abc123",
        }

        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        pc = ProductComponent.objects.latest("id")

        self.assertFalse(History.objects.get_for_object(pc).exists())
        self.assertEqual(self.super_user, pc.created_by)
        self.assertTrue(pc.created_date)

        self.assertIn(self.product2_detail_url, data.pop("product"))
        self.assertIn(self.component2_detail_url, data.pop("component"))
        for field_name, value in data.items():
            self.assertEqual(str(value), str(getattr(pc, field_name)), msg=field_name)

        # No email notifications on ProductComponent.
        self.assertEqual(0, len(mail.outbox))

    def test_api_productcomponent_endpoint_update_put(self):
        self.client.login(username="super_user", password="secret")

        put_data = json.dumps(
            {
                "product": self.product1_detail_url,
                "component": self.component1_detail_url,
                "copyright": "Copyright (C)",
            }
        )
        response = self.client.put(
            self.pc1_valid_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        history = History.objects.get_for_object(self.pc1_valid, action_flag=History.CHANGE).latest(
            "id"
        )
        self.assertEqual("Changed copyright.", history.get_change_message())

        # No email notifications on ProductComponent.
        self.assertEqual(0, len(mail.outbox))

        pc1 = ProductComponent.objects.get(pk=self.pc1_valid.pk)
        self.assertEqual("Copyright (C)", pc1.copyright)

    def test_api_productcomponent_endpoint_update_permissions(self):
        put_data = json.dumps(
            {
                "product": self.product1_detail_url,
                "component": self.component1_detail_url,
                "copyright": "Copyright (C)",
            }
        )

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.put(
            self.pc1_valid_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.put(
            self.pc1_valid_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        add_perm(self.admin_user, "change_productcomponent")
        assign_perm("view_product", self.admin_user, self.product1)
        response = self.client.put(
            self.pc1_valid_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_404_NOT_FOUND, response.status_code)

        assign_perm("change_product", self.admin_user, self.product1)
        response = self.client.put(
            self.pc1_valid_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        pc1 = ProductComponent.objects.get(pk=self.pc1_valid.pk)
        self.assertEqual("Copyright (C)", pc1.copyright)

    def test_api_productcomponent_endpoint_permission_protected_fields(self):
        data = {
            "product": self.product1_detail_url,
            "review_status": self.pc_status1.label,
        }

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        assign_perm("view_product", self.admin_user, self.product1)
        add_perm(self.admin_user, "add_productcomponent")
        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertIsNone(ProductComponent.objects.latest("id").review_status)

        self.admin_user = add_perm(self.admin_user, "change_review_status_on_productcomponent")
        response = self.client.post(self.productcomponent_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertEqual(self.pc_status1, ProductComponent.objects.latest("id").review_status)

    def test_api_productrelation_endpoints_tab_permission(self):
        from dje.api_custom import TabPermission  # Prevent circular import

        self.assertEqual((TabPermission,), ProductComponentViewSet.extra_permissions)
        self.assertEqual((TabPermission,), ProductPackageViewSet.extra_permissions)

    def test_api_productpackage_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.productpackage_list_url)

        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.pp1_detail_url)

    def test_api_secured_productpackage_list_endpoint_results(self):
        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.productpackage_list_url)
        self.assertEqual(0, response.data["count"])
        self.assertNotContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        assign_perm("view_product", self.base_user, self.product1)
        response = self.client.get(self.productpackage_list_url)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.productpackage_list_url)
        self.assertEqual(0, response.data["count"])
        self.assertNotContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        assign_perm("view_product", self.admin_user, self.product1)
        response = self.client.get(self.productpackage_list_url)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

    def test_api_productpackage_detail_endpoint(self):
        self.client.login(username="super_user", password="secret")

        response = self.client.get(self.pp1_detail_url)

        self.assertContains(response, self.product1_detail_url)
        self.assertIn(self.pp1_detail_url, response.data["api_url"])
        self.assertIn(self.product1_detail_url, response.data["product"])
        self.assertIn(self.package1_detail_url, response.data["package"])
        self.assertEqual(str(self.pp1.uuid), response.data["uuid"])

    def test_api_secured_productpackage_detail_endpoint(self):
        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.pp1_detail_url)
        self.assertEqual(404, response.status_code)

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.pp1_detail_url)
        self.assertEqual(404, response.status_code)

        assign_perm("view_product", self.admin_user, self.product1)
        response = self.client.get(self.pp1_detail_url)
        self.assertContains(response, self.product1_detail_url)
        self.assertIn(self.pp1_detail_url, response.data["api_url"])
        self.assertEqual(str(self.pp1.uuid), response.data["uuid"])

    def test_api_productpackage_endpoint_create_minimal(self):
        self.pp1.delete()

        self.client.login(username="super_user", password="secret")
        response = self.client.post(self.productpackage_list_url)
        expected = {
            "product": ["This field is required."],
            "package": ["This field is required."],
        }
        self.assertEqual(expected, response.data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)

        data = {
            "product": self.product1_detail_url,
            "package": self.package1_detail_url,
        }

        response = self.client.post(self.productpackage_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertIn(self.product1_detail_url, response.data["product"])
        self.assertTrue(response.data["is_deployed"])
        self.assertFalse(response.data["is_modified"])

    def test_api_productpackage_endpoint_create_permissions(self):
        self.pp1.delete()

        data = {
            "product": self.product1_detail_url,
            "package": self.package1_detail_url,
        }

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.post(self.productpackage_list_url, data)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.post(self.productpackage_list_url, data)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        add_perm(self.admin_user, "add_productpackage")
        response = self.client.post(self.productpackage_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)

        assign_perm("view_product", self.admin_user, self.product1)
        add_perm(self.admin_user, "add_productpackage")
        response = self.client.post(self.productpackage_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

    def test_api_productpackage_endpoint_vulnerabilities_features(self):
        self.client.login(username="super_user", password="secret")
        vulnerability1 = make_vulnerability(self.dataspace, affecting=self.package1)
        vulnerability2 = make_vulnerability(self.dataspace)
        analysis1 = make_vulnerability_analysis(self.pp1, vulnerability1)

        response = self.client.get(self.pp1_detail_url)
        response_analysis = response.data["vulnerability_analyses"][0]
        self.assertEqual(vulnerability1.vulnerability_id, response_analysis["vulnerability_id"])
        self.assertEqual(analysis1.state, response_analysis["state"])
        self.assertEqual(analysis1.justification, response_analysis["justification"])

        data = {"is_vulnerable": "no"}
        response = self.client.get(self.productpackage_list_url, data)
        self.assertEqual(0, response.data["count"])
        self.assertNotContains(response, self.pp1_detail_url)

        data = {"is_vulnerable": "yes"}
        response = self.client.get(self.productpackage_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.pp1_detail_url)

        data = {"affected_by": vulnerability1.vulnerability_id}
        response = self.client.get(self.productpackage_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.pp1_detail_url)

        data = {"affected_by": vulnerability2.vulnerability_id}
        response = self.client.get(self.productpackage_list_url, data)
        self.assertEqual(0, response.data["count"])
        self.assertNotContains(response, self.pp1_detail_url)

    def test_api_product_endpoint_vulnerabilities_features(self):
        self.client.login(username="super_user", password="secret")
        vulnerability1 = make_vulnerability(self.dataspace, affecting=self.package1)
        vulnerability2 = make_vulnerability(self.dataspace)
        analysis1 = make_vulnerability_analysis(self.pp1, vulnerability1)

        response = self.client.get(self.product1_detail_url)
        response_analysis = response.data["vulnerability_analyses"][0]
        self.assertEqual(vulnerability1.vulnerability_id, response_analysis["vulnerability_id"])
        self.assertEqual(analysis1.state, response_analysis["state"])
        self.assertEqual(analysis1.justification, response_analysis["justification"])

        data = {"is_vulnerable": "no"}
        response = self.client.get(self.product_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertNotContains(response, self.product1_detail_url)
        self.assertContains(response, self.product2_detail_url)

        data = {"is_vulnerable": "yes"}
        response = self.client.get(self.product_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        data = {"affected_by": vulnerability1.vulnerability_id}
        response = self.client.get(self.product_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        data = {"affected_by": vulnerability2.vulnerability_id}
        response = self.client.get(self.product_list_url, data)
        self.assertEqual(0, response.data["count"])
        self.assertNotContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

    def test_api_codebaseresource_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.codebase_resource_list_url)
        self.assertEqual(2, response.data["count"])
        self.assertContains(response, self.codebase_resource1)
        self.assertContains(response, self.codebase_resource2)

    def test_api_secured_codebaseresource_list_endpoint_results(self):
        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.codebase_resource_list_url)
        self.assertEqual(0, response.data["count"])
        self.assertNotContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        assign_perm("view_product", self.base_user, self.product1)
        response = self.client.get(self.codebase_resource_list_url)
        self.assertEqual(2, response.data["count"])
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.codebase_resource_list_url)
        self.assertEqual(0, response.data["count"])
        self.assertNotContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

        assign_perm("view_product", self.admin_user, self.product1)
        response = self.client.get(self.codebase_resource_list_url)
        self.assertEqual(2, response.data["count"])
        self.assertContains(response, self.product1_detail_url)
        self.assertNotContains(response, self.product2_detail_url)

    def test_api_codebaseresource_detail_endpoint(self):
        codebase_resource3 = CodebaseResource.objects.create(
            path="/path3/", product=self.product1, dataspace=self.dataspace
        )
        CodebaseResourceUsage.objects.create(
            deployed_from=self.codebase_resource1,
            deployed_to=self.codebase_resource2,
            dataspace=self.dataspace,
        )
        CodebaseResourceUsage.objects.create(
            deployed_from=codebase_resource3,
            deployed_to=self.codebase_resource1,
            dataspace=self.dataspace,
        )

        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.codebase_resource1_detail_url)
        self.assertContains(response, self.product1_detail_url)
        self.assertIn(self.codebase_resource1_detail_url, response.data["api_url"])
        self.assertIn(self.product1_detail_url, response.data["product"])
        self.assertIn(self.codebase_resource1.path, response.data["path"])
        self.assertEqual(str(self.codebase_resource1.uuid), response.data["uuid"])
        self.assertEqual(
            [codebase_resource3.path],
            response.data["deployed_from"],
        )
        self.assertEqual([self.codebase_resource2.path], response.data["deployed_to"])

    def test_api_secured_codebaseresource_detail_endpoint(self):
        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.codebase_resource1_detail_url)
        self.assertEqual(404, response.status_code)

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.codebase_resource1_detail_url)
        self.assertEqual(404, response.status_code)

        assign_perm("view_product", self.admin_user, self.product1)
        response = self.client.get(self.codebase_resource1_detail_url)
        self.assertContains(response, self.product1_detail_url)
        self.assertIn(self.codebase_resource1_detail_url, response.data["api_url"])
        self.assertEqual(str(self.codebase_resource1.uuid), response.data["uuid"])

    def test_api_codebaseresource_endpoint_create_minimal(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.post(self.codebase_resource_list_url)
        expected = {
            "product": ["This field is required."],
            "path": ["This field is required."],
        }
        self.assertEqual(expected, response.data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)

        data = {
            "product": self.product1_detail_url,
            "path": "/new_path/",
        }

        response = self.client.post(self.codebase_resource_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertIn(self.product1_detail_url, response.data["product"])
        self.assertEqual("/new_path/", response.data["path"])
        self.assertFalse(response.data["is_deployment_path"])
        self.assertIsNone(response.data["product_component"])
        self.assertIsNone(response.data["product_package"])
        self.assertEqual({}, response.data["additional_details"])

    def test_api_codebaseresource_endpoint_create_name_version_support(self):
        self.client.login(username="super_user", password="secret")
        self.assertFalse(self.product1.version)

        data = {
            "product": "{}:{}".format(self.product1.name, self.product1.version),
            "path": "/new_path/",
        }

        response = self.client.post(self.codebase_resource_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertIn(self.product1_detail_url, response.data["product"])

    def test_api_codebaseresource_endpoint_create_deployed_from_support(self):
        self.client.login(username="super_user", password="secret")

        data = {
            "product": self.product1_detail_url,
            "path": "/new_path/",
            "deployed_to": "not_a_list",
        }
        response = self.client.post(self.codebase_resource_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"deployed_to": ["Object with path=not_a_list does not exist."]}
        self.assertEqual(expected, response.data)

        data["deployed_to"] = self.codebase_resource1.path
        response = self.client.post(self.codebase_resource_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        resource = CodebaseResource.objects.get(path=data["path"])
        self.assertEqual([data["deployed_to"]], resource.deployed_to_paths)

        data.update(
            {
                "path": "/another_path/",
                "deployed_to": [
                    self.codebase_resource1.path,
                    "not_available",
                ],
            }
        )
        response = self.client.post(self.codebase_resource_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"deployed_to": ["Object with path=not_available does not exist."]}
        self.assertEqual(expected, response.data)

        data["deployed_to"] = [
            self.codebase_resource1.path,
            self.codebase_resource2.path,
        ]
        response = self.client.post(self.codebase_resource_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        resource = CodebaseResource.objects.get(path=data["path"])
        self.assertEqual(data["deployed_to"], resource.deployed_to_paths)

    def test_api_codebaseresource_endpoint_create_permissions(self):
        data = {
            "product": self.product1_detail_url,
            "path": "/new_path/",
        }

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.post(self.codebase_resource_list_url, data)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.post(self.codebase_resource_list_url, data)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        add_perm(self.admin_user, "add_codebaseresource")
        response = self.client.post(self.codebase_resource_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)

        assign_perm("view_product", self.admin_user, self.product1)
        add_perm(self.admin_user, "add_codebaseresource")
        response = self.client.post(self.codebase_resource_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

    def test_api_codebaseresource_endpoint_create_full(self):
        self.client.login(username="super_user", password="secret")

        data = {
            "product": self.product1_detail_url,
            "path": "/new_path/",
            "is_deployment_path": True,
            "product_component": self.pc1_valid_detail_url,
            "product_package": self.pp1_detail_url,
            "additional_details": {"key": "value"},
            "deployed_to": [
                self.codebase_resource1.path,
                self.codebase_resource2.path,
            ],
        }

        response = self.client.post(
            self.codebase_resource_list_url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        resource = CodebaseResource.objects.get(path=data["path"])

        self.assertFalse(History.objects.get_for_object(resource).exists())
        self.assertEqual(self.super_user, resource.created_by)
        self.assertTrue(resource.created_date)

        self.assertIn(self.product1_detail_url, data.pop("product"))
        self.assertIn(self.pc1_valid_detail_url, data.pop("product_component"))
        self.assertIn(self.pp1_detail_url, data.pop("product_package"))
        self.assertEqual(2, resource.deployed_to.count())
        self.assertEqual(resource.deployed_to_paths, data.pop("deployed_to"))

        for field_name, value in data.items():
            self.assertEqual(str(value), str(getattr(resource, field_name)), msg=field_name)

        # No email notifications on CodebaseResource.
        self.assertEqual(0, len(mail.outbox))

    def test_api_codebaseresource_endpoints_tab_permission(self):
        from dje.api_custom import TabPermission  # Prevent circular import

        self.assertEqual((TabPermission,), CodebaseResourceViewSet.extra_permissions)
