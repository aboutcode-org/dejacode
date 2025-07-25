#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import io
import json
from unittest import mock
from urllib.parse import quote

from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.shortcuts import resolve_url
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils.encoding import force_str

from guardian.shortcuts import assign_perm
from guardian.shortcuts import get_user_perms
from notifications.models import Notification

from component_catalog.models import Component
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import ComponentKeyword
from component_catalog.models import Package
from component_catalog.tests import make_package
from dejacode_toolkit import scancodeio
from dje.models import Dataspace
from dje.models import History
from dje.outputs import get_spdx_extracted_licenses
from dje.tests import MaxQueryMixin
from dje.tests import add_perms
from dje.tests import create_superuser
from dje.tests import create_user
from license_library.models import License
from organization.models import Owner
from policy.models import UsagePolicy
from product_portfolio.forms import ProductForm
from product_portfolio.forms import ProductGridConfigurationForm
from product_portfolio.forms import ProductPackageForm
from product_portfolio.models import CodebaseResource
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductItemPurpose
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductRelationStatus
from product_portfolio.models import ProductStatus
from product_portfolio.models import ScanCodeProject
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_dependency
from product_portfolio.tests import make_product_package
from product_portfolio.tests import make_product_status
from product_portfolio.views import ManageComponentGridView
from vulnerabilities.models import VulnerabilityAnalysis
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.tests import make_vulnerability_analysis
from workflow.models import Request
from workflow.models import RequestTemplate


class ProductPortfolioViewsTestCase(MaxQueryMixin, TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="Alternate")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.basic_user = create_user("basic_user", self.dataspace)
        self.alternate_user = create_superuser("alternate_user", self.alternate_dataspace)

        self.product1 = Product.objects.create(
            name="Product1 With Space", version="1.0", dataspace=self.dataspace
        )
        self.product2 = Product.objects.create(
            name="Product2", version="2.0", dataspace=self.dataspace
        )

        self.alternate_product = Product.objects.create(
            name="AlternateProduct", version="1.0", dataspace=self.alternate_dataspace
        )

        self.component1 = Component.objects.create(
            name="Component1", version="1.0", dataspace=self.dataspace
        )

        self.package1 = make_package(self.dataspace, filename="package1")
        self.vulnerability1 = make_vulnerability(self.dataspace, affecting=self.package1)

    @override_settings(ANONYMOUS_USERS_DATASPACE="nexB")
    def test_product_portfolio_security_detail_view_no_cross_dataspace_access(self):
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.product1.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        response = self.client.get(self.alternate_product.get_absolute_url())
        self.assertEqual(response.status_code, 404)

        self.client.login(username=self.alternate_user.username, password="secret")
        response = self.client.get(self.product1.get_absolute_url())
        self.assertEqual(response.status_code, 404)
        response = self.client.get(self.alternate_product.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_product_portfolio_detail_view_access_with_space_in_version(self):
        self.client.login(username="nexb_user", password="secret")
        self.product1.name = "Product with spaces"
        self.product1.version = "v 2015-11 beta"
        self.product1.save()
        url = self.product1.get_absolute_url()
        self.assertIn("/Product+with+spaces/v+2015-11+beta/", url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_product_portfolio_detail_view_secured_queryset(self):
        url = self.product1.get_absolute_url()
        self.client.login(username=self.basic_user.username, password="secret")
        self.assertEqual(404, self.client.get(url).status_code)

        assign_perm("view_product", self.basic_user, self.product1)
        self.assertEqual(200, self.client.get(url).status_code)

    def test_product_portfolio_detail_view_tab_inventory_and_hierarchy_availability(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_absolute_url()
        expected1 = 'id="tab_inventory"'
        expected2 = 'id="tab_hierarchy"'

        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )
        with self.assertNumQueries(30):
            response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

        data = {"components-review_status": "non_existing"}
        response = self.client.get(url, data=data)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertIn("Inventory", response.context["tabsets"])
        self.assertEqual(
            'Inventory <span class="badge text-bg-primary">1</span>',
            response.context["tabsets"]["Inventory"]["label"],
        )

    def test_product_portfolio_detail_view_tab_inventory_availability(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_absolute_url()
        expected = 'id="tab_inventory"'

        response = self.client.get(url)
        self.assertNotContains(response, expected)

        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        with self.assertNumQueries(27):
            response = self.client.get(url)
        self.assertContains(response, expected)

        self.assertIn("Inventory", response.context["tabsets"])
        self.assertEqual(
            'Inventory <span class="badge text-bg-primary">1</span>',
            response.context["tabsets"]["Inventory"]["label"],
        )

    def test_product_portfolio_detail_view_tab_permissions(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_url("tab_inventory")
        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        response = self.client.get(url)
        self.assertTrue(response.context["has_edit_productcomponent"])
        self.assertTrue(response.context["has_delete_productcomponent"])
        self.assertTrue(response.context["has_edit_productpackage"])
        self.assertTrue(response.context["has_delete_productpackage"])
        self.assertContains(response, 'data-can-delete="yes"')

    def test_product_portfolio_detail_view_tab_imports(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_absolute_url()
        expected = 'id="tab_imports"'

        response = self.client.get(url)
        self.assertNotContains(response, expected)

        ScanCodeProject.objects.create(
            product=self.product1,
            dataspace=self.product1.dataspace,
            type=ScanCodeProject.ProjectType.LOAD_SBOMS,
        )

        response = self.client.get(url)
        self.assertContains(response, expected)
        self.assertIn("Imports", response.context["tabsets"])

    def test_product_portfolio_detail_view_tab_imports_view(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_url("tab_imports")

        response = self.client.get(url)
        self.assertContains(response, "<tbody></tbody>", html=True)

        project = ScanCodeProject.objects.create(
            product=self.product1,
            dataspace=self.product1.dataspace,
            type=ScanCodeProject.ProjectType.LOAD_SBOMS,
            status=ScanCodeProject.Status.SUBMITTED,
        )

        response = self.client.get(url)
        self.assertTrue(response.context["has_projects_in_progress"])
        htmx_refresh = 'hx-trigger="load delay:10s" hx-swap="outerHTML"'
        self.assertContains(response, htmx_refresh)
        self.assertContains(response, "Imports are currently in progress.")
        self.assertContains(response, "Import SBOM")

        project.status = ScanCodeProject.Status.SUCCESS
        project.save()
        response = self.client.get(url)
        self.assertFalse(response.context["has_projects_in_progress"])
        self.assertContains(response, "Import SBOM")
        self.assertNotContains(response, "hx-trigger")
        self.assertNotContains(response, "Imports are currently in progress.")

        expected = "File:"
        download_url = reverse(
            "product_portfolio:scancodeio_project_download_input", args=[str(project.uuid)]
        )
        self.assertNotContains(response, expected)
        self.assertNotContains(response, download_url)
        project.input_file = ContentFile("Data", name="data.json")
        project.save()
        response = self.client.get(url)
        self.assertContains(response, expected)
        self.assertContains(response, download_url)

    def test_product_portfolio_detail_view_tab_dependency_view(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_url("tab_dependencies")

        with self.assertMaxQueries(7):
            response = self.client.get(url)
        self.assertContains(response, "0 results")

        package2 = Package.objects.create(filename="package2", dataspace=self.dataspace)
        # Unresolved package dependency
        make_product_dependency(
            product=self.product1,
            for_package=self.package1,
        )
        # Resolved package dependency
        make_product_dependency(
            product=self.product1,
            for_package=self.package1,
            resolved_to_package=package2,
        )
        # Unresolved Product dependency
        make_product_dependency(
            product=self.product1,
            declared_dependency="pkg:type/name",
        )
        # Unresolved Product dependency
        make_product_dependency(
            product=self.product1,
            resolved_to_package=package2,
        )

        with self.assertMaxQueries(9):
            response = self.client.get(url)
        self.assertContains(response, "4 results")

    def test_product_portfolio_detail_view_tab_vulnerability_queryset(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_url("tab_vulnerabilities")

        with self.assertMaxQueries(9):
            response = self.client.get(url)
        self.assertContains(response, "0 results")

        p1 = make_package(self.dataspace, is_vulnerable=True)
        p2 = make_package(self.dataspace, is_vulnerable=True)
        p3 = make_package(self.dataspace, is_vulnerable=True)
        p4 = make_package(self.dataspace, is_vulnerable=True)
        product1 = make_product(self.dataspace, inventory=[p1, p2, p3, p4])

        self.assertEqual(4, product1.packages.count())
        self.assertEqual(4, product1.packages.vulnerable().count())

        url = product1.get_url("tab_vulnerabilities")
        with self.assertMaxQueries(11):
            response = self.client.get(url)
        self.assertContains(response, "4 results")

    def test_product_portfolio_tab_vulnerability_view_filters(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_url("tab_vulnerabilities")
        response = self.client.get(url)
        self.assertContains(response, "?vulnerabilities-weighted_risk_score=#vulnerabilities")
        self.assertContains(response, "?vulnerabilities-sort=weighted_risk_score#vulnerabilities")
        response = self.client.get(
            url + "?vulnerabilities-sort=weighted_risk_score#vulnerabilities"
        )
        self.assertContains(response, "?vulnerabilities-sort=-weighted_risk_score#vulnerabilities")

    def test_product_portfolio_tab_vulnerability_view_packages_row_rendering(self):
        self.client.login(username="nexb_user", password="secret")
        # Each have a unique vulnerability, and p1 p2 are sharing a common one.
        p1 = make_package(self.dataspace)
        p2 = make_package(self.dataspace)
        vulnerability1 = make_vulnerability(self.dataspace, affecting=[p1, p2])
        make_vulnerability(self.dataspace, affecting=[p1])
        product1 = make_product(self.dataspace, inventory=[p1, p2])
        pp1 = product1.productpackages.get(package=p1)

        url = product1.get_url("tab_vulnerabilities")
        response = self.client.get(url)
        expected = f"""
        <td rowspan="2">
          <strong>
            <a href="{p1.get_absolute_url()}#vulnerabilities" target="_blank">{p1}</a>
          </strong>
        </td>
        """
        self.assertContains(response, expected, html=True)

        expected = f"""
        <span data-bs-toggle="modal"
              data-bs-target="#vulnerability-analysis-modal"
              data-vulnerability-id="{vulnerability1.vcid}"
              data-package-identifier="{p1}"
              data-edit-url="/products/vulnerability_analysis/{pp1.uuid}/{vulnerability1.vcid}/"
        >
        <button type="button" data-bs-toggle="tooltip" title="Edit" class="btn btn-link p-0"
                aria-label="Edit">
            <i class="far fa-edit fa-sm"></i>
          </button>
        </span>
        """
        self.assertContains(response, expected, html=True)

    def test_product_portfolio_tab_vulnerability_view_queries(self):
        self.client.login(username="nexb_user", password="secret")
        # Each have a unique vulnerability, and p1 p2 are sharing a common one.
        p1 = make_package(self.dataspace, is_vulnerable=True)
        p2 = make_package(self.dataspace, is_vulnerable=True)
        p3 = make_package(self.dataspace, is_vulnerable=True)
        vulnerability1 = make_vulnerability(self.dataspace, affecting=[p1, p2])
        vulnerability2 = make_vulnerability(self.dataspace, affecting=[p2, p3])
        product1 = make_product(self.dataspace, inventory=[p3])

        product_package1 = make_product_package(product1, package=p1)
        product_package2 = make_product_package(product1, package=p2)
        make_vulnerability_analysis(product_package1, vulnerability1)
        make_vulnerability_analysis(product_package2, vulnerability1)
        make_vulnerability_analysis(product_package2, vulnerability2)

        url = product1.get_url("tab_vulnerabilities")
        with self.assertNumQueries(11):
            self.client.get(url)

    def test_product_portfolio_tab_vulnerability_risk_threshold(self):
        self.client.login(username="nexb_user", password="secret")

        p1 = make_package(self.dataspace, risk_score=1.0)
        p2 = make_package(self.dataspace, risk_score=5.0)
        vulnerability1 = make_vulnerability(self.dataspace, affecting=[p1], risk_score=1.0)
        vulnerability2 = make_vulnerability(self.dataspace, affecting=[p2], risk_score=5.0)
        product1 = make_product(self.dataspace)
        pp1 = make_product_package(product1, package=p1)
        pp2 = make_product_package(product1, package=p2)
        self.assertEqual(1.0, pp1.weighted_risk_score)
        self.assertEqual(5.0, pp2.weighted_risk_score)

        url = product1.get_url("tab_vulnerabilities")
        response = self.client.get(url)
        self.assertContains(response, vulnerability1.vcid)
        self.assertContains(response, vulnerability2.vcid)
        self.assertContains(response, "2 results")
        self.assertNotContains(response, "A risk threshold filter at")

        product1.update(vulnerabilities_risk_threshold=3.0)
        response = self.client.get(url)
        self.assertNotContains(response, vulnerability1.vcid)
        self.assertContains(response, vulnerability2.vcid)
        self.assertContains(response, "1 results")
        self.assertContains(response, 'A risk threshold filter at "3.0" is currently applied.')

    def test_product_portfolio_tab_vulnerability_view_analysis_rendering(self):
        self.client.login(username="nexb_user", password="secret")
        # Each have a unique vulnerability, and p1 p2 are sharing a common one.
        p1 = make_package(self.dataspace, is_vulnerable=True, name="p1")
        p2 = make_package(self.dataspace, is_vulnerable=True, name="p2")
        vulnerability1 = make_vulnerability(self.dataspace, affecting=[p1, p2])
        product1 = make_product(self.dataspace)
        product_package1 = make_product_package(product1, package=p1)
        make_product_package(product1, package=p2)
        make_vulnerability_analysis(product_package1, vulnerability1)

        url = product1.get_url("tab_vulnerabilities")
        response = self.client.get(url)

        expected = """
        <td>
          <strong>Resolved</strong>
          <span data-bs-toggle="popover" data-bs-placement="right" data-bs-trigger="hover focus"
                data-bs-html="true" data-bs-content="detail">
            <i class="fa-solid fa-circle-info text-muted"></i>
          </span>
        </td>
        <td>Code Not Present</td>
        <td>
          <ul class="ps-3 m-0">
            <li>can_not_fix</li>
            <li>rollback</li>
          </ul>
        </td>
        """
        self.assertContains(response, expected, html=True)

    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.is_configured")
    def test_product_portfolio_detail_view_include_tab_vulnerability_analysis_modal(
        self, mock_is_configured
    ):
        mock_is_configured.return_value = True
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_absolute_url()
        modal_id = 'id="vulnerability-analysis-modal"'
        modal_js = "$('#vulnerability-analysis-modal')"

        self.assertFalse(self.dataspace.enable_vulnerablecodedb_access)
        response = self.client.get(url)
        self.assertNotContains(response, modal_id)
        self.assertNotContains(response, modal_js)

        self.dataspace.enable_vulnerablecodedb_access = True
        self.dataspace.save()
        self.assertEqual(0, self.product1.get_vulnerability_qs().count())
        response = self.client.get(url)
        self.assertNotContains(response, modal_id)
        self.assertNotContains(response, modal_js)

        package1 = make_package(self.dataspace, is_vulnerable=True)
        make_product_package(self.product1, package=package1)
        self.assertEqual(1, self.product1.get_vulnerability_qs().count())
        response = self.client.get(url)
        self.assertContains(response, modal_id)
        self.assertContains(response, modal_js)

    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.is_configured")
    def test_product_portfolio_detail_view_tab_vulnerability_label(self, mock_is_configured):
        mock_is_configured.return_value = True
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_absolute_url()
        response = self.client.get(url)
        self.assertNotContains(response, "tab_vulnerabilities")

        self.dataspace.enable_vulnerablecodedb_access = True
        self.dataspace.save()
        response = self.client.get(url)
        expected = 'aria-controls="tab_vulnerabilities" aria-selected="false" disabled="disabled"'
        self.assertContains(response, expected)
        expected = 'data-bs-toggle="tooltip" title="No vulnerabilities found in this Product"'
        self.assertContains(response, expected)

        package1 = make_package(self.dataspace, is_vulnerable=True)
        make_product_package(self.product1, package=package1)
        response = self.client.get(url)
        expected = 'Vulnerabilities<span class="badge badge-vulnerability'
        self.assertContains(response, expected)

    def test_product_portfolio_detail_view_object_type_filter_in_inventory_tab(self):
        self.client.login(username="nexb_user", password="secret")

        pc_valid = ProductComponent.objects.create(
            product=self.product1,
            component=self.component1,
            is_deployed=False,
            dataspace=self.dataspace,
        )
        pc2_custom = ProductComponent.objects.create(
            product=self.product1, name="temporary name", is_modified=True, dataspace=self.dataspace
        )
        self.package1.update(risk_score=1.0)
        pp1 = ProductPackage.objects.create(
            product=self.product1,
            package=self.package1,
            dataspace=self.dataspace,
        )

        response = self.client.get(self.product1.get_absolute_url())
        self.assertContains(response, 'id="tab_inventory"')

        url = self.product1.get_url("tab_inventory")
        response = self.client.get(url)
        pc_filterset = response.context["inventory_items"][""]

        expected = """
        <div class="dropdown-menu" id="id_inventory-object_type">
          <a href="?inventory-object_type=#inventory" class="dropdown-item active">All</a>
          <a href="?inventory-object_type=catalog#inventory" class="dropdown-item">
            Catalog Components
          </a>
          <a href="?inventory-object_type=custom#inventory" class="dropdown-item">
            Custom Components
          </a>
          <a href="?inventory-object_type=package#inventory" class="dropdown-item">
            Packages
          </a>
        </div>
        """
        self.assertIn(pc_valid, pc_filterset)
        self.assertIn(pc2_custom, pc_filterset)
        self.assertIn(pp1, pc_filterset)
        self.assertContains(response, expected, html=True)

        response = self.client.get(url + "?inventory-object_type=catalog")
        pc_filterset = response.context["inventory_items"][""]
        self.assertIn(pc_valid, pc_filterset)
        self.assertNotIn(pc2_custom, pc_filterset)
        self.assertNotIn(pp1, pc_filterset)

        response = self.client.get(url + "?inventory-object_type=custom")
        pc_filterset = response.context["inventory_items"][""]
        self.assertNotIn(pc_valid, pc_filterset)
        self.assertIn(pc2_custom, pc_filterset)
        self.assertNotIn(pp1, pc_filterset)

        response = self.client.get(url + "?inventory-object_type=package")
        pc_filterset = response.context["inventory_items"][""]
        self.assertNotIn(pc_valid, pc_filterset)
        self.assertNotIn(pc2_custom, pc_filterset)
        self.assertIn(pp1, pc_filterset)

        response = self.client.get(url + "?inventory-object_type=ANYTHINGELSE")
        pc_filterset = response.context["inventory_items"]
        self.assertEqual({}, pc_filterset)

        response = self.client.get(url + "?inventory-is_deployed=no")
        pc_filterset = response.context["inventory_items"][""]
        self.assertIn(pc_valid, pc_filterset)
        self.assertNotIn(pc2_custom, pc_filterset)
        self.assertNotIn(pp1, pc_filterset)

        response = self.client.get(url + "?inventory-is_modified=yes")
        pc_filterset = response.context["inventory_items"][""]
        self.assertNotIn(pc_valid, pc_filterset)
        self.assertIn(pc2_custom, pc_filterset)
        self.assertNotIn(pp1, pc_filterset)

        response = self.client.get(url + "?inventory-weighted_risk_score=low")
        pc_filterset = response.context["inventory_items"][""]
        self.assertNotIn(pc_valid, pc_filterset)
        self.assertNotIn(pc2_custom, pc_filterset)
        self.assertIn(pp1, pc_filterset)

    def test_product_portfolio_detail_view_review_status_filter_in_inventory_tab(self):
        self.client.login(username="nexb_user", password="secret")

        status1 = ProductRelationStatus.objects.create(label="s1", dataspace=self.dataspace)
        status2 = ProductRelationStatus.objects.create(label="s2", dataspace=self.dataspace)
        component2 = Component.objects.create(name="component2", dataspace=self.dataspace)
        pc1 = ProductComponent.objects.create(
            product=self.product1,
            component=self.component1,
            review_status=status1,
            dataspace=self.dataspace,
        )
        pc2 = ProductComponent.objects.create(
            product=self.product1,
            component=component2,
            review_status=status2,
            dataspace=self.dataspace,
        )
        pp1 = ProductPackage.objects.create(
            product=self.product1,
            package=self.package1,
            review_status=status1,
            dataspace=self.dataspace,
        )

        url = self.product1.get_url("tab_inventory")
        response = self.client.get(url)

        self.assertContains(response, self.component1.name)
        self.assertContains(response, component2.name)
        self.assertContains(response, self.package1.filename)

        self.assertContains(
            response,
            '<a href="?inventory-review_status=#inventory" class="dropdown-item active">All</a>',
        )
        expected1 = (
            f'<a href="?inventory-review_status={status1.label}#inventory" '
            f'class="dropdown-item">{status1.label}</a>'
        )
        self.assertContains(response, expected1)
        expected2 = (
            f'<a href="?inventory-review_status={status2.label}#inventory" '
            f'class="dropdown-item">{status2.label}</a>'
        )
        self.assertContains(response, expected2)

        response = self.client.get(url, data={"inventory-review_status": status1.label})
        pc_filterset = response.context["inventory_items"][""]
        self.assertIn(pc1, pc_filterset)
        self.assertNotIn(pc2, pc_filterset)
        self.assertIn(pp1, pc_filterset)

    def test_product_portfolio_detail_view_inventory_tab_filters(self):
        self.client.login(username=self.super_user.username, password="secret")

        package2 = Package.objects.create(filename="package2", dataspace=self.dataspace)
        pp1 = ProductPackage.objects.create(
            product=self.product1, package=self.package1, is_modified=True, dataspace=self.dataspace
        )
        pp2 = ProductPackage.objects.create(
            product=self.product1, package=package2, is_modified=False, dataspace=self.dataspace
        )

        url = self.product1.get_url("tab_inventory")
        response = self.client.get(url)
        self.assertContains(response, self.package1.filename)
        self.assertContains(response, package2.filename)

        data = {"inventory-is_modified": "yes"}
        response = self.client.get(url, data=data)
        pp_filterset = response.context["inventory_items"][""]
        self.assertIn(pp1, pp_filterset)
        self.assertNotIn(pp2, pp_filterset)

    def test_product_portfolio_detail_view_inventory_tab_compliance_alerts(self):
        self.client.login(username="nexb_user", password="secret")

        license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            compliance_alert=UsagePolicy.Compliance.ERROR,
            dataspace=self.dataspace,
        )
        component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            compliance_alert=UsagePolicy.Compliance.ERROR,
            dataspace=self.dataspace,
        )
        license1 = License.objects.create(
            key="l1",
            name="L1",
            short_name="L1",
            usage_policy=license_policy,
            owner=Owner.objects.create(name="Owner1", dataspace=self.dataspace),
            dataspace=self.dataspace,
        )
        pc = ProductComponent.objects.create(
            product=self.product1,
            component=self.component1,
            license_expression=license1.key,
            dataspace=self.dataspace,
        )

        self.component1.usage_policy = component_policy
        self.component1.save()
        self.assertEqual("error", pc.inventory_item_compliance_alert)

        self.assertTrue(self.super_user.dataspace.show_usage_policy_in_user_views)
        url = self.product1.get_url("tab_inventory")
        response = self.client.get(url)
        self.assertContains(response, "Compliance errors")
        self.assertContains(response, "table-danger")

    def test_product_portfolio_detail_view_inventory_tab_purpose_icon(self):
        self.client.login(username="nexb_user", password="secret")

        purpose = ProductItemPurpose.objects.create(
            label="Core",
            text="t",
            icon="icon",
            color_code="#123456",
            dataspace=self.dataspace,
        )
        ProductComponent.objects.create(
            product=self.product1,
            component=self.component1,
            purpose=purpose,
            dataspace=self.dataspace,
        )

        url = self.product1.get_url("tab_inventory")
        response = self.client.get(url)
        expected = (
            '<div class="text-nowrap">'
            '<i class="icon" style="color: #123456;"></i>'
            '<span class="ms-1">Core</span>'
            "</div>"
        )
        self.assertContains(response, expected, html=True)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_list")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.is_configured")
    def test_product_portfolio_detail_view_inventory_tab_display_scan_features(
        self, mock_is_configured, mock_fetch_scan_list
    ):
        mock_is_configured.return_value = True
        self.client.login(username=self.super_user.username, password="secret")
        self.assertFalse(self.super_user.dataspace.enable_package_scanning)
        mock_fetch_scan_list.return_value = None

        url = self.product1.get_url("tab_inventory")
        expected1 = "#scan-package-modal"
        expected2 = "Submit Scan Request"
        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        self.super_user.dataspace.enable_package_scanning = True
        self.super_user.dataspace.save()

        self.assertFalse(self.product1.packages.exists())
        response = self.client.get(url)
        mock_fetch_scan_list.assert_not_called()
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        self.package1.download_url = "https://download_url.value"
        self.package1.save()
        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        response = self.client.get(url)
        mock_fetch_scan_list.assert_called()
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

    def test_product_portfolio_detail_view_inventory_tab_display_vulnerabilities(self):
        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        self.client.login(username=self.super_user.username, password="secret")
        url = self.product1.get_url("tab_inventory")
        response = self.client.get(url)

        expected = f"""
        <a href="{self.package1.details_url}#vulnerabilities" class="vulnerability"
           data-bs-toggle="tooltip" title="Vulnerabilities">
          <i class="fas fa-bug"></i>1
        </a>
        """
        self.assertContains(response, expected, html=True)

    def test_product_portfolio_detail_view_feature_field_grouping_in_inventory_tab(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_url("tab_inventory")
        self.client.get(url)

        pc_valid = ProductComponent.objects.create(
            product=self.product1,
            component=self.component1,
            is_deployed=False,
            dataspace=self.dataspace,
            feature="f2",
        )
        pc2_custom = ProductComponent.objects.create(
            product=self.product1,
            name="temporary name",
            is_modified=True,
            dataspace=self.dataspace,
            feature="f1",
        )
        pp1 = ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace, feature="f1"
        )

        response = self.client.get(url)
        feature_grouped = response.context["inventory_items"]
        expected = {
            "f1": [pc2_custom, pp1],
            "f2": [pc_valid],
        }
        self.assertEqual(expected, feature_grouped)

        self.assertContains(
            response, '<td colspan="100" class="sub-header"><strong>f1</strong></td>'
        )
        self.assertContains(
            response, '<td colspan="100" class="sub-header"><strong>f2</strong></td>'
        )

    def test_product_portfolio_detail_view_configuration_status(self):
        self.client.login(username="nexb_user", password="secret")

        configuration_status = ProductStatus.objects.create(
            label="Status1", dataspace=self.dataspace
        )
        self.product1.configuration_status = configuration_status
        self.product1.save()

        url = self.product1.get_absolute_url()
        response = self.client.get(url)

        self.assertContains(response, "Status1")
        self.assertContains(response, "Configuration status")

    def test_product_portfolio_detail_view_exclude_reference_data_label(self):
        url = self.product1.get_absolute_url()
        self.assertTrue(self.product1.dataspace.is_reference)
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(url)
        self.assertNotContains(response, "Reference Data")

    def test_product_portfolio_detail_view_workflow_request(self):
        self.client.login(username="nexb_user", password="secret")
        product_ct = ContentType.objects.get_for_model(Product)
        request_template_product = RequestTemplate.objects.create(
            name="P",
            description="D",
            dataspace=self.super_user.dataspace,
            is_active=True,
            content_type=product_ct,
        )
        request_product = Request.objects.create(
            title="Title",
            request_template=request_template_product,
            requester=self.super_user,
            content_object=self.product1,
            dataspace=self.dataspace,
        )

        component_ct = ContentType.objects.get_for_model(Component)
        request_template_component = RequestTemplate.objects.create(
            name="C",
            description="D",
            dataspace=self.super_user.dataspace,
            is_active=True,
            content_type=component_ct,
        )
        Request.objects.create(
            title="Title",
            request_template=request_template_component,
            requester=self.super_user,
            content_object=self.component1,
            dataspace=self.dataspace,
        )
        ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )

        response = self.client.get(self.product1.get_absolute_url())

        # Request templates button dropdown
        self.assertContains(
            response,
            '<a class="btn btn-request dropdown-toggle" data-bs-toggle="dropdown" '
            '   role="button" href="#">Requests</a>',
            html=True,
        )
        self.assertContains(
            response,
            f'<a class="dropdown-item" href="{request_template_product.get_absolute_url()}'
            f'?content_object_id={self.product1.id}">',
        )

        # Activity tab
        self.assertContains(response, 'id="tab_activity"')
        self.assertContains(
            response,
            f'<a href="{request_product.get_absolute_url()}">'
            f"{request_product} {request_product.title}</a>",
        )
        self.assertContains(response, "Open")
        self.assertContains(response, request_template_product.name)

        # Request R icon link in Inventory tab
        expected = (
            f'<a href="{self.component1.get_absolute_url()}#activity" '
            f'data-bs-toggle="tooltip" title="Requests">'
        )
        self.assertContains(response, expected)

    def test_product_portfolio_detail_view_license_tab(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_absolute_url()

        owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        l1 = License.objects.create(
            key="l1",
            name="L1",
            short_name="L1",
            owner=owner1,
            is_active=False,
            dataspace=self.dataspace,
        )
        l2 = License.objects.create(
            key="l2",
            name="L2",
            short_name="L2",
            owner=owner1,
            is_active=False,
            dataspace=self.dataspace,
        )

        self.product1.license_expression = f"{l1.key} AND {l2.key}"
        self.product1.save()

        l1_str = f"{l1.short_name} ({l1.key})"
        l2_str = f"{l2.short_name} ({l2.key})"
        response = self.client.get(url)

        self.assertContains(response, 'id="tab_license"')

        def no_whitespace(s):
            return "".join(force_str(s).split())

        expected = f"<td>{l1_str}</td><td>{l2_str}</td>"
        self.assertIn(no_whitespace(expected), no_whitespace(response.content))

        self.product1.license_expression = f"{l2.key} AND {l1.key}"
        self.product1.save()
        response = self.client.get(url)
        expected = f"<td>{l2_str}</td><td>{l1_str}</td>"
        self.assertIn(no_whitespace(expected), no_whitespace(response.content))

    def test_product_portfolio_detail_view_hierarchy_tab(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_absolute_url()
        pc1 = ProductComponent.objects.create(
            product=self.product1,
            component=self.component1,
            dataspace=self.dataspace,
            feature="feature1",
        )
        pp1 = ProductPackage.objects.create(
            product=self.product1,
            package=self.package1,
            dataspace=self.dataspace,
            feature="feature2",
        )
        self.assertEqual(1, self.product1.productcomponents.count())
        self.assertEqual(1, self.product1.productpackages.count())

        response = self.client.get(url)
        self.assertIn("Hierarchy", response.context["tabsets"])

        hierarchy_fields = response.context["tabsets"]["Hierarchy"]["fields"]
        feature_grouped = hierarchy_fields[0][1]["relations_feature_grouped"]
        expected = {
            "feature1": [pc1],
            "feature2": [pp1],
        }
        self.assertEqual(expected, feature_grouped)

        expected_in_response = [
            f'<div id="product_{self.product1.id}" class="card bg-body-tertiary mb-2">',
            f'<div id="component_{pc1.id}" class="card bg-body-tertiary mb-2">',
            f'<div id="package_{pp1.id}" class="card bg-body-tertiary mb-2">',
            f"var target_id = 'product_{self.product1.id}'",
            f"var source_id = 'component_{pc1.id}'",
            f"var source_id = 'package_{pp1.id}'",
            f'<h4 class="feature-title text-center">{pc1.feature}</h4>',
            f'<h4 class="feature-title text-center">{pp1.feature}</h4>',
            '<i class="fa fa-briefcase cursor-help"></i>',
            '<i class="fa fa-puzzle-piece cursor-help"></i>',
            '<i class="fa fa-archive cursor-help"></i>',
        ]

        for expected in expected_in_response:
            self.assertContains(response, expected)

    def test_product_portfolio_detail_view_codebase_tab_loader(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.product1.get_absolute_url()
        response = self.client.get(url)
        self.assertNotIn("Codebase", response.context["tabsets"])

        CodebaseResource.objects.create(
            path="/path1/", product=self.product1, dataspace=self.dataspace
        )
        response = self.client.get(url)
        self.assertIn("Codebase", response.context["tabsets"])
        self.assertContains(response, "Fetching codebase resources...")
        tab_codebase_view_url = self.product1.get_url("tab_codebase")
        self.assertContains(response, tab_codebase_view_url)

    def test_product_portfolio_detail_view_codebase_tab_view(self):
        self.client.login(username="nexb_user", password="secret")
        tab_codebase_view_url = self.product1.get_url("tab_codebase")
        response = self.client.get(tab_codebase_view_url)

        self.assertContains(response, 'id="tab-codebase-search-input"')
        self.assertContains(response, "0 results")
        self.assertContains(response, '<span class="page-link">Page 1 of 1</span>')
        self.assertContains(response, "No results.")

        CodebaseResource.objects.create(
            path="/path1/", product=self.product1, dataspace=self.dataspace
        )
        CodebaseResource.objects.create(
            path="/path2/", product=self.product1, dataspace=self.dataspace
        )
        response = self.client.get(tab_codebase_view_url)
        self.assertContains(response, "2 results")
        self.assertContains(response, "/path1/")
        self.assertContains(response, "/path2/")

        data = {"codebase-q": "path1"}
        response = self.client.get(tab_codebase_view_url, data=data)
        self.assertContains(response, "1 results")
        self.assertContains(response, "/path1/")
        self.assertNotContains(response, "/path2/")

        data = {"codebase-is_deployment_path": "yes"}
        response = self.client.get(tab_codebase_view_url, data=data)
        self.assertContains(response, '<a href="?all=true#codebase">Clear search and filters</a>')
        self.assertContains(response, "0 results")
        self.assertNotContains(response, "/path1/")
        self.assertNotContains(response, "/path2/")

    def test_product_portfolio_detail_edit_productpackage_permissions(self):
        self.client.login(username=self.basic_user.username, password="secret")

        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        url = self.product1.get_absolute_url()

        edit_link = "#edit-productrelation-modal"
        edit_modal = "edit-productrelation-modal"
        delete_button = 'id="update-productrelation-delete"'

        assign_perm("view_product", self.basic_user, self.product1)
        response = self.client.get(url)
        self.assertNotContains(response, edit_link)
        self.assertNotContains(response, edit_modal)
        self.assertNotContains(response, delete_button)

        assign_perm("change_product", self.basic_user, self.product1)
        response = self.client.get(url)
        self.assertNotContains(response, edit_link)
        self.assertNotContains(response, edit_modal)
        self.assertNotContains(response, delete_button)

        add_perms(self.basic_user, ["change_product", "change_productpackage"])
        response = self.client.get(url)
        self.assertContains(response, edit_link)
        self.assertContains(response, edit_modal)
        self.assertNotContains(response, delete_button)

        add_perms(self.basic_user, ["delete_productpackage"])
        response = self.client.get(url)
        self.assertContains(response, delete_button)

    def test_product_portfolio_detail_edit_productcomponent_permissions(self):
        self.client.login(username=self.basic_user.username, password="secret")

        ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )
        url = self.product1.get_absolute_url()

        edit_link = "#edit-productrelation-modal"
        edit_modal = "edit-productrelation-modal"
        delete_button = 'id="update-productrelation-delete"'

        assign_perm("view_product", self.basic_user, self.product1)
        response = self.client.get(url)
        self.assertNotContains(response, edit_link)
        self.assertNotContains(response, edit_modal)
        self.assertNotContains(response, delete_button)

        assign_perm("change_product", self.basic_user, self.product1)
        response = self.client.get(url)
        self.assertNotContains(response, edit_link)
        self.assertNotContains(response, edit_modal)
        self.assertNotContains(response, delete_button)

        add_perms(self.basic_user, ["change_product", "change_productcomponent"])
        response = self.client.get(url)
        self.assertContains(response, edit_link)
        self.assertContains(response, edit_modal)
        self.assertNotContains(response, delete_button)

        add_perms(self.basic_user, ["delete_productcomponent"])
        response = self.client.get(url)
        self.assertContains(response, delete_button)

    def test_product_portfolio_detail_view_display_purldb_features(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.assertFalse(self.super_user.dataspace.enable_purldb_access)
        url = self.product1.get_absolute_url()

        expected1 = '<div class="dropdown-header">PurlDB</div>'
        expected2 = "<strong>Improve</strong> Packages from PurlDB"
        expected3 = self.product1.get_url("improve_packages_from_purldb")

        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)

        self.dataspace.enable_purldb_access = True
        self.dataspace.save()
        url = self.product1.get_absolute_url()
        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)

    def test_product_portfolio_detail_view_status_is_locked(self):
        self.client.login(username=self.super_user.username, password="secret")
        url = self.product1.get_absolute_url()
        expected1 = (
            '<button type="button" class="btn btn-outline-dark dropdown-toggle" disabled>'
            '<i class="fas fa-tasks"></i> Manage'
            "</button>"
        )
        expected2 = (
            '<button type="button" class="btn btn-outline-dark dropdown-toggle" disabled>'
            '<i class="fas fa-toolbox"></i> Actions'
            "</button>"
        )
        expected3 = (
            "This product version is marked as read-only, preventing any modifications "
            "to its inventory."
        )

        locked_status = make_product_status(self.dataspace, is_locked=True)
        self.product1.update(configuration_status=locked_status)
        response = self.client.get(url)
        self.assertContains(response, expected1, html=True)
        self.assertContains(response, expected2, html=True)
        self.assertContains(response, expected3, html=True)

    def test_product_portfolio_list_view_secured_queryset(self):
        self.client.login(username=self.basic_user.username, password="secret")
        url = resolve_url("product_portfolio:product_list")
        response = self.client.get(url)
        self.assertContains(response, "No results.")
        self.assertEqual(0, len(response.context_data["object_list"]))

        assign_perm("view_product", self.basic_user, self.product1)
        response = self.client.get(url)
        self.assertEqual(1, len(response.context_data["object_list"]))
        self.assertIn(self.product1, response.context_data["object_list"])
        self.assertNotIn(self.product2, response.context_data["object_list"])

        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertEqual(2, len(response.context_data["object_list"]))
        self.assertIn(self.product1, response.context_data["object_list"])
        self.assertIn(self.product2, response.context_data["object_list"])

    def test_product_portfolio_list_view_admin_links(self):
        self.client.login(username=self.super_user.username, password="secret")
        url = resolve_url("product_portfolio:product_list")
        response = self.client.get(url)

        add_url = reverse("admin:product_portfolio_product_add")
        changelist_url = reverse("admin:product_portfolio_product_changelist")
        import_component_url = reverse("admin:product_portfolio_productcomponent_import")
        import_package_url = reverse("admin:product_portfolio_productpackage_import")
        import_codebaseresource_url = reverse("admin:product_portfolio_codebaseresource_import")
        expected3 = (
            f'<a href="{import_component_url}" class="dropdown-item">Import product components</a>'
        )
        expected4 = (
            f'<a href="{import_package_url}" class="dropdown-item">Import product packages</a>'
        )
        expected5 = (
            f'<a href="{import_codebaseresource_url}" class="dropdown-item">'
            f"Import codebase resources</a>"
        )

        self.assertNotContains(response, add_url, html=True)
        self.assertNotContains(response, changelist_url, html=True)
        self.assertContains(response, expected3, html=True)
        self.assertContains(response, expected4, html=True)
        self.assertContains(response, expected5, html=True)

        self.super_user.is_superuser = False
        self.super_user.is_staff = False
        self.super_user.save()
        response = self.client.get(url)
        self.assertNotContains(response, add_url, html=True)
        self.assertNotContains(response, changelist_url, html=True)
        self.assertNotContains(response, expected3, html=True)
        self.assertNotContains(response, expected4, html=True)
        self.assertNotContains(response, expected5, html=True)

        self.super_user.is_staff = True
        self.super_user.save()
        response = self.client.get(url)
        self.assertNotContains(response, add_url, html=True)
        self.assertNotContains(response, changelist_url, html=True)
        self.assertNotContains(response, expected3, html=True)
        self.assertNotContains(response, expected4, html=True)
        self.assertNotContains(response, expected5, html=True)

        perms = ["add_product", "change_product", "add_productcomponent"]
        self.super_user = add_perms(self.super_user, perms)
        response = self.client.get(url)
        self.assertNotContains(response, add_url, html=True)
        self.assertNotContains(response, changelist_url, html=True)
        self.assertContains(response, expected3, html=True)
        self.assertNotContains(response, expected4, html=True)
        self.assertNotContains(response, expected5, html=True)

        self.super_user = add_perms(self.super_user, ["add_productpackage"])
        response = self.client.get(url)
        self.assertContains(response, expected4, html=True)

        self.super_user = add_perms(self.super_user, ["add_codebaseresource"])
        response = self.client.get(url)
        self.assertContains(response, expected5, html=True)

    def test_product_portfolio_list_view_add_product_link(self):
        self.client.login(username=self.super_user.username, password="secret")
        url = resolve_url("product_portfolio:product_list")
        response = self.client.get(url)

        add_url = reverse("product_portfolio:product_add")
        self.assertContains(response, add_url)

        self.super_user.is_superuser = False
        self.super_user.is_staff = False
        self.super_user.save()
        response = self.client.get(url)
        self.assertNotContains(response, add_url)

        perms = ["add_product"]
        self.super_user = add_perms(self.super_user, perms)
        response = self.client.get(url)
        self.assertContains(response, add_url)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.is_configured")
    def test_product_portfolio_details_view_admin_links(self, mock_is_configured):
        mock_is_configured.return_value = True

        self.client.login(username=self.super_user.username, password="secret")
        url = self.product1.get_absolute_url()
        self.super_user.dataspace.enable_package_scanning = True
        self.super_user.dataspace.save()

        manage_components_url = self.product1.get_manage_components_url()
        manage_packages_url = self.product1.get_manage_packages_url()
        expected1 = "Scan all Packages"

        response = self.client.get(url)
        self.assertContains(response, expected1, html=True)
        self.assertContains(response, manage_components_url)
        self.assertContains(response, manage_packages_url)

        self.super_user.is_superuser = False
        self.super_user.is_staff = False
        self.super_user.save()
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

        self.super_user.is_staff = True
        self.super_user.save()
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

        assign_perm("view_product", self.super_user, self.product1)
        response = self.client.get(url)
        self.assertNotContains(response, expected1, html=True)
        self.assertNotContains(response, manage_components_url)
        self.assertNotContains(response, manage_packages_url)

        perms = ["change_productcomponent"]
        self.super_user = add_perms(self.super_user, perms)
        response = self.client.get(url)
        self.assertNotContains(response, expected1, html=True)
        self.assertNotContains(response, manage_components_url)
        self.assertNotContains(response, manage_packages_url)

        assign_perm("change_product", self.super_user, self.product1)
        response = self.client.get(url)
        self.assertNotContains(response, expected1, html=True)
        self.assertContains(response, manage_components_url)
        self.assertNotContains(response, manage_packages_url)

        self.super_user = add_perms(self.super_user, ["change_productpackage"])
        response = self.client.get(url)
        self.assertNotContains(response, expected1, html=True)
        self.assertContains(response, manage_components_url)
        self.assertContains(response, manage_packages_url)

        self.super_user.is_superuser = True
        self.super_user.save()
        response = self.client.get(url)
        self.assertContains(response, expected1, html=True)

    def test_product_portfolio_list_view_request_links(self):
        self.client.login(username="nexb_user", password="secret")

        product_ct = ContentType.objects.get_for_model(Product)
        request_template_product = RequestTemplate.objects.create(
            name="P",
            description="D",
            dataspace=self.super_user.dataspace,
            is_active=True,
            content_type=product_ct,
        )
        Request.objects.create(
            title="Title",
            request_template=request_template_product,
            requester=self.super_user,
            content_object=self.product1,
            dataspace=self.dataspace,
        )

        response = self.client.get(resolve_url("product_portfolio:product_list"))
        expected = f"""
        <a href="{self.product1.get_absolute_url()}#activity" class="r-link">
            <span class="badge text-bg-request">R</span>
        </a>"""
        self.assertContains(response, expected, html=True)

    def test_product_portfolio_list_view_license_expression(self):
        self.client.login(username="nexb_user", password="secret")

        owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        l1 = License.objects.create(
            key="l1", name="L1", short_name="L1", owner=owner1, dataspace=self.dataspace
        )

        self.product1.license_expression = l1.key
        self.product1.save()
        self.assertIn(l1, self.product1.licenses.all())

        response = self.client.get(resolve_url("product_portfolio:product_list"))
        expected = (
            f'<td><span class="license-expression">'
            f'<a href="{l1.get_absolute_url()}" title="{l1.short_name}">{l1.key}</a>'
            f"</span></td>"
        )
        self.assertContains(response, expected, html=True)

    def test_product_portfolio_list_view_compare_button(self):
        self.client.login(username="nexb_user", password="secret")
        url = resolve_url("product_portfolio:product_list")
        response = self.client.get(url)
        expected = """
        <button id="compare_button" href="/products/compare/" class="btn btn-outline-dark disabled">
          <i class="fa-solid fa-code-compare"></i> Compare
        </button>
        """
        self.assertContains(response, expected, html=True)

    def test_product_portfolio_list_view_search(self):
        self.client.login(username="nexb_user", password="secret")
        url = resolve_url("product_portfolio:product_list")

        response = self.client.get(url)
        self.assertEqual(2, len(response.context_data["object_list"]))
        self.assertIn(self.product1, response.context_data["object_list"])
        self.assertIn(self.product2, response.context_data["object_list"])

        response = self.client.get(url + f"?q={self.product1.name}")
        self.assertContains(response, f'value="{self.product1.name}">')
        self.assertEqual(1, len(response.context_data["object_list"]))
        self.assertIn(self.product1, response.context_data["object_list"])
        self.assertNotIn(self.product2, response.context_data["object_list"])

        response = self.client.get(url + f"?q={self.product2.version}")
        self.assertEqual(1, len(response.context_data["object_list"]))
        self.assertNotIn(self.product1, response.context_data["object_list"])
        self.assertIn(self.product2, response.context_data["object_list"])

        ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )
        response = self.client.get(url + f"?q={self.component1.name}")
        self.assertEqual(1, len(response.context_data["object_list"]))
        self.assertIn(self.product1, response.context_data["object_list"])
        self.assertNotIn(self.product2, response.context_data["object_list"])

        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        response = self.client.get(url + f"?q={self.package1.filename}")
        self.assertEqual(1, len(response.context_data["object_list"]))
        self.assertIn(self.product1, response.context_data["object_list"])
        self.assertNotIn(self.product2, response.context_data["object_list"])

        filename = self.package1.filename[1:-1]
        response = self.client.get(url + f"?q={filename}")
        self.assertEqual(1, len(response.context_data["object_list"]))
        self.assertIn(self.product1, response.context_data["object_list"])

    def test_product_portfolio_list_view_inventory_count(self):
        self.client.login(username="nexb_user", password="secret")
        url = resolve_url("product_portfolio:product_list")

        response = self.client.get(url)
        self.assertContains(response, "<td>0</td>", html=True)
        product1 = response.context_data["object_list"][0]
        self.assertEqual(0, product1.productinventoryitem_count)

        ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )
        response = self.client.get(url)
        expected = f'<a href="{self.product1.get_absolute_url()}#inventory">1</a>'
        self.assertContains(response, expected, html=True)
        product1 = response.context_data["object_list"][0]
        self.assertEqual(1, product1.productinventoryitem_count)

        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        response = self.client.get(url)
        expected = f'<a href="{self.product1.get_absolute_url()}#inventory">2</a>'
        self.assertContains(response, expected, html=True)
        product1 = response.context_data["object_list"][0]
        self.assertEqual(2, product1.productinventoryitem_count)

    def test_product_portfolio_product_tree_comparison_view_proper(self):
        self.client.login(username="nexb_user", password="secret")
        url = resolve_url(
            "product_portfolio:product_tree_comparison",
            left_uuid=self.product1.uuid,
            right_uuid=self.product2.uuid,
        )
        response = self.client.get(url)
        expected = f'{self.product1} <i class="fas fa-exchange-alt mx-2"></i> {self.product2}'
        self.assertContains(response, expected)

        purpose = ProductItemPurpose.objects.create(
            label="Core", text="t", dataspace=self.dataspace
        )
        c1 = Component.objects.create(name="C", version="1.0", dataspace=self.dataspace)
        p1_c1 = ProductComponent.objects.create(
            product=self.product1, component=c1, dataspace=self.dataspace
        )
        p2_c1 = ProductComponent.objects.create(
            product=self.product2, component=c1, dataspace=self.dataspace
        )
        pkg1 = Package.objects.create(filename="pkg1", dataspace=self.dataspace)
        p1_pkg1 = ProductPackage.objects.create(
            product=self.product1, package=pkg1, dataspace=self.dataspace
        )
        p2_pkg1 = ProductPackage.objects.create(
            product=self.product2, package=pkg1, dataspace=self.dataspace
        )

        response = self.client.get(url)
        self.assertContains(response, "<td>Unchanged</td>")
        self.assertContains(response, "Unchanged (2)")

        p2_c1.notes = "New Notes"
        p2_c1.purpose = purpose
        p2_c1.save()
        p2_pkg1.feature = "feature"
        p2_pkg1.save()
        response = self.client.get(url)
        self.assertContains(response, "<td>Changed</td>")
        self.assertContains(response, "Changed (2)")
        left_diff_html = """
        <ul class="list-unstyled left-diff">
          <li>-<strong>Notes</strong></li>
          <li>-<strong>Purpose</strong>None</li>
        </ul>
        """
        self.assertContains(response, left_diff_html, html=True)
        right_diff_html = """
        <ul class="list-unstyled right-diff">
          <li>+<strong>Notes</strong>New Notes</li>
          <li>+<strong>Purpose</strong>Core</li>
        </ul>
        """
        self.assertContains(response, right_diff_html, html=True)

        response = self.client.get(url + "?exclude=purpose")
        left_diff_html = """
        <ul class="list-unstyled left-diff">
            <li>-<strong>Notes</strong></li>
        </ul>
        """
        self.assertContains(response, left_diff_html, html=True)
        right_diff_html = """
        <ul class="list-unstyled right-diff">
            <li>+<strong>Notes</strong>New Notes</li>
        </ul>
        """
        self.assertContains(response, right_diff_html, html=True)

        p2_c1.delete()
        p2_pkg1.delete()
        response = self.client.get(url)
        self.assertContains(response, "<td>Removed</td>")
        self.assertContains(response, "Removed (2)")

        p1_c1.delete()
        p1_pkg1.delete()
        ProductComponent.objects.create(
            product=self.product2, component=c1, dataspace=self.dataspace
        )
        ProductPackage.objects.create(product=self.product2, package=pkg1, dataspace=self.dataspace)
        response = self.client.get(url)
        self.assertContains(response, "<td>Added</td>")
        self.assertContains(response, "Added (2)")

        c2 = Component.objects.create(name=c1.name, version="2.0", dataspace=self.dataspace)
        pkg2 = Package.objects.create(
            filename=pkg1.filename, version="1.1", dataspace=self.dataspace
        )
        ProductComponent.objects.create(
            product=self.product1, component=c2, dataspace=self.dataspace
        )
        ProductPackage.objects.create(product=self.product1, package=pkg2, dataspace=self.dataspace)
        response = self.client.get(url)
        self.assertContains(response, "<td>Updated</td>")
        self.assertContains(response, "Updated (2)")

        c3 = Component.objects.create(name="C", version="3.0", dataspace=self.dataspace)
        p1_c3 = ProductComponent.objects.create(
            product=self.product1, component=c3, dataspace=self.dataspace
        )
        response = self.client.get(url)
        self.assertContains(response, "<td>Added</td>")
        self.assertContains(response, "<td>Removed</td>")
        self.assertContains(response, "Updated (1)")
        self.assertContains(response, "Added (1)")
        self.assertContains(response, "Removed (2)")

        p1_c3.delete()
        ProductComponent.objects.create(
            product=self.product2, component=c3, dataspace=self.dataspace
        )
        response = self.client.get(url)
        self.assertContains(response, "<td>Added</td>")
        self.assertContains(response, "<td>Removed</td>")
        self.assertContains(response, "Updated (1)")
        self.assertContains(response, "Added (2)")
        self.assertContains(response, "Removed (1)")

        response = self.client.get(url, data={"download_xlsx": True})
        expected_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        self.assertEqual(expected_type, response.headers.get("Content-Type"))
        expected_disposition = "attachment; filename=product_comparison.xlsx"
        self.assertEqual(expected_disposition, response.headers.get("Content-Disposition"))

    def test_product_portfolio_product_tree_comparison_view_package_identifier(self):
        self.client.login(username="nexb_user", password="secret")
        url = resolve_url(
            "product_portfolio:product_tree_comparison",
            left_uuid=self.product1.uuid,
            right_uuid=self.product2.uuid,
        )

        p1 = Package(dataspace=self.dataspace)
        p1.set_package_url("pkg:bar/baz/pypdf@4.1.0")
        p1.save()
        pp1 = ProductPackage.objects.create(
            product=self.product1, package=p1, dataspace=self.dataspace
        )

        # Same name different type and namespace
        p2 = Package(dataspace=self.dataspace)
        p2.set_package_url("pkg:github/py-pdf/pypdf@4.2.0")
        p2.save()
        pp2 = ProductPackage.objects.create(
            product=self.product2, package=p2, dataspace=self.dataspace
        )

        response = self.client.get(url)
        expected = [("removed", pp1, None, None), ("added", None, pp2, None)]
        self.assertEqual(expected, response.context["rows"])

        # Same type, namespace, name combo
        p2.set_package_url("pkg:bar/baz/pypdf@4.2.0")
        p2.save()
        response = self.client.get(url)
        expected = [("updated", pp1, pp2, None)]
        self.assertEqual(expected, response.context["rows"])

        # More than 2 packages with same unique identifier
        p3 = Package(dataspace=self.dataspace)
        p3.set_package_url("pkg:bar/baz/pypdf@4.3.0")
        p3.save()
        pp3 = ProductPackage.objects.create(
            product=self.product2, package=p3, dataspace=self.dataspace
        )
        response = self.client.get(url)
        expected = [
            ("removed", pp1, None, None),
            ("added", None, pp2, None),
            ("added", None, pp3, None),
        ]
        self.assertEqual(expected, response.context["rows"])

    def test_product_portfolio_product_tree_comparison_view_secured_access(self):
        self.client.login(username=self.basic_user.username, password="secret")
        url = resolve_url(
            "product_portfolio:product_tree_comparison",
            left_uuid=self.product1.uuid,
            right_uuid=self.product2.uuid,
        )

        self.assertEqual(404, self.client.get(url).status_code)

        assign_perm("view_product", self.basic_user, self.product1)
        self.assertEqual(404, self.client.get(url).status_code)

        assign_perm("view_product", self.basic_user, self.product2)
        self.assertEqual(200, self.client.get(url).status_code)

    def test_authenticated_users_can_see_the_generate_attribution_button(self):
        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(self.product1.get_absolute_url())
        expected = (
            f'<a class="btn btn-outline-dark" href="{self.product1.get_attribution_url()}"'
            f' target="_blank" data-bs-toggle="tooltip" title="Generate Attribution">'
        )
        self.assertContains(response, expected, status_code=200)

    @override_settings(REFERENCE_DATASPACE="nexB")
    def test_product_portfolio_list_view_alternate_user_access(self):
        self.client.login(username=self.alternate_user.username, password="secret")
        response = self.client.get(self.alternate_product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        response = self.client.get(self.product1.get_absolute_url())
        self.assertEqual(response.status_code, 404)

        response = self.client.get(reverse("product_portfolio:product_list"))
        self.assertEqual(response.status_code, 200)

    def test_product_send_about_files_view(self):
        self.assertTrue(" " in self.product1.name)

        about_files_url = self.product1.get_about_files_url()
        self.assertEqual(302, self.client.get(about_files_url).status_code)

        self.client.login(username=self.basic_user.username, password="secret")
        self.assertEqual(404, self.client.get(about_files_url).status_code)

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.product1.get_absolute_url())
        self.assertContains(response, about_files_url)

        response = self.client.get(about_files_url)
        package_qs = Package.objects.filter(component__in=self.product1.components.all())
        self.assertEqual(0, package_qs.count())
        self.assertEqual(404, response.status_code)

        ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=self.package1, dataspace=self.dataspace
        )

        response = self.client.get(about_files_url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("application/zip", response["content-type"])
        self.assertEqual("183", response["content-length"])
        self.assertEqual(
            'attachment; filename="Product1_With_Space_1.0_about.zip"',
            response["content-disposition"],
        )

        # 2 Components assigned to same Package, only Package data is included
        component2 = Component.objects.create(name="Component2", dataspace=self.dataspace)
        ComponentAssignedPackage.objects.create(
            component=component2, package=self.package1, dataspace=self.dataspace
        )
        response = self.client.get(about_files_url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("153", response["content-length"])

        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        response = self.client.get(about_files_url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("153", response["content-length"])

        ComponentAssignedPackage.objects.all().delete()
        self.assertEqual(200, response.status_code)
        self.assertEqual("153", response["content-length"])

    @mock.patch("dje.tasks.scancodeio_submit_scan.delay")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.is_configured")
    def test_product_scan_all_packages_view(self, mock_is_configured, mock_scancodeio_submit_scan):
        mock_is_configured.return_value = True

        scan_all_packages_url = self.product1.get_scan_all_packages_url()
        response = self.client.get(scan_all_packages_url)
        self.assertEqual(302, response.status_code)

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(scan_all_packages_url)
        self.assertEqual(404, response.status_code)

        self.super_user.dataspace.enable_package_scanning = True
        self.super_user.dataspace.save()
        response = self.client.get(scan_all_packages_url)
        self.assertEqual(404, response.status_code)

        self.package1.download_url = "https://proper-url.com"
        self.package1.save()
        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        package2 = Package.objects.create(
            download_url="wrong://url", filename="package2", dataspace=self.dataspace
        )
        ProductPackage.objects.create(
            product=self.product1, package=package2, dataspace=self.dataspace
        )
        self.assertTrue(len(self.product1.all_packages))

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.get(scan_all_packages_url, follow=True)

        self.assertRedirects(response, self.product1.get_absolute_url())
        self.assertContains(response, "Click here to see the Scans list.")
        self.assertContains(response, reverse("component_catalog:scan_list"))

        self.assertEqual(len(callbacks), 1)
        mock_scancodeio_submit_scan.assert_called_once_with(
            uris=[self.package1.download_url],
            user_uuid=self.super_user.uuid,
            dataspace_uuid=self.super_user.dataspace.uuid,
        )

        self.super_user.is_superuser = False
        self.super_user.save()
        response = self.client.get(scan_all_packages_url)
        self.assertEqual(404, response.status_code)

    def test_product_portfolio_product_add_view_permission_access(self):
        add_url = reverse("product_portfolio:product_add")
        response = self.client.get(add_url)
        self.assertEqual(302, response.status_code)
        self.assertRedirects(response, f"/login/?next={add_url}")

        self.super_user.is_superuser = False
        self.super_user.is_staff = False
        self.super_user.save()
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(add_url)
        self.assertEqual(403, response.status_code)

        perms = ["add_product"]
        self.super_user = add_perms(self.super_user, perms)
        response = self.client.get(add_url)
        self.assertEqual(200, response.status_code)

    def test_product_portfolio_product_update_view_permission_access(self):
        change_url = self.product1.get_change_url()
        response = self.client.get(change_url)
        self.assertEqual(302, response.status_code)
        self.assertRedirects(response, f"/login/?next={quote(change_url)}")

        self.super_user.is_superuser = False
        self.super_user.is_staff = False
        self.super_user.save()
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(change_url)
        self.assertEqual(403, response.status_code)

        perms = ["change_product"]
        self.super_user = add_perms(self.super_user, perms)
        response = self.client.get(change_url)
        self.assertEqual(404, response.status_code)

        assign_perm("change_product", self.super_user, self.product1)
        response = self.client.get(change_url)
        self.assertEqual(200, response.status_code)

    def test_product_portfolio_product_add_view_create_proper(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.assertTrue(self.super_user.is_superuser)
        add_url = reverse("product_portfolio:product_add")

        owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        l1 = License.objects.create(
            key="l1", name="L1", short_name="L1", owner=owner1, dataspace=self.dataspace
        )
        configuration_status = ProductStatus.objects.create(
            label="Status1", dataspace=self.dataspace
        )
        keyword = ComponentKeyword.objects.create(label="Keyword1", dataspace=self.dataspace)

        data = {
            "name": "Name",
            "version": "1.0",
            "owner": "Unknown",
            "license_expression": l1.key,
            "copyright": "Copyright",
            "notice_text": "Notice",
            "description": "Description",
            "keywords": keyword.label,
            "primary_language": "Python",
            "homepage_url": "https://nexb.com",
            "contact": "contact@nexb.com",
            "is_active": "on",
            "configuration_status": configuration_status.pk,
            "release_date": "2019-03-01",
            "submit": "Add Product",
        }

        response = self.client.post(add_url, data, follow=True)
        product = Product.objects.get_queryset(self.super_user).get(name="Name", version="1.0")
        self.assertEqual("Unknown", product.owner.name)
        self.assertEqual(configuration_status, product.configuration_status)
        self.assertEqual(l1.key, product.license_expression)
        expected = "Product &quot;Name 1.0&quot; was successfully created."
        self.assertContains(response, expected)

    def test_product_portfolio_product_update_view_proper(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.assertTrue(self.super_user.is_superuser)
        change_url = self.product1.get_change_url()

        owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        l1 = License.objects.create(
            key="l1", name="L1", short_name="L1", owner=owner1, dataspace=self.dataspace
        )
        configuration_status = ProductStatus.objects.create(
            label="Status1", dataspace=self.dataspace
        )
        keyword = ComponentKeyword.objects.create(label="Keyword1", dataspace=self.dataspace)

        data = {
            "name": "Name",
            "version": "1.0",
            "owner": owner1.name,
            "license_expression": l1.key,
            "copyright": "Copyright",
            "notice_text": "Notice",
            "description": "Description",
            "keywords": keyword.label,
            "primary_language": "Python",
            "homepage_url": "https://nexb.com",
            "contact": "contact@nexb.com",
            "is_active": "on",
            "configuration_status": configuration_status.pk,
            "release_date": "2019-03-01",
            "submit": "Update Product",
        }

        response = self.client.post(change_url, data, follow=True)
        product = Product.objects.get_queryset(self.super_user).get(name="Name", version="1.0")
        self.assertEqual(owner1, product.owner)
        self.assertEqual(configuration_status, product.configuration_status)
        self.assertEqual(l1.key, product.license_expression)
        self.assertEqual([keyword.label], product.keywords)
        expected = "Product &quot;Name 1.0&quot; was successfully updated."
        self.assertContains(response, expected)

        keyword2 = ComponentKeyword.objects.create(label="Keyword2", dataspace=self.dataspace)
        data["keywords"] = keyword2.label
        change_url = product.get_change_url()
        response = self.client.post(change_url, data, follow=True)
        self.assertContains(response, expected)
        product = Product.objects.get_queryset(self.super_user).get(name="Name", version="1.0")
        self.assertEqual([keyword2.label], product.keywords)

        data["keywords"] = f"{keyword.label}, {keyword2.label}"
        response = self.client.post(change_url, data, follow=True)
        self.assertContains(response, expected)
        product = Product.objects.get_queryset(self.super_user).get(name="Name", version="1.0")
        self.assertEqual(sorted([keyword.label, keyword2.label]), sorted(product.keywords))

        data["keywords"] = ""
        response = self.client.post(change_url, data, follow=True)
        self.assertContains(response, expected)
        product = Product.objects.get_queryset(self.super_user).get(name="Name", version="1.0")
        self.assertEqual(0, len(product.keywords))

    def test_product_portfolio_product_update_view_no_changes(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.assertTrue(self.super_user.is_superuser)
        change_url = self.product1.get_change_url()

        data = {
            "name": self.product1.name,
            "version": self.product1.version,
            "is_active": "on",
            "submit": "Update Product",
        }

        response = self.client.post(change_url, data, follow=True)
        expected = "No fields changed."
        self.assertContains(response, expected)

    def test_product_portfolio_product_update_view_is_active_false(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.assertTrue(self.super_user.is_superuser)
        change_url = self.product1.get_change_url()

        data = {
            "name": self.product1.name,
            "version": self.product1.version,
            "submit": "Update Product",
        }

        response = self.client.post(change_url, data, follow=True)
        product_list_url = resolve_url("product_portfolio:product_list")
        self.assertRedirects(response, product_list_url)
        expected = f"Product &quot;{self.product1}&quot; was successfully updated."
        self.assertContains(response, expected)

    def test_product_portfolio_product_update_save_as_new(self):
        self.client.login(username=self.super_user.username, password="secret")

        self.assertTrue(self.super_user.is_superuser)
        add_url = reverse("product_portfolio:product_add")
        response = self.client.get(add_url)
        expected = 'value="Save as new"'
        self.assertNotContains(response, expected)

        self.super_user.is_superuser = False
        self.super_user.is_staff = False
        self.super_user.save()
        self.super_user = add_perms(self.super_user, ["change_product"])
        assign_perm("change_product", self.super_user, self.product1)
        change_url = self.product1.get_change_url()
        response = self.client.get(change_url)
        self.assertNotContains(response, expected)

        self.super_user = add_perms(self.super_user, ["add_product"])
        response = self.client.get(change_url)
        self.assertContains(response, expected)

        ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )
        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        CodebaseResource.objects.create(
            path="/path1/", product=self.product1, dataspace=self.dataspace
        )
        initial_product_count = Product.objects.get_queryset(self.super_user).count()

        data = {
            "name": self.product1.name,
            "version": "new version",
            "is_active": "on",
            "save_as_new": "Save as new",
        }

        response = self.client.post(change_url, data, follow=True)

        new_count = Product.objects.get_queryset(self.super_user).count()
        self.assertEqual(new_count, initial_product_count + 1)
        cloned_product = Product.objects.get_queryset(self.super_user).latest("id")
        self.assertRedirects(response, cloned_product.get_absolute_url())
        self.assertContains(response, "was successfully cloned.")

        self.assertNotEqual(self.product1.id, cloned_product.id)
        self.assertEqual(1, cloned_product.productcomponents.count())
        self.assertEqual(1, cloned_product.productpackages.count())
        self.assertEqual(1, cloned_product.codebaseresources.count())

    def test_product_portfolio_product_delete_view(self):
        delete_url = self.product1.get_delete_url()
        details_url = self.product1.get_absolute_url()
        self.client.login(username=self.basic_user.username, password="secret")

        assign_perm("view_product", self.basic_user, self.product1)
        response = self.client.get(details_url)
        self.assertEqual(200, response.status_code)
        self.assertNotContains(response, delete_url)

        response = self.client.get(delete_url)
        self.assertEqual(403, response.status_code)

        self.basic_user = add_perms(self.basic_user, ["delete_product"])
        assign_perm("delete_product", self.basic_user, self.product1)
        response = self.client.get(details_url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, delete_url)

        ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )
        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        self.assertTrue(Product.objects.get_queryset(self.basic_user).exists())
        self.assertTrue(self.product1.components.exists())
        self.assertTrue(self.product1.packages.exists())

        response = self.client.get(delete_url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, f"Delete {self.product1}")
        expected = f'Are you sure you want to delete "{self.product1}"?'
        self.assertContains(response, expected, html=True)
        expected = '<input type="submit" class="btn btn-danger" value="Confirm deletion">'
        self.assertContains(response, expected, html=True)
        response = self.client.post(delete_url, follow=True)
        self.assertRedirects(response, reverse("product_portfolio:product_list"))
        self.assertContains(response, "was successfully deleted.")
        self.assertFalse(Product.objects.get_queryset(self.basic_user).exists())
        self.assertFalse(ProductComponent.objects.exists())
        self.assertFalse(ProductPackage.objects.exists())

    def test_product_portfolio_product_form_add(self):
        self.super_user.is_superuser = False
        self.super_user.is_staff = False
        self.super_user.save()
        perms = ["add_product"]
        self.super_user = add_perms(self.super_user, perms)

        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        status = ProductStatus.objects.create(label="Status1", dataspace=self.dataspace)
        keyword = ComponentKeyword.objects.create(label="Keyword1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="l1",
            name="L1",
            short_name="L1",
            owner=owner,
            is_active=False,
            dataspace=self.dataspace,
        )

        alternate_owner = Owner.objects.create(name="Owner1", dataspace=self.alternate_dataspace)
        alternate_status = ProductStatus.objects.create(
            label="Status1", dataspace=self.alternate_dataspace
        )
        ComponentKeyword.objects.create(label="Alternate", dataspace=self.alternate_dataspace)

        form = ProductForm(user=self.super_user)

        # Dataspace scoping
        self.assertEqual(1, len(form.fields["owner"].queryset))
        self.assertIn(owner, form.fields["owner"].queryset)
        self.assertNotIn(alternate_owner, form.fields["owner"].queryset)

        self.assertEqual(1, len(form.fields["configuration_status"].queryset))
        self.assertIn(status, form.fields["configuration_status"].queryset)
        self.assertNotIn(alternate_status, form.fields["configuration_status"].queryset)

        # NameVersionValidationFormMixin
        data = {
            "name": self.product1.name,
            "version": self.product1.version,
        }
        form = ProductForm(user=self.super_user, data=data)
        self.assertFalse(form.is_valid())
        errors = {"__all__": ["Product with this Name and Version already exists."]}
        self.assertEqual(errors, form.errors)

        # Save
        data = {
            "name": "Name",
            "version": "1.0",
            "owner": owner.name,
            "license_expression": license1.key,
            "copyright": "Copyright",
            "notice_text": "Notice",
            "description": "Description",
            "keywords": keyword.label,
            "primary_language": "Python",
            "homepage_url": "https://nexb.com",
            "contact": "contact@nexb.com",
            "is_active": "on",
            "configuration_status": status.pk,
            "release_date": "2019-03-01",
            "submit": "Add Product",
        }
        form = ProductForm(user=self.super_user, data=data)
        self.assertTrue(form.is_valid())
        product = form.save()
        self.assertEqual(owner, product.owner)
        self.assertEqual(status, product.configuration_status)
        self.assertEqual(license1.key, product.license_expression)

        expected = ["view_product"]
        self.assertEqual(expected, list(get_user_perms(self.super_user, product)))

        perms = ["change_product", "delete_product"]
        self.super_user = add_perms(self.super_user, perms)
        form = ProductForm(user=self.super_user, data={"name": "p1"})
        p1 = form.save()
        expected = ["change_product", "delete_product", "view_product"]
        self.assertEqual(expected, list(get_user_perms(self.super_user, p1)))

    def test_product_portfolio_productpackage_form(self):
        productpackage = ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )

        purpose = ProductItemPurpose.objects.create(
            label="Core", text="t", dataspace=self.dataspace
        )
        alternate_purpose = ProductItemPurpose.objects.create(
            label="Core", text="t", dataspace=self.alternate_dataspace
        )
        status = ProductRelationStatus.objects.create(label="Status1", dataspace=self.dataspace)
        alternate_status = ProductRelationStatus.objects.create(
            label="Status1", dataspace=self.alternate_dataspace
        )

        # Dataspace scoping
        form = ProductPackageForm(self.super_user, instance=productpackage)
        self.assertEqual(1, len(form.fields["review_status"].queryset))
        self.assertIn(status, form.fields["review_status"].queryset)
        self.assertNotIn(alternate_status, form.fields["review_status"].queryset)

        self.assertEqual(1, len(form.fields["purpose"].queryset))
        self.assertIn(purpose, form.fields["purpose"].queryset)
        self.assertNotIn(alternate_purpose, form.fields["purpose"].queryset)

        # Change status permission
        form = ProductPackageForm(self.basic_user, instance=productpackage)
        self.assertIn('<select name="review_status" disabled', str(form))

        self.basic_user = add_perms(self.basic_user, ["change_review_status_on_productpackage"])
        form = ProductPackageForm(self.basic_user, instance=productpackage)
        expected = (
            '<select name="review_status" aria-describedby="id_review_status_helptext" '
            'id="id_review_status">'
        )
        self.assertIn(expected, str(form))

        data = {
            "product": productpackage.product.pk,
            "package": productpackage.package.pk,
            "purpose": purpose.pk,
        }
        form = ProductPackageForm(self.super_user, instance=productpackage, data=data)
        self.assertTrue(form.is_valid())
        productpackage = form.save()
        self.assertEqual(purpose, productpackage.purpose)

    def test_product_portfolio_edit_productrelation_ajax_view_package(self):
        purpose = ProductItemPurpose.objects.create(
            label="Core", text="t", dataspace=self.dataspace
        )
        productpackage = ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        edit_url = reverse(
            "product_portfolio:edit_productrelation_ajax", args=["package", productpackage.uuid]
        )
        product_url = self.product1.get_absolute_url()

        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(edit_url)
        self.assertEqual(403, response.status_code)
        self.assertEqual("application/json", response["content-type"])

        assign_perm("view_product", self.basic_user, self.product1)
        assign_perm("change_product", self.basic_user, self.product1)
        add_perms(self.basic_user, ["change_product", "change_productpackage"])
        response = self.client.get(edit_url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/html; charset=utf-8", response["content-type"])
        self.assertContains(response, 'id="update-productrelation-form"')

        data = {
            "product": productpackage.product.pk,
            "package": productpackage.package.pk,
            "purpose": purpose.pk,
        }
        response = self.client.post(edit_url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertEqual("application/json", response["content-type"])
        self.assertEqual(b'{"success": "updated"}', response.content)

        productpackage.refresh_from_db()
        self.assertEqual(purpose, productpackage.purpose)

        history_entries = History.objects.get_for_object(productpackage.product)
        expected_messages = ['Changed package "package1" purpose, is_deployed']
        self.assertEqual(expected_messages, [entry.change_message for entry in history_entries])
        self.assertEqual(self.basic_user, productpackage.product.last_modified_by)

        response = self.client.get(f"{edit_url}?delete=1")
        self.assertRedirects(response, product_url + "#inventory")

        add_perms(self.basic_user, ["delete_productpackage"])
        response = self.client.get(f"{edit_url}?delete=1", follow=True)
        self.assertRedirects(response, product_url + "#inventory")
        msg = f"Package relationship {productpackage} successfully deleted."
        self.assertContains(response, msg)
        self.assertFalse(ProductPackage.objects.filter(pk=productpackage.pk).exists())
        history_entries = History.objects.get_for_object(productpackage.product)
        expected_messages = 'Deleted package "package1"'
        self.assertEqual(expected_messages, history_entries.latest("id").change_message)

        wrong_url = reverse(
            "product_portfolio:edit_productrelation_ajax", args=["wrong_url", productpackage.uuid]
        )
        response = self.client.get(wrong_url)
        self.assertEqual(403, response.status_code)
        self.assertEqual("application/json", response["content-type"])

    def test_product_portfolio_edit_productrelation_ajax_view_component(self):
        purpose = ProductItemPurpose.objects.create(
            label="Core", text="t", dataspace=self.dataspace
        )
        productcomponent = ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )
        edit_url = reverse(
            "product_portfolio:edit_productrelation_ajax", args=["component", productcomponent.uuid]
        )
        product_url = self.product1.get_absolute_url()

        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(edit_url)
        self.assertEqual(403, response.status_code)
        self.assertEqual("application/json", response["content-type"])

        assign_perm("view_product", self.basic_user, self.product1)
        assign_perm("change_product", self.basic_user, self.product1)
        add_perms(self.basic_user, ["change_product", "change_productcomponent"])
        response = self.client.get(edit_url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/html; charset=utf-8", response["content-type"])
        self.assertContains(response, 'id="update-productrelation-form"')

        data = {
            "product": productcomponent.product.pk,
            "component": productcomponent.component.pk,
            "purpose": purpose.pk,
        }
        response = self.client.post(edit_url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertEqual("application/json", response["content-type"])
        self.assertEqual(b'{"success": "updated"}', response.content)

        productcomponent.refresh_from_db()
        self.assertEqual(purpose, productcomponent.purpose)

        history_entries = History.objects.get_for_object(productcomponent.product)
        expected_messages = ['Changed component "Component1 1.0" purpose, is_deployed']
        self.assertEqual(expected_messages, [entry.change_message for entry in history_entries])
        self.assertEqual(self.basic_user, productcomponent.product.last_modified_by)

        response = self.client.get(f"{edit_url}?delete=1")
        self.assertRedirects(response, product_url + "#inventory")

        add_perms(self.basic_user, ["delete_productcomponent"])
        response = self.client.get(f"{edit_url}?delete=1", follow=True)
        self.assertRedirects(response, product_url + "#inventory")
        msg = f"Component relationship {productcomponent} successfully deleted."
        self.assertContains(response, msg)
        self.assertFalse(ProductComponent.objects.filter(pk=productcomponent.pk).exists())
        history_entries = History.objects.get_for_object(productcomponent.product)
        expected_messages = 'Deleted component "Component1 1.0"'
        self.assertEqual(expected_messages, history_entries.latest("id").change_message)

    def test_product_portfolio_edit_productrelation_ajax_view_custom_component(self):
        purpose = ProductItemPurpose.objects.create(
            label="Core", text="t", dataspace=self.dataspace
        )
        productcomponent = ProductComponent.objects.create(
            product=self.product1, name="Custom", version="1.2", dataspace=self.dataspace
        )
        edit_url = reverse(
            "product_portfolio:edit_productrelation_ajax",
            args=["custom-component", productcomponent.uuid],
        )
        product_url = self.product1.get_absolute_url()

        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(edit_url)
        self.assertEqual(403, response.status_code)
        self.assertEqual("application/json", response["content-type"])

        assign_perm("view_product", self.basic_user, self.product1)
        assign_perm("change_product", self.basic_user, self.product1)
        add_perms(self.basic_user, ["change_product", "change_productcomponent"])
        response = self.client.get(edit_url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/html; charset=utf-8", response["content-type"])
        self.assertContains(response, 'id="update-productrelation-form"')

        data = {
            "product": productcomponent.product.pk,
            "purpose": purpose.pk,
            "owner": "owner",
            "copyright": "copyright",
        }
        response = self.client.post(edit_url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertEqual("application/json", response["content-type"])
        self.assertEqual(b'{"success": "updated"}', response.content)

        productcomponent.refresh_from_db()
        self.assertEqual(purpose, productcomponent.purpose)
        self.assertEqual(data["copyright"], productcomponent.copyright)
        self.assertEqual(data["owner"], productcomponent.owner)

        history_entries = History.objects.get_for_object(productcomponent.product)
        expected_messages = [
            'Changed custom component "(Component data missing)" name, version, owner,'
            " copyright, purpose, is_deployed"
        ]
        self.assertEqual(expected_messages, [entry.change_message for entry in history_entries])
        self.assertEqual(self.basic_user, productcomponent.product.last_modified_by)

        response = self.client.get(f"{edit_url}?delete=1")
        self.assertRedirects(response, product_url + "#inventory")

        add_perms(self.basic_user, ["delete_productcomponent"])
        response = self.client.get(f"{edit_url}?delete=1", follow=True)
        self.assertRedirects(response, product_url + "#inventory")
        msg = f"Component relationship {productcomponent} successfully deleted."
        self.assertContains(response, msg)
        self.assertFalse(ProductComponent.objects.filter(pk=productcomponent.pk).exists())

        history_entries = History.objects.get_for_object(productcomponent.product)
        expected_messages = 'Deleted custom component "(Component data missing)"'
        self.assertEqual(expected_messages, history_entries.latest("id").change_message)

    def test_product_portfolio_add_customcomponent_ajax_view(self):
        add_customcomponent_url = self.product1.get_add_customcomponent_ajax_url()
        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(add_customcomponent_url)
        self.assertEqual(404, response.status_code)

        purpose = ProductItemPurpose.objects.create(
            label="Core", text="t", dataspace=self.dataspace
        )
        assign_perm("view_product", self.basic_user, self.product1)
        assign_perm("change_product", self.basic_user, self.product1)
        add_perms(self.basic_user, ["change_product", "add_productcomponent"])
        response = self.client.get(add_customcomponent_url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/html; charset=utf-8", response["content-type"])
        self.assertContains(response, 'id="update-productrelation-form"')

        data = {
            "product": self.product1.pk,
            "name": "custom1",
            "purpose": purpose.pk,
            "owner": "owner",
            "copyright": "copyright",
        }
        response = self.client.post(add_customcomponent_url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertEqual("application/json", response["content-type"])
        self.assertEqual(b'{"success": "added"}', response.content)

        productcomponent = ProductComponent.objects.latest("id")
        self.assertEqual(data["product"], productcomponent.product.id)
        self.assertEqual(data["name"], productcomponent.name)
        self.assertEqual(purpose, productcomponent.purpose)
        self.assertEqual(data["copyright"], productcomponent.copyright)
        self.assertEqual(data["owner"], productcomponent.owner)

        history_entries = History.objects.get_for_object(productcomponent.product)
        expected_messages = ['Added custom component "custom1 "']
        self.assertEqual(expected_messages, [entry.change_message for entry in history_entries])
        self.assertEqual(self.basic_user, productcomponent.product.last_modified_by)

    def test_product_portfolio_product_manage_grid_configuration(self):
        self.client.login(username=self.super_user.username, password="secret")
        manage_url = self.product1.get_manage_components_url()
        session_key = ManageComponentGridView.configuration_session_key

        default_fields = [
            "license_expression",
            "review_status",
            "purpose",
            "notes",
            "is_deployed",
            "is_modified",
            "extra_attribution_text",
            "feature",
            "issue_ref",
        ]

        response = self.client.get(manage_url)
        configuration_form = response.context["grid_configuration_form"]
        self.assertEqual(default_fields, configuration_form.initial["displayed_fields"])
        self.assertEqual(default_fields, ProductGridConfigurationForm.get_fields_name())
        self.assertNotIn(session_key, self.client.session)

        displayed_fields = [
            "license_expression",
            "review_status",
        ]
        data = {
            "update-grid-configuration": True,
            "displayed_fields": displayed_fields,
        }
        response = self.client.post(manage_url, data, follow=True)
        self.assertRedirects(response, manage_url)
        self.assertContains(response, "Grid configuration updated.")
        self.assertEqual(displayed_fields, self.client.session[session_key])

        data["displayed_fields"] = ["not_existing"]
        response = self.client.post(manage_url, data, follow=True)
        self.assertNotContains(response, "Grid configuration updated.")
        self.assertEqual(default_fields, configuration_form.initial["displayed_fields"])

        # To modify the session and then save it, it must be stored in a variable first
        # (because a new SessionStore is created every time this property is accessed)
        # https://docs.djangoproject.com/en/dev/topics/testing/tools/#django.test.Client.session
        session = self.client.session
        session[session_key] = ["not_existing", "notes"]
        session.save()
        response = self.client.get(manage_url)
        configuration_form = response.context["grid_configuration_form"]
        self.assertEqual(["notes"], configuration_form.initial["displayed_fields"])

    def test_product_portfolio_product_details_view_manage_components_permissions(self):
        product_url = self.product1.get_absolute_url()
        manage_components_url = self.product1.get_manage_components_url()
        self.client.login(username=self.basic_user.username, password="secret")

        assign_perm("view_product", self.basic_user, self.product1)
        response = self.client.get(product_url)
        self.assertNotContains(response, manage_components_url)

        assign_perm("change_product", self.basic_user, self.product1)
        response = self.client.get(product_url)
        self.assertNotContains(response, manage_components_url)

        add_perms(self.basic_user, ["change_productcomponent"])
        response = self.client.get(product_url)
        self.assertContains(response, manage_components_url)

    def test_product_portfolio_product_manage_components_grid_view_permissions(self):
        manage_url = self.product1.get_manage_components_url()

        response = self.client.get(manage_url)
        self.assertRedirects(response, f"/login/?next={quote(manage_url)}")

        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(manage_url)
        self.assertEqual(403, response.status_code)

        assign_perm("view_product", self.basic_user, self.product1)
        response = self.client.get(manage_url)
        self.assertEqual(403, response.status_code)

        add_perms(self.basic_user, ["change_productcomponent"])
        response = self.client.get(manage_url)
        self.assertEqual(404, response.status_code)

        assign_perm("change_product", self.basic_user, self.product1)
        response = self.client.get(manage_url)
        self.assertEqual(200, response.status_code)

    def test_product_portfolio_product_manage_components_grid_view_delete(self):
        self.client.login(username=self.basic_user.username, password="secret")

        manage_url = self.product1.get_manage_components_url()
        assign_perm("change_product", self.basic_user, self.product1)
        add_perms(self.basic_user, ["change_productcomponent"])

        pc1 = ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )

        expected = "id_form-0-DELETE"
        response = self.client.get(manage_url)
        self.assertNotContains(response, expected)

        add_perms(self.basic_user, ["delete_productcomponent"])
        response = self.client.get(manage_url)
        self.assertContains(response, expected)

        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-MIN_NUM_FORMS": 0,
            "form-MAX_NUM_FORMS": 1000,
            "form-0-id": pc1.id,
            "form-0-DELETE": "on",
        }
        response = self.client.post(manage_url, data, follow=True)
        self.assertContains(response, "Product changes saved.")
        self.assertEqual(0, ProductComponent.objects.count())

    def test_product_portfolio_product_manage_components_grid_view_get(self):
        self.client.login(username=self.super_user.username, password="secret")
        manage_url = self.product1.get_manage_components_url()
        ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )

        response = self.client.get(manage_url)
        self.assertEqual(self.product1, response.context["product"])

        forms = response.context["formset"].forms
        self.assertEqual(1, len(forms))
        self.assertEqual(self.component1.pk, forms[0].initial["component"])

    def test_product_portfolio_product_manage_components_grid_view_component_add_form(self):
        self.client.login(username=self.basic_user.username, password="secret")
        manage_url = self.product1.get_manage_components_url()
        assign_perm("change_product", self.basic_user, self.product1)
        add_perms(self.basic_user, ["change_productcomponent"])

        modal_id = 'id="create-component-modal"'
        modal_open_link = 'data-bs-target="#create-component-modal"'

        response = self.client.get(manage_url)
        self.assertNotIn("component_add_form", response.context)
        self.assertNotContains(response, modal_id)
        self.assertNotContains(response, modal_open_link)

        add_perms(self.basic_user, ["add_component"])
        response = self.client.get(manage_url)
        component_add_form = response.context["component_add_form"]
        self.assertEqual("ComponentAjaxForm", type(component_add_form).__name__)
        self.assertContains(response, modal_id)
        self.assertContains(response, modal_open_link)

    def test_product_portfolio_product_manage_components_grid_view_post(self):
        self.client.login(username=self.super_user.username, password="secret")
        manage_url = self.product1.get_manage_components_url()

        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-MIN_NUM_FORMS": 0,
            "form-MAX_NUM_FORMS": 1000,
            "form-0-product": self.product1.pk,
            "form-0-component": self.component1.pk,
            "form-0-object_display": str(self.component1),
            "form-0-license_expression": "",
            "form-0-review_status": "",
            "form-0-purpose": "",
            "form-0-notes": "Some notes",
        }
        response = self.client.post(manage_url, data, follow=True)
        self.assertContains(response, "Product changes saved.")
        self.assertRedirects(response, manage_url)

        pc1 = ProductComponent.objects.get(product=self.product1, component=self.component1)
        self.assertEqual(data["form-0-notes"], pc1.notes)

        history_entry = History.objects.get_for_object(self.product1).get()
        expected_messages = 'Added component "Component1 1.0"'
        self.assertEqual(expected_messages, history_entry.change_message)
        self.product1.refresh_from_db()
        self.assertEqual(self.super_user, self.product1.last_modified_by)

        data["form-0-id"] = pc1.pk
        data["form-INITIAL_FORMS"] = 1
        data["save"] = True
        response = self.client.post(manage_url, data, follow=True)
        self.assertContains(response, "No changes to save.")
        self.assertRedirects(response, self.product1.get_absolute_url())

    def test_product_portfolio_product_manage_components_grid_filterset(self):
        self.client.login(username=self.super_user.username, password="secret")
        manage_url = self.product1.get_manage_components_url()

        component2 = Component.objects.create(name="component2", dataspace=self.dataspace)
        pc1 = ProductComponent.objects.create(
            product=self.product1,
            component=self.component1,
            dataspace=self.dataspace,
            is_deployed=False,
            is_modified=True,
        )
        pc2 = ProductComponent.objects.create(
            product=self.product1,
            component=component2,
            dataspace=self.dataspace,
            is_deployed=True,
            is_modified=False,
        )

        response = self.client.get(manage_url)
        self.assertEqual(2, len(response.context["formset"].forms))
        filterset_qs = response.context["filterset"].qs
        self.assertEqual(2, len(filterset_qs))
        self.assertIn(pc1, filterset_qs)
        self.assertIn(pc2, filterset_qs)

        response = self.client.get(manage_url + "?is_deployed=yes")
        self.assertEqual(1, len(response.context["formset"].forms))
        filterset_qs = response.context["filterset"].qs
        self.assertEqual(1, len(filterset_qs))
        self.assertNotIn(pc1, filterset_qs)
        self.assertIn(pc2, filterset_qs)

        response = self.client.get(manage_url + "?is_modified=yes")
        self.assertEqual(1, len(response.context["formset"].forms))
        filterset_qs = response.context["filterset"].qs
        self.assertEqual(1, len(filterset_qs))
        self.assertIn(pc1, filterset_qs)
        self.assertNotIn(pc2, filterset_qs)

        response = self.client.get(manage_url + f"?q={self.component1.name}")
        self.assertEqual(1, len(response.context["formset"].forms))
        filterset_qs = response.context["filterset"].qs
        self.assertEqual(1, len(filterset_qs))
        self.assertIn(pc1, filterset_qs)
        self.assertNotIn(pc2, filterset_qs)

        response = self.client.get(manage_url + "?q=NORESULTS")
        self.assertEqual(0, len(response.context["formset"].forms))
        filterset_qs = response.context["filterset"].qs
        self.assertEqual(0, len(filterset_qs))

    def test_product_portfolio_product_details_view_manage_packages_permissions(self):
        product_url = self.product1.get_absolute_url()
        manage_packages_url = self.product1.get_manage_packages_url()
        self.client.login(username=self.basic_user.username, password="secret")

        assign_perm("view_product", self.basic_user, self.product1)
        response = self.client.get(product_url)
        self.assertNotContains(response, manage_packages_url)

        assign_perm("change_product", self.basic_user, self.product1)
        response = self.client.get(product_url)
        self.assertNotContains(response, manage_packages_url)

        add_perms(self.basic_user, ["change_productpackage"])
        response = self.client.get(product_url)
        self.assertContains(response, manage_packages_url)

    def test_product_portfolio_product_manage_packages_grid_view_permissions(self):
        manage_url = self.product1.get_manage_packages_url()

        response = self.client.get(manage_url)
        self.assertRedirects(response, f"/login/?next={quote(manage_url)}")

        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(manage_url)
        self.assertEqual(403, response.status_code)

        assign_perm("view_product", self.basic_user, self.product1)
        response = self.client.get(manage_url)
        self.assertEqual(403, response.status_code)

        add_perms(self.basic_user, ["change_productpackage"])
        response = self.client.get(manage_url)
        self.assertEqual(404, response.status_code)

        assign_perm("change_product", self.basic_user, self.product1)
        response = self.client.get(manage_url)
        self.assertEqual(200, response.status_code)

    def test_product_portfolio_product_manage_packages_grid_view_delete(self):
        self.client.login(username=self.basic_user.username, password="secret")

        manage_url = self.product1.get_manage_packages_url()
        assign_perm("change_product", self.basic_user, self.product1)
        add_perms(self.basic_user, ["change_productpackage"])

        pp1 = ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )

        expected = "id_form-0-DELETE"
        response = self.client.get(manage_url)
        self.assertNotContains(response, expected)

        add_perms(self.basic_user, ["delete_productpackage"])
        response = self.client.get(manage_url)
        self.assertContains(response, expected)

        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-MIN_NUM_FORMS": 0,
            "form-MAX_NUM_FORMS": 1000,
            "form-0-id": pp1.id,
            "form-0-DELETE": "on",
        }
        response = self.client.post(manage_url, data, follow=True)
        self.assertContains(response, "Product changes saved.")
        self.assertEqual(0, ProductPackage.objects.count())

    def test_product_portfolio_product_manage_packages_grid_view_get(self):
        self.client.login(username=self.super_user.username, password="secret")
        manage_url = self.product1.get_manage_packages_url()
        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )

        response = self.client.get(manage_url)
        self.assertEqual(self.product1, response.context["product"])

        forms = response.context["formset"].forms
        self.assertEqual(1, len(forms))
        self.assertEqual(self.package1.pk, forms[0].initial["package"])

    def test_product_portfolio_product_package_components_grid_view_post(self):
        self.client.login(username=self.super_user.username, password="secret")
        manage_url = self.product1.get_manage_packages_url()

        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-MIN_NUM_FORMS": 0,
            "form-MAX_NUM_FORMS": 1000,
            "form-0-product": self.product1.pk,
            "form-0-package": self.package1.pk,
            "form-0-object_display": str(self.package1),
            "form-0-license_expression": "",
            "form-0-review_status": "",
            "form-0-purpose": "",
            "form-0-notes": "Some notes",
        }
        response = self.client.post(manage_url, data, follow=True)
        self.assertContains(response, "Product changes saved.")
        self.assertRedirects(response, manage_url)

        pp1 = ProductPackage.objects.get(product=self.product1, package=self.package1)
        self.assertEqual(data["form-0-notes"], pp1.notes)

        history_entry = History.objects.get_for_object(self.product1).get()
        expected_messages = 'Added package "package1"'
        self.assertEqual(expected_messages, history_entry.change_message)
        self.product1.refresh_from_db()
        self.assertEqual(self.super_user, self.product1.last_modified_by)

        data["form-0-id"] = pp1.pk
        data["form-INITIAL_FORMS"] = 1
        data["save"] = True
        response = self.client.post(manage_url, data, follow=True)
        self.assertContains(response, "No changes to save.")
        self.assertRedirects(response, self.product1.get_absolute_url())

    def test_product_portfolio_product_manage_packages_grid_filterset(self):
        self.client.login(username=self.super_user.username, password="secret")
        manage_url = self.product1.get_manage_packages_url()

        package2 = Package.objects.create(filename="package2", dataspace=self.dataspace)
        pp1 = ProductPackage.objects.create(
            product=self.product1,
            package=self.package1,
            dataspace=self.dataspace,
            is_deployed=False,
            is_modified=True,
        )
        pp2 = ProductPackage.objects.create(
            product=self.product1,
            package=package2,
            dataspace=self.dataspace,
            is_deployed=True,
            is_modified=False,
        )

        response = self.client.get(manage_url)
        self.assertEqual(2, len(response.context["formset"].forms))
        filterset_qs = response.context["filterset"].qs
        self.assertEqual(2, len(filterset_qs))
        self.assertIn(pp1, filterset_qs)
        self.assertIn(pp2, filterset_qs)

        response = self.client.get(manage_url + "?is_deployed=yes")
        self.assertEqual(1, len(response.context["formset"].forms))
        filterset_qs = response.context["filterset"].qs
        self.assertEqual(1, len(filterset_qs))
        self.assertNotIn(pp1, filterset_qs)
        self.assertIn(pp2, filterset_qs)

        response = self.client.get(manage_url + "?is_modified=yes")
        self.assertEqual(1, len(response.context["formset"].forms))
        filterset_qs = response.context["filterset"].qs
        self.assertEqual(1, len(filterset_qs))
        self.assertIn(pp1, filterset_qs)
        self.assertNotIn(pp2, filterset_qs)

        response = self.client.get(manage_url + f"?q={self.package1.filename}")
        self.assertEqual(1, len(response.context["formset"].forms))
        filterset_qs = response.context["filterset"].qs
        self.assertEqual(1, len(filterset_qs))
        self.assertIn(pp1, filterset_qs)
        self.assertNotIn(pp2, filterset_qs)

        response = self.client.get(manage_url + "?q=NORESULTS")
        self.assertEqual(0, len(response.context["formset"].forms))
        filterset_qs = response.context["filterset"].qs
        self.assertEqual(0, len(filterset_qs))

    def test_product_portfolio_product_license_summary_view(self):
        owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="l1", name="L1", short_name="L1", owner=owner1, dataspace=self.dataspace
        )

        self.package1.license_expression = license1.key
        self.package1.save()
        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )

        self.component1.license_expression = license1.key
        self.component1.save()
        ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )

        self.client.login(username=self.super_user.username, password="secret")
        license_summary_url = self.product1.get_license_summary_url()
        response = self.client.get(license_summary_url)

        expected = {license1: [self.component1, self.package1]}
        self.assertEqual(expected, response.context["license_index"])

        self.assertContains(response, str(license1.key))
        self.assertContains(response, str(self.package1))
        self.assertContains(response, str(self.component1))

        response = self.client.get(license_summary_url + "?export=csv")
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/csv", response["Content-Type"])
        self.assertEqual("89", response["Content-Length"])
        expected = 'attachment; filename="Product1_With_Space_1.0_license_summary.csv"'
        self.assertEqual(expected, response["Content-Disposition"])

    def test_product_portfolio_product_export_spdx_view(self):
        self.client.login(username=self.super_user.username, password="secret")
        export_spdx_url = self.product1.get_export_spdx_url()
        response = self.client.get(export_spdx_url)
        self.assertEqual(
            "dejacode_nexb_product_product1_with_space_1.0.spdx.json", response.filename
        )
        self.assertEqual("application/json", response.headers["Content-Type"])

    def test_product_portfolio_product_export_spdx_get_spdx_extracted_licenses(self):
        owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="l1",
            name="L1",
            short_name="L1",
            owner=owner1,
            full_text="A",
            dataspace=self.dataspace,
        )
        license2 = License.objects.create(
            key="l2",
            name="L2",
            short_name="L2",
            owner=owner1,
            full_text="B",
            dataspace=self.dataspace,
        )

        self.component1.license_expression = f"{license1.key} OR {license2.key}"
        self.component1.save()
        ProductComponent.objects.create(
            product=self.product1,
            component=self.component1,
            license_expression=license1.key,
            dataspace=self.dataspace,
        )

        spdx_packages = self.product1.get_spdx_packages()
        extracted_licenses = get_spdx_extracted_licenses(spdx_packages)
        extracted_licenses_as_dict = [
            licensing_info.as_dict() for licensing_info in extracted_licenses
        ]
        expected = [
            {
                "licenseId": "LicenseRef-dejacode-l1",
                "extractedText": "A",
                "name": "L1",
                "seeAlsos": [
                    "https://github.com/nexB/scancode-toolkit/tree/develop/src/"
                    "licensedcode/data/licenses/l1.LICENSE",
                    "https://scancode-licensedb.aboutcode.org/l1",
                ],
            },
            {
                "licenseId": "LicenseRef-dejacode-l2",
                "extractedText": "B",
                "name": "L2",
                "seeAlsos": [
                    "https://github.com/nexB/scancode-toolkit/tree/develop/src/"
                    "licensedcode/data/licenses/l2.LICENSE",
                    "https://scancode-licensedb.aboutcode.org/l2",
                ],
            },
        ]

        self.assertEqual(
            sorted(expected, key=lambda x: x["licenseId"]),
            sorted(extracted_licenses_as_dict, key=lambda x: x["licenseId"]),
        )

        self.package1.license_expression = license2.key
        self.package1.save()
        spdx_packages = self.package1.get_spdx_packages()
        extracted_licenses = get_spdx_extracted_licenses(spdx_packages)
        extracted_licenses_as_dict = [
            licensing_info.as_dict() for licensing_info in extracted_licenses
        ]
        expected = [
            {
                "extractedText": "B",
                "licenseId": "LicenseRef-dejacode-l2",
                "name": "L2",
                "seeAlsos": [
                    "https://github.com/nexB/scancode-toolkit/tree/develop/src/"
                    "licensedcode/data/licenses/l2.LICENSE",
                    "https://scancode-licensedb.aboutcode.org/l2",
                ],
            }
        ]
        self.assertEqual(expected, extracted_licenses_as_dict)

    def test_product_portfolio_product_details_view_cyclonedx_links(self):
        self.client.login(username=self.super_user.username, password="secret")
        url = self.product1.get_absolute_url()

        export_cyclonedx_url = self.product1.get_export_cyclonedx_url()
        sbom_link = f"{export_cyclonedx_url}?spec_version=1.6"
        vex_link = f"{export_cyclonedx_url}?spec_version=1.6&content=vex"
        combined_link = f"{export_cyclonedx_url}?spec_version=1.6&content=combined"

        response = self.client.get(url)
        self.assertContains(response, "SBOM")
        self.assertContains(response, sbom_link)
        self.assertNotContains(response, "VEX (only)")
        self.assertNotContains(response, vex_link)
        self.assertNotContains(response, "SBOM+VEX (combined)")
        self.assertNotContains(response, combined_link)

        self.dataspace.enable_vulnerablecodedb_access = True
        self.dataspace.save()
        response = self.client.get(url)
        self.assertContains(response, "SBOM")
        self.assertContains(response, sbom_link)
        self.assertContains(response, "VEX (only)")
        self.assertContains(response, vex_link)
        self.assertContains(response, "SBOM+VEX (combined)")
        self.assertContains(response, combined_link)

    def test_product_portfolio_product_export_cyclonedx_view(self):
        owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="l1",
            name="L1",
            short_name="L1",
            owner=owner1,
            full_text="A",
            dataspace=self.dataspace,
        )
        license2 = License.objects.create(
            key="l2",
            name="L2",
            short_name="L2",
            owner=owner1,
            full_text="B",
            dataspace=self.dataspace,
        )

        self.component1.license_expression = f"{license1.key} OR {license2.key}"
        self.component1.save()
        ProductComponent.objects.create(
            product=self.product1,
            component=self.component1,
            license_expression=license1.key,
            dataspace=self.dataspace,
        )

        package = Package.objects.create(
            filename="package.zip",
            type="deb",
            namespace="debian",
            name="curl",
            version="7.50.3-1",
            md5="md5",
            sha1="sha1",
            sha256="sha256",
            sha512="sha512",
            download_url="https://download.url",
            primary_language="Python",
            dataspace=self.dataspace,
        )
        ProductPackage.objects.create(
            product=self.product1, package=package, dataspace=self.dataspace
        )
        vulnerability1 = make_vulnerability(self.dataspace, affecting=[package])

        self.client.login(username=self.super_user.username, password="secret")
        export_cyclonedx_url = self.product1.get_export_cyclonedx_url()
        response = self.client.get(export_cyclonedx_url)
        self.assertEqual(
            "dejacode_nexb_product_product1_with_space_1.0.cdx.json", response.filename
        )
        self.assertEqual("application/json", response.headers["Content-Type"])

        content = io.BytesIO(b"".join(response.streaming_content))
        bom_as_dict = json.loads(content.read().decode("utf-8"))
        del bom_as_dict["serialNumber"]
        del bom_as_dict["dependencies"]  # unstable ordering
        del bom_as_dict["metadata"]["timestamp"]
        del bom_as_dict["metadata"]["tools"][0]["version"]

        # Fails on the CI
        # expected = {
        #     "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        #     "bomFormat": "CycloneDX",
        #     "specVersion": "1.6",
        #     "version": 1,
        #     "metadata": {
        #         "authors": [{"name": " "}],
        #         "component": {
        #             "bom-ref": str(self.product1.uuid),
        #             "copyright": "",
        #             "description": "",
        #             "name": "Product1 With Space",
        #             "type": "application",
        #             "version": "1.0",
        #         },
        #         "tools": [{"name": "DejaCode", "vendor": "nexB"}],
        #     },
        #     "components": [
        #         {
        #             "bom-ref": str(self.component1.uuid),
        #             "copyright": "",
        #             "cpe": "",
        #             "description": "",
        #             "licenses": [{"expression": "LicenseRef-dejacode-l1"}],
        #             "name": "Component1",
        #             "type": "library",
        #             "version": "1.0",
        #         },
        #         {
        #             "author": "",
        #             "bom-ref": "pkg:deb/debian/curl@7.50.3-1",
        #             "copyright": "",
        #             "cpe": "",
        #             "description": "",
        #             "hashes": [
        #                 {"alg": "MD5", "content": "md5"},
        #                 {"alg": "SHA-1", "content": "sha1"},
        #                 {"alg": "SHA-256", "content": "sha256"},
        #                 {"alg": "SHA-512", "content": "sha512"},
        #             ],
        #             "name": "curl",
        #             "properties": [
        #                 {"name": "aboutcode:download_url", "value": "https://download.url"},
        #                 {"name": "aboutcode:filename", "value": "package.zip"},
        #                 {"name": "aboutcode:primary_language", "value": "Python"},
        #             ],
        #             "purl": "pkg:deb/debian/curl@7.50.3-1",
        #             "type": "library",
        #             "version": "7.50.3-1",
        #         },
        #     ],
        # }
        # self.assertDictEqual(expected, bom_as_dict)

        self.assertEqual("http://cyclonedx.org/schema/bom-1.6.schema.json", bom_as_dict["$schema"])

        # Old spec version
        response = self.client.get(export_cyclonedx_url, data={"spec_version": "1.5"})
        self.assertIn('"specVersion": "1.5"', str(response.getvalue()))

        response = self.client.get(export_cyclonedx_url, data={"spec_version": "10.10"})
        self.assertEqual(404, response.status_code)

        response = self.client.get(export_cyclonedx_url, data={"content": "vex"})
        response_str = str(response.getvalue())
        self.assertIn("vulnerabilities", response_str)
        self.assertIn(vulnerability1.vulnerability_id, response_str)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.submit_project")
    def test_product_portfolio_load_sbom_view(self, mock_submit):
        mock_submit.return_value = None
        self.client.login(username=self.super_user.username, password="secret")
        url = self.product1.get_load_sboms_url()
        response = self.client.get(url)
        expected = "Import SBOM"
        self.assertContains(response, expected)

        data = {"input_file": ContentFile('{"data": "data"}', name="file.json")}
        response = self.client.post(url, data=data, follow=True)
        expected = "SBOM file submitted to ScanCode.io for inspection."
        self.assertContains(response, expected)
        self.assertEqual(1, ScanCodeProject.objects.count())

        data = {"input_file": ContentFile('{"data": "data"}', name="file2.json")}
        with override_settings(CLAMD_ENABLED=True):
            with mock.patch("dje.fields.SmartFileField.scan_file_for_virus") as scan:
                response = self.client.post(url, data=data, follow=True)
                scan.assert_called_once()

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.submit_project")
    def test_product_portfolio_import_manifest_view(self, mock_submit):
        mock_submit.return_value = None
        self.client.login(username=self.super_user.username, password="secret")
        url = self.product1.get_import_manifests_url()
        response = self.client.get(url)
        expected = "Import Package manifests"
        self.assertContains(response, expected)

        data = {"input_file": ContentFile("Data")}
        response = self.client.post(url, data=data, follow=True)
        expected = "Manifest file submitted to ScanCode.io for inspection."
        self.assertContains(response, expected)
        self.assertEqual(1, ScanCodeProject.objects.count())

        with override_settings(CLAMD_ENABLED=True):
            with mock.patch("dje.fields.SmartFileField.scan_file_for_virus") as scan:
                data = {"input_file": ContentFile("Data")}
                self.client.post(url, data=data, follow=True)
                scan.assert_called_once()

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_project_dependencies")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_project_packages")
    def test_product_portfolio_import_packages_from_scancodeio_view(
        self,
        mock_fetch_packages,
        mock_fetch_dependencies,
    ):
        self.client.login(username=self.super_user.username, password="secret")
        mock_fetch_packages.return_value = [
            {
                "type": "maven",
                "namespace": "org.apache.activemq",
                "name": "activemq-camel",
                "version": "5.11.0",
                "primary_language": "Java",
            }
        ]
        mock_fetch_dependencies.return_value = [
            {
                "purl": "pkg:pypi/aboutcode-toolkit@10",
            }
        ]

        scancodeproject = ScanCodeProject.objects.create(
            product=self.product1,
            dataspace=self.product1.dataspace,
            type=ScanCodeProject.ProjectType.LOAD_SBOMS,
            created_by=self.super_user,
        )

        view_name = "product_portfolio:import_packages_from_scancodeio"
        webhook_url = scancodeio.get_webhook_url(view_name, "wrong_uuid")
        self.assertIn("/products/import_packages_from_scancodeio/", webhook_url)
        response = self.client.get(webhook_url)
        self.assertEqual(405, response.status_code)

        response = self.client.post(webhook_url)
        self.assertEqual(404, response.status_code)

        data = {
            "project": {
                "uuid": "5f2cdda6-fe86-4587-81f1-4d407d4d2c02",
            },
            "run": {
                "status": "success",
            },
        }
        response = self.client.post(webhook_url, data=data, content_type="application/json")
        self.assertEqual(404, response.status_code)

        webhook_url = scancodeio.get_webhook_url(view_name, self.super_user.uuid)
        response = self.client.post(webhook_url, data=data, content_type="application/json")
        self.assertEqual(404, response.status_code)

        data["project"]["uuid"] = scancodeproject.project_uuid

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(webhook_url, data=data, content_type="application/json")

        self.assertEqual(200, response.status_code)
        purl = "pkg:maven/org.apache.activemq/activemq-camel@5.11.0"
        self.assertEqual([purl], [package.package_url for package in self.product1.packages.all()])
        self.assertEqual(b'{"message": "Received, packages import started."}', response.content)

        notif = Notification.objects.get()
        self.assertTrue(notif.unread)
        self.assertEqual(self.super_user, notif.actor)
        self.assertEqual("Import SBOM", notif.verb)
        self.assertEqual(self.product1, notif.action_object)
        self.assertEqual(self.super_user, notif.recipient)
        expected_message = "- Imported 1 package.\n- 1 dependency error occurred during import."
        self.assertEqual(expected_message, notif.description)

        scancodeproject.refresh_from_db()
        self.assertEqual("success", scancodeproject.status)
        self.assertEqual(expected_message.split("\n"), scancodeproject.import_log)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.find_project")
    def test_product_portfolio_pull_project_data_from_scancodeio_view(self, mock_find_project):
        self.client.login(username=self.super_user.username, password="secret")

        url = self.product1.get_pull_project_data_url()
        response = self.client.get(url)
        self.assertEqual(405, response.status_code)

        response = self.client.post(url)
        self.assertEqual(404, response.status_code)

        form_data = {
            "project_name_or_uuid": "",
            "update_existing_packages": False,
        }
        response = self.client.post(url, data=form_data)
        self.assertEqual(404, response.status_code)

        project_uuid = "4545f46c-af06-4b6e-a094-ff929cef1a67"
        form_data = {
            "project_name_or_uuid": project_uuid,
            "update_existing_packages": False,
        }
        mock_find_project.return_value = None
        response = self.client.post(url, data=form_data, follow=True)
        self.assertRedirects(response, self.product1.get_absolute_url())
        self.assertContains(response, "<strong>Error:</strong>")
        self.assertContains(response, "not found on ScanCode.io.")

        mock_find_project.return_value = {
            "uuid": project_uuid,
        }
        response = self.client.post(url, data=form_data, follow=True)
        self.assertRedirects(response, f"{self.product1.get_absolute_url()}#imports")
        project = ScanCodeProject.objects.get(project_uuid=project_uuid)
        self.assertEqual(self.product1, project.product)
        self.assertEqual(ScanCodeProject.ProjectType.PULL_FROM_SCANCODEIO, project.type)
        self.assertFalse(project.update_existing_packages)
        self.assertEqual(ScanCodeProject.Status.SUBMITTED, project.status)
        self.assertEqual(self.super_user, project.created_by)

    @mock.patch("dejacode_toolkit.purldb.PurlDB.is_configured")
    def test_product_portfolio_improve_packages_from_purldb_view(self, mock_is_configured):
        mock_is_configured.return_value = True
        self.dataspace.enable_purldb_access = True
        self.dataspace.save()
        make_product_package(self.product1)

        self.assertFalse(self.basic_user.has_perm("change_product", self.product1))
        self.client.login(username=self.basic_user.username, password="secret")
        url = self.product1.get_url("improve_packages_from_purldb")
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

        self.assertTrue(self.super_user.has_perm("change_product", self.product1))
        self.client.login(username=self.super_user.username, password="secret")
        url = self.product1.get_url("improve_packages_from_purldb")
        response = self.client.get(url, follow=True)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Improve Packages from PurlDB in progress...")

        ScanCodeProject.objects.create(
            product=self.product1,
            dataspace=self.product1.dataspace,
            type=ScanCodeProject.ProjectType.IMPROVE_FROM_PURLDB,
            status=ScanCodeProject.Status.IMPORT_STARTED,
        )
        response = self.client.get(url, follow=True)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Improve Packages already in progress...")

    def test_product_portfolio_scancodeio_project_download_input_view(self):
        test_file_content = b"dummy input file content"
        test_file = SimpleUploadedFile(
            "input.zip", test_file_content, content_type="application/zip"
        )

        # Create a ScanCodeProject with file
        scancode_project = ScanCodeProject.objects.create(
            product=self.product1,
            dataspace=self.product1.dataspace,
            input_file=test_file,
            type=ScanCodeProject.ProjectType.LOAD_SBOMS,
            status=ScanCodeProject.Status.SUCCESS,
        )

        download_url = reverse(
            "product_portfolio:scancodeio_project_download_input", args=[str(scancode_project.uuid)]
        )

        # No permission initially
        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 404)

        # Grant permission
        assign_perm("view_product", self.basic_user, self.product1)
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 200)
        downloaded_content = b"".join(response.streaming_content)
        self.assertEqual(test_file_content, downloaded_content)
        self.assertEqual(
            response["Content-Disposition"], f'attachment; filename="{test_file.name}"'
        )

        # Remove the file and test for 404
        scancode_project.input_file.delete(save=True)
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 404)

    def test_product_portfolio_vulnerability_analysis_form_view(self):
        self.client.login(username=self.super_user.username, password="secret")

        package1 = make_package(self.dataspace)
        vulnerability1 = make_vulnerability(self.dataspace, affecting=[package1])
        product1 = make_product(self.dataspace, inventory=[package1])
        pp1 = product1.productpackages.get()

        url = reverse(
            "product_portfolio:vulnerability_analysis_form",
            args=[pp1.uuid, vulnerability1.vulnerability_id],
        )

        response = self.client.get(url)
        self.assertContains(response, 'name="csrfmiddlewaretoken')
        self.assertContains(response, 'name="product_package"')
        self.assertContains(response, 'name="state"')
        self.assertContains(response, 'name="justification"')
        self.assertEqual(0, VulnerabilityAnalysis.objects.count())

        product_package = ProductPackage.objects.get(product=product1, package=package1)
        data = {
            "product_package": product_package.pk,
            "vulnerability": vulnerability1.pk,
            "state": "resolved",
        }
        response = self.client.post(url, data=data)
        self.assertEqual(b'{"success": "updated"}', response.content)
        self.assertEqual(1, VulnerabilityAnalysis.objects.count())
        analysis = VulnerabilityAnalysis.objects.get()
        self.assertEqual(product_package, analysis.product_package)
        self.assertEqual(vulnerability1, analysis.vulnerability)
        self.assertEqual("resolved", analysis.state)
