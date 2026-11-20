#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging

from django.conf import settings

import requests

logger = logging.getLogger("dje")

DEJACODE_SITE_URL = settings.SITE_URL.rstrip("/")


class BaseIntegration:
    """Base class for managing issue tracker integrations from DejaCode requests."""

    default_timeout = 10
    open_status = "open"
    closed_status = "closed"
    # Dataspace configuration field holding the only base URL the credentials are sent to.
    base_url_field_name = None

    def __init__(self, dataspace, timeout=None):
        if not dataspace:
            raise ValueError("Dataspace must be provided.")
        self.dataspace = dataspace
        self.timeout = timeout or self.default_timeout
        self.session = self.get_session()

    def get_session(self):
        session = requests.Session()
        session.headers.update(self.get_headers())
        return session

    def get_headers(self):
        """
        Return authentication headers specific to the integration.
        Must be implemented in subclasses.
        """
        raise NotImplementedError

    def is_allowed_url(self, url):
        """Return True if the integration credentials can be sent to the `url`."""
        if not self.base_url_field_name:
            return True

        base_url = self.dataspace.get_configuration(self.base_url_field_name)
        if not base_url:
            return False

        base_url = base_url.rstrip("/")
        return url == base_url or url.startswith(f"{base_url}/")

    def request(self, method, url, params=None, data=None, json=None):
        """Send a HTTP request."""
        if not self.is_allowed_url(url):
            raise ValueError(
                f"The {url} URL does not match the {self.base_url_field_name} set on the Dataspace."
            )

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                json=json,
                timeout=self.timeout,
            )
        except requests.Timeout:
            logger.warning(f"Timeout occurred during {method} request to {url}")
            raise

        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            self._log_http_error(method, url, response, error)
            raise

        # If there's no content (e.g. 204 No Content), return None
        if response.status_code == 204:
            return

        return response.json()

    def _log_http_error(self, method, url, response, error):
        """Log HTTP errors with detailed information."""
        logger.error(
            f"[{self.dataspace}] HTTP error during {method} request to {url}: {error}\n"
            f"Response status code: {response.status_code}\n"
            f"Response body: {response.text}"
        )

    def get(self, url, params=None):
        """Send a GET request."""
        return self.request("GET", url, params=params)

    def post(self, url, json=None):
        """Send a POST request."""
        return self.request("POST", url, json=json)

    def put(self, url, json=None):
        """Send a PUT request."""
        return self.request("PUT", url, json=json)

    def patch(self, url, json=None):
        """Send a PATCH request."""
        return self.request("PATCH", url, json=json)

    def sync(self, request):
        """Sync the given request by creating or updating an external issue."""
        raise NotImplementedError

    def post_comment(self, repo_id, issue_id, comment_body, base_url=None):
        """Post a comment on an external issue."""
        raise NotImplementedError

    def get_status(self, request):
        if request.is_closed:
            return self.closed_status
        return self.open_status

    @staticmethod
    def make_issue_title(request):
        return f"[DEJACODE] {request.title}"

    @staticmethod
    def make_issue_body(request):
        request_url = f"{DEJACODE_SITE_URL}{request.get_absolute_url()}"
        label_fields = [
            ("📝 Request Template", request.request_template),
            ("📦 Product Context", request.product_context),
            ("📌 Applies To", request.content_object),
            ("🙋 Submitted By", request.requester),
            ("👤 Assigned To", request.assignee),
            ("🚨 Priority", request.priority),
            ("🗒️ Notes", request.notes),
            ("🔗️ DejaCode URL", request_url),
        ]

        lines = []
        for label, value in label_fields:
            if value:
                lines.append(f"### {label}\n{value}")

        lines.append("----")

        for question in request.get_serialized_data_as_list():
            label = question.get("label")
            value = question.get("value")
            input_type = question.get("input_type")

            if input_type == "BooleanField":
                value = "Yes" if str(value).lower() in ("1", "true", "yes") else "No"

            lines.append(f"### {label}\n{value}")

        return "\n\n".join(lines)
