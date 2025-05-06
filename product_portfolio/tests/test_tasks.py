#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import uuid
from unittest import mock

from django.core.files.base import ContentFile
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
from product_portfolio.tasks import pull_project_data_from_scancodeio_task
from product_portfolio.tasks import scancodeio_submit_project_task
from product_portfolio.tests import make_product


class ProductPortfolioTasksTestCase(MaxQueryMixin, TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.basic_user = create_user("basic_user", self.dataspace)
        self.product1 = make_product(self.dataspace)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.submit_project")
    def test_scancodeio_submit_project_task(self, mock_submit_project):
        scancodeproject = ScanCodeProject.objects.create(
            product=self.product1,
            dataspace=self.product1.dataspace,
            type=ScanCodeProject.ProjectType.LOAD_SBOMS,
            input_file=ContentFile("Data", name="data.json"),
        )

        mock_submit_project.return_value = None
        scancodeio_submit_project_task(
            scancodeproject_uuid=scancodeproject.uuid,
            user_uuid=self.super_user.uuid,
            pipeline_name="load_sboms",
        )
        scancodeproject.refresh_from_db()
        self.assertEqual("failure", scancodeproject.status)
        self.assertIsNone(scancodeproject.project_uuid)
        expected = ["- Error: File could not be submitted to ScanCode.io"]
        self.assertEqual(expected, scancodeproject.import_log)

        # Reset the instance values
        scancodeproject.status = ""
        scancodeproject.import_log = []
        scancodeproject.save()

        project_uuid = uuid.uuid4()
        mock_submit_project.return_value = {"uuid": project_uuid}
        scancodeio_submit_project_task(
            scancodeproject_uuid=scancodeproject.uuid,
            user_uuid=self.super_user.uuid,
            pipeline_name="load_sboms",
        )

        scancodeproject.refresh_from_db()
        self.assertEqual("submitted", scancodeproject.status)
        self.assertEqual(project_uuid, scancodeproject.project_uuid)
        expected = ["- File submitted to ScanCode.io for inspection"]
        self.assertEqual(expected, scancodeproject.import_log)

    @mock.patch("product_portfolio.models.ScanCodeProject.import_data_from_scancodeio")
    def test_product_portfolio_pull_project_data_from_scancodeio_task(self, mock_import_data):
        scancode_project = ScanCodeProject.objects.create(
            product=self.product1,
            dataspace=self.product1.dataspace,
            type=ScanCodeProject.ProjectType.PULL_FROM_SCANCODEIO,
            created_by=self.super_user,
        )

        mock_import_data.side_effect = Exception("Error")
        pull_project_data_from_scancodeio_task(scancodeproject_uuid=scancode_project.uuid)
        scancode_project.refresh_from_db()
        self.assertEqual(ScanCodeProject.Status.FAILURE, scancode_project.status)
        self.assertEqual(["Error"], scancode_project.import_log)
        notif = Notification.objects.get()
        self.assertTrue(notif.unread)
        self.assertEqual(self.super_user, notif.actor)
        self.assertEqual("Import packages from ScanCode.io", notif.verb)
        self.assertEqual(self.product1, notif.action_object)
        self.assertEqual(self.super_user, notif.recipient)
        self.assertEqual("Import failed.", notif.description)

        Notification.objects.all().delete()
        scancode_project.import_log = []
        scancode_project.status = ScanCodeProject.Status.SUBMITTED
        scancode_project.save()
        mock_import_data.side_effect = None
        mock_import_data.return_value = (
            {"package": ["package1"]},
            {"package": ["package2"]},
            {"package": ["error1"]},
        )
        pull_project_data_from_scancodeio_task(scancodeproject_uuid=scancode_project.uuid)
        scancode_project.refresh_from_db()
        self.assertEqual(ScanCodeProject.Status.SUCCESS, scancode_project.status)
        expected = [
            "- Imported 1 package.",
            "- 1 package skipped: already available in the dataspace.",
            "- 1 package error occurred during import.",
        ]
        self.assertEqual(expected, scancode_project.import_log)

        notif = Notification.objects.get()
        self.assertTrue(notif.unread)
        self.assertEqual(self.super_user, notif.actor)
        self.assertEqual("Import packages from ScanCode.io", notif.verb)
        self.assertEqual(self.product1, notif.action_object)
        self.assertEqual(self.super_user, notif.recipient)
        self.assertEqual("\n".join(scancode_project.import_log), notif.description)

    def test_product_portfolio_pull_project_data_from_scancodeio_task_can_start_import(self):
        scancode_project = ScanCodeProject.objects.create(
            product=self.product1,
            dataspace=self.product1.dataspace,
            type=ScanCodeProject.ProjectType.PULL_FROM_SCANCODEIO,
            status=ScanCodeProject.Status.IMPORT_STARTED,
            created_by=self.super_user,
        )

        with self.assertLogs(tasks_logger) as cm:
            pull_project_data_from_scancodeio_task(scancodeproject_uuid=scancode_project.uuid)

        expected = [
            f"INFO:product_portfolio.tasks:Entering pull_project_data_from_scancodeio task with "
            f"scancodeproject_uuid={scancode_project.uuid}",
            "ERROR:product_portfolio.tasks:Cannot start import",
        ]
        self.assertEqual(expected, cm.output)

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
