#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest.mock import patch

from django.test import TestCase

from component_catalog.tests import make_package
from dje.models import Dataspace
from dje.models import DataspaceConfiguration
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_package


class ProductSaveSignalTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    @patch("policy.signals.evaluate_product_rules_task.delay")
    def test_product_save_queues_task(self, mock_delay):
        product = make_product(self.dataspace)
        mock_delay.assert_called_with(product_uuid=product.uuid)

    @patch("policy.signals.evaluate_product_rules_task.delay")
    def test_product_update_queues_task(self, mock_delay):
        product = make_product(self.dataspace)
        mock_delay.reset_mock()
        product.save()
        mock_delay.assert_called_once_with(product_uuid=product.uuid)


class ProductPackageSignalTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    @patch("policy.signals.evaluate_product_rules_task.delay")
    def test_productpackage_save_queues_task(self, mock_delay):
        make_product_package(self.product)
        mock_delay.assert_called_with(product_uuid=self.product.uuid)

    @patch("policy.signals.evaluate_product_rules_task.delay")
    def test_productpackage_delete_queues_task(self, mock_delay):
        pp = make_product_package(self.product)
        mock_delay.reset_mock()
        pp.delete()
        mock_delay.assert_called_once_with(product_uuid=self.product.uuid)


class PackageSaveSignalTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.product = make_product(self.dataspace)

    @patch("policy.signals.evaluate_all_products_rules_task.delay")
    def test_package_create_does_not_queue_task(self, mock_delay):
        make_package(self.dataspace)
        mock_delay.assert_not_called()

    @patch("policy.signals.evaluate_all_products_rules_task.delay")
    def test_package_update_with_products_queues_task(self, mock_delay):
        package = make_package(self.dataspace)
        make_product_package(self.product, package=package)
        mock_delay.reset_mock()
        package.save()
        mock_delay.assert_called_once()
        called_uuids = mock_delay.call_args[1]["product_uuids"]
        self.assertIn(self.product.uuid, called_uuids)

    @patch("policy.signals.evaluate_all_products_rules_task.delay")
    def test_package_update_without_products_does_not_queue_task(self, mock_delay):
        package = make_package(self.dataspace)
        mock_delay.reset_mock()
        package.save()
        mock_delay.assert_not_called()


class DataspaceConfigurationSignalTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.config = DataspaceConfiguration.objects.create(dataspace=self.dataspace)
        self.product = make_product(self.dataspace)

    @patch("policy.signals.evaluate_all_products_rules_task.delay")
    def test_full_save_queues_task(self, mock_delay):
        self.config.save()
        mock_delay.assert_called_once()

    @patch("policy.signals.evaluate_all_products_rules_task.delay")
    def test_policy_rules_config_update_fields_queues_task(self, mock_delay):
        self.config.policy_rules_config = {"usage_policy_error": {"is_active": True}}
        self.config.save(update_fields=["policy_rules_config"])
        mock_delay.assert_called_once()
        called_uuids = mock_delay.call_args[1]["product_uuids"]
        self.assertIn(self.product.uuid, called_uuids)

    @patch("policy.signals.evaluate_all_products_rules_task.delay")
    def test_unrelated_update_fields_does_not_queue_task(self, mock_delay):
        self.config.save(update_fields=["scancodeio_url"])
        mock_delay.assert_not_called()

    @patch("policy.signals.evaluate_all_products_rules_task.delay")
    def test_no_products_in_dataspace_does_not_queue_task(self, mock_delay):
        empty_dataspace = Dataspace.objects.create(name="Empty")
        empty_config = DataspaceConfiguration.objects.create(dataspace=empty_dataspace)
        mock_delay.reset_mock()
        empty_config.save(update_fields=["policy_rules_config"])
        mock_delay.assert_not_called()
