#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
from pathlib import Path
from unittest import mock

from django.test import TestCase

from component_catalog.models import Package
from component_catalog.tests import make_component
from component_catalog.tests import make_package
from dejacode_toolkit.vulnerablecode import VulnerableCode
from dje.models import Dataspace
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_package
from vulnerabilities.models import Vulnerability
from vulnerabilities.models import VulnerabilityAnalysis
from vulnerabilities.tests import make_vulnerability


class VulnerabilitiesModelsTestCase(TestCase):
    data = Path(__file__).parent / "data"

    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.request_get")
    def test_vulnerability_mixin_get_entry_for_package(self, mock_request_get):
        vulnerablecode = VulnerableCode(self.dataspace)
        package1 = make_package(self.dataspace, package_url="pkg:composer/guzzlehttp/psr7@1.9.0")
        response_file = self.data / "vulnerabilities" / "idna_3.6_response.json"
        mock_request_get.return_value = json.loads(response_file.read_text())

        affected_by_vulnerabilities = package1.get_entry_for_package(vulnerablecode)
        self.assertEqual(1, len(affected_by_vulnerabilities))
        self.assertEqual("VCID-j3au-usaz-aaag", affected_by_vulnerabilities[0]["vulnerability_id"])

    @mock.patch("vulnerabilities.models.AffectedByVulnerabilityMixin.get_entry_for_package")
    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.is_configured")
    def test_vulnerability_mixin_get_entry_from_vulnerablecode(
        self, mock_is_configured, mock_get_entry_for_package
    ):
        package1 = make_package(self.dataspace, package_url="pkg:pypi/idna@3.6")
        self.assertIsNone(package1.get_entry_from_vulnerablecode())

        mock_get_entry_for_package.return_value = None
        self.dataspace.enable_vulnerablecodedb_access = True
        self.dataspace.save()
        mock_is_configured.return_value = True
        package1.get_entry_from_vulnerablecode()
        mock_get_entry_for_package.assert_called_once()

    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.request_get")
    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.is_configured")
    def test_vulnerability_mixin_fetch_vulnerabilities(self, mock_is_configured, mock_request_get):
        mock_is_configured.return_value = True
        self.dataspace.enable_vulnerablecodedb_access = True
        self.dataspace.save()
        response_file = self.data / "vulnerabilities" / "idna_3.6_response.json"
        mock_request_get.return_value = json.loads(response_file.read_text())

        package1 = make_package(self.dataspace, package_url="pkg:pypi/idna@3.6")
        package1.fetch_vulnerabilities()

        self.assertEqual(1, Vulnerability.objects.scope(self.dataspace).count())
        self.assertEqual(1, package1.affected_by_vulnerabilities.count())
        vulnerability = package1.affected_by_vulnerabilities.get()
        self.assertEqual("VCID-j3au-usaz-aaag", vulnerability.vulnerability_id)

    def test_vulnerability_mixin_create_vulnerabilities(self):
        response_file = self.data / "vulnerabilities" / "idna_3.6_response.json"
        response_json = json.loads(response_file.read_text())
        vulnerabilities_data = response_json["results"][0]["affected_by_vulnerabilities"]

        package1 = make_package(self.dataspace, package_url="pkg:pypi/idna@3.6")
        package1.create_vulnerabilities(vulnerabilities_data)

        self.assertEqual(1, Vulnerability.objects.scope(self.dataspace).count())
        self.assertEqual(1, package1.affected_by_vulnerabilities.count())
        vulnerability = package1.affected_by_vulnerabilities.get()
        self.assertEqual("VCID-j3au-usaz-aaag", vulnerability.vulnerability_id)

    def test_vulnerability_model_affected_packages_m2m(self):
        package1 = make_package(self.dataspace)
        vulnerability1 = make_vulnerability(dataspace=self.dataspace, affecting=package1)
        self.assertEqual(package1, vulnerability1.affected_packages.get())
        self.assertEqual(vulnerability1, package1.affected_by_vulnerabilities.get())

    def test_vulnerability_model_affected_by_vulnerability_relationship_delete(self):
        package1 = make_package(self.dataspace)
        vulnerability1 = make_vulnerability(dataspace=self.dataspace, affecting=package1)
        package1.delete()
        self.assertEqual(vulnerability1, Vulnerability.objects.get())
        self.assertEqual(0, Package.objects.count())

        package1 = make_package(self.dataspace)
        vulnerability1.add_affected(package1)
        vulnerability1.delete()
        self.assertEqual(package1, Package.objects.get())
        self.assertEqual(0, Vulnerability.objects.count())

    def test_vulnerability_model_add_affected(self):
        vulnerability1 = make_vulnerability(dataspace=self.dataspace)
        package1 = make_package(self.dataspace)
        package2 = make_package(self.dataspace)
        vulnerability1.add_affected(package1)
        vulnerability1.add_affected([package2])
        self.assertEqual(2, vulnerability1.affected_packages.count())

        vulnerability2 = make_vulnerability(dataspace=self.dataspace)
        component1 = make_component(self.dataspace)
        vulnerability2.add_affected([component1, package1])
        self.assertQuerySetEqual(vulnerability2.affected_packages.all(), [package1])
        self.assertQuerySetEqual(vulnerability2.affected_components.all(), [component1])

    def test_vulnerability_model_fixed_packages_count_generated_field(self):
        vulnerability1 = make_vulnerability(dataspace=self.dataspace)
        self.assertEqual(0, vulnerability1.fixed_packages_count)

        vulnerability1.fixed_packages = [
            {"purl": "pkg:pypi/gitpython@3.1.41", "is_vulnerable": True},
            {"purl": "pkg:pypi/gitpython@3.2", "is_vulnerable": False},
        ]
        vulnerability1.save()
        vulnerability1.refresh_from_db()
        self.assertEqual(2, vulnerability1.fixed_packages_count)

    def test_vulnerability_model_create_from_data(self):
        package1 = make_package(self.dataspace)
        vulnerability_data = {
            "vulnerability_id": "VCID-q4q6-yfng-aaag",
            "summary": "In Django 3.2 before 3.2.25, 4.2 before 4.2.11, and 5.0.",
            "aliases": ["CVE-2024-27351", "GHSA-vm8q-m57g-pff3", "PYSEC-2024-47"],
            "references": [
                {
                    "reference_url": "https://access.redhat.com/hydra/rest/"
                    "securitydata/cve/CVE-2024-27351.json",
                    "reference_id": "",
                    "scores": [
                        {
                            "value": "7.5",
                            "scoring_system": "cvssv3",
                            "scoring_elements": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H",
                        }
                    ],
                },
            ],
            "resource_url": "http://public.vulnerablecode.io/vulnerabilities/VCID-q4q6-yfng-aaag",
        }

        vulnerability1 = Vulnerability.create_from_data(
            dataspace=self.dataspace,
            data=vulnerability_data,
            affecting=package1,
        )
        self.assertEqual(vulnerability_data["vulnerability_id"], vulnerability1.vulnerability_id)
        self.assertEqual(vulnerability_data["summary"], vulnerability1.summary)
        self.assertEqual(vulnerability_data["aliases"], vulnerability1.aliases)
        self.assertEqual(vulnerability_data["references"], vulnerability1.references)
        self.assertEqual(vulnerability_data["resource_url"], vulnerability1.resource_url)
        self.assertQuerySetEqual(vulnerability1.affected_packages.all(), [package1])

    def test_vulnerability_model_queryset_count_methods(self):
        package1 = make_package(self.dataspace)
        package2 = make_package(self.dataspace)
        vulnerability1 = make_vulnerability(dataspace=self.dataspace)
        vulnerability1.add_affected([package1, package2])
        make_product(self.dataspace, inventory=[package1, package2])

        qs = (
            Vulnerability.objects.scope(self.dataspace)
            .with_affected_products_count()
            .with_affected_packages_count()
        )
        self.assertEqual(2, qs[0].affected_packages_count)
        self.assertEqual(1, qs[0].affected_products_count)

    def test_vulnerability_model_as_cyclonedx(self):
        response_file = self.data / "vulnerabilities" / "idna_3.6_response.json"
        json_data = json.loads(response_file.read_text())
        affected_by_vulnerabilities = json_data["results"][0]["affected_by_vulnerabilities"]
        vulnerability1 = Vulnerability.create_from_data(
            dataspace=self.dataspace,
            data=affected_by_vulnerabilities[0],
        )
        package1 = make_package(
            self.dataspace,
            package_url="pkg:type/name@1.9.0",
            uuid="dd0afd00-89bd-46d6-b1f0-57b553c44d32",
        )

        vulnerability1_as_cdx = vulnerability1.as_cyclonedx(affected_instances=[package1])
        as_dict = json.loads(vulnerability1_as_cdx.as_json())
        as_dict.pop("ratings", None)  # The sorting is inconsistent
        results = json.dumps(as_dict, indent=2)

        expected_location = self.data / "vulnerabilities" / "idna_3.6_as_cyclonedx.json"
        # Uncomment to regen the expected results
        # if True:
        #     expected_location.write_text(results)

        self.assertJSONEqual(results, expected_location.read_text())

        product1 = make_product(self.dataspace)
        product_package1 = make_product_package(product1, package=package1)
        analysis = VulnerabilityAnalysis(
            product_package=product_package1,
            vulnerability=vulnerability1,
            state=VulnerabilityAnalysis.State.RESOLVED,
            justification=VulnerabilityAnalysis.Justification.CODE_NOT_PRESENT,
            responses=[
                VulnerabilityAnalysis.Response.CAN_NOT_FIX,
                VulnerabilityAnalysis.Response.ROLLBACK,
            ],
            detail="detail",
            dataspace=self.dataspace,
        )
        vulnerability1_as_cdx = vulnerability1.as_cyclonedx(
            affected_instances=[package1], analysis=analysis
        )
        as_dict = json.loads(vulnerability1_as_cdx.as_json())
        expected = {
            "detail": "detail",
            "justification": "code_not_present",
            "response": ["can_not_fix", "rollback"],
            "state": "resolved",
        }
        self.assertEqual(expected, as_dict["analysis"])

    def test_vulnerability_model_vulnerability_analysis_save(self):
        vulnerability1 = make_vulnerability(dataspace=self.dataspace)
        product_package1 = make_product_package(make_product(self.dataspace))

        analysis = VulnerabilityAnalysis(
            product_package=product_package1,
            vulnerability=vulnerability1,
            dataspace=self.dataspace,
        )

        msg = "At least one of state, justification, responses or detail must be provided."
        with self.assertRaisesMessage(ValueError, msg):
            analysis.save()

        analysis.state = VulnerabilityAnalysis.State.RESOLVED
        analysis.save()

        # Refresh from db
        analysis = VulnerabilityAnalysis.objects.get(pk=analysis.pk)
        self.assertEqual(vulnerability1, analysis.vulnerability)
        self.assertEqual(product_package1, analysis.product_package)
        self.assertEqual(product_package1.product, analysis.product)
        self.assertEqual(product_package1.package, analysis.package)
        self.assertEqual(VulnerabilityAnalysis.State.RESOLVED, analysis.state)
