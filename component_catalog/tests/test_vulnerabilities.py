#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import io
import json
from pathlib import Path
from unittest import mock

from django.test import TestCase

from component_catalog.models import Package
from component_catalog.tests import make_package
from component_catalog.vulnerabilities import fetch_for_queryset
from component_catalog.vulnerabilities import fetch_from_vulnerablecode
from dje.models import Dataspace


class VulnerabilitiesTestCase(TestCase):
    data = Path(__file__).parent / "testfiles"

    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    @mock.patch("component_catalog.vulnerabilities.fetch_for_queryset")
    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.is_configured")
    def test_vulnerabilities_fetch_from_vulnerablecode(
        self, mock_is_configured, mock_fetch_for_queryset
    ):
        buffer = io.StringIO()
        make_package(self.dataspace, package_url="pkg:pypi/idna@3.6")
        make_package(self.dataspace, package_url="pkg:pypi/idna@2.0")
        mock_is_configured.return_value = True
        mock_fetch_for_queryset.return_value = 2
        fetch_from_vulnerablecode(self.dataspace, batch_size=1, timeout=None, log_func=buffer.write)
        expected = "2 Packages in the queue.+ Created 2 vulnerabilitiesCompleted in 0 seconds"
        self.assertEqual(expected, buffer.getvalue())
        self.dataspace.refresh_from_db()
        self.assertIsNotNone(self.dataspace.vulnerabilities_updated_at)

    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.bulk_search_by_purl")
    def test_vulnerabilities_fetch_for_queryset(self, mock_bulk_search_by_purl):
        buffer = io.StringIO()
        package1 = make_package(self.dataspace, package_url="pkg:pypi/idna@3.6")
        make_package(self.dataspace, package_url="pkg:pypi/idna@2.0")
        queryset = Package.objects.scope(self.dataspace)
        response_file = self.data / "vulnerabilities" / "idna_3.6_response.json"
        response_json = json.loads(response_file.read_text())
        mock_bulk_search_by_purl.return_value = response_json["results"]

        created_vulnerabilities = fetch_for_queryset(
            queryset, self.dataspace, batch_size=1, log_func=buffer.write
        )
        self.assertEqual(1, created_vulnerabilities)
        self.assertEqual("Progress: 1/2Progress: 2/2", buffer.getvalue())
        self.assertEqual(1, package1.affected_by_vulnerabilities.count())
        vulnerability = package1.affected_by_vulnerabilities.get()
        self.assertEqual("VCID-j3au-usaz-aaag", vulnerability.vulnerability_id)
