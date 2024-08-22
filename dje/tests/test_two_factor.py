#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

import django_otp
from django_otp.forms import OTPTokenForm
from django_otp.oath import totp as oauth_totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from dje.models import Dataspace
from dje.tests import create_user


class TwoFactorAuthenticationTestCase(TestCase):
    def setUp(self):
        self.login_url = reverse("login")
        self.login_redirect_url = reverse(settings.LOGIN_REDIRECT_URL)
        self.profile_url = reverse("account_profile")
        self.tfa_enable_url = reverse("account_2fa_enable")
        self.tfa_disable_url = reverse("account_2fa_disable")
        self.tfa_verify_url = reverse("account_2fa_verify")

        self.dataspace = Dataspace.objects.create(name="nexB")
        self.user = create_user("user", self.dataspace)

    @staticmethod
    def _create_device(user):
        return TOTPDevice.objects.create(user=user, name="default")

    @staticmethod
    def _get_valid_token(bin_key):
        return oauth_totp(bin_key)

    def test_two_factor_authentication_django_otp_utils(self):
        self.assertFalse(list(django_otp.devices_for_user(self.user)))
        self.assertFalse(django_otp.user_has_device(self.user))

        device = self._create_device(self.user)
        devices = list(django_otp.devices_for_user(self.user))
        self.assertEqual(1, len(devices))
        self.assertEqual(device, devices[0])
        self.assertTrue(django_otp.user_has_device(self.user))

    def test_two_factor_authentication_enable_2fa(self):
        response = self.client.get(self.tfa_enable_url)
        self.assertRedirects(response, f"{self.login_url}?next={self.tfa_enable_url}")

        self.client.login(username=self.user.username, password="secret")

        response = self.client.get(self.profile_url)
        self.assertContains(response, "Enable two-factor authentication")
        self.assertContains(response, self.tfa_enable_url)
        self.assertNotContains(response, self.tfa_disable_url)

        response = self.client.get(self.tfa_enable_url)
        expected = (
            '<input type="number" name="token" min="0" max="999999" '
            'class="input-block-level numberinput form-control" '
            'placeholder="Authentication token" autofocus="True" required '
            'id="id_token">'
        )
        self.assertContains(response, expected, html=True)
        expected = (
            '<input type="submit" name="submit" value="Enable two-factor" '
            'class="btn btn-primary" id="submit-id-submit">'
        )
        self.assertContains(response, expected, html=True)
        expected = '<svg width="53mm" height="53mm" version="1.1"'
        self.assertContains(response, expected)

        data = {}
        response = self.client.post(self.tfa_enable_url, data=data)
        self.assertContains(response, "This field is required.")

        data = {"token": "123456"}
        response = self.client.post(self.tfa_enable_url, data=data)
        form_error = (
            "<strong>Invalid token. Please make sure you have entered it correctly.</strong>"
        )
        self.assertContains(response, form_error, html=True)

        bin_key = response.context_data["form"].bin_key
        valid_token = self._get_valid_token(bin_key)
        data = {"token": valid_token}
        response = self.client.post(self.tfa_enable_url, data=data, follow=True)
        self.assertContains(response, "Two-factor authentication enabled")
        self.assertTrue(django_otp.user_has_device(self.user))
        devices = list(django_otp.devices_for_user(self.user))
        self.assertEqual(1, len(devices))

        response = self.client.get(self.tfa_enable_url)
        self.assertRedirects(response, self.profile_url)

    def test_two_factor_authentication_disable_2fa(self):
        response = self.client.get(self.tfa_disable_url)
        self.assertRedirects(response, f"{self.login_url}?next={self.tfa_disable_url}")

        self.client.login(username=self.user.username, password="secret")

        self.assertFalse(django_otp.user_has_device(self.user))
        response = self.client.get(self.tfa_disable_url)
        self.assertRedirects(response, self.profile_url)

        device = self._create_device(self.user)
        response = self.client.get(self.profile_url)
        self.assertContains(response, "Disable two-factor authentication")
        self.assertNotContains(response, self.tfa_enable_url)
        self.assertContains(response, self.tfa_disable_url)

        response = self.client.get(self.tfa_disable_url)
        expected = (
            '<input type="text" name="otp_token" autocomplete="off" class="input-block-level '
            'textinput form-control" placeholder="Authentication token" autofocus="True" '
            'id="id_otp_token">'
        )
        self.assertContains(response, expected, html=True)
        expected = (
            '<input type="submit" name="submit" value="Disable two-factor" '
            'class="btn btn-primary btn-danger" id="submit-id-submit">'
        )
        self.assertContains(response, expected, html=True)

        data = {}
        response = self.client.post(self.tfa_disable_url, data=data)
        self.assertContains(response, "Please enter your OTP token.")

        data = {"otp_token": "123456"}
        response = self.client.post(self.tfa_disable_url, data=data)
        form_error = "Invalid token. Please make sure you have entered it correctly."
        self.assertContains(response, form_error)

        device.refresh_from_db()
        self.assertEqual(1, device.throttling_failure_count)
        self.assertTrue(device.throttling_failure_timestamp)
        # We need to reset the failure for the following token to be valid
        device.throttling_failure_count = 0
        device.throttling_failure_timestamp = None
        device.save()

        valid_token = self._get_valid_token(device.bin_key)
        device_form_value = OTPTokenForm.device_choices(self.user)[0][0]
        data = {
            "otp_token": valid_token,
            "otp_device": device_form_value,
        }
        response = self.client.post(self.tfa_disable_url, data=data, follow=True)
        self.assertContains(response, "Two-factor authentication disabled")
        self.assertFalse(django_otp.user_has_device(self.user))

    def test_two_factor_authentication_login_with_2fa(self):
        response = self.client.post(self.tfa_verify_url, data={})
        self.assertEqual(404, response.status_code)

        self.assertFalse(django_otp.user_has_device(self.user))
        data = {"username": self.user.username, "password": "secret"}
        response = self.client.post(self.login_url, data=data)
        self.assertRedirects(response, self.login_redirect_url)
        self.client.logout()

        device = self._create_device(self.user)
        data = {"username": self.user.username, "password": "secret"}
        response = self.client.post(self.login_url, data=data)
        self.assertRedirects(response, self.tfa_verify_url)
        session_keys = self.client.session.keys()
        self.assertIn("_2fa_user_id", session_keys)
        self.assertIn("_auth_user_backend", session_keys)

        data = {}
        response = self.client.post(self.tfa_verify_url, data=data)
        self.assertContains(response, "Please enter your OTP token.")

        valid_token = self._get_valid_token(device.bin_key)
        device_form_value = OTPTokenForm.device_choices(self.user)[0][0]
        data = {
            "otp_token": valid_token,
            "otp_device": device_form_value,
        }
        response = self.client.post(self.tfa_verify_url, data=data)
        self.assertRedirects(response, self.login_redirect_url)
        session_keys = self.client.session.keys()
        self.assertIn("_auth_user_backend", session_keys)
        self.assertIn("_auth_user_id", session_keys)
        self.assertIn("_auth_user_hash", session_keys)
        self.assertIn("otp_device_id", session_keys)
