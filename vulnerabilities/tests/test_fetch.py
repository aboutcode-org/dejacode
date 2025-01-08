#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import io
import json
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.test import TestCase

from notifications.models import Notification

from component_catalog.models import Package
from component_catalog.tests import make_package
from dje.models import Dataspace
from dje.tests import create_user
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_item_purpose
from product_portfolio.tests import make_product_package
from vulnerabilities.fetch import fetch_for_packages
from vulnerabilities.fetch import fetch_from_vulnerablecode
from vulnerabilities.fetch import notify_vulnerability_data_update


class VulnerabilitiesFetchTestCase(TestCase):
    data = Path(__file__).parent / "data"

    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    @mock.patch("vulnerabilities.fetch.fetch_for_packages")
    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.is_configured")
    def test_vulnerabilities_fetch_from_vulnerablecode(
        self, mock_is_configured, mock_fetch_for_packages
    ):
        buffer = io.StringIO()
        make_package(self.dataspace, package_url="pkg:pypi/idna@3.6")
        make_package(self.dataspace, package_url="pkg:pypi/idna@2.0")
        mock_is_configured.return_value = True
        mock_fetch_for_packages.return_value = {"created": 2, "updated": 0}
        fetch_from_vulnerablecode(
            self.dataspace, batch_size=1, update=True, timeout=None, log_func=buffer.write
        )
        expected = (
            "2 Packages in the queue."
            "+ Created 2 vulnerabilities"
            "+ Updated 0 vulnerabilities"
            "Completed in 0 seconds"
        )
        self.assertEqual(expected, buffer.getvalue())
        self.dataspace.refresh_from_db()
        self.assertIsNotNone(self.dataspace.vulnerabilities_updated_at)

    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.bulk_search_by_purl")
    def test_vulnerabilities_fetch_for_packages(self, mock_bulk_search_by_purl):
        buffer = io.StringIO()
        package1 = make_package(self.dataspace, package_url="pkg:pypi/idna@3.6")
        product1 = make_product(self.dataspace)
        pp1 = make_product_package(product1, package=package1)
        queryset = Package.objects.scope(self.dataspace)
        response_file = self.data / "vulnerabilities" / "idna_3.6_response.json"
        response_json = json.loads(response_file.read_text())
        mock_bulk_search_by_purl.return_value = response_json["results"]

        results = fetch_for_packages(
            queryset, self.dataspace, batch_size=1, update=True, log_func=buffer.write
        )
        self.assertEqual(results, {"created": 1, "updated": 0})

        self.assertEqual("Progress: 1/1", buffer.getvalue())
        self.assertEqual(1, package1.affected_by_vulnerabilities.count())
        vulnerability = package1.affected_by_vulnerabilities.get()
        self.assertEqual("VCID-j3au-usaz-aaag", vulnerability.vulnerability_id)
        self.assertEqual(Decimal("2.0"), vulnerability.exploitability)
        self.assertEqual(Decimal("4.2"), vulnerability.weighted_severity)
        self.assertEqual(Decimal("8.4"), vulnerability.risk_score)
        package1.refresh_from_db()
        pp1.refresh_from_db()
        self.assertEqual(Decimal("8.4"), package1.risk_score)
        self.assertEqual(Decimal("8.4"), pp1.weighted_risk_score)

        # Update
        purpose1 = make_product_item_purpose(self.dataspace, exposure_factor=0.5)
        pp1.raw_update(purpose=purpose1)
        response_json["results"][0]["affected_by_vulnerabilities"][0]["risk_score"] = 10.0
        mock_bulk_search_by_purl.return_value = response_json["results"]
        results = fetch_for_packages(
            queryset, self.dataspace, batch_size=1, update=True, log_func=buffer.write
        )
        self.assertEqual(results, {"created": 0, "updated": 1})
        vulnerability = package1.affected_by_vulnerabilities.get()
        self.assertEqual(Decimal("10.0"), vulnerability.risk_score)
        package1.refresh_from_db()
        pp1.refresh_from_db()
        self.assertEqual(Decimal("8.4"), package1.risk_score)
        self.assertEqual(Decimal("4.2"), pp1.weighted_risk_score)

    @mock.patch("vulnerabilities.fetch.find_and_fire_hook")
    def test_vulnerabilities_fetch_notify_vulnerability_data_update(self, mock_fire_hook):
        notify_vulnerability_data_update(self.dataspace)
        mock_fire_hook.assert_not_called()
        self.assertEqual(0, Notification.objects.count())

        make_package(self.dataspace, is_vulnerable=True)
        create_user("test", self.dataspace, vulnerability_impact_notification=True)
        notify_vulnerability_data_update(self.dataspace)
        mock_fire_hook.assert_called_once()
        self.assertEqual(1, Notification.objects.count())
        notification = Notification.objects.get()
        self.assertEqual("New vulnerabilities detected", notification.verb)
