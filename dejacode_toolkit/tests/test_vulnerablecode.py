#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import io
from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch

import urllib3.connectionpool
from requests.adapters import HTTPAdapter
from urllib3.response import HTTPResponse
from urllib3.util.retry import Retry

from dejacode_toolkit.vulnerablecode import VulnerableCode


def make_dataspace(vulnerablecode_url="https://public.vulnerablecode.io"):
    config = MagicMock()
    config.vulnerablecode_url = vulnerablecode_url
    dataspace = MagicMock()
    dataspace.get_configuration.return_value = config
    return dataspace


def make_urllib3_response(status, body=b"", headers=None):
    return HTTPResponse(
        body=io.BytesIO(body),
        headers=headers or {},
        status=status,
        preload_content=False,
    )


class VulnerableCodenTestCase(TestCase):
    def setUp(self):
        self.service = VulnerableCode(make_dataspace())

    def test_get_session_retry_configuration(self):
        session = self.service.get_session()
        adapter = session.get_adapter("https://example.com")

        self.assertIsInstance(adapter, HTTPAdapter)
        self.assertIsInstance(adapter.max_retries, Retry)
        self.assertEqual(adapter.max_retries.total, 3)
        self.assertIn(429, adapter.max_retries.status_forcelist)
        self.assertIn("POST", adapter.max_retries.allowed_methods)
        self.assertTrue(adapter.max_retries.respect_retry_after_header)

    @patch.object(urllib3.connectionpool.HTTPSConnectionPool, "_get_conn")
    @patch.object(urllib3.connectionpool.HTTPSConnectionPool, "_make_request")
    def test_bulk_search_by_purl_retries_on_429(self, mock_make_request, mock_get_conn):
        # _get_conn is mocked to prevent any real TCP connection attempt.
        mock_get_conn.return_value = MagicMock()

        # _make_request is called once per attempt inside urllib3's retry loop,
        # so two side_effect values simulate: 429 on first try, 200 on retry.
        mock_make_request.side_effect = [
            make_urllib3_response(
                429,
                headers={"Retry-After": "0"},
            ),
            make_urllib3_response(
                200,
                body=b'{"count": 1, "results": [{"purl": "pkg:pypi/django@4.2"}]}',
                headers={"Content-Type": "application/json"},
            ),
        ]

        result = self.service.bulk_search_by_purl(purls=["pkg:pypi/django@4.2"])

        self.assertEqual(mock_make_request.call_count, 2)
        self.assertIsNotNone(result)
        self.assertEqual(result["count"], 1)
