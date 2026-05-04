#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core import signing
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from django_altcha import AltchaField
from django_registration.backends.activation.views import REGISTRATION_SALT
from django_registration.backends.activation.views import RegistrationView

from dje.registration import REGISTRATION_DEFAULT_GROUPS
from dje.tests import refresh_url_cache


@override_settings(
    ENABLE_SELF_REGISTRATION=True,
    ADMINS=[("admin", "admin@nexb.com")],
)
class DejaCodeUserRegistrationTestCase(TestCase):
    """Tests for the dejacode.com registration workflow."""

    def setUp(self):
        refresh_url_cache()

        self.captcha_patch = patch.object(AltchaField, "validate", return_value=True)
        self.captcha_patch.start()

        self.registration_data = {
            "username": "username",
            "email": "username@company.com",
            "first_name": "first_name",
            "last_name": "last_name",
            "company": "company",
            "password1": "P4ssw*rd",
        }

    def tearDown(self):
        self.captcha_patch.stop()

    @override_settings(ALTCHA_HMAC_KEY="abcdef123456")
    def test_user_registration_form_submit(self):
        url = reverse("django_registration_register")
        response = self.client.get(url)
        # Making sure the form is present
        self.assertContains(response, "<form")
        self.assertContains(response, "id_username")

        response = self.client.post(url, self.registration_data, follow=True)
        self.assertRedirects(response, reverse("django_registration_complete"))
        self.assertContains(response, "Thank you for creating your account for DejaCode")

        # 1 notification email to the new user, 1 notification to the admins
        self.assertEqual(len(mail.outbox), 2)
        body = mail.outbox[1].body
        self.assertTrue("/account/activate/" in body)
        self.assertTrue("Your DejaCode Evaluation account is pending activation." in body)
        self.assertTrue("Username: {}".format(self.registration_data["username"]) in body)
        self.assertTrue("{} days to activate".format(settings.ACCOUNT_ACTIVATION_DAYS) in body)
        # Verify the activation URL uses the querystring format
        self.assertTrue("?activation_key=" in body)

        new_user = get_user_model().objects.get(username=self.registration_data["username"])
        self.assertEqual(new_user.email, self.registration_data["email"])
        self.assertEqual(new_user.first_name, self.registration_data["first_name"])
        self.assertEqual(new_user.last_name, self.registration_data["last_name"])
        self.assertEqual(new_user.company, self.registration_data["company"])

        self.assertFalse(new_user.is_active)
        self.assertTrue(new_user.is_staff)
        self.assertFalse(new_user.is_superuser)
        self.assertTrue(new_user.has_usable_password())

        subject = mail.outbox[0].subject
        self.assertEqual("[DejaCode] New User registration", subject)
        body = mail.outbox[0].body
        self.assertTrue("New registration for user username username@company.com" in body)

    @override_settings(ALTCHA_HMAC_KEY="abcdef123456")
    def test_user_registration_form_validators(self):
        self.captcha_patch.stop()

        url = reverse("django_registration_register")
        self.registration_data["username"] = "ab"
        self.registration_data["email"] = "wrong"
        self.registration_data["password1"] = "p"
        del self.registration_data["first_name"]
        del self.registration_data["last_name"]
        del self.registration_data["company"]

        response = self.client.post(url, self.registration_data, follow=True)
        expected = {
            "username": ["Ensure this value has at least 3 characters (it has 2)."],
            "email": ["Enter a valid email address."],
            "first_name": ["This field is required."],
            "last_name": ["This field is required."],
            "company": ["This field is required."],
            "password1": [
                "This password is too short. It must contain at least 8 characters.",
                "Your password must contain at least one special character.",
            ],
            "captcha": ["ALTCHA CAPTCHA token is missing."],
        }
        self.assertEqual(expected, response.context["form"].errors)
        self.captcha_patch.start()

    def test_user_registration_account_activation(self):
        url = reverse("django_registration_register")
        self.client.post(url, self.registration_data)
        user = get_user_model().objects.get(username=self.registration_data["username"])
        self.assertFalse(user.is_active)

        self.assertEqual(2, len(mail.outbox))
        self.assertEqual("[DejaCode] New User registration", mail.outbox[0].subject)
        self.assertEqual(
            "New registration for user username username@company.com", mail.outbox[0].body
        )

        self.assertEqual("[DejaCode] Please activate your account", mail.outbox[1].subject)
        activation_key = RegistrationView().get_activation_key(user)
        activation_url = reverse("django_registration_activate")
        # Check the validity of URL in activation email
        # WARNING: The key of the URL set in the email may be different since it is not
        # generated at the same time as the `activation_key` and the result is based on
        # the timestamp.
        expected_url_in_email = f"{activation_url}?activation_key={activation_key}"
        self.assertTrue(expected_url_in_email in mail.outbox[1].body)
        # Activate the account via POST (django-registration 5.x requires POST)
        response = self.client.post(
            activation_url,
            data={"activation_key": activation_key},
            follow=True,
        )
        self.assertRedirects(response, reverse("django_registration_activation_complete"))
        self.assertContains(response, "account is now active")
        # Now the user is active
        user = get_user_model().objects.get(username=self.registration_data["username"])
        self.assertTrue(user.is_active)
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        # Make sure the activation link can be used multiple times within the
        # `ACCOUNT_ACTIVATION_DAYS` period.
        response = self.client.post(
            activation_url,
            data={"activation_key": activation_key},
            follow=True,
        )
        self.assertContains(response, "account is now active")

    def test_user_registration_activation_form_displayed_on_get(self):
        url = reverse("django_registration_register")
        self.client.post(url, self.registration_data)
        user = get_user_model().objects.get(username=self.registration_data["username"])
        activation_key = RegistrationView().get_activation_key(user)
        activation_url = reverse("django_registration_activate")

        response = self.client.get(f"{activation_url}?activation_key={activation_key}")
        self.assertEqual(response.status_code, 200)
        # The page should display the activation form, not redirect or auto-activate
        self.assertContains(response, "Activate my account")
        # User should NOT be active yet (security: GET should not activate)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_user_registration_activate_wrong_key(self):
        activation_url = reverse("django_registration_activate")
        response = self.client.post(activation_url, data={"activation_key": "wrong_key"})
        self.assertEqual(response.status_code, 200)
        # The form should reject the invalid activation key
        self.assertContains(response, "invalid")
        # No user should have been created or activated
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_user_registration_activate_empty_key(self):
        activation_url = reverse("django_registration_activate")
        response = self.client.post(activation_url, data={"activation_key": ""})
        self.assertEqual(response.status_code, 200)
        # Form should reject the empty key
        self.assertContains(response, "required")

    def test_user_registration_activate_expired_key(self):
        url = reverse("django_registration_register")
        self.client.post(url, self.registration_data)
        user = get_user_model().objects.get(username=self.registration_data["username"])

        # Generate a key with a timestamp older than ACCOUNT_ACTIVATION_DAYS
        expired_days = settings.ACCOUNT_ACTIVATION_DAYS + 1
        with patch("django.core.signing.time.time") as mock_time:
            past_timestamp = (timezone.now() - timedelta(days=expired_days)).timestamp()
            mock_time.return_value = past_timestamp
            expired_key = signing.dumps(obj=user.username, salt=REGISTRATION_SALT)

        activation_url = reverse("django_registration_activate")
        response = self.client.post(activation_url, data={"activation_key": expired_key})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "expired")
        # User should remain inactive
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_user_registration_activate_unknown_user(self):
        # Generate a key for a user that doesn't exist
        bogus_key = signing.dumps(obj="nonexistent_user", salt=REGISTRATION_SALT)
        activation_url = reverse("django_registration_activate")
        response = self.client.post(activation_url, data={"activation_key": bogus_key}, follow=True)
        self.assertEqual(response.status_code, 200)
        # Should display the activation error template content
        self.assertContains(response, "The account you attempted to activate is invalid")

    def test_user_registration_unique_email(self):
        url = reverse("django_registration_register")
        # First registration succeeds
        self.client.post(url, self.registration_data)
        # Second registration with same email but different username
        duplicate_data = dict(self.registration_data)
        duplicate_data["username"] = "different_username"
        response = self.client.post(url, duplicate_data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)

    def test_user_registration_unique_username(self):
        url = reverse("django_registration_register")
        self.client.post(url, self.registration_data)
        duplicate_data = dict(self.registration_data)
        duplicate_data["email"] = "different@company.com"
        response = self.client.post(url, duplicate_data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)

    def test_user_registration_default_dataspace_assigned(self):
        url = reverse("django_registration_register")
        self.client.post(url, self.registration_data)
        new_user = get_user_model().objects.get(username=self.registration_data["username"])
        self.assertEqual(new_user.dataspace.name, "Evaluation")

    def test_user_registration_default_groups(self):
        for group_name in REGISTRATION_DEFAULT_GROUPS:
            Group.objects.create(name=group_name)

        url = reverse("django_registration_register")
        self.client.post(url, self.registration_data, follow=True)

        new_user = get_user_model().objects.get(username=self.registration_data["username"])
        self.assertEqual(len(REGISTRATION_DEFAULT_GROUPS), new_user.groups.count())

    def test_user_registration_default_groups_missing(self):
        # Don't create any groups
        url = reverse("django_registration_register")
        response = self.client.post(url, self.registration_data, follow=True)
        # Registration should succeed
        self.assertRedirects(response, reverse("django_registration_complete"))
        new_user = get_user_model().objects.get(username=self.registration_data["username"])
        self.assertEqual(0, new_user.groups.count())

    def test_user_registration_password_field_only_password1(self):
        url = reverse("django_registration_register")
        response = self.client.get(url)
        self.assertContains(response, 'name="password1"')
        self.assertNotContains(response, 'name="password2"')

    @override_settings(REGISTRATION_OPEN=False)
    def test_user_registration_closed(self):
        resp = self.client.get(reverse("django_registration_register"))
        self.assertRedirects(resp, reverse("django_registration_disallowed"))

    @override_settings(REGISTRATION_OPEN=False)
    def test_user_registration_closed_post_blocked(self):
        resp = self.client.post(reverse("django_registration_register"), self.registration_data)
        self.assertRedirects(resp, reverse("django_registration_disallowed"))
        # No user should have been created
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_user_registration_admin_notification_email_sent(self):
        url = reverse("django_registration_register")
        self.client.post(url, self.registration_data)

        admin_email = mail.outbox[0]
        self.assertEqual("[DejaCode] New User registration", admin_email.subject)
        # Check that admin@nexb.com is in any of the recipient tuples or strings
        recipients_str = str(admin_email.to)
        self.assertIn("admin@nexb.com", recipients_str)
        self.assertIn(self.registration_data["username"], admin_email.body)
        self.assertIn(self.registration_data["email"], admin_email.body)