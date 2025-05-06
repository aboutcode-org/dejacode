#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest import mock

from django.db import IntegrityError
from django.test import TestCase

from guardian.shortcuts import assign_perm
from notifications.models import Notification

from dje.models import Dataspace
from dje.tests import MaxQueryMixin
from dje.tests import create_superuser
from dje.tests import create_user
from product_portfolio.models import ScanCodeProject
from product_portfolio.tasks import improve_packages_from_purldb_task
from product_portfolio.tasks import logger as tasks_logger
from product_portfolio.tests import make_product


class ProductPortfolioTasksTestCase(MaxQueryMixin, TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.basic_user = create_user("basic_user", self.dataspace)
        self.product1 = make_product(self.dataspace)

    @mock.patch("product_portfolio.models.Product.improve_packages_from_purldb")
    def test_product_portfolio_improve_packages_from_purldb_task(self, mock_improve):
        mock_improve.return_value = ["pkg1", "pkg2"]

        self.assertFalse(self.basic_user.has_perm("change_product", self.product1))
        with self.assertLogs(tasks_logger) as cm:
            improve_packages_from_purldb_task(self.product1.uuid, self.basic_user.uuid)

        expected = (
            "ERROR:product_portfolio.tasks:[improve_packages_from_purldb]: "
            f"Product uuid={self.product1.uuid} does not exists."
        )
        self.assertIn(expected, cm.output)

        assign_perm("view_product", self.basic_user, self.product1)
        self.assertFalse(self.basic_user.has_perm("change_product", self.product1))
        with self.assertLogs(tasks_logger) as cm:
            improve_packages_from_purldb_task(self.product1.uuid, self.basic_user.uuid)

        expected = (
            "ERROR:product_portfolio.tasks:[improve_packages_from_purldb]: Permission denied."
        )
        self.assertIn(expected, cm.output)

        self.assertTrue(self.super_user.has_perm("change_product", self.product1))
        with self.assertLogs(tasks_logger) as cm:
            improve_packages_from_purldb_task(self.product1.uuid, self.super_user.uuid)

        mock_improve.assert_called_once()
        expected = [
            "INFO:product_portfolio.tasks:Entering improve_packages_from_purldb task with "
            f"product_uuid={self.product1.uuid} "
            f"user_uuid={self.super_user.uuid}",
            "INFO:product_portfolio.tasks:[improve_packages_from_purldb]: 2 updated from PurlDB.",
        ]
        self.assertEqual(expected, cm.output)

        import_project = self.product1.scancodeprojects.get()
        self.assertEqual(import_project.type, ScanCodeProject.ProjectType.IMPROVE_FROM_PURLDB)
        self.assertEqual(import_project.status, ScanCodeProject.Status.SUCCESS)
        expected = ["Improved packages from PurlDB:", "pkg1, pkg2"]
        self.assertEqual(expected, import_project.import_log)

        notification = Notification.objects.get()
        self.assertEqual("Improved packages from PurlDB:", notification.verb)
        self.assertEqual("pkg1, pkg2", notification.description)
        self.assertEqual("dejacodeuser", notification.actor_content_type.model)
        self.assertEqual(self.product1, notification.action_object)

    @mock.patch("product_portfolio.models.Product.improve_packages_from_purldb")
    def test_product_portfolio_improve_packages_from_purldb_task_exception(self, mock_improve):
        mock_improve.side_effect = IntegrityError("duplicate key value violates unique constraint")

        self.assertFalse(self.basic_user.has_perm("change_product", self.product1))
        with self.assertLogs(tasks_logger) as cm:
            results = improve_packages_from_purldb_task(self.product1.uuid, self.super_user.uuid)
        self.assertIsNone(results)

        import_project = self.product1.scancodeprojects.get()
        self.assertEqual(import_project.type, ScanCodeProject.ProjectType.IMPROVE_FROM_PURLDB)
        self.assertEqual(import_project.status, ScanCodeProject.Status.FAILURE)
        expected = ["Error:", "duplicate key value violates unique constraint"]
        self.assertEqual(expected, import_project.import_log)

        expected = (
            "ERROR:product_portfolio.tasks:[improve_packages_from_purldb]: "
            "duplicate key value violates unique constraint."
        )
        self.assertIn(expected, cm.output)
