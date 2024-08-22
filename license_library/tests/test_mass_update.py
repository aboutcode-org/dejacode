#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from dje.models import Dataspace
from dje.models import History
from license_library.models import License
from license_library.models import LicenseStyle
from organization.models import Owner


class LicenseMassUpdateTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.user = get_user_model().objects.create_superuser(
            "test", "test@test.com", "t3st", self.dataspace, data_email_notification=True
        )

        self.owner = Owner.objects.create(name="Owner", dataspace=self.dataspace)
        self.license1 = License.objects.create(
            key="license1",
            name="License1",
            short_name="License1",
            dataspace=self.dataspace,
            owner=self.owner,
        )
        self.license2 = License.objects.create(
            key="license2",
            name="License2",
            short_name="License2",
            dataspace=self.dataspace,
            owner=self.owner,
        )

        self.license_changelist_url = reverse("admin:license_library_license_changelist")
        self.base_data = {
            "_selected_action": [self.license1.pk, self.license2.pk],
            "action": "mass_update",
            "select_across": 0,
        }
        # Add some data for the request to actually apply the mass update
        self.action_data = self.base_data.copy()
        self.action_data["apply"] = "Update records"
        self.action_data["chk_id_is_active"] = "on"
        self.action_data["is_active"] = 2  # 2 is for True

    def test_mass_update_form_view(self):
        self.client.login(username="test", password="t3st")
        response = self.client.post(self.license_changelist_url, self.base_data)
        self.assertContains(response, "<h1>Mass update Licenses</h1>", html=True)
        self.assertContains(response, "owner")
        # The following should not be part of the mass update
        self.assertNotContains(response, "id_name")
        self.assertNotContains(response, '"id_key"')
        self.assertNotContains(response, "id_license_profile")
        # The list of selected object on the right
        self.assertContains(response, self.license1.get_admin_link(), html=True)
        self.assertContains(response, self.license2.get_admin_link(), html=True)

    def test_mass_update_preserve_filters_in_form_view(self):
        self.client.login(username="test", password="t3st")
        params = "?o=-3"
        preserved_filters = "?_changelist_filters=o%3D-3"
        url_with_params = self.license_changelist_url + params
        response = self.client.post(url_with_params, self.base_data)

        # Selected records links
        self.assertContains(
            response, '<a href="{}{}">'.format(self.license1.get_admin_url(), preserved_filters)
        )
        self.assertContains(
            response, '<a href="{}{}">'.format(self.license2.get_admin_url(), preserved_filters)
        )
        # Button
        self.assertContains(
            response,
            '<a class="grp-button cancel-link" href="{}">Return to list</a>'.format(
                url_with_params
            ),
        )
        # Breadcrumbs
        self.assertContains(response, '<li><a href="{}">Licenses</a></li>'.format(url_with_params))

        # Submit the mass update
        response = self.client.post(url_with_params, self.action_data, follow=True)
        self.assertContains(response, '<li class="grp-info">Updated 2 records</li>', html=True)
        self.assertRedirects(response, url_with_params)

    def test_mass_update_fk_fields_scope_to_dataspace(self):
        # The limitation of the FKs is done in dje.forms.DejacodeMassUpdateForm
        self.client.login(username="test", password="t3st")

        # Create another dataspace with data for further testing
        other_dataspace = Dataspace.objects.create(name="Other")
        license_style = LicenseStyle.objects.create(name="style1", dataspace=self.dataspace)
        other_style = LicenseStyle.objects.create(name="other_style", dataspace=other_dataspace)

        response = self.client.post(self.license_changelist_url, self.base_data)
        # Make sure the organization in the user owner org are available but
        # not the others.
        self.assertContains(response, license_style.name)
        self.assertNotContains(response, other_style.name)

    def test_mass_update_values_updated(self):
        self.client.login(username="test", password="t3st")

        self.license1.is_active = False
        self.license1.save()
        self.license2.is_active = None
        self.license2.save()
        self.assertIsNone(self.license1.last_modified_by)

        response = self.client.post(self.license_changelist_url, self.action_data, follow=True)
        self.assertContains(response, '<li class="grp-info">Updated 2 records</li>', html=True)
        # Making sure the values were set
        self.license1.refresh_from_db()
        self.license2.refresh_from_db()
        self.assertTrue(self.license1.is_active)
        self.assertTrue(self.license2.is_active)
        self.assertEqual(self.user, self.license1.last_modified_by)

    def test_log_entry_on_mass_update(self):
        self.client.login(username="test", password="t3st")
        self.client.post(self.license_changelist_url, self.action_data)

        history = History.objects.get_for_object(self.license1).get()
        self.assertEqual("Mass update applied on is_active.", history.change_message)

    @override_settings(
        EMAIL_HOST_USER="user",
        EMAIL_HOST_PASSWORD="password",
        EMAIL_HOST="localhost",
        EMAIL_PORT=25,
        DEFAULT_FROM_EMAIL="webmaster@localhost",
    )
    def test_email_notification_mass_update_queryset(self):
        self.client.login(username="test", password="t3st")
        response = self.client.post(self.license_changelist_url, self.action_data)
        self.assertEqual(302, response.status_code)

        self.assertEqual(1, len(mail.outbox))
        self.assertEqual("Multiple Licenses updated", mail.outbox[0].subject)
        body = mail.outbox[0].body
        self.assertTrue("Changes details:\n\n* is_active\nNew value: True" in body)
        self.assertTrue(str(self.license1) in body)
        self.assertTrue(str(self.license2) in body)
