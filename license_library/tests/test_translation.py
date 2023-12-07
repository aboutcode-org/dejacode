#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import translation

from dje.models import Dataspace
from license_library.models import License
from organization.models import Owner


class LocaleTranslationTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Dataspace")
        self.user = get_user_model().objects.create_superuser(
            "test", "test@test.com", "t3st", self.dataspace
        )

        self.owner = Owner.objects.create(name="Owner", dataspace=self.dataspace)
        self.license1 = License.objects.create(
            key="license1",
            name="License1",
            short_name="License1",
            is_active=True,
            owner=self.owner,
            dataspace=self.dataspace,
        )

    def tearDown(self):
        translation.activate("en")

    def test_changeview_translation(self):
        self.client.login(username="test", password="t3st")
        url_name = "admin:license_library_license_change"
        url = reverse(url_name, args=[self.license1.pk])

        translation.activate("en")
        response = self.client.get(url)
        expected = '<label for="id_license_profile">License profile</label>'
        self.assertContains(response, expected)

        translation.activate("en_GB")  # Activate the custom translation locale
        response = self.client.get(url)
        # The verbose part of the label is properly translated.
        expected = '<label for="id_license_profile">Attribution type</label>'
        self.assertContains(response, expected)

    def test_admin_index_view_translation(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:index")

        translation.activate("en")
        response = self.client.get(url)
        expected = "<strong>License profiles</strong>"
        self.assertContains(response, expected)

        translation.activate("en-gb")  # Activate the custom translation locale
        response = self.client.get(url)
        # The verbose part of the label is properly translated.
        expected = "<strong>Attribution types</strong>"
        self.assertContains(response, expected)

    def test_license_library_detail_view_fields_label_translation(self):
        self.client.login(username="test", password="t3st")
        expected_en = "License profile"
        expected_cu = "Attribution type"

        translation.activate("en")
        url = self.license1.get_absolute_url()
        response = self.client.get(url)
        self.assertContains(response, expected_en)
        self.assertNotContains(response, expected_cu)

        translation.activate("en-gb")  # Activate the custom translation locale
        url = self.license1.get_absolute_url()  # Need to refresh the URL
        response = self.client.get(url)
        # The verbose part of the label is properly translated.
        self.assertContains(response, expected_cu)
        self.assertNotContains(response, expected_en)

    @override_settings(LANGUAGE_CODE="en-gb")
    def test_no_translation_file_found(self):
        self.assertEqual("Cancel", translation.gettext("Return to list"))
