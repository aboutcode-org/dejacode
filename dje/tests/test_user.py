#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from io import StringIO
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation
from django.contrib.auth.hashers import get_hasher
from django.contrib.auth.management.commands import changepassword
from django.core import mail
from django.core import signing
from django.core.exceptions import NON_FIELD_ERRORS
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.shortcuts import resolve_url
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from django_registration.backends.activation.views import REGISTRATION_SALT

from dje.filters import DataspaceFilter
from dje.models import Dataspace
from dje.registration import DejaCodeActivationView
from dje.tests import create
from dje.tests import create_superuser
from dje.tests import create_user


class UsersTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="other_dataspace")
        self.different_dataspace = Dataspace.objects.create(name="different_dataspace")

        self.nexb_user = create_superuser("nexb_user", self.nexb_dataspace)
        self.other_user = create_superuser("other_user", self.other_dataspace)
        self.different_user = create_superuser("different_user", self.different_dataspace)

    def test_limit_qs_to_dataspace(self):
        self.client.login(username="other_user", password="secret")
        url = reverse("admin:dje_dejacodeuser_changelist")
        response = self.client.get(url)
        self.assertContains(response, "other_user")
        self.assertNotContains(response, "nexb_user")

        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, "other_user")
        self.assertContains(response, "nexb_user")

    def test_limit_dataspace_qs_choices_for_addition(self):
        self.client.login(username="other_user", password="secret")
        url = reverse("admin:dje_dejacodeuser_add")
        response = self.client.get(url)
        expected = f'<option value="{self.other_dataspace.id}" selected>other_dataspace</option>'
        self.assertContains(response, expected, html=True)
        self.assertNotContains(response, "nexB</option>")

        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, "other_dataspace</option><")
        self.assertContains(response, "nexB</option>")

    def test_limited_dataspace_filter_choices(self):
        self.client.login(username="other_user", password="secret")
        url = reverse("admin:organization_owner_changelist")

        response = self.client.get(url)
        self.assertContains(response, "<label>Dataspace</label>")
        self.assertContains(response, "selected='selected'>other_dataspace</option>")
        self.assertContains(response, "nexB</option>")
        self.assertNotContains(response, "different_dataspace</option>")

        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, "<label>Dataspace</label>")
        self.assertContains(response, "selected='selected'>nexB</option>")
        self.assertContains(response, "nexB</option>")
        self.assertContains(response, "different_dataspace</option>")

    def test_user_changelist_list_filter_includes_dataspace(self):
        # The dataspace list filter is only available to reference user.
        url = reverse("admin:dje_dejacodeuser_changelist")

        self.assertTrue(self.nexb_dataspace.is_reference)
        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, DataspaceFilter.parameter_name)

        self.assertFalse(self.other_dataspace.is_reference)
        self.client.login(username="other_user", password="secret")
        response = self.client.get(url)
        self.assertNotContains(response, DataspaceFilter.parameter_name)

    def test_user_admin_changelist_list_filter_is_active(self):
        url = reverse("admin:dje_dejacodeuser_changelist")
        self.different_user.is_active = False
        self.different_user.save()
        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)

        expected = """
        <div class="grp-row">
            <label>Active</label>
            <select class="grp-filter-choice" data-field-name="is_active">
                <option value="?" selected='selected'>All</option>
                <option value="?is_active__exact=1">Yes</option>
                <option value="?is_active__exact=0">No</option>
            </select>
        </div>
        """
        self.assertContains(response, expected, html=True)
        queryset = response.context_data["cl"].queryset
        self.assertEqual(3, response.context_data["cl"].result_count)
        self.assertIn(self.nexb_user, queryset)
        self.assertIn(self.other_user, queryset)
        self.assertIn(self.different_user, queryset)

        data = {"is_active__exact": "1"}
        response = self.client.get(url, data)
        queryset = response.context_data["cl"].queryset
        self.assertEqual(2, response.context_data["cl"].result_count)
        self.assertIn(self.nexb_user, queryset)
        self.assertIn(self.other_user, queryset)
        self.assertNotIn(self.different_user, queryset)

        data = {"is_active__exact": "0"}
        response = self.client.get(url, data)
        queryset = response.context_data["cl"].queryset
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertNotIn(self.nexb_user, queryset)
        self.assertNotIn(self.other_user, queryset)
        self.assertIn(self.different_user, queryset)

    def test_change_permission_for_non_reference_dataspace(self):
        self.client.login(username="other_user", password="secret")
        owner = create("Owner", self.nexb_dataspace)
        url = owner.get_admin_url()
        response = self.client.get(url)
        self.assertContains(response, "<h1>403 Forbidden</h1>", status_code=403)

        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_login_as_inactive_user(self):
        login_url = resolve_url("login")
        self.nexb_user.is_active = False
        self.nexb_user.save()
        data = {"username": self.nexb_user.username, "password": "secret"}
        response = self.client.post(login_url, data)
        form = response.context_data["form"]
        expected_error = {
            NON_FIELD_ERRORS: [
                "Please enter a correct username and password. "
                "Note that both fields may be case-sensitive."
            ],
        }
        self.assertEqual(expected_error, form.errors)

    def test_login_missing_data(self):
        login_url = resolve_url("login")
        # First not giving a password
        data = {"username": self.nexb_user.username, "password": ""}
        response = self.client.post(login_url, data)
        form = response.context_data["form"]
        expected_error = {"password": ["This field is required."]}
        self.assertEqual(expected_error, form.errors)

        # And now, missing username
        data = {"username": "", "password": self.nexb_user.password}
        response = self.client.post(login_url, data)
        form = response.context_data["form"]
        expected_error = {"username": ["This field is required."]}
        self.assertEqual(expected_error, form.errors)

    def test_login_with_wrong_credential(self):
        login_url = resolve_url("login")
        data = {
            "username": "i-do-not-exist",
            "password": "p4ssW0rd",
        }
        response = self.client.post(login_url, data)
        self.assertContains(response, "Please enter a correct username and password.")
        self.assertContains(response, "Note that both fields may be case-sensitive.")

    def test_login_with_email(self):
        login_url = resolve_url("login")
        data = {
            "username": "username@domain.com",
            "password": "p4ssW0rd",
        }
        response = self.client.post(login_url, data)
        expected = (
            "Be sure to enter your DejaCode username rather than your email "
            "address to sign in to DejaCode."
        )
        self.assertContains(response, expected)

    def test_delete_user_from_admin_view(self):
        self.assertTrue(self.other_user.is_active)
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:dje_dejacodeuser_delete", args=(self.other_user.pk,))
        data = {"post": "yes"}
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("admin:dje_dejacodeuser_changelist"))
        self.other_user.refresh_from_db()
        self.assertFalse(self.other_user.is_active)
        self.assertFalse(self.other_user.has_usable_password())

    def test_delete_user_from_action_is_not_available(self):
        # The bulk delete from action has been disabled for the User ModelAdmin
        # as the delete() is on the QuerySet and we cannot override it.
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:dje_dejacodeuser_changelist")
        response = self.client.get(url)
        # Making sure the action is not available
        self.assertNotContains(response, '<option value="delete_selected">')

    def test_user_set_inactive_action(self):
        # both *_email_notification will be set to False during the action
        self.nexb_user.data_email_notification = True
        self.nexb_user.workflow_email_notification = True
        self.nexb_user.save()

        self.assertTrue(self.nexb_user.is_active)
        self.assertTrue(self.other_user.is_active)

        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:dje_dejacodeuser_changelist")

        response = self.client.get(url)
        self.assertContains(response, '<option value="set_inactive">')

        data = {
            "post": "yes",
            "_selected_action": [self.nexb_user.pk, self.other_user.pk],
            "selected_across": 0,
            "action": "set_inactive",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)

        self.nexb_user.refresh_from_db()
        self.other_user.refresh_from_db()
        self.assertFalse(self.nexb_user.is_active)
        self.assertFalse(self.other_user.is_active)
        self.assertFalse(self.nexb_user.data_email_notification)
        self.assertFalse(self.other_user.data_email_notification)
        self.assertFalse(self.nexb_user.workflow_email_notification)
        self.assertFalse(self.other_user.workflow_email_notification)

    def test_user_export_csv_action(self):
        self.nexb_user.is_superuser = False
        self.nexb_user.save()
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:dje_dejacodeuser_changelist")
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

        self.nexb_user.is_superuser = True
        self.nexb_user.save()
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:dje_dejacodeuser_changelist")
        response = self.client.get(url)
        self.assertContains(response, '<option value="export_as_csv">')

        data = {
            "post": "yes",
            "_selected_action": [self.nexb_user.pk],
            "selected_across": 0,
            "action": "export_as_csv",
        }
        response = self.client.post(url, data)
        self.assertEqual("text/csv", response["content-type"])
        self.assertEqual(
            'attachment; filename="dejacode_user_export.csv"', response["content-disposition"]
        )

    def test_anonymous_user_bypass_login_page(self):
        with override_settings(ANONYMOUS_USERS_DATASPACE=None):
            response = self.client.get("/")
            self.assertRedirects(response, resolve_url("login") + "?next=/")

        with override_settings(ANONYMOUS_USERS_DATASPACE=self.nexb_dataspace):
            response = self.client.get("/")
            # Not using assertRedirects for compatibility across all settings
            self.assertEqual(response.url, resolve_url(settings.LOGIN_REDIRECT_URL))
            self.assertEqual(302, response.status_code)

    def test_save_new_user_from_admin_view_registration(self):
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:dje_dejacodeuser_add")

        data = {
            "username": "new_user",
            "dataspace": self.nexb_dataspace.id,
        }

        response = self.client.post(url, data, follow=True)
        expected = {"email": ["This field is required."]}
        self.assertEqual(expected, response.context_data["adminform"].form.errors)

        data["email"] = "user@mail.com"
        response = self.client.post(url, data, follow=True)

        expected = "was added successfully. You may edit it again below.</li>"
        self.assertContains(response, expected)
        expected = "An activation email will be sent shortly to the email address."
        self.assertContains(response, expected)

        user = get_user_model().objects.get(username="new_user")
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual("[DejaCode] Please activate your account", mail.outbox[0].subject)
        body = mail.outbox[0].body
        self.assertTrue("/account/activate/" in body)
        self.assertTrue("DejaCode {} account".format(user.dataspace.name) in body)
        self.assertTrue("Username: {}".format(user.username) in body)
        self.assertTrue("{} days to activate".format(settings.ACCOUNT_ACTIVATION_DAYS) in body)

        # Call the url to activate the account
        activation_key = signing.dumps(obj=data["username"], salt=REGISTRATION_SALT)
        activation_url = reverse("django_registration_activate", args=[activation_key])
        response = self.client.get(activation_url, follow=True)
        password_reset_form_url = response.redirect_chain[-1][0]

        data = {
            "new_password1": "secret",
            "new_password2": "secret",
        }
        response = self.client.post(password_reset_form_url, data)
        expected = {
            "new_password2": [
                "This password is too short. It must contain at least 8 characters.",
                "Your password must contain at least one special character.",
            ]
        }
        self.assertEqual(expected, response.context["form"].errors)

        data = {
            "new_password1": "Th1s_iS-V4lid",
            "new_password2": "Th1s_iS-V4lid",
        }
        response = self.client.post(password_reset_form_url, data)
        self.assertRedirects(response, reverse("password_reset_complete"))

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_user_admin_send_activation_email_view(self):
        self.client.login(username="nexb_user", password="secret")
        self.assertTrue(self.other_user.has_usable_password())
        self.assertTrue(self.other_user.is_active)

        url = reverse("admin:dje_dejacodeuser_send_activation_email", args=[self.other_user.id])
        response = self.client.get(url, follow=True)
        expected = "An activation email will be sent shortly to the email address."
        self.assertContains(response, expected)

        self.other_user.refresh_from_db()
        self.assertFalse(self.other_user.is_active)
        self.assertFalse(self.other_user.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual("[DejaCode] Please activate your account", mail.outbox[0].subject)
        body = mail.outbox[0].body

        # Grep the key form the email body
        activation_key = ""
        for line in body.split("\n"):
            if line.startswith("http"):
                activation_key = line.rstrip("/").rpartition("/")[-1]

        activation_url = reverse("django_registration_activate", args=[activation_key])
        self.assertTrue("DejaCode {} account".format(self.other_user.dataspace.name) in body)
        self.assertTrue("Username: {}".format(self.other_user.username) in body)
        self.assertTrue("{} days to activate".format(settings.ACCOUNT_ACTIVATION_DAYS) in body)

        response = self.client.get(activation_url, follow=True)
        self.assertContains(response, "DejaCode Password Assistance")

    def test_user_admin_changeform_group_field_includes_link_to_details(self):
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:dje_dejacodeuser_add")
        response = self.client.get(url)
        self.assertContains(response, reverse("admin:auth_group_permission_details"))

    def test_user_admin_changeform_submit_row_delete_button_label(self):
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:dje_dejacodeuser_change", args=[self.other_user.pk])
        response = self.client.get(url)
        expected = (
            f'<a href="/admin/dje/dejacodeuser/{self.other_user.pk}/delete/" '
            f'class="grp-button grp-delete-link">Disable</a>'
        )
        self.assertContains(response, expected, html=True)

    def test_user_admin_form_scope_homepage_layout_choices(self):
        self.client.login(username=self.nexb_user.username, password="secret")
        url = reverse("admin:dje_dejacodeuser_change", args=[self.nexb_user.pk])

        card_layout_nexb = create("CardLayout", self.nexb_dataspace)
        card_layout_other = create("CardLayout", self.other_dataspace)

        response = self.client.get(url)
        expected = '<label for="id_homepage_layout">Homepage layout</label>'
        self.assertContains(response, expected, html=True)
        self.assertContains(response, card_layout_nexb.name)
        self.assertNotContains(response, card_layout_other.name)

    def test_user_model_send_internal_notification(self):
        notification = self.nexb_user.send_internal_notification(
            verb="Updated", description="details"
        )
        self.assertEqual("Updated", notification.verb)
        self.assertEqual("details", notification.description)
        self.assertEqual("dejacodeuser", notification.actor_content_type.model)
        self.assertEqual(self.nexb_user.id, notification.actor_object_id)


class UsersPasswordTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.user = create_superuser("user", self.nexb_dataspace)
        self.strong_password = "wqeSDSA2$"
        self.weak_password = "a"

    def test_password_validation_validate_password(self):
        valid_passwords = [
            "awdrtg1@",
            "wqeSDSA2$",
            "SDJ--EUD1",
            "#sadsa7sd",
            "p4ssw0r__D",
        ]

        invalid_passwords = [
            "wdrtg1@",  # less than 8 chars
            "pssw0rdD",  # missing 1 special char
        ]

        for password in valid_passwords:
            self.assertIsNone(password_validation.validate_password(password))

        for password in invalid_passwords:
            with self.assertRaises(ValidationError):
                password_validation.validate_password(password)

    def test_user_change_password_field_is_strong(self):
        self.client.login(username="user", password="secret")
        url = reverse("password_change")
        response = self.client.get(url)
        self.assertContains(response, password_validation.password_validators_help_text_html())

        data = {
            "old_password": "secret",
            "new_password1": self.weak_password,
            "new_password2": self.weak_password,
        }
        response = self.client.post(url, data)
        expected = {
            "new_password2": [
                "This password is too short. It must contain at least 8 characters.",
                "Your password must contain at least one special character.",
            ]
        }
        self.assertEqual(expected, response.context["form"].errors)

        data["new_password2"] = data["new_password1"] = self.strong_password
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("password_change_done"))

    def _check_change_password_email_notification(self):
        self.assertEqual(len(mail.outbox), 1)
        subject = mail.outbox[0].subject
        self.assertEqual("Your DejaCode password has been changed.", subject)
        body = mail.outbox[0].body
        self.assertTrue(
            "The password for your DejaCode user account user was recently changed." in body
        )
        self.assertTrue(
            "If you didn't change your password, your account might be compromised." in body
        )
        self.assertTrue("/account/password_reset/" in body)

    def test_user_change_password_view_email_notification(self):
        self.client.login(username="user", password="secret")
        url = reverse("password_change")
        data = {
            "old_password": "secret",
            "new_password1": self.strong_password,
            "new_password2": self.strong_password,
        }
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("password_change_done"))
        self._check_change_password_email_notification()

    def test_user_model_set_password_email_notification(self):
        self.user.set_password("pass")
        self.user.save()
        self._check_change_password_email_notification()

    def test_user_model_changepassword_command_email_notification(self):
        out = StringIO()
        cmd = changepassword.Command()
        cmd._get_pass = lambda *args: self.strong_password
        call_command(cmd, self.user.username, stdout=out)

        self.assertIn("Changing password for user 'user'", out.getvalue())
        self.assertIn("Password changed successfully for user 'user'", out.getvalue())

        self._check_change_password_email_notification()

    def test_user_model_hash_change_do_not_trigger_email_notification(self):
        # login triggers a `check_password` call that may update the stored password
        # in case the password hasher was changed (like an iterations increase).
        # Since this is not a "real" password change, we do not want to notifiy the user.
        self.client.login(username="user", password="secret")
        self.assertEqual(len(mail.outbox), 0)

        # Forcing a password hash upgrades, this shouldn't be considered password changes.
        hasher = get_hasher()
        with mock.patch.object(hasher, "must_update", return_value=True) as mock_must_update:
            self.client.login(username="user", password="secret")
            self.assertEqual(len(mail.outbox), 0)
            mock_must_update.assert_called()

    def test_user_change_password_in_admin_redirect(self):
        # The view to change your password in the admin redirect to the main one
        self.client.login(username="user", password="secret")
        admin_url = reverse("admin:password_change")
        url = reverse("password_change")
        self.assertRedirects(self.client.get(admin_url), url, status_code=301)

    def test_admin_set_user_password_view_is_not_allowed(self):
        self.client.login(username="user", password="secret")
        change_password_url = reverse("admin:auth_user_password_change", args=(self.user.pk,))
        data = {
            "password1": self.weak_password,
            "password2": self.weak_password,
        }
        response = self.client.post(change_password_url, data)
        self.assertEqual(403, response.status_code)
        response = self.client.get(change_password_url)
        self.assertEqual(403, response.status_code)

    def test_admin_create_user_password_field_not_available(self):
        self.client.login(username="user", password="secret")
        url = reverse("admin:dje_dejacodeuser_add")
        response = self.client.get(url)
        fields = response.context_data["adminform"].form.fields.keys()
        self.assertIn("username", fields)
        self.assertNotIn("password", fields)

    def test_user_password_reset_flow(self):
        # User is not logged in as it do not remember his password
        password_reset_url = reverse("password_reset")
        response = self.client.get(password_reset_url)
        email_input = (
            '<input type="email" class="form-control" name="email" id="id_email" value="">'
        )
        self.assertContains(response, email_input, html=True)

        data = {"email": self.user.email}
        response = self.client.post(password_reset_url, data)
        self.assertRedirects(response, reverse("password_reset_done"))
        # An email is sent with the reset link at this point
        self.assertEqual(len(mail.outbox), 1)
        subject = mail.outbox[0].subject
        self.assertEqual("DejaCode Password Assistance", subject)
        body = mail.outbox[0].body
        self.assertTrue(
            "We received a request to reset the password associated with this e-mail address."
            in body
        )
        self.assertTrue(
            "Click the link below to reset your password using our secure server:" in body
        )
        self.assertTrue("Your username, in case you've forgotten: user" in body)

        reset_confirm_url = DejaCodeActivationView.get_password_reset_confirm_url(self.user)
        response = self.client.get(reset_confirm_url, follow=True)
        self.assertContains(response, password_validation.password_validators_help_text_html())

        password_reset_form_url = response.redirect_chain[-1][0]
        data = {
            "new_password1": self.weak_password,
            "new_password2": self.weak_password,
        }
        response = self.client.post(password_reset_form_url, data)
        expected = {
            "new_password2": [
                "This password is too short. It must contain at least 8 characters.",
                "Your password must contain at least one special character.",
            ]
        }
        self.assertEqual(expected, response.context["form"].errors)

        self.assertTemplateUsed(response, "registration/password_reset_confirm.html")

        data["new_password2"] = data["new_password1"] = self.strong_password
        response = self.client.post(password_reset_form_url, data)
        self.assertRedirects(response, reverse("password_reset_complete"))

        del mail.outbox[0]
        self._check_change_password_email_notification()


class DejaCodeUserModelTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    def test_user_model_queryset_manager(self):
        active = create_user("active", self.dataspace)
        superuser = create_superuser("superuser", self.dataspace)
        inactive = create_user("inactive", self.dataspace)
        inactive.is_active = False
        inactive.save()
        self.different_user = create_superuser("different_user", self.dataspace)

        actives_qs = get_user_model().objects.actives()
        self.assertIn(active, actives_qs)
        self.assertIn(superuser, actives_qs)
        self.assertNotIn(inactive, actives_qs)

        standards_qs = get_user_model().objects.standards()
        self.assertIn(active, standards_qs)
        self.assertNotIn(superuser, standards_qs)
        self.assertIn(inactive, standards_qs)

        admins_qs = get_user_model().objects.admins()
        self.assertNotIn(active, admins_qs)
        self.assertIn(superuser, admins_qs)
        self.assertNotIn(inactive, admins_qs)

        actives_standards_qs = get_user_model().objects.actives().standards()
        self.assertIn(active, actives_standards_qs)
        self.assertNotIn(superuser, actives_standards_qs)
        self.assertNotIn(inactive, actives_standards_qs)

        admins_actives_qs = get_user_model().objects.admins().actives()
        self.assertNotIn(active, admins_actives_qs)
        self.assertIn(superuser, admins_actives_qs)
        self.assertNotIn(inactive, admins_actives_qs)

    def test_user_model_create_auth_token(self):
        user = create_user("active", self.dataspace)
        self.assertEqual(40, len(user.auth_token.key))

    def test_user_model_regenerate_api_key(self):
        user = create_user("active", self.dataspace)

        initial_key = str(user.auth_token.key)
        self.assertEqual(40, len(initial_key))

        user.regenerate_api_key()
        new_key = user.auth_token.key
        self.assertEqual(40, len(new_key))
        self.assertNotEqual(initial_key, new_key)

    def test_user_model_regenerate_get_homepage_layout(self):
        user = create_user("active", self.dataspace)
        self.assertIsNone(user.get_homepage_layout())

        card_layout_from_dataspace = create("CardLayout", self.dataspace)
        configuration = create("DataspaceConfiguration", self.dataspace)
        configuration.homepage_layout = card_layout_from_dataspace
        configuration.save()
        self.assertEqual(card_layout_from_dataspace, user.get_homepage_layout())

        card_layout_from_user = create("CardLayout", self.dataspace)
        user.homepage_layout = card_layout_from_user
        user.save()
        self.assertEqual(card_layout_from_user, user.get_homepage_layout())

    def test_user_model_last_active_property(self):
        user = create_user("active", self.dataspace)
        self.assertEqual(user.last_active, user.date_joined)

        user.last_login = timezone.now()
        user.save()
        self.assertEqual(user.last_active, user.last_login)

        user.last_api_access = timezone.now()
        user.save()
        self.assertEqual(user.last_active, user.last_api_access)

    def test_user_model_serialize_user_data(self):
        user = create_user("active", self.dataspace)
        user.date_joined = "2020-09-01 23:13:05.611210Z"
        user.last_login = "2021-09-01 23:13:05.611210Z"
        user.save()

        expected = {
            "email": "user@email.com",
            "first_name": "",
            "last_name": "",
            "username": "active",
            "company": "",
            "last_login": "2021-09-01 23:13:05.611210Z",
            "date_joined": "2020-09-01 23:13:05.611210Z",
            "last_active": "2021-09-01 23:13:05.611210Z",
            "is_superuser": "False",
            "is_staff": "False",
            "is_active": "True",
            "updates_email_notification": "False",
            "dataspace": "nexB",
        }
        self.assertEqual(expected, user.serialize_user_data())
