#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest import mock

from django.test import TestCase

from dejacode_toolkit.purldb import PurlDB
from dje.models import Dataspace
from dje.tests import create_user


class PurlDBToolkitTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Dataspace")
        self.basic_user = create_user("basic_user", self.dataspace)

    @mock.patch("dejacode_toolkit.purldb.PurlDB.request_get")
    def test_purldb_toolkit_get_package_list(self, mock_request_get):
        purldb = PurlDB(self.basic_user)
        purldb.package_api_url = "/api/packages/"
        get_package_list = purldb.get_package_list

        get_package_list()
        mock_request_get.assert_called_with("/api/packages/", params={}, timeout=None)

        get_package_list(
            page_size=1,
            page=1,
            timeout=3,
            extra_payload={"extra": "payload"},
        )
        mock_request_get.assert_called_with(
            "/api/packages/",
            params={"page_size": 1, "page": 1, "extra": "payload"},
            timeout=3,
        )

        get_package_list(search="package_name")
        mock_request_get.assert_called_with(
            "/api/packages/", params={"search": "package_name"}, timeout=None
        )

        get_package_list(search="pkg:type/name@1.0")
        mock_request_get.assert_called_with(
            "/api/packages/", params={"purl": "pkg:type/name@1.0"}, timeout=None
        )

        get_package_list(search="type/name@1.0")
        mock_request_get.assert_called_with(
            "/api/packages/", params={"purl": "type/name@1.0"}, timeout=None
        )
