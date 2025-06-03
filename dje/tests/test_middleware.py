#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest.mock import MagicMock

from django.test import RequestFactory
from django.test import TestCase
from django.utils import timezone

from dje.middleware import TimezoneMiddleware
from dje.middleware import validate_timezone
from dje.models import Dataspace
from dje.tests import create_superuser


class DJEMiddlewaresTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("nexb_user", self.dataspace)

    def test_dje_middleware_prohibit_in_query_string_middleware(self):
        response = self.client.get("/?a=%00", follow=True)
        self.assertEqual(404, response.status_code)

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get("/?a=%00")
        self.assertEqual(404, response.status_code)


class TimezoneMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = TimezoneMiddleware(lambda req: req)

    def test_validate_timezone(self):
        self.assertEqual(validate_timezone("America/New_York"), "America/New_York")
        self.assertIsNone(validate_timezone("Invalid/Timezone"))
        self.assertIsNone(validate_timezone(None))

    def test_user_authenticated_with_valid_timezone(self):
        request = self.factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.timezone = "Europe/London"

        tz = self.middleware.get_timezone_from_request(request)
        self.assertEqual(tz, "Europe/London")

    def test_user_authenticated_with_invalid_timezone(self):
        request = self.factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.timezone = "Invalid/Timezone"

        tz = self.middleware.get_timezone_from_request(request)
        self.assertIsNone(tz)

    def test_user_not_authenticated_with_valid_cookie_timezone(self):
        request = self.factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = False
        request.COOKIES["client_timezone"] = "Asia/Tokyo"

        tz = self.middleware.get_timezone_from_request(request)
        self.assertEqual(tz, "Asia/Tokyo")

    def test_user_not_authenticated_with_invalid_cookie_timezone(self):
        request = self.factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = False
        request.COOKIES["client_timezone"] = "Invalid/Timezone"

        tz = self.middleware.get_timezone_from_request(request)
        self.assertIsNone(tz)

    def test_middleware_activates_valid_timezone(self):
        request = self.factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.timezone = "Europe/London"

        self.middleware(request)
        self.assertEqual(timezone.get_current_timezone_name(), "Europe/London")

    def test_middleware_deactivates_invalid_timezone(self):
        request = self.factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.timezone = "Invalid/Timezone"

        self.middleware(request)
        self.assertEqual(timezone.get_current_timezone_name(), "UTC")

    def test_middleware_uses_cookie_if_no_user_timezone(self):
        request = self.factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.timezone = None
        request.COOKIES["client_timezone"] = "Asia/Tokyo"

        self.middleware(request)
        self.assertEqual(timezone.get_current_timezone_name(), "Asia/Tokyo")
