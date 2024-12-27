#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase

from guardian.shortcuts import assign_perm

from component_catalog.models import Component
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import Package
from component_catalog.tests import make_package
from dje.models import Dataspace
from dje.models import History
from dje.tests import add_perms
from dje.tests import create_admin
from dje.tests import create_superuser
from dje.tests import create_user
from license_library.models import License
from organization.models import Owner
from policy.models import UsagePolicy
from product_portfolio.models import CodebaseResource
from product_portfolio.models import CodebaseResourceUsage
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductComponentAssignedLicense
from product_portfolio.models import ProductDependency
from product_portfolio.models import ProductInventoryItem
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductRelationStatus
from product_portfolio.models import ProductSecuredManager
from product_portfolio.models import ProductStatus
from product_portfolio.models import ScanCodeProject
from product_portfolio.tests import make_product_item_purpose
from product_portfolio.tests import make_product_package
from vulnerabilities.tests import make_vulnerability
from workflow.models import RequestTemplate


class ProductPortfolioModelsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)
        self.product1 = Product.objects.create(name="Product1", dataspace=self.dataspace)
        self.codebase_resource1 = CodebaseResource.objects.create(
            path="/path1/", product=self.product1, dataspace=self.dataspace
        )
        self.codebase_resource2 = CodebaseResource.objects.create(
            path="/path2/", product=self.product1, dataspace=self.dataspace
        )

        owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        self.license1 = License.objects.create(
            key="l-1", name="L1", short_name="L1", dataspace=self.dataspace, owner=owner1
        )
        self.license2 = License.objects.create(
            key="l-2", name="L2", short_name="L2", dataspace=self.dataspace, owner=owner1
        )

    def test_product_model_default_status_on_product_addition(self):
        status1 = ProductStatus.objects.create(
            label="S1", text="Status1", default_on_addition=True, dataspace=self.dataspace
        )
        status2 = ProductStatus.objects.create(label="S2", text="Status2", dataspace=self.dataspace)

        # No status given at creation time, the default is set
        p1 = Product.objects.create(name="P1", dataspace=self.dataspace)
        self.assertEqual(status1, p1.configuration_status)

        # A status is given at creation time, no default is set
        p2 = Product.objects.create(
            name="P2", configuration_status=status2, dataspace=self.dataspace
        )
        self.assertEqual(status2, p2.configuration_status)

    def test_product_model_get_attribution_url(self):
        self.assertEqual(
            "/products/nexB/Product1/attribution/", self.product1.get_attribution_url()
        )

        self.product1.version = "1.0"
        self.product1.save()
        self.assertEqual(
            "/products/nexB/Product1/1.0/attribution/", self.product1.get_attribution_url()
        )

    def test_product_model_secured_manager(self):
        self.assertTrue(isinstance(Product.objects, ProductSecuredManager))
        self.assertTrue(Product.objects.is_secured)
        self.assertEqual([], list(Product.objects.all()))
        self.assertEqual([], list(Product.objects.get_queryset()))
        self.assertEqual(0, Product.objects.count())

        self.assertEqual(1, Product.objects.get_queryset(self.super_user).count())
        self.assertIn(self.product1, Product.objects.get_queryset(self.super_user))

    def test_product_model_is_active(self):
        qs = Product.objects.get_queryset(self.super_user)
        self.assertIn(self.product1, qs)
        qs = Product.objects.get_queryset(self.super_user, include_inactive=True)
        self.assertIn(self.product1, qs)

        self.product1.is_active = False
        self.product1.save()

        qs = Product.objects.get_queryset(self.super_user)
        self.assertNotIn(self.product1, qs)
        qs = Product.objects.get_queryset(self.super_user, include_inactive=True)
        self.assertIn(self.product1, qs)

    def test_product_model_all_packages(self):
        package1 = Package.objects.create(filename="package1", dataspace=self.dataspace)
        package2 = Package.objects.create(filename="package2", dataspace=self.dataspace)
        component1 = Component.objects.create(name="c1", dataspace=self.dataspace)
        ComponentAssignedPackage.objects.create(
            component=component1, package=package1, dataspace=self.dataspace
        )
        ComponentAssignedPackage.objects.create(
            component=component1, package=package2, dataspace=self.dataspace
        )
        ProductComponent.objects.create(
            product=self.product1, component=component1, dataspace=self.dataspace
        )
        package3 = Package.objects.create(filename="package3", dataspace=self.dataspace)
        ProductPackage.objects.create(
            product=self.product1, package=package3, dataspace=self.dataspace
        )

        all_packages = self.product1.all_packages
        self.assertEqual(3, len(all_packages))
        self.assertIn(package1, all_packages)
        self.assertIn(package2, all_packages)
        self.assertIn(package3, all_packages)

    def test_product_model_get_feature_values_and_get_feature_datalist(self):
        ProductComponent.objects.create(
            product=self.product1, name="p1", feature="f1", dataspace=self.dataspace
        )
        ProductComponent.objects.create(
            product=self.product1, name="p2", feature="f1", dataspace=self.dataspace
        )
        ProductComponent.objects.create(
            product=self.product1, name="p3", feature="f2", dataspace=self.dataspace
        )

        expected = ["f1", "f2"]
        pc_queryset = self.product1.productcomponents
        self.assertEqual(expected, list(self.product1.get_feature_values(pc_queryset)))

        expected = (
            '<datalist id="feature_datalist">'
            "<option>f1</option>"
            "<option>f2</option>"
            "</datalist>"
        )
        self.assertEqual(expected, self.product1.get_feature_datalist())

        package1 = Package.objects.create(filename="package1", dataspace=self.dataspace)
        ProductPackage.objects.create(
            product=self.product1, package=package1, feature="f0", dataspace=self.dataspace
        )
        expected = ["f0"]
        pp_queryset = self.product1.productpackages
        self.assertEqual(expected, list(self.product1.get_feature_values(pp_queryset)))

        expected = (
            '<datalist id="feature_datalist">'
            "<option>f0</option>"
            "<option>f1</option>"
            "<option>f2</option>"
            "</datalist>"
        )
        self.assertEqual(expected, self.product1.get_feature_datalist())

    def test_productcomponent_model_default_status_on_product_addition(self):
        status1 = ProductRelationStatus.objects.create(
            label="S1", text="Status1", default_on_addition=True, dataspace=self.dataspace
        )
        status2 = ProductRelationStatus.objects.create(
            label="S2", text="Status2", dataspace=self.dataspace
        )

        # No status given at creation time, the default is set
        p1 = ProductComponent.objects.create(
            product=self.product1, name="p1", dataspace=self.dataspace
        )
        self.assertEqual(status1, p1.review_status)

        # A status is given at creation time, no default is set
        pc2 = ProductComponent.objects.create(
            product=self.product1, name="c2", review_status=status2, dataspace=self.dataspace
        )
        self.assertEqual(status2, pc2.review_status)

    def test_productcomponent_model_str_method(self):
        component1 = Component(name="p1", version="1.0")
        self.assertEqual(
            "(Component data missing)", str(ProductComponent(component=None, name="", version=""))
        )
        self.assertEqual("p1 1.0", str(ProductComponent(component=component1, name="", version="")))
        self.assertEqual("c2 ", str(ProductComponent(component=None, name="c2", version="")))
        self.assertEqual(" v2", str(ProductComponent(component=None, name="", version="v2")))
        self.assertEqual("c2 v2", str(ProductComponent(component=None, name="c2", version="v2")))

    def test_product_model_save_license_expression_handle_assigned_licenses(self):
        expression = "{} AND {}".format(self.license1.key, self.license2.key)

        p1 = Product.objects.create(
            name="p 1",
            dataspace=self.dataspace,
            license_expression=expression,
        )

        self.assertEqual(2, p1.licenses.count())
        self.assertIn(self.license1, p1.licenses.all())
        self.assertIn(self.license2, p1.licenses.all())

        p1.license_expression = self.license1.key
        p1.save()

        self.assertEqual(1, p1.licenses.count())
        self.assertIn(self.license1, p1.licenses.all())
        self.assertNotIn(self.license2, p1.licenses.all())

        p1.license_expression = ""
        p1.save()
        self.assertEqual(0, p1.licenses.count())

    def test_product_model_can_be_changed_by(self):
        basic_user = create_user("basic_user", self.dataspace)

        self.assertFalse(self.product1.can_be_changed_by(basic_user))
        self.assertFalse(self.product1.can_be_changed_by(self.admin_user))
        self.assertTrue(self.product1.can_be_changed_by(self.super_user))

        basic_user = add_perms(basic_user, ["change_product"])
        self.assertFalse(self.product1.can_be_changed_by(basic_user))

        assign_perm("change_product", basic_user, self.product1)
        self.assertTrue(self.product1.can_be_changed_by(basic_user))

    def test_product_model_assign_objects(self):
        status1 = ProductRelationStatus.objects.create(
            label="S1", text="Status1", default_on_addition=True, dataspace=self.dataspace
        )
        self.assertEqual(0, self.product1.productcomponents.count())

        with self.assertRaises(ValueError) as cm:
            self.product1.assign_objects([status1], self.super_user)
        self.assertEqual("Unsupported object model: productrelationstatus", str(cm.exception))

        created, updated, unchanged = self.product1.assign_objects([], self.super_user)
        self.assertEqual(0, created)
        self.assertEqual(0, updated)
        self.assertEqual(0, unchanged)

        component1 = Component.objects.create(
            name="c1",
            license_expression=self.license1.key,
            dataspace=self.dataspace,
        )
        created, updated, unchanged = self.product1.assign_objects([component1], self.super_user)
        self.assertEqual(1, created)
        self.assertEqual(0, updated)
        self.assertEqual(0, unchanged)

        pc = ProductComponent.objects.get(product=self.product1, component=component1)
        self.assertEqual(self.license1.key, pc.license_expression)
        self.assertEqual(status1, pc.review_status)
        self.assertEqual(self.super_user, pc.created_by)
        self.assertEqual(self.super_user, pc.last_modified_by)
        self.assertEqual(32, len(str(pc.created_date)))
        self.assertEqual(32, len(str(pc.last_modified_date)))

        self.product1.refresh_from_db()
        history_entries = History.objects.get_for_object(self.product1)
        expected_messages = sorted(
            [
                'Added component "c1"',
            ]
        )
        self.assertEqual(
            expected_messages, sorted([entry.change_message for entry in history_entries])
        )
        self.assertEqual(self.super_user, self.product1.last_modified_by)

    def test_product_model_assign_object_replace_version_component(self):
        component1 = Component.objects.create(name="c", version="1.0", dataspace=self.dataspace)
        component2 = Component.objects.create(name="c", version="2.0", dataspace=self.dataspace)

        # Assign component1
        status, relation = self.product1.assign_object(component1, self.super_user)
        self.assertEqual("created", status)
        self.assertTrue(relation)
        self.assertQuerySetEqual([component1], self.product1.components.all())

        # Re-assign component1, relation already exists.
        status, relation = self.product1.assign_object(component1, self.super_user)
        self.assertEqual("unchanged", status)
        self.assertIsNone(relation)
        self.assertQuerySetEqual([component1], self.product1.components.all())
        # With replace_version
        status, relation = self.product1.assign_object(
            component1, self.super_user, replace_version=1
        )
        self.assertEqual("unchanged", status)
        self.assertIsNone(relation)
        self.assertQuerySetEqual([component1], self.product1.components.all())

        # Assign component2
        status, p1_c2 = self.product1.assign_object(component2, self.super_user)
        self.assertEqual("created", status)
        self.assertTrue(p1_c2)
        self.assertQuerySetEqual([component1, component2], self.product1.components.all())

        # Replacing the current single existing version.
        p1_c2.delete()
        status, p1_c2 = self.product1.assign_object(
            component2, self.super_user, replace_version=True
        )
        self.assertEqual("updated", status)
        self.assertTrue(p1_c2)
        self.assertQuerySetEqual([component2], self.product1.components.all())

        history_entries = History.objects.get_for_object(self.product1)
        expected_message = 'Updated component "c 1.0" to "c 2.0"'
        self.assertEqual(expected_message, history_entries.latest("action_time").change_message)

    def test_product_model_assign_object_replace_version_package(self):
        package_data = {
            "filename": "package.zip",
            "type": "deb",
            "namespace": "debian",
            "name": "curl",
            "dataspace": self.dataspace,
        }
        package1 = Package.objects.create(**package_data, version="1.0")
        package2 = Package.objects.create(**package_data, version="2.0")

        # Assign package1
        status, relation = self.product1.assign_object(package1, self.super_user)
        self.assertEqual("created", status)
        self.assertTrue(relation)
        self.assertQuerySetEqual([package1], self.product1.packages.all())

        # Re-assign package1, relation already exists.
        status, relation = self.product1.assign_object(package1, self.super_user)
        self.assertEqual("unchanged", status)
        self.assertIsNone(relation)
        self.assertQuerySetEqual([package1], self.product1.packages.all())
        # With replace_version
        status, relation = self.product1.assign_object(package1, self.super_user, replace_version=1)
        self.assertEqual("unchanged", status)
        self.assertIsNone(relation)
        self.assertQuerySetEqual([package1], self.product1.packages.all())

        # Assign package2
        status, p1_p2 = self.product1.assign_object(package2, self.super_user)
        self.assertEqual("created", status)
        self.assertTrue(p1_p2)
        self.assertQuerySetEqual([package1, package2], self.product1.packages.all())

        # Replacing the current single existing version.
        p1_p2.delete()
        status, p1_p2 = self.product1.assign_object(package2, self.super_user, replace_version=True)
        self.assertEqual("updated", status)
        self.assertTrue(p1_p2)
        self.assertQuerySetEqual([package2], self.product1.packages.all())

        history_entries = History.objects.get_for_object(self.product1)
        expected_message = 'Updated package "pkg:deb/debian/curl@1.0" to "pkg:deb/debian/curl@2.0"'
        self.assertEqual(expected_message, history_entries.latest("action_time").change_message)

    def test_product_model_find_assigned_other_versions_component(self):
        component1 = Component.objects.create(name="c", version="1.0", dataspace=self.dataspace)
        component2 = Component.objects.create(name="c", version="2.0", dataspace=self.dataspace)
        component3 = Component.objects.create(name="c", version="3.0", dataspace=self.dataspace)

        # No other version assigned
        self.assertQuerySetEqual([], self.product1.find_assigned_other_versions(component1))
        self.assertQuerySetEqual([], self.product1.find_assigned_other_versions(component2))
        self.assertQuerySetEqual([], self.product1.find_assigned_other_versions(component3))

        # 1 other version assigned
        _, p1_c1 = self.product1.assign_object(component1, self.super_user)
        self.assertQuerySetEqual([], self.product1.find_assigned_other_versions(component1))
        self.assertQuerySetEqual([p1_c1], self.product1.find_assigned_other_versions(component2))
        self.assertQuerySetEqual([p1_c1], self.product1.find_assigned_other_versions(component3))

        # 2 other versions assigned
        _, p1_c2 = self.product1.assign_object(component2, self.super_user)
        self.assertQuerySetEqual([p1_c2], self.product1.find_assigned_other_versions(component1))
        self.assertQuerySetEqual([p1_c1], self.product1.find_assigned_other_versions(component2))
        self.assertQuerySetEqual(
            [p1_c1, p1_c2], self.product1.find_assigned_other_versions(component3)
        )

    def test_product_model_find_assigned_other_versions_package(self):
        package_data = {
            "filename": "package.zip",
            "type": "deb",
            "namespace": "debian",
            "name": "curl",
            "dataspace": self.dataspace,
        }
        package1 = Package.objects.create(**package_data, version="1.0")
        package2 = Package.objects.create(**package_data, version="2.0")
        package3 = Package.objects.create(**package_data, version="3.0")

        # No other version assigned
        self.assertQuerySetEqual([], self.product1.find_assigned_other_versions(package1))
        self.assertQuerySetEqual([], self.product1.find_assigned_other_versions(package2))
        self.assertQuerySetEqual([], self.product1.find_assigned_other_versions(package3))

        # 1 other version assigned
        _, p1_p1 = self.product1.assign_object(package1, self.super_user)
        self.assertQuerySetEqual([], self.product1.find_assigned_other_versions(package1))
        self.assertQuerySetEqual([p1_p1], self.product1.find_assigned_other_versions(package2))
        self.assertQuerySetEqual([p1_p1], self.product1.find_assigned_other_versions(package3))

        # 2 other versions assigned
        _, p1_p2 = self.product1.assign_object(package2, self.super_user)
        self.assertQuerySetEqual([p1_p2], self.product1.find_assigned_other_versions(package1))
        self.assertQuerySetEqual([p1_p1], self.product1.find_assigned_other_versions(package2))
        self.assertQuerySetEqual(
            [p1_p1, p1_p2], self.product1.find_assigned_other_versions(package3)
        )

        # Only PURL fields are used as lookups as the filename and download_url
        # fields change between version.
        package_data["filename"] = "different_filename"
        package4 = Package.objects.create(**package_data, version="4.0")
        self.assertQuerySetEqual(
            [p1_p1, p1_p2], self.product1.find_assigned_other_versions(package4)
        )

    def test_product_model_field_changes_mixin(self):
        self.assertFalse(Product().has_changed("name"))

        product = Product.objects.get_queryset(self.super_user).get(name="Product1")
        self.assertFalse(product.has_changed("name"))
        self.assertFalse(product.has_changed("configuration_status_id"))

        with self.assertRaises(AttributeError):
            product.has_changed("non-existing-field")

        product.name = "new name"
        self.assertTrue(product.has_changed("name"))
        product.save()
        self.assertTrue(product.has_changed("name"))

    def test_product_model_actions_on_status_change(self):
        product = Product.objects.get_queryset(self.super_user).get(name="Product1")
        self.assertIsNone(product.configuration_status)

        product_ct = ContentType.objects.get(app_label="product_portfolio", model="product")
        request_template1 = RequestTemplate.objects.create(
            name="Template1",
            description="Description",
            dataspace=self.super_user.dataspace,
            content_type=product_ct,
        )

        status1 = ProductStatus.objects.create(
            label="status1",
            text="status1",
            request_to_generate=request_template1,
            dataspace=self.dataspace,
        )

        product.configuration_status = status1
        product.last_modified_by = self.super_user
        self.assertTrue(product.has_changed("configuration_status_id"))
        product.save()
        self.assertEqual(1, request_template1.requests.count())
        request = request_template1.requests.get()
        self.assertEqual("Review Product Product1 in status1 status", request.title)

        product.refresh_from_db()
        self.assertEqual(1, product.request_count)

    @mock.patch("component_catalog.models.Package.update_from_purldb")
    def test_product_model_improve_packages_from_purldb(self, mock_update_from_purldb):
        mock_update_from_purldb.return_value = 1

        pp1 = make_product_package(self.product1, license_expression="unknown")
        pp1.package.update(declared_license_expression="apache-2.0")
        make_product_package(self.product1)
        self.assertEqual(2, self.product1.packages.count())

        updated_packages = self.product1.improve_packages_from_purldb(self.super_user)
        self.assertEqual(2, len(updated_packages))
        self.assertEqual(2, mock_update_from_purldb.call_count)

        # Updated from the package during improve_packages_from_purldb
        pp1.refresh_from_db()
        self.assertEqual("apache-2.0", pp1.license_expression)

    def test_product_model_get_vulnerability_qs(self):
        package1 = make_package(self.dataspace)
        package2 = make_package(self.dataspace)
        vulnerability1 = make_vulnerability(
            self.dataspace, affecting=[package1, package2], risk_score=10.0
        )
        vulnerability2 = make_vulnerability(
            self.dataspace, affecting=[package1, package2], risk_score=1.0
        )
        make_product_package(self.product1, package=package1)
        make_product_package(self.product1, package=package2)

        queryset = self.product1.get_vulnerability_qs()
        # Makeing sure the distinct() is properly applied
        self.assertEqual(2, len(queryset))
        self.assertIn(vulnerability1, queryset)
        self.assertIn(vulnerability2, queryset)

        queryset = self.product1.get_vulnerability_qs(risk_threshold=5.0)
        # Makeing sure the distinct() is properly applied
        self.assertEqual(1, len(queryset))
        self.assertIn(vulnerability1, queryset)
        self.assertNotIn(vulnerability2, queryset)

    def test_product_model_vulnerability_count_property(self):
        self.assertEqual(0, self.product1.vulnerability_count)

        package1 = make_package(self.dataspace)
        package2 = make_package(self.dataspace)
        make_vulnerability(self.dataspace, affecting=[package1, package2])
        make_vulnerability(self.dataspace, affecting=[package1, package2])
        make_product_package(self.product1, package=package1)
        make_product_package(self.product1, package=package2)

        # Still 0 on the instance as it is a cached_property
        self.assertEqual(0, self.product1.vulnerability_count)
        self.product1 = Product.unsecured_objects.get(pk=self.product1.pk)
        self.assertEqual(2, self.product1.vulnerability_count)

    def test_product_model_get_vulnerabilities_risk_threshold(self):
        self.assertIsNone(self.product1.get_vulnerabilities_risk_threshold())

        self.product1.dataspace.set_configuration("vulnerabilities_risk_threshold", 5.0)
        self.assertEqual(5.0, self.product1.get_vulnerabilities_risk_threshold())

        self.product1.update(vulnerabilities_risk_threshold=10.0)
        self.assertEqual(10.0, self.product1.get_vulnerabilities_risk_threshold())

    def test_productcomponent_model_license_expression_handle_assigned_licenses(self):
        p1 = ProductComponent.objects.create(
            product=self.product1, name="p1", dataspace=self.dataspace
        )

        self.assertFalse(p1.licenses.exists())
        self.assertFalse(p1.license_expression)

        ProductComponentAssignedLicense.objects.create(
            productcomponent=p1, license=self.license2, dataspace=self.dataspace
        )

        p1.license_expression = "{} AND non-existing".format(self.license1.key)
        p1.save()  # .save() triggers handle_assigned_licenses()

        # license1 is assigned from the expression, and license is deleted as not in expression
        self.assertEqual(1, p1.licenses.count())
        self.assertIn(self.license1, p1.licenses.all())
        self.assertNotIn(self.license2, p1.licenses.all())

    def test_productcomponent_model_manager_queryset_product_secured(self):
        ProductComponent.objects.create(product=self.product1, name="p1", dataspace=self.dataspace)

        self.assertEqual(1, ProductComponent.objects.count())
        self.assertEqual(0, ProductComponent.objects.product_secured().count())
        self.assertEqual(1, ProductComponent.objects.product_secured(self.super_user).count())

        self.assertEqual(0, ProductComponent.objects.product_secured(self.admin_user).count())
        assign_perm("view_product", self.admin_user, self.product1)
        self.assertEqual(1, ProductComponent.objects.product_secured(self.admin_user).count())

        perms = ("view_product", "change_product")
        qs = ProductComponent.objects.product_secured(self.admin_user, perms)
        self.assertEqual(0, qs.count())
        assign_perm("change_product", self.admin_user, self.product1)
        qs = ProductComponent.objects.product_secured(self.admin_user, perms)
        self.assertEqual(1, qs.count())

    def test_productcomponent_model_manager_queryset_group_by(self):
        pc1 = ProductComponent.objects.create(
            product=self.product1, name="p1", feature="f1", dataspace=self.dataspace
        )
        pc2 = ProductComponent.objects.create(
            product=self.product1, name="p2", feature="f2", dataspace=self.dataspace
        )
        pc3 = ProductComponent.objects.create(
            product=self.product1, name="p3", feature="f1", dataspace=self.dataspace
        )

        grouped = ProductComponent.objects.order_by("feature").group_by("feature")
        self.assertEqual(list(grouped.keys()), ["f1", "f2"])
        self.assertEqual([pc2], grouped["f2"])
        self.assertIn(pc1, grouped["f1"])
        self.assertIn(pc3, grouped["f1"])

        grouped = ProductComponent.objects.group_by("feature")
        self.assertEqual(list(grouped.keys()), ["f1", "f2"])
        self.assertEqual([pc2], grouped["f2"])
        self.assertIn(pc1, grouped["f1"])
        self.assertIn(pc3, grouped["f1"])

    def test_productcomponent_model_standard_notice_property(self):
        license_expression = "{} AND {}".format(self.license1.key, self.license2.key)
        pc1 = ProductComponent.objects.create(
            product=self.product1,
            name="p1",
            dataspace=self.dataspace,
            license_expression=license_expression,
        )
        self.assertEqual("", pc1.standard_notice)

        self.license1.standard_notice = "Standard notice for License 1"
        self.license1.save()
        pc1 = ProductComponent.objects.get(pk=pc1.pk)
        self.assertEqual(self.license1.standard_notice, pc1.standard_notice)

        self.license2.standard_notice = "Standard notice for License 2"
        self.license2.save()
        pc1 = ProductComponent.objects.get(pk=pc1.pk)
        self.assertEqual(
            pc1.standard_notice,
            "{}\n\n{}".format(self.license1.standard_notice, self.license2.standard_notice),
        )

    def test_productcomponent_model_compliance_table_class(self):
        component1 = Component.objects.create(name="c1", dataspace=self.dataspace)
        pc1 = ProductComponent.objects.create(
            product=self.product1,
            component=component1,
            dataspace=self.dataspace,
        )

        self.assertIsNone(pc1.inventory_item_compliance_alert)
        self.assertIsNone(pc1.compliance_table_class())

        component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            compliance_alert=UsagePolicy.Compliance.ERROR,
            dataspace=self.dataspace,
        )
        component1.usage_policy = component_policy
        component1.save()

        pc1 = ProductComponent.objects.get(pk=pc1.pk)
        self.assertEqual("error", pc1.inventory_item_compliance_alert)
        self.assertEqual("table-danger", pc1.compliance_table_class())

    def test_productcomponent_model_get_status_from_item_policy(self):
        component1 = Component.objects.create(name="c1", dataspace=self.dataspace)
        pc1 = ProductComponent.objects.create(
            product=self.product1,
            component=component1,
            dataspace=self.dataspace,
        )
        self.assertIsNone(pc1.get_status_from_item_policy())

        component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.dataspace,
        )
        component1.usage_policy = component_policy
        component1.save()
        self.assertIsNone(pc1.get_status_from_item_policy())

        status1 = ProductRelationStatus.objects.create(
            label="S1", text="Status1", dataspace=self.dataspace
        )
        component_policy.associated_product_relation_status = status1
        component_policy.save()
        self.assertEqual(status1, pc1.get_status_from_item_policy())

    def test_productcomponent_model_set_review_status_from_policy(self):
        status_from_policy = ProductRelationStatus.objects.create(
            label="S1", text="Status1", dataspace=self.dataspace
        )
        status2 = ProductRelationStatus.objects.create(
            label="S2", text="Status2", dataspace=self.dataspace
        )
        component1 = Component.objects.create(name="c1", dataspace=self.dataspace)
        pc1 = ProductComponent.objects.create(
            product=self.product1,
            component=component1,
            dataspace=self.dataspace,
        )
        pc1.set_review_status_from_policy()
        self.assertIsNone(pc1.review_status)

        component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            associated_product_relation_status=status_from_policy,
            dataspace=self.dataspace,
        )
        component1.usage_policy = component_policy
        component1.save()
        pc1.set_review_status_from_policy()
        # Status is set from the policy since not already set on instance
        self.assertEqual(status_from_policy, pc1.review_status)

        pc1.review_status = status2
        pc1.set_review_status_from_policy()
        # Status is NOT set from policy has value already set
        self.assertEqual(status2, pc1.review_status)

        status2.default_on_addition = True
        status2.save()
        pc1.set_review_status_from_policy()
        # Status is set from the policy as existing one if the default
        self.assertEqual(status_from_policy, pc1.review_status)

    def test_productcomponent_model_is_custom_component(self):
        pc1 = ProductComponent.objects.create(
            product=self.product1, name="p1", dataspace=self.dataspace
        )
        self.assertTrue(pc1.is_custom_component)

        component1 = Component.objects.create(name="c1", dataspace=self.dataspace)
        pc1.component = component1
        pc1.save()
        self.assertFalse(pc1.is_custom_component)

    def test_product_relationship_queryset_vulnerable(self):
        pp1 = make_product_package(self.product1)
        product_package_qs = ProductPackage.objects.vulnerable()
        self.assertEqual(0, product_package_qs.count())

        pp1.raw_update(weighted_risk_score=5.0)
        product_package_qs = ProductPackage.objects.vulnerable()
        self.assertEqual(1, product_package_qs.count())
        self.assertIn(pp1, product_package_qs)

    def test_product_relationship_queryset_annotate_weighted_risk_score(self):
        purpose1 = make_product_item_purpose(self.dataspace, exposure_factor=0.5)
        package1 = make_package(self.dataspace, risk_score=4.0)
        make_product_package(self.product1, package=package1, purpose=purpose1)

        product_package_qs = ProductPackage.objects.annotate_weighted_risk_score()
        self.assertEqual(0.5, product_package_qs[0].exposure_factor)
        self.assertEqual(4.0, product_package_qs[0].risk_score)
        self.assertEqual(2.0, product_package_qs[0].computed_weighted_risk_score)

    def test_product_relationship_queryset_update_weighted_risk_score(self):
        purpose1 = make_product_item_purpose(self.dataspace)

        # 1. package.risk_score = None, purpose = None
        package1 = make_package(self.dataspace)
        pp1 = make_product_package(self.product1, package=package1)
        updated_count = ProductPackage.objects.update_weighted_risk_score()
        self.assertEqual(1, updated_count)
        pp1.refresh_from_db()
        self.assertIsNone(pp1.weighted_risk_score)

        # 2. package.risk_score = 4.0, purpose.exposure_factor = None
        package1.raw_update(risk_score=4.0)
        pp1.raw_update(purpose=purpose1)
        updated_count = ProductPackage.objects.update_weighted_risk_score()
        self.assertEqual(1, updated_count)
        pp1.refresh_from_db()
        self.assertEqual(4.0, pp1.weighted_risk_score)

        # 3. package.risk_score = 4.0, purpose.exposure_factor = 0.5
        purpose1.raw_update(exposure_factor=0.5)
        updated_count = ProductPackage.objects.update_weighted_risk_score()
        self.assertEqual(1, updated_count)
        pp1.refresh_from_db()
        self.assertEqual(2.0, pp1.weighted_risk_score)

        # 4. package.risk_score = None, purpose.exposure_factor = 0.5
        package1.raw_update(risk_score=None)
        updated_count = ProductPackage.objects.update_weighted_risk_score()
        self.assertEqual(1, updated_count)
        pp1.refresh_from_db()
        self.assertIsNone(pp1.weighted_risk_score)

    def test_productrelation_model_related_component_or_package_property(self):
        component1 = Component.objects.create(name="c1", dataspace=self.dataspace)
        pc1 = ProductComponent.objects.create(
            product=self.product1, component=component1, dataspace=self.dataspace
        )
        self.assertEqual(component1, pc1.related_component_or_package)

        package1 = Package.objects.create(filename="package1", dataspace=self.dataspace)
        pp1 = ProductPackage.objects.create(
            product=self.product1, package=package1, dataspace=self.dataspace
        )
        self.assertEqual(package1, pp1.related_component_or_package)

    def test_codebaseresource_model_str(self):
        self.assertEqual("/path1/", self.codebase_resource1.__str__())

    def test_codebaseresource_model_clean(self):
        product2 = Product.objects.create(name="Product2", dataspace=self.dataspace)
        component1 = Component.objects.create(name="p1", dataspace=self.dataspace)
        pc1 = ProductComponent.objects.create(
            product=product2, component=component1, dataspace=self.dataspace
        )

        self.codebase_resource1.product_component = pc1
        with self.assertRaises(ValidationError) as cm:
            self.codebase_resource1.clean()
        self.assertEqual(["p1 is not available on Product1."], cm.exception.messages)

        package1 = Package.objects.create(filename="package1", dataspace=self.dataspace)
        pp1 = ProductPackage.objects.create(
            product=product2, package=package1, dataspace=self.dataspace
        )

        self.codebase_resource1.product_component = None
        self.codebase_resource1.product_package = pp1
        with self.assertRaises(ValidationError) as cm:
            self.codebase_resource1.clean()
        self.assertEqual(["package1 is not available on Product1."], cm.exception.messages)

    def test_codebaseresource_model_deployed_from_paths_property(self):
        CodebaseResourceUsage.objects.create(
            deployed_from=self.codebase_resource1,
            deployed_to=self.codebase_resource2,
            dataspace=self.dataspace,
        )
        self.assertEqual([], list(self.codebase_resource1.deployed_from_paths))
        self.assertEqual(
            [self.codebase_resource1.path], list(self.codebase_resource2.deployed_from_paths)
        )

    def test_codebaseresource_model_deployed_to_paths_property(self):
        CodebaseResourceUsage.objects.create(
            deployed_from=self.codebase_resource1,
            deployed_to=self.codebase_resource2,
            dataspace=self.dataspace,
        )
        self.assertEqual(
            [self.codebase_resource2.path], list(self.codebase_resource1.deployed_to_paths)
        )
        self.assertEqual([], list(self.codebase_resource2.deployed_to_paths))

    def test_codebaseresourceusage_model_str(self):
        resource_usage = CodebaseResourceUsage.objects.create(
            deployed_from=self.codebase_resource1,
            deployed_to=self.codebase_resource2,
            dataspace=self.dataspace,
        )
        self.assertEqual("/path1/ -> /path2/", resource_usage.__str__())

    def test_codebaseresourceusage_model_clean(self):
        resource_usage = CodebaseResourceUsage(
            deployed_from=self.codebase_resource1,
            deployed_to=self.codebase_resource1,
            dataspace=self.dataspace,
        )

        with self.assertRaises(ValidationError) as cm:
            resource_usage.clean()
        self.assertEqual(["A codebase resource cannot deploy to itself."], cm.exception.messages)

    def test_codebaseresourceusage_model_delete(self):
        resource_usage = CodebaseResourceUsage.objects.create(
            deployed_from=self.codebase_resource1,
            deployed_to=self.codebase_resource2,
            dataspace=self.dataspace,
        )

        with self.assertRaises(ProtectedError):
            self.codebase_resource2.delete()

        self.codebase_resource1.delete()
        self.assertFalse(CodebaseResourceUsage.objects.filter(pk=resource_usage.pk).exists())

    def test_product_model_get_about_files(self):
        package1 = Package.objects.create(filename="package1", dataspace=self.dataspace)
        component1 = Component.objects.create(name="c1", dataspace=self.dataspace)
        ComponentAssignedPackage.objects.create(
            component=component1, package=package1, dataspace=self.dataspace
        )
        ProductComponent.objects.create(
            product=self.product1, component=component1, dataspace=self.dataspace
        )
        package2 = Package.objects.create(filename="package2", dataspace=self.dataspace)
        ProductPackage.objects.create(
            product=self.product1, package=package2, dataspace=self.dataspace
        )

        self.assertEqual(2, self.product1.all_packages.count())
        self.assertIn(package1, self.product1.all_packages)
        self.assertIn(package2, self.product1.all_packages)

        expected = [
            ("package1.ABOUT", "about_resource: package1\nname: c1\n"),
            ("package2.ABOUT", "about_resource: package2\n"),
        ]
        self.assertEqual(expected, self.product1.get_about_files())

    def test_product_portfolio_product_inventory_item_model(self):
        component1 = Component.objects.create(name="c1", dataspace=self.dataspace)
        ProductComponent.objects.create(
            product=self.product1, component=component1, dataspace=self.dataspace
        )
        package1 = Package.objects.create(filename="package1", dataspace=self.dataspace)
        ProductPackage.objects.create(
            product=self.product1, package=package1, dataspace=self.dataspace
        )

        self.assertEqual(2, ProductInventoryItem.objects.all().count())
        item = ProductInventoryItem.objects.get(item="package1")
        self.assertEqual(str(package1), item.item)
        self.assertEqual(package1.id, item.package_id)
        self.assertEqual(package1, item.package)
        self.assertEqual(self.product1, item.product)
        self.assertEqual(self.dataspace, item.dataspace)
        self.assertEqual("package", item.item_type)
        self.assertIsNone(item.component_id)

    def test_product_model_get_spdx_packages(self):
        component1 = Component.objects.create(name="c1", dataspace=self.dataspace)
        pc1 = ProductComponent.objects.create(
            product=self.product1, component=component1, dataspace=self.dataspace
        )

        package1 = Package.objects.create(filename="package1", dataspace=self.dataspace)
        package2 = Package.objects.create(filename="package2", dataspace=self.dataspace)
        pp1 = ProductPackage.objects.create(
            product=self.product1, package=package1, dataspace=self.dataspace
        )

        # ComponentAssignedPackage are not currently included in the SPDX output.
        ComponentAssignedPackage.objects.create(
            component=component1, package=package1, dataspace=self.dataspace
        )
        ComponentAssignedPackage.objects.create(
            component=component1, package=package2, dataspace=self.dataspace
        )

        # CustomComponent are not included in SPDX output.
        custom1 = ProductComponent.objects.create(
            product=self.product1, name="custom1", dataspace=self.dataspace
        )
        self.assertTrue(custom1.is_custom_component)

        self.assertEqual([pc1, pp1], self.product1.get_spdx_packages())

    def test_product_relationship_models_as_spdx(self):
        component1 = Component.objects.create(
            name="c1",
            license_expression=f"{self.license1.key} OR {self.license2.key}",
            declared_license_expression=f"{self.license1.key} OR {self.license2.key}",
            dataspace=self.dataspace,
        )
        pc1 = ProductComponent.objects.create(
            product=self.product1,
            component=component1,
            license_expression=self.license2.key,
            dataspace=self.dataspace,
        )
        expected = {
            "name": "c1",
            "SPDXID": f"SPDXRef-dejacode-component-{component1.uuid}",
            "downloadLocation": "NOASSERTION",
            "licenseConcluded": "LicenseRef-dejacode-l-2",
            "licenseDeclared": "LicenseRef-dejacode-l-1 OR LicenseRef-dejacode-l-2",
            "copyrightText": "NOASSERTION",
            "filesAnalyzed": False,
        }
        self.assertEqual(expected, pc1.as_spdx().as_dict())

        package1 = Package.objects.create(
            filename="package1",
            license_expression=f"{self.license1.key} OR {self.license2.key}",
            declared_license_expression=f"{self.license1.key} OR {self.license2.key}",
            dataspace=self.dataspace,
        )
        pp1 = ProductPackage.objects.create(
            product=self.product1,
            package=package1,
            license_expression=self.license1.key,
            dataspace=self.dataspace,
        )
        expected = {
            "name": "package1",
            "SPDXID": f"SPDXRef-dejacode-package-{package1.uuid}",
            "downloadLocation": "NOASSERTION",
            "licenseConcluded": "LicenseRef-dejacode-l-1",
            "licenseDeclared": "LicenseRef-dejacode-l-1 OR LicenseRef-dejacode-l-2",
            "copyrightText": "NOASSERTION",
            "filesAnalyzed": False,
            "packageFileName": "package1",
        }
        self.assertEqual(expected, pp1.as_spdx().as_dict())

    def test_product_model_as_cyclonedx(self):
        cyclonedx_data = self.product1.as_cyclonedx()
        self.assertEqual("application", cyclonedx_data.type)
        self.assertEqual(self.product1.name, cyclonedx_data.name)
        self.assertEqual(self.product1.version, cyclonedx_data.version)
        self.assertEqual(str(self.product1.uuid), str(cyclonedx_data.bom_ref))

    def test_product_portfolio_scancode_project_model_can_start_import(self):
        scancode_project = ScanCodeProject.objects.create(
            product=self.product1,
            dataspace=self.product1.dataspace,
            type=ScanCodeProject.ProjectType.LOAD_SBOMS,
        )
        self.assertTrue(scancode_project.can_start_import)

        scancode_project.status = ScanCodeProject.Status.IMPORT_STARTED
        self.assertFalse(scancode_project.can_start_import)
        scancode_project.status = ScanCodeProject.Status.SUCCESS
        self.assertFalse(scancode_project.can_start_import)
        scancode_project.status = ScanCodeProject.Status.FAILURE
        self.assertFalse(scancode_project.can_start_import)

    def test_product_dependency_model_save_validation(self):
        package1 = Package.objects.create(filename="package1", dataspace=self.dataspace)
        with self.assertRaises(ValidationError) as cm:
            ProductDependency.objects.create(
                product=self.product1,
                for_package=package1,
                resolved_to_package=package1,
                dataspace=self.dataspace,
            )
        self.assertEqual(
            ["The 'for_package' cannot be the same as 'resolved_to_package'."],
            cm.exception.messages,
        )

    def test_product_dependency_prackage_queryset_declared_dependencies_count(self):
        package1 = Package.objects.create(filename="package1", dataspace=self.dataspace)
        package2 = Package.objects.create(filename="package2", dataspace=self.dataspace)
        ProductDependency.objects.create(
            product=self.product1,
            for_package=package1,
            resolved_to_package=package2,
            dataspace=self.dataspace,
        )
        product2 = Product.objects.create(name="Product2", dataspace=self.dataspace)
        ProductDependency.objects.create(
            product=product2,
            for_package=package1,
            resolved_to_package=package2,
            dataspace=self.dataspace,
        )

        self.assertEqual(2, package1.declared_dependencies.count())
        self.assertEqual(0, package1.resolved_from_dependencies.count())
        self.assertEqual(0, package2.declared_dependencies.count())
        self.assertEqual(2, package2.resolved_from_dependencies.count())

        qs = Package.objects.declared_dependencies_count(product=self.product1)
        annotated_package1 = qs.filter(pk=package1.pk)[0]
        self.assertEqual(1, annotated_package1.declared_dependencies_count)
