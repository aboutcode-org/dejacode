#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import tempfile
import uuid
from pathlib import Path
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from guardian.shortcuts import assign_perm

from component_catalog.models import Component
from component_catalog.models import Package
from dje.models import Dataspace
from dje.tests import create_admin
from dje.tests import create_superuser
from license_library.models import License
from license_library.models import LicenseChoice
from organization.models import Owner
from product_portfolio.importers import CodebaseResourceImporter
from product_portfolio.importers import ImportFromScan
from product_portfolio.importers import ImportPackageFromScanCodeIO
from product_portfolio.importers import ProductComponentImporter
from product_portfolio.importers import ProductPackageImporter
from product_portfolio.models import CodebaseResource
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductItemPurpose
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductRelationStatus


class ProductRelationImporterTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)

        self.owner = Owner.objects.create(
            name="Apache Software Foundation", dataspace=self.dataspace
        )
        self.license1 = License.objects.create(
            key="l1", short_name="l1", name="l1", owner=self.owner, dataspace=self.dataspace
        )
        self.license2 = License.objects.create(
            key="l2", short_name="l2", name="l2", owner=self.owner, dataspace=self.dataspace
        )

        self.c1 = Component.objects.create(name="log4j", owner=self.owner, dataspace=self.dataspace)
        self.p1 = Product.objects.create(name="Product1", dataspace=self.dataspace)

        self.component_formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-product": "{}:{}".format(self.p1.name, self.p1.version),
            "form-0-component": "",
            "form-0-license_expression": "",
            "form-0-review_status": "",
            "form-0-purpose": "",
            "form-0-notes": "",
            "form-0-is_deployed": "",
            "form-0-is_modified": "",
            "form-0-extra_attribution_text": "",
            "form-0-package_paths": "",
            "form-0-name": "",
            "form-0-version": "",
            "form-0-owner": "",
            "form-0-copyright": "",
            "form-0-homepage_url": "",
            "form-0-download_url": "",
        }

        self.package_formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-product": "{}:{}".format(self.p1.name, self.p1.version),
            "form-0-package": "",
            "form-0-license_expression": "",
            "form-0-review_status": "",
            "form-0-purpose": "",
            "form-0-notes": "",
            "form-0-is_deployed": "",
            "form-0-is_modified": "",
            "form-0-extra_attribution_text": "",
            "form-0-package_paths": "",
        }

    def test_productcomponent_import_mandatory_columns(self):
        formset_data = self.component_formset_data.copy()
        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        self.assertEqual(ProductComponent.objects.latest("id"), importer.results["added"][0])

        del formset_data["form-0-product"]
        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        expected_errors = [{"product": ["This field is required."]}]
        self.assertEqual(expected_errors, importer.formset.errors)

    def test_productcomponent_import_product_syntax_issues(self):
        formset_data = self.component_formset_data.copy()
        formset_data["form-0-product"] = "{}".format(self.p1.name)
        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        expected = [{"product": ['Invalid format. Expected format: "<name>:<version>".']}]
        self.assertEqual(expected, importer.formset.errors)

    def test_productcomponent_import_product_matching_issues(self):
        formset_data = self.component_formset_data.copy()
        formset_data["form-0-product"] = "not:existing"
        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        expected = [{"product": ["Could not find the product."]}]
        self.assertEqual(expected, importer.formset.errors)

    def test_productcomponent_import_product_matching_proper(self):
        formset_data = self.component_formset_data.copy()
        self.p1.name = "name : with :: colon"
        self.p1.version = "1.0"
        self.p1.save()
        formset_data["form-0-product"] = "{}:{}".format(self.p1.name, self.p1.version)
        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

    def test_productcomponent_import_product_column_secured(self):
        formset_data = self.component_formset_data.copy()
        importer = ProductComponentImporter(self.admin_user, formset_data=formset_data)
        expected = [{"product": ["Could not find the product."]}]
        self.assertEqual(expected, importer.formset.errors)

        assign_perm("change_product", self.admin_user, self.p1)
        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))

    def test_productcomponent_import_duplicated_empty_component_row_possible(self):
        formset_data = self.component_formset_data.copy()
        formset_data["form-TOTAL_FORMS"] = "2"
        formset_data["form-1-product"] = formset_data["form-0-product"]
        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertEqual(2, len(importer.results["added"]))

    def test_productcomponent_import_duplicated_component_row_error(self):
        formset_data = self.component_formset_data.copy()
        formset_data["form-TOTAL_FORMS"] = "2"
        formset_data["form-1-product"] = formset_data["form-0-product"]
        formset_data["form-0-component"] = "{}:{}".format(self.c1.name, self.c1.version)
        formset_data["form-1-component"] = "{}:{}".format(self.c1.name, self.c1.version)
        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        self.assertTrue(
            "Please correct the duplicate data for product and component, which must be unique."
            in importer.formset.non_form_errors()
        )
        # List of errors, skipping the empty dicts
        errors = [error for error in importer.formset.errors if error]
        self.assertEqual(1, len(errors))

    def test_productcomponent_import_license_expression(self):
        formset_data = self.component_formset_data.copy()
        expression = "{} AND {}".format(self.license1.key, self.license2.key)
        self.c1.license_expression = expression
        self.c1.save()

        formset_data["form-0-component"] = "{}:{}".format(self.c1.name, self.c1.version)
        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()

        # license_expression empty, the expression is taken from the component
        pc = ProductComponent.objects.latest("id")
        self.assertEqual(expression, self.c1.license_expression)
        self.assertEqual(pc.component.license_expression, pc.license_expression)

        # Provided, the expression is validated against the component one
        pc.delete()
        formset_data["form-0-license_expression"] = "wrong"
        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {"license_expression": ["Unknown license key(s): wrong<br>Available licenses: l1, l2"]}
        ]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-license_expression"] = str(self.license1.key)
        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        pc = ProductComponent.objects.latest("id")
        self.assertEqual(str(self.license1.key), pc.license_expression)

        # No component, expression is validated against the licenses in the current dataspace
        pc.delete()
        formset_data["form-0-component"] = ""
        formset_data["form-0-license_expression"] = "wrong"
        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [{"license_expression": ["Unknown license key(s): wrong"]}]
        self.assertEqual(expected, importer.formset.errors)

    def test_productcomponent_import_is_deployed_field(self):
        formset_data = self.component_formset_data.copy()
        for value in ["on", 1, "True", "true", "1", "Y", "y", "Yes", "yes", "T", "t"]:
            formset_data["form-0-is_deployed"] = value
            importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
            self.assertTrue(importer.formset.is_valid())
            importer.save_all()
            self.assertTrue(ProductComponent.objects.latest("id").is_deployed)

        for value in ["False", "false", "0", "F", "f", "N", "n", "No", "no"]:
            formset_data["form-0-is_deployed"] = value
            importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
            self.assertTrue(importer.formset.is_valid())
            importer.save_all()
            self.assertFalse(ProductComponent.objects.latest("id").is_deployed)

    def test_productcomponent_import_is_deployed_is_modified_default_value(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"product,component\n,")
            f.flush()

        importer = ProductComponentImporter(self.super_user, f.name)
        self.assertTrue(importer.formset.is_valid())
        self.assertTrue(importer.formset.forms[0].instance.is_deployed)
        self.assertFalse(importer.formset.forms[0].instance.is_modified)

    def test_productcomponent_import_save_all(self):
        formset_data = self.component_formset_data.copy()
        review_status = ProductRelationStatus.objects.create(label="A", dataspace=self.dataspace)
        purpose = ProductItemPurpose.objects.create(
            label="Core", text="t", dataspace=self.dataspace
        )

        formset_data["form-0-component"] = f"{self.c1.name}:{self.c1.version}"
        formset_data["form-0-review_status"] = review_status.label
        formset_data["form-0-purpose"] = purpose.label
        formset_data["form-0-notes"] = "notes"
        formset_data["form-0-is_deployed"] = ""
        formset_data["form-0-is_modified"] = "on"
        formset_data["form-0-name"] = "c_name"
        formset_data["form-0-version"] = "c_version"
        formset_data["form-0-owner"] = "c_owner"

        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))

        productcomponent = ProductComponent.objects.latest("id")
        self.assertEqual(self.c1, productcomponent.component)
        self.assertEqual(purpose, productcomponent.purpose)
        self.assertEqual(review_status, productcomponent.review_status)
        self.assertEqual("notes", productcomponent.notes)
        self.assertEqual(False, productcomponent.is_deployed)
        self.assertEqual(True, productcomponent.is_modified)
        self.assertEqual("c_name", productcomponent.name)
        self.assertEqual("c_version", productcomponent.version)
        self.assertEqual("c_owner", productcomponent.owner)

    def test_productcomponent_import_license_expression_from_choice(self):
        formset_data = self.component_formset_data.copy()
        self.c1.license_expression = self.license1.key
        self.c1.save()
        formset_data["form-0-component"] = "{}:{}".format(self.c1.name, self.c1.version)
        formset_data["form-0-license_expression"] = self.license2.key

        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        expected = [
            {"license_expression": ["Unknown license key(s): l2<br>Available licenses: l1"]}
        ]
        self.assertEqual(expected, importer.formset.errors)

        LicenseChoice.objects.create(
            from_expression=self.license1.key,
            to_expression=self.license2.key,
            dataspace=self.dataspace,
        )

        importer = ProductComponentImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        productcomponent = ProductComponent.objects.latest("id")
        self.assertEqual(self.license2.key, productcomponent.license_expression)

    def test_productpackage_import_mandatory_columns(self):
        formset_data = self.package_formset_data.copy()

        formset_data["form-0-product"] = ""
        formset_data["form-0-package"] = ""
        importer = ProductPackageImporter(self.super_user, formset_data=formset_data)
        expected_errors = [
            {
                "package": ["This field is required."],
                "product": ["This field is required."],
            }
        ]
        self.assertEqual(expected_errors, importer.formset.errors)

        del formset_data["form-0-product"]
        del formset_data["form-0-package"]
        importer = ProductPackageImporter(self.super_user, formset_data=formset_data)
        expected_errors = [
            {
                "package": ["This field is required."],
                "product": ["This field is required."],
            }
        ]
        self.assertEqual(expected_errors, importer.formset.errors)

    def test_productpackage_import_non_existing_package(self):
        formset_data = self.package_formset_data.copy()

        formset_data["form-0-package"] = "non_existing"
        importer = ProductPackageImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [{"package": ["The following package does not exists: non_existing"]}]
        self.assertEqual(expected, importer.formset.errors)

    def test_productpackage_import_duplicated_package_multiple_objects_returned(self):
        formset_data = self.package_formset_data.copy()

        package1 = Package.objects.create(filename="package.zip", dataspace=self.dataspace)
        package2 = Package.objects.create(
            filename="package.zip", download_url="http://download.url", dataspace=self.dataspace
        )

        formset_data["form-0-package"] = package1.filename
        importer = ProductPackageImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())

        expected_errors = [{"package": ['Multiple packages with the same "package.zip" filename.']}]
        self.assertEqual(expected_errors, importer.formset.errors)

        formset_data["form-0-package"] = package2.uuid
        importer = ProductPackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        productpackage = ProductPackage.objects.latest("id")
        self.assertEqual(package2, productpackage.package)

    def test_productpackage_import_save_all(self):
        formset_data = self.package_formset_data.copy()

        review_status = ProductRelationStatus.objects.create(label="A", dataspace=self.dataspace)
        purpose = ProductItemPurpose.objects.create(
            label="Core", text="t", dataspace=self.dataspace
        )
        package1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace)

        formset_data["form-0-package"] = package1.filename
        formset_data["form-0-review_status"] = review_status.label
        formset_data["form-0-purpose"] = purpose.label
        formset_data["form-0-notes"] = "notes"
        formset_data["form-0-is_deployed"] = ""
        formset_data["form-0-is_modified"] = "on"

        importer = ProductPackageImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))

        productpackage = ProductPackage.objects.latest("id")
        self.assertEqual(package1, productpackage.package)
        self.assertEqual(purpose, productpackage.purpose)
        self.assertEqual(review_status, productpackage.review_status)
        self.assertEqual("notes", productpackage.notes)
        self.assertEqual(False, productpackage.is_deployed)
        self.assertEqual(True, productpackage.is_modified)


class CodebaseResourceImporterTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)

        self.owner = Owner.objects.create(
            name="Apache Software Foundation", dataspace=self.dataspace
        )

        self.c1 = Component.objects.create(name="log4j", owner=self.owner, dataspace=self.dataspace)
        self.package1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace)
        self.product1 = Product.objects.create(name="Product1", dataspace=self.dataspace)

        self.codebase_resource_formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-product": "{}:{}".format(self.product1.name, self.product1.version),
            "form-0-path": "/path/",
            "form-0-is_deployment_path": "",
            "form-0-product_component": "",
            "form-0-product_package": "",
            "form-0-additional_details": "",
            "form-0-admin_notes": "",
        }

    def test_codebaseresource_import_mandatory_columns(self):
        formset_data = self.codebase_resource_formset_data.copy()
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        self.assertEqual(CodebaseResource.objects.latest("id"), importer.results["added"][0])
        CodebaseResource.objects.all().delete()

        del formset_data["form-0-product"]
        del formset_data["form-0-path"]
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected_errors = [
            {
                "product": ["This field is required."],
                "path": ["This field is required."],
            }
        ]
        self.assertEqual(expected_errors, importer.formset.errors)

    def test_codebaseresource_import_product_syntax_issues(self):
        formset_data = self.codebase_resource_formset_data.copy()
        formset_data["form-0-product"] = "{}".format(self.product1.name)
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        expected = [{"product": ['Invalid format. Expected format: "<name>:<version>".']}]
        self.assertEqual(expected, importer.formset.errors)

    def test_codebaseresource_import_product_matching_issues(self):
        formset_data = self.codebase_resource_formset_data.copy()
        formset_data["form-0-product"] = "not:existing"
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        expected = [{"product": ["Could not find the product."]}]
        self.assertEqual(expected, importer.formset.errors)

    def test_codebaseresource_import_product_column_secured(self):
        formset_data = self.codebase_resource_formset_data.copy()
        importer = CodebaseResourceImporter(self.admin_user, formset_data=formset_data)
        expected = [{"product": ["Could not find the product."]}]
        self.assertEqual(expected, importer.formset.errors)

        assign_perm("change_product", self.admin_user, self.product1)
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))

    def test_codebaseresource_import_is_deployment_path_field(self):
        formset_data = self.codebase_resource_formset_data.copy()
        for idx, value in enumerate(
            ["on", 1, "True", "true", "1", "Y", "y", "Yes", "yes", "T", "t"]
        ):
            formset_data["form-0-is_deployment_path"] = value
            formset_data["form-0-path"] = idx
            importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
            self.assertTrue(importer.formset.is_valid())
            importer.save_all()
            self.assertTrue(CodebaseResource.objects.latest("id").is_deployment_path)

        for idx, value in enumerate(["False", "false", "0", "F", "f", "N", "n", "No", "no"]):
            formset_data["form-0-is_deployment_path"] = value
            formset_data["form-0-path"] = idx + 100
            importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
            self.assertTrue(importer.formset.is_valid())
            importer.save_all()
            self.assertFalse(CodebaseResource.objects.latest("id").is_deployment_path)

    def test_codebaseresource_import_additional_details_field(self):
        formset_data = self.codebase_resource_formset_data.copy()

        del formset_data["form-0-additional_details"]
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual({}, CodebaseResource.objects.latest("id").additional_details)
        CodebaseResource.objects.all().delete()

        formset_data["form-0-additional_details"] = None
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual({}, CodebaseResource.objects.latest("id").additional_details)
        CodebaseResource.objects.all().delete()

        formset_data["form-0-additional_details"] = ""
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual({}, CodebaseResource.objects.latest("id").additional_details)
        CodebaseResource.objects.all().delete()

        formset_data["form-0-additional_details"] = '{"key":}'
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [{"additional_details": ["Enter a valid JSON."]}]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-additional_details"] = '{"key": "value"}'
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        expected = {"key": "value"}
        self.assertEqual(expected, CodebaseResource.objects.latest("id").additional_details)

    def test_codebaseresource_import_path_field_unique(self):
        formset_data = self.codebase_resource_formset_data.copy()

        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        codebase_resource = CodebaseResource.objects.latest("id")
        self.assertEqual(formset_data["form-0-path"], codebase_resource.path)

        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        self.assertEqual(codebase_resource, importer.formset[0].instance)

    def test_codebaseresource_import_product_component(self):
        formset_data = self.codebase_resource_formset_data.copy()

        formset_data["form-0-product_component"] = "non_existing"
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [{"product_component": ['Invalid format. Expected format: "<name>:<version>".']}]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-product_component"] = "name:version"
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {
                "product_component": [
                    f'The component "name:version" is not available on {self.product1}'
                ]
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-product_component"] = f"{self.c1.name}:{self.c1.version}"
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {"product_component": [f'The component "log4j:" is not available on {self.product1}']}
        ]
        self.assertEqual(expected, importer.formset.errors)

        product_component = ProductComponent.objects.create(
            product=self.product1, component=self.c1, dataspace=self.dataspace
        )
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertTrue(importer.formset.is_valid())
        self.assertEqual(product_component, CodebaseResource.objects.latest("id").product_component)

    def test_codebaseresource_import_custom_product_component(self):
        formset_data = self.codebase_resource_formset_data.copy()

        product_component = ProductComponent.objects.create(
            name="custom",
            version="1.0",
            product=self.product1,
            dataspace=self.dataspace,
        )
        formset_data[
            "form-0-product_component"
        ] = f"{product_component.name}:{product_component.version}"
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertTrue(importer.formset.is_valid())
        self.assertEqual(product_component, CodebaseResource.objects.latest("id").product_component)

        product_component.component = self.c1
        product_component.name = self.c1.name
        product_component.version = self.c1.version
        product_component.save()
        formset_data[
            "form-0-product_component"
        ] = f"{product_component.name}:{product_component.version}"
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertTrue(importer.formset.is_valid())
        self.assertEqual(product_component, CodebaseResource.objects.latest("id").product_component)

    def test_codebaseresource_import_product_package(self):
        formset_data = self.codebase_resource_formset_data.copy()

        formset_data["form-0-product_package"] = "non_existing"
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {
                "product_package": [
                    f'The package "non_existing" is not available on {self.product1}'
                ],
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-product_package"] = self.package1.filename
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {
                "product_package": [
                    f'The package "{self.package1}" is not available on {self.product1}'
                ],
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

        product_package = ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertTrue(importer.formset.is_valid())
        self.assertEqual(product_package, CodebaseResource.objects.latest("id").product_package)

    def test_codebaseresource_import_codebase_resource_usage(self):
        formset_data = self.codebase_resource_formset_data.copy()

        formset_data["form-0-deployed_to"] = "/path_in_input/, /path_in_db/, "
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {
                "deployed_to": [
                    "Path /path_in_input/ is not available.",
                    "Path /path_in_db/ is not available.",
                ]
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

        CodebaseResource.objects.create(
            path="/path_in_db/", product=self.product1, dataspace=self.dataspace
        )
        formset_data["form-TOTAL_FORMS"] = 2
        formset_data["form-1-product"] = formset_data["form-0-product"]
        formset_data["form-1-path"] = "/path_in_input/"
        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        expected = ["/path_in_input/", "/path_in_db/"]
        self.assertEqual(expected, importer.formset[0].deployed_to_paths)

        importer.save_all()
        codebase_resource0 = CodebaseResource.objects.get(path=formset_data["form-0-path"])
        self.assertEqual(
            ["/path_in_db/", "/path_in_input/"], list(codebase_resource0.deployed_to_paths)
        )
        self.assertEqual([], list(codebase_resource0.deployed_from_paths))
        codebase_resource1 = CodebaseResource.objects.get(path=formset_data["form-1-path"])
        self.assertEqual([], list(codebase_resource1.deployed_to_paths))
        self.assertEqual(["/path/"], list(codebase_resource1.deployed_from_paths))

    def test_codebaseresource_import_save_all(self):
        formset_data = self.codebase_resource_formset_data.copy()

        product_component = ProductComponent.objects.create(
            product=self.product1, component=self.c1, dataspace=self.dataspace
        )
        product_package = ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )

        formset_data["form-0-is_deployment_path"] = True
        formset_data["form-0-product_component"] = f"{self.c1.name}:{self.c1.version}"
        formset_data["form-0-product_package"] = f"{self.package1.filename}"
        formset_data["form-0-additional_details"] = {"key": "value"}
        formset_data["form-0-admin_notes"] = "admin_notes"

        importer = CodebaseResourceImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))

        codebaseresource = CodebaseResource.objects.latest("id")
        self.assertEqual(self.product1, codebaseresource.product)
        self.assertEqual("/path/", codebaseresource.path)
        self.assertEqual(True, codebaseresource.is_deployment_path)
        self.assertEqual(product_component, codebaseresource.product_component)
        self.assertEqual(product_package, codebaseresource.product_package)
        self.assertEqual({"key": "value"}, codebaseresource.additional_details)
        self.assertEqual("admin_notes", codebaseresource.admin_notes)

    def test_codebaseresource_import_proper_results_view(self):
        self.client.login(username=self.super_user.username, password="secret")
        url = reverse("admin:product_portfolio_codebaseresource_import")
        data = self.codebase_resource_formset_data.copy()
        response = self.client.post(url, data=data)
        self.assertContains(response, "<strong>1 Added Codebase Resources:</strong>")


class ProductImportFromScanTestCase(TestCase):
    testfiles_path = Path(__file__).parent / "testfiles"

    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.product1 = Product.objects.create(name="P1", version="1.0", dataspace=self.dataspace)
        repository_download_url = "https://registry.npmjs.org/test-package/-/test-package-0.0.1.tgz"
        self.expected_package_data = {
            "package_url": "pkg:npm/test-package@0.0.1",
            "license_expression": "apache-2.0",
            "copyright": "Copyright",
            "filename": "test-package-0.0.1.tgz",
            "download_url": "https://registry.npmjs.org/test-package/-/test-package-0.0.1.tgz",
            "primary_language": "JavaScript",
            "repository_homepage_url": "https://www.npmjs.com/package/test-package",
            "repository_download_url": repository_download_url,
        }

    def test_product_portfolio_product_import_from_scan_proper(self):
        scan_input_location = self.testfiles_path / "import_from_scan.json"
        importer = ImportFromScan(self.product1, self.super_user, scan_input_location)
        warnings, created_counts = importer.save()
        self.assertEqual([], warnings)
        self.assertEqual(
            {"Packages": 1, "Product Packages": 1, "Codebase Resources": 3}, created_counts
        )

        self.assertEqual(0, self.product1.productcomponents.count())
        self.assertEqual(0, self.product1.components.count())
        self.assertEqual(1, self.product1.productpackages.count())
        self.assertEqual(1, self.product1.packages.count())
        self.assertEqual(3, self.product1.codebaseresources.count())

        package = self.product1.packages.last()
        self.assertEqual(self.super_user, package.created_by)
        for field_name, expected_value in self.expected_package_data.items():
            self.assertEqual(expected_value, getattr(package, field_name))

        self.assertEqual(self.super_user, self.product1.productpackages.last().created_by)
        self.assertEqual(self.super_user, self.product1.codebaseresources.last().created_by)

        resource = self.product1.codebaseresources.get(path="component-package/package/src1")
        expected_details = {
            "md5": "2c83032298cf2cc80238d47dcd8260f0",
            "date": "2023-02-16",
            "sha1": "dab23f227b065e0dc81b043a71ef7c21a51a417c",
            "size": 56,
            "file_type": "ASCII text",
            "mime_type": "text/plain",
            "import_source": "import_from_scan.json",
            "detected_license_expression": "apache-2.0",
            "detected_license_expression_spdx": "Apache-2.0",
        }
        self.assertDictEqual(expected_details, resource.additional_details)

        # Make sure we do not create duplicates on re-importing
        importer = ImportFromScan(self.product1, self.super_user, scan_input_location)
        warnings, created_counts = importer.save()
        self.assertEqual([], warnings)
        self.assertEqual({}, created_counts)

    def test_product_portfolio_product_import_from_scan_scanpipe_results(self):
        scan_input_location = self.testfiles_path / "scancodeio_scan_codebase_results.json"
        importer = ImportFromScan(self.product1, self.super_user, scan_input_location)
        warnings, created_counts = importer.save()
        self.assertEqual([], warnings)
        self.assertEqual(
            {"Packages": 1, "Product Packages": 1, "Codebase Resources": 3}, created_counts
        )

        self.assertEqual(0, self.product1.productcomponents.count())
        self.assertEqual(0, self.product1.components.count())
        self.assertEqual(1, self.product1.productpackages.count())
        self.assertEqual(1, self.product1.packages.count())
        self.assertEqual(3, self.product1.codebaseresources.count())

        package = self.product1.packages.last()
        self.assertEqual(self.super_user, package.created_by)
        for field_name, expected_value in self.expected_package_data.items():
            self.assertEqual(expected_value, getattr(package, field_name))

        self.assertEqual(self.super_user, self.product1.productpackages.last().created_by)
        self.assertEqual(self.super_user, self.product1.codebaseresources.last().created_by)

        resource = self.product1.codebaseresources.get(path="package.tar.xz-extract/package/src1")
        expected_details = {
            "md5": "2c83032298cf2cc80238d47dcd8260f0",
            "sha1": "dab23f227b065e0dc81b043a71ef7c21a51a417c",
            "size": 56,
            "file_type": "ASCII text",
            "mime_type": "text/plain",
            "import_source": "scancodeio_scan_codebase_results.json",
        }
        self.assertDictEqual(expected_details, resource.additional_details)

        # Make sure we do not create duplicates on re-importing
        importer = ImportFromScan(self.product1, self.super_user, scan_input_location)
        warnings, created_counts = importer.save()
        self.assertEqual([], warnings)
        self.assertEqual({}, created_counts)

    def test_product_portfolio_product_import_from_scan_package_without_purl(self):
        scan_input_location = self.testfiles_path / "package_without_purl.json"
        importer = ImportFromScan(self.product1, self.super_user, scan_input_location)
        warnings, created_counts = importer.save()
        self.assertEqual([], warnings)
        self.assertEqual({}, created_counts)

    def test_product_portfolio_product_import_from_scan_duplicated_purl_are_imported_once(self):
        scan_input_location = self.testfiles_path / "duplicated_purl.json"
        importer = ImportFromScan(self.product1, self.super_user, scan_input_location)
        warnings, created_counts = importer.save()

        self.assertEqual([], warnings)
        expected = {"Codebase Resources": 2, "Packages": 1, "Product Packages": 1}
        self.assertEqual(expected, created_counts)
        self.assertEqual(1, self.product1.packages.count())
        self.assertEqual(1, self.product1.productpackages.count())
        self.assertEqual(2, self.product1.codebaseresources.count())

        package = self.product1.packages.get()
        self.assertEqual(self.super_user, package.created_by)
        self.assertEqual("", package.filename)
        self.assertEqual("", package.download_url)
        self.assertEqual("Python", package.primary_language)
        self.assertEqual("Python 2 and 3 compatibility utilities", package.description)
        self.assertEqual("mit", package.license_expression)
        self.assertEqual("https://github.com/benjaminp/six", package.homepage_url)

        codebase_resources = self.product1.codebaseresources.values_list("path", flat=True)
        self.assertIn("artifacts/six-1.13.0/setup.py", codebase_resources)
        self.assertIn("artifacts/six-1.14.0/setup.py", codebase_resources)

    def test_product_portfolio_product_import_from_scan_input_file_errors(self):
        expected = "The file content is not proper JSON."
        scan_input_location = Path(__file__)
        importer = ImportFromScan(self.product1, self.super_user, scan_input_location)
        with self.assertRaisesMessage(ValidationError, expected):
            importer.save()

        expected = "The uploaded file is not a proper ScanCode output results."
        scan_input_location = self.testfiles_path / "json_but_not_scan_results.json"
        importer = ImportFromScan(self.product1, self.super_user, scan_input_location)
        with self.assertRaisesMessage(ValidationError, expected):
            importer.save()

        options_str = "--copyright --package"
        expected = f"The Scan run is missing those required options: {options_str}"
        scan_input_location = self.testfiles_path / "missing_scancode_options.json"
        importer = ImportFromScan(self.product1, self.super_user, scan_input_location)
        with self.assertRaisesMessage(ValidationError, expected):
            importer.save()

        expected = "This ScanPipe output does not have results from a valid pipeline."
        scan_input_location = self.testfiles_path / "missing_correct_pipeline.json"
        importer = ImportFromScan(self.product1, self.super_user, scan_input_location)
        with self.assertRaisesMessage(ValidationError, expected):
            importer.save()

    def test_product_portfolio_product_import_from_scan_input_data_validation_errors(self):
        expected = (
            "pkg:pypi/six?uuid=bbe2794a-d81a-4728-a66d-5700a3735977 license_expression: "
            "Ensure this value has at most 1024 characters (it has 3466)."
        )
        scan_input_location = self.testfiles_path / "package_data_validation_error.json"
        importer = ImportFromScan(
            self.product1, self.super_user, scan_input_location, stop_on_error=True
        )
        with self.assertRaisesMessage(ValidationError, expected):
            importer.save()

        importer = ImportFromScan(self.product1, self.super_user, scan_input_location)
        warnings, created_counts = importer.save()
        expected = [
            "pkg:pypi/six?uuid=bbe2794a-d81a-4728-a66d-5700a3735977 license_expression: "
            "Ensure this value has at most 1024 characters (it has 3466).",
            "pkg:pypi/six?uuid=bd0ba183-ace6-489e-8f74-44cc11da93c8 download_url: "
            "Enter a valid URI.",
            "pkg:pypi/six?uuid=bd0ba183-ace6-489e-8f74-44cc11da93c8 repository_download_url: "
            "Enter a valid URL.",
        ]
        self.assertEqual(expected, warnings)
        self.assertEqual({"Packages": 1, "Product Packages": 1}, created_counts)

    def test_product_portfolio_product_import_from_scan_view_base(self):
        self.client.login(username=self.super_user.username, password="secret")
        scan_input_location = self.testfiles_path / "import_from_scan.json"

        import_scan_url = self.product1.get_import_from_scan_url()
        with scan_input_location.open() as f:
            self.client.post(import_scan_url, {"upload_file": f})

        self.assertEqual(0, self.product1.productcomponents.count())
        self.assertEqual(0, self.product1.components.count())
        self.assertEqual(1, self.product1.packages.count())
        # Form `create_codebase_resources` option not provided
        self.assertEqual(0, self.product1.codebaseresources.count())

    def test_product_portfolio_product_import_from_scan_view_errors(self):
        self.client.login(username=self.super_user.username, password="secret")
        scan_input_location = self.testfiles_path / "package_data_validation_error.json"

        import_scan_url = self.product1.get_import_from_scan_url()
        with scan_input_location.open() as f:
            response = self.client.post(import_scan_url, {"upload_file": f}, follow=True)

        expected1 = (
            "pkg:pypi/six?uuid=bbe2794a-d81a-4728-a66d-5700a3735977 license_expression: "
            "Ensure this value has at most 1024 characters (it has 3466)."
        )
        expected2 = (
            "pkg:pypi/six?uuid=bd0ba183-ace6-489e-8f74-44cc11da93c8 download_url: "
            "Enter a valid URI."
        )
        expected3 = (
            "pkg:pypi/six?uuid=bd0ba183-ace6-489e-8f74-44cc11da93c8 repository_download_url: "
            "Enter a valid URL."
        )
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)

        expected4 = "<strong>Success:</strong>"
        expected5 = "Imported from Scan:<br> &bull; 1 Packages<br> &bull; 1 Product Packages"
        self.assertContains(response, expected4, html=True)
        self.assertContains(response, expected5)

        self.assertEqual(1, self.product1.packages.count())
        self.assertEqual(1, self.product1.productpackages.count())
        self.assertEqual(0, self.product1.codebaseresources.count())

    def test_product_portfolio_product_import_from_scan_view_empty_packages(self):
        self.client.login(username=self.super_user.username, password="secret")
        scan_input_location = self.testfiles_path / "empty_packages.json"
        import_scan_url = self.product1.get_import_from_scan_url()
        with scan_input_location.open() as f:
            response = self.client.post(import_scan_url, {"upload_file": f}, follow=True)

        expected1 = "<strong>Error:</strong>"
        expected2 = "No detected Packages to import from the provided scan results."
        expected3 = "&quot;packages&quot; is empty in the uploaded json file."
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_project_packages")
    def test_product_portfolio_import_packages_from_scancodeio_importer(self, mock_fetch_packages):
        purl = "pkg:maven/org.apache.activemq/activemq-camel@5.11.0"
        dependencies = [
            {
                "purl": "pkg:maven/org.apache.camel/camel-catalog",
                "scope": "compile",
                "is_runtime": True,
                "is_optional": False,
                "is_resolved": False,
                "extracted_requirement": "2.18.1",
            }
        ]
        mock_fetch_packages.return_value = [
            {
                "type": "maven",
                "namespace": "org.apache.activemq",
                "name": "activemq-camel",
                "version": "5.11.0",
                "primary_language": "Java",
                "purl": purl,
                "declared_license_expression": "bsd-new",
                "dependencies": dependencies,
            }
        ]

        importer = ImportPackageFromScanCodeIO(
            user=self.super_user,
            project_uuid=uuid.uuid4(),
            product=self.product1,
        )
        created, existing, errors = importer.save()
        self.assertEqual(1, len(created))
        created_package = created[0]
        self.assertEqual(purl, created_package.package_url)
        self.assertEqual("bsd-new", created_package.license_expression)
        self.assertEqual(dependencies, created_package.dependencies)
        self.assertEqual([], existing)
        self.assertEqual([purl], [package.package_url for package in self.product1.packages.all()])
        self.assertEqual([], errors)

        importer = ImportPackageFromScanCodeIO(
            user=self.super_user,
            project_uuid=uuid.uuid4(),
            product=self.product1,
        )
        created, existing, errors = importer.save()
        self.assertEqual([], created)
        self.assertEqual([purl], [package.package_url for package in existing])
        self.assertEqual([], errors)
