#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
from datetime import UTC
from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import TestCase

from cyclonedx.model import bom as cyclonedx_bom

from component_catalog.tests import make_package
from dejacode import __version__ as dejacode_version
from dje import outputs
from dje.models import Dataspace
from dje.tests import create_superuser
from dje.tests import create_user
from product_portfolio.models import Product
from product_portfolio.tests import make_product_package
from vulnerabilities.tests import VulnerabilityAnalysis
from vulnerabilities.tests import make_vulnerability
from vulnerabilities.tests import make_vulnerability_analysis


class OutputsTestCase(TestCase):
    data = Path(__file__).parent / "testfiles" / "outputs"

    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.basic_user = create_user("basic_user", self.dataspace)

        self.product1 = Product.objects.create(
            name="Product1 With Space",
            version="1.0",
            uuid="b2561aa6-1092-44ef-afe2-b0b331514bab",
            dataspace=self.dataspace,
        )

    def test_outputs_safe_filename(self):
        self.assertEqual("low_-_up_", outputs.safe_filename("low -_UP*&//"))

    def test_outputs_get_attachment_response(self):
        response = outputs.get_attachment_response(
            file_content="AAA", filename="file.txt", content_type="application/json"
        )
        expected = 'attachment; filename="file.txt"'
        self.assertEqual(expected, response["Content-Disposition"])
        self.assertEqual("application/json", response["Content-Type"])

    def test_outputs_get_spdx_document(self):
        package = make_package(self.dataspace, package_url="pkg:type/name")
        make_product_package(self.product1, package)

        document = outputs.get_spdx_document(self.product1, self.super_user)
        document.creation_info.created = "2000-01-01T01:02:03Z"
        expected = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "dejacode_nexb_product_product1_with_space_1.0",
            "documentNamespace": f"https://dejacode.com/spdxdocs/{self.product1.uuid}",
            "creationInfo": {
                "created": "2000-01-01T01:02:03Z",
                "creators": [
                    "Person:   (user@email.com)",
                    "Organization: nexB ()",
                    f"Tool: DejaCode-{dejacode_version}",
                ],
                "licenseListVersion": "3.18",
            },
            "packages": [
                {
                    "name": "name",
                    "SPDXID": f"SPDXRef-dejacode-package-{package.uuid}",
                    "downloadLocation": "NOASSERTION",
                    "licenseConcluded": "NOASSERTION",
                    "copyrightText": "NOASSERTION",
                    "filesAnalyzed": False,
                    "externalRefs": [
                        {
                            "referenceCategory": "PACKAGE-MANAGER",
                            "referenceType": "purl",
                            "referenceLocator": "pkg:type/name",
                        }
                    ],
                }
            ],
            "documentDescribes": [f"SPDXRef-dejacode-package-{package.uuid}"],
        }
        self.assertEqual(expected, document.as_dict())

    def test_outputs_get_spdx_filename(self):
        document = outputs.get_spdx_document(self.product1, self.super_user)
        self.assertEqual(
            "dejacode_nexb_product_product1_with_space_1.0.spdx.json",
            outputs.get_spdx_filename(document),
        )

    def test_outputs_get_cyclonedx_bom(self):
        bom = outputs.get_cyclonedx_bom(instance=self.product1, user=self.super_user)
        self.assertIsInstance(bom, cyclonedx_bom.Bom)

    def test_outputs_get_cyclonedx_bom_include_vex(self):
        package_in_product = make_package(self.dataspace, package_url="pkg:type/name")
        product_package1 = make_product_package(self.product1, package_in_product)
        package_not_in_product = make_package(self.dataspace)
        vulnerability1 = make_vulnerability(
            self.dataspace, affecting=[package_in_product, package_not_in_product]
        )
        make_vulnerability(self.dataspace, affecting=[package_not_in_product])

        bom = outputs.get_cyclonedx_bom(
            instance=self.product1,
            user=self.super_user,
            include_vex=True,
        )
        self.assertIsInstance(bom, cyclonedx_bom.Bom)
        self.assertEqual(1, len(bom.vulnerabilities))
        self.assertEqual(vulnerability1.vulnerability_id, bom.vulnerabilities[0].id)
        self.assertIsNone(bom.vulnerabilities[0].analysis)

        analysis1 = make_vulnerability_analysis(product_package1, vulnerability1)
        bom = outputs.get_cyclonedx_bom(
            instance=self.product1,
            user=self.super_user,
            include_vex=True,
        )
        analysis = bom.vulnerabilities[0].analysis
        expected = {
            "detail": analysis1.detail,
            "justification": str(analysis1.justification),
            "response": [str(response) for response in analysis1.responses],
            "state": str(analysis1.state),
        }
        self.assertEqual(expected, json.loads(analysis.as_json()))

    def test_outputs_get_cyclonedx_bom_json(self):
        bom = outputs.get_cyclonedx_bom(instance=self.product1, user=self.super_user)
        bom_json = outputs.get_cyclonedx_bom_json(bom)
        self.assertIn('"bomFormat": "CycloneDX"', bom_json)

    def test_outputs_get_cyclonedx_filename(self):
        self.assertEqual(
            "dejacode_nexb_product_product1_with_space_1.0.cdx.json",
            outputs.get_cyclonedx_filename(instance=self.product1),
        )

    def test_outputs_get_csaf_security_advisory(self):
        package1 = make_package(self.dataspace, package_url="pkg:type/name@1.0")
        package2 = make_package(self.dataspace, package_url="pkg:type/name@2.0")
        package3 = make_package(self.dataspace, package_url="pkg:type/name@3.0")
        product_package1 = make_product_package(self.product1, package1)
        product_package2 = make_product_package(self.product1, package2)
        make_product_package(self.product1, package3)
        vulnerability1 = make_vulnerability(
            self.dataspace,
            vulnerability_id="VCID-0001",
            aliases=["CVE-1984-1010"],
            affecting=[package1],
        )
        vulnerability2 = make_vulnerability(
            self.dataspace, vulnerability_id="VCID-0002", affecting=[package2]
        )
        make_vulnerability(self.dataspace, vulnerability_id="VCID-0003", affecting=[package3])

        make_vulnerability_analysis(
            product_package1,
            vulnerability1,
            state=VulnerabilityAnalysis.State.NOT_AFFECTED,
            justification=VulnerabilityAnalysis.Justification.CODE_NOT_PRESENT,
            detail="Code is not present",
        )
        make_vulnerability_analysis(
            product_package2,
            vulnerability2,
            state=VulnerabilityAnalysis.State.EXPLOITABLE,
            responses=[VulnerabilityAnalysis.Response.UPDATE],
            is_reachable=True,
            detail="Need an update",
        )

        mock_now = datetime(2024, 12, 19, 12, 0, 0, tzinfo=UTC)
        with mock.patch("dje.outputs.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            security_advisory = outputs.get_csaf_security_advisory(self.product1)

        security_advisory_json = security_advisory.model_dump_json(indent=2, exclude_none=True)

        expected_location = self.data / "csaf_security_advisory.csaf.json"
        # if True:
        #     expected_location.write_text(security_advisory_json)

        self.assertJSONEqual(security_advisory_json, expected_location.read_text())
