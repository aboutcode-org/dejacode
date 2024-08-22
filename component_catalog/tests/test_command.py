#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from io import StringIO
from unittest import mock

from django.core import management
from django.core.management.base import CommandError
from django.test import TestCase

from component_catalog.models import Component
from component_catalog.models import Package
from dje.models import Dataspace
from dje.models import History
from dje.tests import create_superuser


class ComponentCatalogManagementCommandsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("super_user", self.dataspace)

        self.component1 = Component.objects.create(
            name="component", version="1.0", dataspace=self.dataspace
        )

    def test_component_update_completion_levels_management_command(self):
        self.assertFalse(self.component1.completion_level)
        output = StringIO()

        with self.assertRaises(CommandError) as error:
            management.call_command("updatecompletionlevels", stdout=output)
        self.assertEqual(
            "Error: the following arguments are required: dataspace", str(error.exception)
        )

        management.call_command(
            "updatecompletionlevels", self.dataspace.name, stdout=output, no_color=True
        )
        self.component1.refresh_from_db()
        self.assertTrue(self.component1.completion_level)
        self.assertEqual("1 Component(s) updated.\n", output.getvalue())

    def test_package_setpurls_management_command(self):
        output = StringIO()
        package = Package.objects.create(
            filename="package.zip",
            download_url="http://repo1.maven.org/maven2/jdbm/jdbm/0.20-dev/",
            dataspace=self.dataspace,
        )

        self.assertTrue(package.last_modified_date)
        initial_modified_date = package.last_modified_date

        with self.assertRaises(CommandError) as error:
            management.call_command("setpurls", stdout=output)
        self.assertEqual(
            "Error: the following arguments are required: dataspace, username",
            str(error.exception),
        )

        options = [
            self.dataspace.name,
            self.super_user.username,
        ]
        management.call_command("setpurls", *options, stdout=output, no_color=True)
        package.refresh_from_db()

        expected_output = [
            "1 Package(s) updated with a Package URL in the nexB Dataspace.",
            "Pre-update: 1 Packages, 0 (0%) with a Package URL, 1 without.",
            "Post-update: 1 Packages, 1 (100%) with a Package URL, 0 without.",
            "Number of errors encountered when updating Packages: 0",
        ]
        self.assertIn("\n".join(expected_output), output.getvalue().strip())
        self.assertEqual("pkg:maven/jdbm/jdbm@0.20-dev", package.package_url)
        self.assertEqual(initial_modified_date, package.last_modified_date)

        output = StringIO()
        Package.objects.filter(pk=package.pk).update(
            download_url="http://repo1.maven.org/maven2/abc/abc/1.0/"
        )
        initial_modified_date = package.last_modified_date

        options = [
            self.dataspace.name,
            self.super_user.username,
            "--history",
            "--overwrite",
            "--save",
        ]
        management.call_command("setpurls", *options, stdout=output, no_color=True)
        package.refresh_from_db()
        expected_output[1] = "Pre-update: 1 Packages, 1 (100%) with a Package URL, 0 without."
        self.assertEqual("\n".join(expected_output), output.getvalue().strip())
        self.assertEqual("pkg:maven/abc/abc@1.0", package.package_url)
        self.assertNotEqual(initial_modified_date, package.last_modified_date)

        history_entry = History.objects.get_for_object(package).get()
        expected_messages = "Set Package URL from Download URL"
        self.assertEqual(expected_messages, history_entry.change_message)
        self.assertEqual(self.super_user, package.last_modified_by)

    def test_collectcpes_management_command(self):
        self.assertFalse(self.component1.completion_level)
        output = StringIO()

        with self.assertRaises(CommandError) as error:
            management.call_command("collectcpes", stdout=output)

        expected = (
            "Error: the following arguments are required: dataspace, " "cpe_dictionary_location"
        )
        self.assertEqual(expected, str(error.exception))

    def test_componentfrompackage_management_command(self):
        output = StringIO()

        with self.assertRaises(CommandError) as error:
            management.call_command("componentfrompackage", stdout=output)

        expected = "Error: the following arguments are required: dataspace, username"
        self.assertEqual(expected, str(error.exception))

    @mock.patch("component_catalog.vulnerabilities.fetch_from_vulnerablecode")
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
