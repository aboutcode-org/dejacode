#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging
from os import getenv

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

import requests

logger = logging.getLogger("dejacode_toolkit")


def get_settings(var_name, default=None):
    """Return the settings value from the environment or Django settings."""
    return getenv(var_name) or getattr(settings, var_name, default)


def is_service_available(label, session, url, raise_exceptions):
    """Check if a configured integration service is available."""
    try:
        response = session.head(url, timeout=5)
        response.raise_for_status()
    except requests.exceptions.RequestException as request_exception:
        logger.debug(f"{label} is_available() error: {request_exception}")
        if raise_exceptions:
            raise
        return False

    return response.status_code == requests.codes.ok


class BaseService:
    label = None
    settings_prefix = None
    url_field_name = None
    api_key_field_name = None
    default_timeout = 5

    def __init__(self, dataspace):
        if not dataspace:
            raise ValueError("Dataspace must be provided.")

        self.service_url = None
        self.service_api_key = None
        self.basic_auth_user = None
        self.basic_auth_password = None

        try:
            dataspace_configuration = dataspace.configuration
        except ObjectDoesNotExist:
            dataspace_configuration = None

        # Take the integration settings from the Dataspace when defined
        if dataspace_configuration:
            self.service_url = getattr(
                dataspace_configuration, self.url_field_name)
            self.service_api_key = getattr(
                dataspace_configuration, self.api_key_field_name)

        # Fallback on the global application settings
        if not self.service_url:
            self.service_url = get_settings(
                f"{self.settings_prefix}_URL", default="")
            self.service_api_key = get_settings(
                f"{self.settings_prefix}_API_KEY")
            # Basic Authentication only available with configuration through settings
            self.basic_auth_user = get_settings(f"{self.settings_prefix}_USER")
            self.basic_auth_password = get_settings(
                f"{self.settings_prefix}_PASSWORD")

        self.api_url = f'{self.service_url.rstrip("/")}/api/'

    def get_session(self):
        session = requests.Session()

        if self.service_api_key:
            session.headers.update(
                {"Authorization": f"Token {self.service_api_key}"})

        basic_auth_enabled = self.basic_auth_user and self.basic_auth_password
        if basic_auth_enabled:
            session.auth = (self.basic_auth_user, self.basic_auth_password)

        return session

    @property
    def session(self):
        return self.get_session()

    def is_configured(self):
        """Return True if the ``service_url`` is set."""
        if self.service_url:
            return True
        return False

    def is_available(self, raise_exceptions=False):
        """Return True if the configured service is available."""
        if not self.is_configured():
            return False

        return is_service_available(self.label, self.session, self.api_url, raise_exceptions)

    def request_get(self, url, **kwargs):
        """Wrap the HTTP request calls on the API."""
        if not url:
            return

        if "timeout" not in kwargs:
            kwargs["timeout"] = self.default_timeout

        params = kwargs.get("params")
        if params and "format" not in params:
            params["format"] = "json"

        logger.debug(f"{self.label}: url={url} params={params}")
        try:
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError, TypeError) as exception:
            logger.error(f"{self.label} [Exception] {exception}")

    def request_post(self, url, **kwargs):
        """Return the response from a HTTP POST request on the provided `url` ."""
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.default_timeout

        # Do not `raise_for_status` as the response may contain valuable data
        # even on non 200 status code.
        try:
            response = self.session.post(url, **kwargs)
            return response.json()
        except (requests.RequestException, ValueError, TypeError) as exception:
            logger.error(f"{self.label} [Exception] {exception}")
