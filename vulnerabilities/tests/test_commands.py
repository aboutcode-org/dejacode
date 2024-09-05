#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest import mock

from django.core import management
from django.core.management.base import CommandError
from django.test import TestCase

from dje.models import Dataspace
from dje.tests import create_superuser


class VulnerabilityManagementCommandsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("super_user", self.dataspace)

    @mock.patch("vulnerabilities.fetch.fetch_from_vulnerablecode")
    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.is_configured")
    def test_fetchvulnerabilities_management_command(self, mock_is_configured, mock_fetch):
        mock_is_configured.return_value = False
        self.assertFalse(self.dataspace.enable_vulnerablecodedb_access)

        options = [self.dataspace.name]
        with self.assertRaises(CommandError) as error:
            management.call_command("fetchvulnerabilities", *options)
        expected = "VulnerableCode is not enabled on this Dataspace."
        self.assertEqual(expected, str(error.exception))

        self.dataspace.enable_vulnerablecodedb_access = True
        self.dataspace.save()
        with self.assertRaises(CommandError) as error:
            management.call_command("fetchvulnerabilities", *options)
        expected = "VulnerableCode is not configured."
        self.assertEqual(expected, str(error.exception))

        mock_is_configured.return_value = True
        management.call_command("fetchvulnerabilities", *options)
        mock_fetch.assert_called_once()
