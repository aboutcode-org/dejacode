#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import logging
import zoneinfo
from datetime import datetime

from django.http import Http404
from django.utils import timezone


class APILoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("dejacode.api")

    def __call__(self, request):
        response = self.get_response(request)

        if request.path.startswith("/api/"):
            self.log_as_json(request, response)

        return response

    def log_as_json(self, request, response):
        """Log selected data from the `request` and `response` as json."""
        data = {
            "user": request.user.username,
            "dataspace": str(getattr(request.user, "dataspace", "")),
            "date": str(datetime.now()),
            "remote_address": request.META.get("REMOTE_ADDR", ""),
            "method": request.method,
            "path": request.path,
            "query_string": request.META.get("QUERY_STRING", ""),
            "status_code": response.status_code,
            "http_referer": request.META.get("HTTP_REFERER", ""),
        }
        self.logger.info(json.dumps(data))


class LastAPIAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.path.startswith("/api/"):
            self.update_last_api_access(request.user)

        return response

    @staticmethod
    def update_last_api_access(user):
        """
        Update the last_api_access date for the user requesting the API.
        Limited to 1 update per hour to avoid un-necessary DB queries.
        """
        if not hasattr(user, "last_api_access"):  # AnonymousUser
            return

        now = timezone.now()
        if not user.last_api_access or now > user.last_api_access + timezone.timedelta(hours=1):
            user.last_api_access = now
            user.save(update_fields=["last_api_access"])


class ProhibitInQueryStringMiddleware:
    """Protect from special characters vulnerability attacks."""

    prohibited_strings = [
        "%00",  # Null character
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # This check needs to be executed before the view.
        query_string = request.META.get("QUERY_STRING", "")
        for string in self.prohibited_strings:
            if string in query_string:
                raise Http404

        return self.get_response(request)


def validate_timezone(tz):
    """Return a valid timezone or None if invalid."""
    try:
        return zoneinfo.ZoneInfo(tz).key
    except (zoneinfo.ZoneInfoNotFoundError, TypeError, ValueError):
        return


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz = self.get_timezone_from_request(request)

        if tz:
            timezone.activate(zoneinfo.ZoneInfo(tz))
        else:
            timezone.deactivate()

        return self.get_response(request)

    @staticmethod
    def get_timezone_from_request(request):
        """
        Determine the appropriate timezone for the request, prioritizing user settings
        but falling back to the browser's timezone if necessary.
        """
        # 1. Try user profile timezone (if authenticated)
        if request.user.is_authenticated:
            if tz := validate_timezone(request.user.timezone):
                return tz

        # 2. Fallback to browser timezone from cookie
        return validate_timezone(request.COOKIES.get("client_timezone"))
