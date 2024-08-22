#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from django_registration.backends.activation.views import RegistrationView
from hcaptcha_field import hCaptchaField

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

        self.hcaptcha_patch = patch.object(hCaptchaField, "validate", return_value=True)
        self.hcaptcha_patch.start()

        self.registration_data = {
            "username": "username",
            "email": "username@company.com",
            "first_name": "first_name",
            "last_name": "last_name",
            "company": "company",
            "password1": "P4ssw*rd",
        }

    def tearDown(self):
        self.hcaptcha_patch.stop()

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

    def test_user_registration_form_validators(self):
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
        }
        self.assertEqual(expected, response.context["form"].errors)

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
        activation_url = reverse("django_registration_activate", args=[activation_key])
        # Check the validity of URL in activation email
        # WARNING: The key of the URL set in the email may be different since it is not
        # generated at the same time as the `activation_key` and the results is based on
        # the timestamp.
        self.assertTrue(activation_url in mail.outbox[1].body)

        # Call the url to activate the account
        response = self.client.get(activation_url, follow=True)
        self.assertRedirects(response, reverse("django_registration_activation_complete"))
        self.assertContains(response, "account is now active")
        # Now the user is active
        user = get_user_model().objects.get(username=self.registration_data["username"])
        self.assertTrue(user.is_active)
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)

        # Make sure the activation link can be use multiple time within the
        # `ACCOUNT_ACTIVATION_DAYS` period.
        response = self.client.get(activation_url, follow=True)
        self.assertContains(response, "account is now active")

    def test_user_registration_activate_wrong_key(self):
        activation_url = reverse("django_registration_activate", args=["wrong_key"])
        response = self.client.get(activation_url)
        self.assertContains(response, "Error during your account activation")

    def test_user_registration_default_groups(self):
        for group_name in REGISTRATION_DEFAULT_GROUPS:
            Group.objects.create(name=group_name)

        url = reverse("django_registration_register")
        self.client.post(url, self.registration_data, follow=True)

        new_user = get_user_model().objects.get(username=self.registration_data["username"])
        self.assertEqual(len(REGISTRATION_DEFAULT_GROUPS), new_user.groups.count())

    @override_settings(REGISTRATION_OPEN=False)
    def test_user_registration_closed(self):
        resp = self.client.get(reverse("django_registration_register"))
        self.assertRedirects(resp, reverse("django_registration_disallowed"))
