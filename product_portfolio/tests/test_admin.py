#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.exceptions import NON_FIELD_ERRORS
from django.test import TestCase
from django.urls import NoReverseMatch
from django.urls import reverse

from component_catalog.models import Component
from component_catalog.models import Package
from dje.filters import DataspaceFilter
from dje.models import Dataspace
from dje.tests import create_superuser
from license_library.models import License
from organization.models import Owner
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductPackage


class ProductPortfolioAdminsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="alternate")
        self.user = create_superuser("nexb_user", self.dataspace)
        self.alternate_user = create_superuser(
            "alternate_user", self.alternate_dataspace)

        self.product1 = Product.objects.create(
            name="Product1", dataspace=self.dataspace)
        self.product_changelist_url = reverse(
            "admin:product_portfolio_product_changelist")

        self.owner1 = Owner.objects.create(
            name="Owner1", dataspace=self.dataspace)
        self.license1 = License.objects.create(
            key="l-1", name="L1", short_name="L1", dataspace=self.dataspace, owner=self.owner1
        )
        self.license2 = License.objects.create(
            key="l-2", name="L2", short_name="L2", dataspace=self.dataspace, owner=self.owner1
        )

        self.component1 = Component.objects.create(
            name="c1", version="1.0", dataspace=self.dataspace
        )

        self.package1 = Package.objects.create(
            filename="package1", dataspace=self.dataspace)

    def test_product_admin_form_clean_license_expression(self):
        self.client.login(username=self.user.username, password="secret")

        url = reverse("admin:product_portfolio_product_add")
        data = {
            "name": "p1",
            "license_expression": "invalid",
            "is_active": 1,
            "productcomponents-INITIAL_FORMS": 0,
            "productcomponents-TOTAL_FORMS": 0,
            "productpackages-INITIAL_FORMS": 0,
            "productpackages-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        expected_errors = [["Unknown license key(s): invalid"]]
        self.assertEqual(expected_errors, response.context_data["errors"])

        data["license_expression"] = self.license1.key
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        product = Product.objects.get_queryset(user=self.user).latest("id")
        self.assertEqual(1, product.licenses.count())
        self.assertEqual(self.license1, product.licenses.get())

    def test_product_admin_form_clean_license_expression_in_alternate_dataspace(self):
        alternate_p1 = Product.objects.create(
            name="alternate p1", dataspace=self.alternate_dataspace
        )
        url = alternate_p1.get_admin_url()

        self.client.login(
            username=self.alternate_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)

        # No cross dataspace allowed on Product
        self.client.login(username=self.user.username, password="secret")
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse("admin:index"))
        expected = (
            f'<li class="grp-warning">product with ID “{alternate_p1.id}” doesn’t exist.'
            f" Perhaps it was deleted?</li>"
        )
        self.assertContains(response, expected, html=True)

        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse("admin:index"))
        self.assertContains(response, expected, html=True)

    def test_product_security_admin_changelist_available_actions(self):
        self.client.login(username=self.user.username, password="secret")
        response = self.client.get(self.product_changelist_url)
        expected = [("", "---------"), ("mass_update", "Mass update")]
        self.assertEqual(
            expected, response.context_data["action_form"].fields["action"].choices)

        with self.assertRaises(NoReverseMatch):
            reverse("admin:product_portfolio_product_copy")

    def test_product_security_admin_changelist_dataspace_filter_not_allowed(self):
        self.client.login(username=self.user.username, password="secret")
        data = {DataspaceFilter.parameter_name: self.alternate_dataspace.id}
        response = self.client.get(self.product_changelist_url, data)
        self.assertEqual(400, response.status_code)

    def test_product_admin_changeform_product_component_feature_datalist(self):
        self.client.login(username=self.user.username, password="secret")

        url = reverse("admin:product_portfolio_product_add")
        response = self.client.get(url)
        expected = '<datalist id="feature_datalist"></datalist>'
        self.assertContains(response, expected, html=True)

        url = self.product1.get_admin_url()
        response = self.client.get(url)
        expected = '<datalist id="feature_datalist"></datalist>'
        self.assertContains(response, expected, html=True)

        ProductComponent.objects.create(
            product=self.product1,
            component=self.component1,
            dataspace=self.dataspace,
            feature="Feature 1",
        )
        response = self.client.get(url)
        expected = '<datalist id="feature_datalist"><option>Feature 1</option></datalist>'
        self.assertContains(response, expected, html=True)

        ProductPackage.objects.create(
            product=self.product1,
            package=self.package1,
            dataspace=self.dataspace,
            feature="Feature 2",
        )
        response = self.client.get(url)
        expected = (
            '<datalist id="feature_datalist">'
            "<option>Feature 1</option>"
            "<option>Feature 2</option>"
            "</datalist>"
        )
        self.assertContains(response, expected, html=True)

    def test_product_admin_changeform_unique_validation(self):
        self.client.login(username=self.user.username, password="secret")

        url = reverse("admin:product_portfolio_product_add")
        data = {
            "name": self.product1.name,
            "version": self.product1.version,
            "productcomponents-INITIAL_FORMS": 0,
            "productcomponents-TOTAL_FORMS": 0,
            "productpackages-INITIAL_FORMS": 0,
            "productpackages-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        error_msg = "Product with this Name and Version already exists."
        self.assertContains(response, error_msg)
        expected = {NON_FIELD_ERRORS: [error_msg]}
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

        url = self.product1.get_admin_url()
        data["_saveasnew"] = "Save as new"
        response = self.client.post(url, data)
        self.assertContains(response, error_msg)
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

        data["version"] = "1.0"
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

    def test_productcomponent_admin_changeform_feature_datalist(self):
        self.client.login(username=self.user.username, password="secret")
        url = reverse("admin:product_portfolio_productcomponent_add")

        response = self.client.get(url)
        expected = '<datalist id="feature_datalist"></datalist>'
        self.assertContains(response, expected, html=True)

        pc1 = ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )
        url = pc1.get_admin_url()
        response = self.client.get(url)
        expected = '<datalist id="feature_datalist"></datalist>'
        self.assertContains(response, expected, html=True)

        pc1.feature = "Feature 1"
        pc1.save()
        response = self.client.get(url)
        expected = '<datalist id="feature_datalist"><option>Feature 1</option></datalist>'
        self.assertContains(response, expected, html=True)

        ProductPackage.objects.create(
            product=self.product1,
            package=self.package1,
            dataspace=self.dataspace,
            feature="Feature 2",
        )
        response = self.client.get(url)
        expected = (
            '<datalist id="feature_datalist">'
            "<option>Feature 1</option>"
            "<option>Feature 2</option>"
            "</datalist>"
        )
        self.assertContains(response, expected, html=True)

    def test_productcomponent_admin_license_expression_from_component(self):
        self.client.login(username=self.user.username, password="secret")

        url = reverse("admin:product_portfolio_productcomponent_add")
        data = {
            "product": self.product1.id,
            "component": self.component1.id,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        pc = ProductComponent.objects.latest("id")
        self.assertEqual("", self.component1.license_expression)
        self.assertEqual("", pc.license_expression)
        self.assertFalse(self.component1.licenses.exists())
        self.assertFalse(pc.licenses.exists())
        pc.delete()

        self.component1.license_expression = self.license1.key
        self.component1.save()

        # license_expression empty, value taken from Component
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.license1.key, self.component1.license_expression)
        pc = ProductComponent.objects.latest("id")
        self.assertEqual(self.license1.key, self.component1.license_expression)
        self.assertEqual(self.license1.key, pc.license_expression)
        self.assertTrue(self.component1.licenses.exists())
        self.assertTrue(pc.licenses.exists())
        self.assertEqual(self.component1.license_expression,
                         pc.license_expression)
        pc.delete()

    def test_productcomponent_admin_license_expression_widget(self):
        self.client.login(username=self.user.username, password="secret")
        url = reverse("admin:product_portfolio_productcomponent_add")
        response = self.client.get(url)
        self.assertContains(response, 'related_model_name="Component" ')
        self.assertContains(response, 'related_api_url="/api/v2/components/"')

    def test_productpackage_admin_license_expression_from_package(self):
        self.client.login(username=self.user.username, password="secret")

        url = reverse("admin:product_portfolio_productpackage_add")
        data = {
            "product": self.product1.id,
            "package": self.package1.id,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        pp = ProductPackage.objects.latest("id")
        self.assertEqual("", self.package1.license_expression)
        self.assertEqual("", pp.license_expression)
        self.assertFalse(self.package1.licenses.exists())
        self.assertFalse(pp.licenses.exists())
        pp.delete()

        self.package1.license_expression = self.license1.key
        self.package1.save()

        # license_expression empty, value taken from Component
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.license1.key, self.package1.license_expression)
        pc = ProductPackage.objects.latest("id")
        self.assertEqual(self.license1.key, self.package1.license_expression)
        self.assertEqual(self.license1.key, pc.license_expression)
        self.assertTrue(self.package1.licenses.exists())
        self.assertTrue(pc.licenses.exists())
        self.assertEqual(self.package1.license_expression,
                         pc.license_expression)
        pc.delete()

    def test_productpackage_admin_license_expression_widget(self):
        self.client.login(username=self.user.username, password="secret")
        url = reverse("admin:product_portfolio_productpackage_add")
        response = self.client.get(url)
        self.assertContains(response, 'related_model_name="Package" ')
        self.assertContains(response, 'related_api_url="/api/v2/packages/"')

    def test_productcomponent_admin_license_expression_validation(self):
        self.client.login(username=self.user.username, password="secret")

        # No Component FK, validates against licenses in current dataspace
        url = reverse("admin:product_portfolio_productcomponent_add")
        data = {
            "product": self.product1.id,
            "license_expression": "invalid",
        }

        response = self.client.post(url, data)
        expected = {"license_expression": ["Unknown license key(s): invalid"]}
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

        # Component FK set, validates against component.license_expression
        self.component1.license_expression = self.license1.key
        self.component1.save()
        data["component"] = self.component1.id
        data["license_expression"] = self.license1.key
        self.client.post(url, data)
        pc = ProductComponent.objects.latest("id")
        self.assertEqual(self.license1.key, self.component1.license_expression)
        self.assertEqual(self.license1.key, pc.license_expression)
        self.assertTrue(self.component1.licenses.exists())
        self.assertTrue(pc.licenses.exists())
        self.assertEqual(self.component1.license_expression,
                         pc.license_expression)

        pc.delete()
        data["license_expression"] = self.license2.key
        response = self.client.post(url, data)
        expected = {
            "license_expression": ["Unknown license key(s): l-2<br>Available licenses: l-1"]
        }
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

    def test_productpackage_admin_license_expression_validation(self):
        self.client.login(username=self.user.username, password="secret")

        url = reverse("admin:product_portfolio_productpackage_add")
        data = {
            "product": self.product1.id,
            "package": self.package1.id,
            "license_expression": "invalid",
        }

        response = self.client.post(url, data)
        expected = {"license_expression": ["Unknown license key(s): invalid"]}
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

        self.package1.license_expression = self.license1.key
        self.package1.save()
        data["license_expression"] = self.license1.key
        self.client.post(url, data)
        pp = ProductPackage.objects.latest("id")
        self.assertEqual(self.license1.key, self.package1.license_expression)
        self.assertEqual(self.license1.key, pp.license_expression)
        self.assertTrue(self.package1.licenses.exists())
        self.assertTrue(pp.licenses.exists())
        self.assertEqual(self.package1.license_expression,
                         pp.license_expression)

        pp.delete()
        data["license_expression"] = self.license2.key
        response = self.client.post(url, data)
        expected = {
            "license_expression": ["Unknown license key(s): l-2<br>Available licenses: l-1"]
        }
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

    def test_productcomponent_admin_changelist_component_completeness_list_filter(self):
        self.client.login(username=self.user.username, password="secret")
        pc_valid = ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )
        pc_custom = ProductComponent.objects.create(
            product=self.product1, name="CustomComponent", dataspace=self.dataspace
        )

        url = reverse("admin:product_portfolio_productcomponent_changelist")

        response = self.client.get(url)
        self.assertEqual(2, response.context_data["cl"].result_count)
        self.assertIn(pc_valid, response.context_data["cl"].queryset)
        self.assertIn(pc_custom, response.context_data["cl"].queryset)

        response = self.client.get(url, {"completeness": "catalog"})
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(pc_valid, response.context_data["cl"].queryset)
        self.assertNotIn(pc_custom, response.context_data["cl"].queryset)

        response = self.client.get(url, {"completeness": "custom"})
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertNotIn(pc_valid, response.context_data["cl"].queryset)
        self.assertIn(pc_custom, response.context_data["cl"].queryset)

        response = self.client.get(url, {"completeness": "WRONG"})
        self.assertEqual(2, response.context_data["cl"].result_count)
        self.assertIn(pc_valid, response.context_data["cl"].queryset)
        self.assertIn(pc_custom, response.context_data["cl"].queryset)

    def test_productcomponent_admin_check_for_update_actions(self):
        expected1 = "check_related_updates_in_reference"
        expected2 = "check_related_newer_version_in_reference"
        url = reverse("admin:product_portfolio_productcomponent_changelist")

        self.assertTrue(self.user.dataspace.is_reference)
        self.client.login(username=self.user.username, password="secret")
        response = self.client.get(url)
        actions_choices = response.context_data["action_form"].fields["action"].choices
        actions = [name for name, _ in actions_choices]
        self.assertNotIn(expected1, actions)
        self.assertNotIn(expected2, actions)

        self.assertFalse(self.alternate_user.dataspace.is_reference)
        self.client.login(
            username=self.alternate_user.username, password="secret")
        response = self.client.get(url)
        actions_choices = response.context_data["action_form"].fields["action"].choices
        actions = [name for name, _ in actions_choices]
        self.assertIn(expected1, actions)
        self.assertIn(expected2, actions)

    def test_product_admin_changeform_save_as_includes_relationships(self):
        self.client.login(username=self.user.username, password="secret")

        ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.dataspace
        )
        ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )

        url = self.product1.get_admin_url()
        data = {
            "_saveasnew": "Save as new",
            "name": self.product1.name,
            "version": "new version",
            "productcomponents-INITIAL_FORMS": 0,
            "productcomponents-TOTAL_FORMS": 0,
            "productpackages-INITIAL_FORMS": 0,
            "productpackages-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        new_product = Product.unsecured_objects.get(
            name=self.product1.name, version="new version")
        self.assertEqual(1, new_product.productcomponents.count())
        self.assertEqual(1, new_product.productpackages.count())

    def test_codebaseresource_admin_changeform_product_prefill_on_save_addanother(self):
        self.client.login(username=self.user.username, password="secret")
        url = reverse("admin:product_portfolio_codebaseresource_add")

        data = {
            "product": self.product1.id,
            "path": "path1",
            "related_deployed_from-TOTAL_FORMS": 0,
            "related_deployed_from-INITIAL_FORMS": 0,
            "related_deployed_to-TOTAL_FORMS": 0,
            "related_deployed_to-INITIAL_FORMS": 0,
            "_addanother": "Save and add another",
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        expected = f"{url}?product={self.product1.id}"
        self.assertEqual(expected, response.url)

    def test_codebaseresource_admin_changeform_lookup_autocomplete(self):
        self.client.login(username=self.user.username, password="secret")
        # url = reverse('admin:product_portfolio_codebaseresource_add')
        autocomplete_url = reverse("grp_autocomplete_lookup")
        expected = b'[{"value": null, "label": "0 results"}]'

        model = "product"
        url = f"{autocomplete_url}?app_label=product_portfolio&model_name={model}&term=term"
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual(expected, response.content)

        model = "productcomponent"
        url = f"{autocomplete_url}?app_label=product_portfolio&model_name={model}&term=term"
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual(expected, response.content)

        model = "productpackage"
        url = f"{autocomplete_url}?app_label=product_portfolio&model_name={model}&term=term"
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual(expected, response.content)
