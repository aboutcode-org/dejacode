#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from collections import OrderedDict
from io import StringIO
from os.path import dirname
from os.path import join

from django.contrib.auth import get_user_model
from django.core import management
from django.core.management.base import CommandError
from django.test import TestCase

from dje.management import ALL_MODELS
from dje.management import ALL_MODELS_NO_PP
from dje.management import POLICY_MODELS
from dje.management import REPORTING_MODELS
from dje.models import Dataspace
from dje.models import get_unsecured_manager


class CommandsTestCase(TestCase):
    testfiles_location = join(dirname(__file__), "testfiles")

    fixture_by_app = OrderedDict(
        [
            ("user", join(testfiles_location, "test_dataset_user_only.json")),
            ("organization", join(testfiles_location, "test_dataset_organization_only.json")),
            ("license_library", join(testfiles_location, "test_dataset_ll_only.json")),
            ("component_catalog", join(testfiles_location, "test_dataset_cc_only.json")),
            ("product_portfolio", join(testfiles_location, "test_dataset_pp_only.json")),
            ("policy", join(testfiles_location, "test_dataset_policy.json")),
            ("workflow", join(testfiles_location, "test_dataset_workflow.json")),
        ]
    )

    fixtures = fixture_by_app.values()

    def check_dumpdataset(self, app, expected_location, regen=False):
        """
        Given an app name, run dumpdataset for this app and verify that
        the results are the same as the expected JSON fixture.
        Regen the fixture based on the latest results if regen is True.
        """
        output = StringIO()
        apps = {app: True}
        management.call_command("dumpdataset", "nexB", stdout=output, **apps)
        results = output.getvalue()

        if regen:
            with open(expected_location, "w") as fixture_file:
                fixture_file.write(results)

        with open(expected_location) as expected:
            self.assertJSONEqual(expected.read(), results)

    def test_management_command_dumpdataset_no_option(self):
        # Nothing if no option
        output = StringIO()
        management.call_command("dumpdataset", "nexB", stdout=output)
        self.assertEqual("[\n]\n", output.getvalue())

    def test_management_command_dumpdataset_user(self):
        app = "user"
        expected_location = self.fixture_by_app[app]
        self.check_dumpdataset(app, expected_location)

    def test_management_command_dumpdataset_org(self):
        app = "organization"
        expected_location = self.fixture_by_app[app]
        self.check_dumpdataset(app, expected_location)

    def test_management_command_dumpdataset_license(self):
        app = "license_library"
        expected_location = self.fixture_by_app[app]
        self.check_dumpdataset(app, expected_location)

    def test_management_command_dumpdataset_component(self):
        app = "component_catalog"
        expected_location = self.fixture_by_app[app]
        self.check_dumpdataset(app, expected_location)

    def test_management_command_dumpdataset_product(self):
        app = "product_portfolio"
        expected_location = self.fixture_by_app[app]
        self.check_dumpdataset(app, expected_location)

    def test_management_command_dumpdataset_policy(self):
        app = "policy"
        expected_location = self.fixture_by_app[app]
        self.check_dumpdataset(app, expected_location)

    def test_management_command_dumpdataset_workflow(self):
        app = "workflow"
        expected_location = self.fixture_by_app[app]
        self.check_dumpdataset(app, expected_location)

    def test_management_command_flushdataset(self):
        output = StringIO()
        models = ALL_MODELS + POLICY_MODELS

        # Making sure every model is represented in the test fixtures
        for model in models:
            manager = get_unsecured_manager(model)
            # In the Component case we have 2 entry to handle Subcomponent
            self.assertGreaterEqual(manager.count(), 1, msg=str(model))

        # First, we want to keep the Users and Dataspace
        management.call_command(
            "flushdataset", "nexB", keep_users=True, stdout=output, no_color=True
        )
        expected = 'All the "nexB" Dataspace data have been removed.\n'
        self.assertEqual(expected, output.getvalue())

        for model in models:
            self.assertEqual(0, model.objects.count())

        self.assertEqual(1, get_user_model().objects.count())
        self.assertEqual(1, Dataspace.objects.count())

        # Re-execute the command without options
        output = StringIO()
        management.call_command("flushdataset", "nexB", stdout=output, no_color=True)
        self.assertEqual(expected, output.getvalue())
        self.assertEqual(0, get_user_model().objects.count())
        self.assertEqual(0, Dataspace.objects.count())

    def test_management_command_createhistory(self):
        with self.assertRaises(CommandError):
            management.call_command("createhistory")

        output = StringIO()
        management.call_command("createhistory", "nexb_user", stdout=output)
        expected = "Created 29 History entries\n"
        self.assertEqual(expected, output.getvalue())

    def test_management_command_clonedataset(self):
        output = StringIO()
        Dataspace.objects.create(name="Alternate")
        management.call_command("clonedataset", "nexB", "Alternate", "nexb_user", stdout=output)

        models = ALL_MODELS_NO_PP + REPORTING_MODELS + POLICY_MODELS
        for model in models:
            self.assertEqual(
                model.objects.scope_by_name("nexB").count(),
                model.objects.scope_by_name("Alternate").count(),
            )

        output = output.getvalue()
        self.assertIn("Data copy completed.", output)
        self.assertNotIn("Error", output)
