#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import os

from django.contrib.auth import get_user_model
from django.test import TestCase

from dje.models import Dataspace
from dje.models import History
from organization.importers import OwnerImporter
from organization.models import Owner

# WARNING: Do not import from local DJE apps except 'dje' and 'organization'


class OwnerImporterTestCase(TestCase):
    def setUp(self):
        self.testfiles_location = os.path.join(os.path.dirname(__file__), "testfiles", "import")
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.dataspace
        )

        self.owner = Owner.objects.create(
            name="Apache Software Foundation", dataspace=self.dataspace
        )

    def test_owner_import_mandatory_columns(self):
        # The first file is missing the mandatory columns
        file = os.path.join(self.testfiles_location, "missing_mandatory_columns.csv")
        importer = OwnerImporter(self.user, file)
        # Make sure the errors are returned and no results
        self.assertTrue(importer.fatal_errors)
        self.assertFalse(getattr(importer, "formset", None))

        # Now using a file containing the mandatory columns
        file = os.path.join(self.testfiles_location, "including_mandatory_columns.csv")
        importer = OwnerImporter(self.user, file)
        # Make sure no errors are returned and we got some results
        self.assertFalse(importer.fatal_errors)
        self.assertTrue(importer.formset)
        self.assertTrue(importer.formset.is_valid())

    def test_owner_import_save_all(self):
        # Manually creating a formset with 1 new Owner and 1 existing
        formset_data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-MAX_NUM_FORMS": "",
            "form-0-name": self.owner.name,
            "form-0-homepage_url": "http://homepage.org",
            "form-0-notes": "Notes",
            "form-0-type": "Organization",
            "form-1-name": "Some New Name",
            "form-1-homepage_url": "http://homepage2.org",
            "form-1-notes": "Notes",
            "form-1-type": "Organization",
        }
        importer = OwnerImporter(self.user, formset_data=formset_data)
        importer.save_all()
        self.assertEqual(importer.results["unmodified"], [self.owner])
        added_owner = importer.results["added"][0]
        self.assertTrue(added_owner)

        self.assertFalse(History.objects.get_for_object(added_owner).exists())
        self.assertEqual(self.user, added_owner.created_by)
        self.assertTrue(added_owner.created_date)

    def test_url_striping_extra_spaces(self):
        file = os.path.join(self.testfiles_location, "homepage_url.csv")
        importer = OwnerImporter(self.user, file)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        added_owner = importer.results["added"][0]
        self.assertFalse(" " in added_owner.homepage_url)
