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

    def __init__(self, dataspace):
        if not dataspace:
            raise ValueError("Dataspace must be provided.")
        self.dataspace = dataspace
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

    def post(self, url, data):
        response = self.session.post(url, json=data, timeout=self.default_timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as err:
            logger.error(f"HTTP error during POST to {url}: {err}\nResponse body: {response.text}")
            raise

        return response.json()

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
