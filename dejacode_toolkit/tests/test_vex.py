#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#


import json
import os

from django.contrib.auth import get_user_model
from django.test import TestCase

from cyclonedx.output.json import SchemaVersion1Dot4
from serializable import _SerializableJsonEncoder

from component_catalog.models import Package
from dejacode_toolkit.vex import create_auto_vex
from dejacode_toolkit.vex import get_references_and_rating
from dejacode_toolkit.vex import get_vex_document
from dejacode_toolkit.vex import vulnerability_format_vcio_to_cyclonedx
from dje.models import Dataspace
from dje.tests import create_user
from product_portfolio.models import Product
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductPackageVEX

User = get_user_model()


class VEXTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.nexb_user = User.objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.basic_user = create_user("basic_user", self.nexb_dataspace)
        self.product1 = Product.objects.create(
            name="Product1 With Space", version="1.0", dataspace=self.nexb_dataspace
        )
        self.package1 = Package.objects.create(filename="package1", dataspace=self.nexb_dataspace)
        self.package1.type = "pypi"
        self.package1.namespace = ""
        self.package1.name = "flask"
        self.package1.version = "2.3.2"

        self.productpacakge1 = ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.nexb_dataspace
        )
        self.vex1 = ProductPackageVEX.objects.create(
            dataspace=self.productpacakge1.dataspace,
            productpackage=self.productpacakge1,
            vulnerability_id="VCID-111c-u9bh-aaac",
            responses=["CNF"],
            justification="CNP",
            detail=(
                "Automated dataflow analysis and manual "
                "code review indicates that the vulnerable code is not reachable,"
                " either directly or indirectly."
            ),
        )
        self.vex2 = ProductPackageVEX.objects.create(
            dataspace=self.productpacakge1.dataspace,
            productpackage=self.productpacakge1,
            vulnerability_id="VCID-z6fe-2j8a-aaak",
            state="R",  # resolved
            detail="This version of Product DEF has been fixed.",
        )

    def test_create_auto_vex1(self):
        vulnerabilities = [
            {
                "affected_by_vulnerabilities": [
                    {
                        "url": "http://public.vulnerablecode.io/api/vulnerabilities/121332",
                        "vulnerability_id": "VCID-111c-u9bh-aaac",
                    }
                ]
            },
            {
                "affected_by_vulnerabilities": [
                    {
                        "url": "https://public.vulnerablecode.io/api/vulnerabilities/121331",
                        "vulnerability_id": "VCID-uxf9-7c97-aaaj",
                    }
                ]
            },
        ]
        assert ProductPackageVEX.objects.count() == 2
        create_auto_vex(self.package1, vulnerabilities)
        assert ProductPackageVEX.objects.count() == 3

        # run create_auto_vex agian and make sure that the databse ignore errors
        create_auto_vex(self.package1, vulnerabilities)
        assert ProductPackageVEX.objects.count() == 3

    def test_create_auto_vex2(self):
        # duplicated vulnerability
        vulnerabilities = [
            {
                "affected_by_vulnerabilities": [
                    {
                        "url": "http://public.vulnerablecode.io/api/vulnerabilities/121332",
                        "vulnerability_id": "VCID-111c-u9bh-aaac",
                    }
                ]
            },
            {
                "affected_by_vulnerabilities": [
                    {
                        "url": "http://public.vulnerablecode.io/api/vulnerabilities/121332",
                        "vulnerability_id": "VCID-111c-u9bh-aaac",
                    }
                ]
            },
        ]
        assert ProductPackageVEX.objects.count() == 2
        create_auto_vex(self.package1, vulnerabilities)
        assert ProductPackageVEX.objects.count() == 2

    def test_get_references_and_rating(self):
        references = [
            {
                "reference_url": "https://nvd.nist.gov/vuln/detail/CVE-2017-1000136",
                "reference_id": "CVE-2017-1000136",
                "scores": [
                    {
                        "value": "5.0",
                        "scoring_system": "cvssv2",
                        "scoring_elements": "AV:N/AC:L/Au:N/C:P/I:N/A:N",
                    },
                    {
                        "value": "5.3",
                        "scoring_system": "cvssv3",
                        "scoring_elements": "CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N",
                    },
                ],
                "url": "https://nvd.nist.gov/vuln/detail/CVE-2017-1000136",
            }
        ]
        ref, rate = get_references_and_rating(references)

        assert json.dumps(
            ref,
            cls=_SerializableJsonEncoder,
            view_=SchemaVersion1Dot4,
        ) == json.dumps(
            [
                {
                    "id": "CVE-2017-1000136",
                    "source": {"url": "https://nvd.nist.gov/vuln/detail/CVE-2017-1000136"},
                }
            ]
        )

        assert json.dumps(
            rate,
            cls=_SerializableJsonEncoder,
            view_=SchemaVersion1Dot4,
        ) == json.dumps(
            [
                {
                    "method": "CVSSv2",
                    "score": "5.0",
                    "source": {"url": "https://nvd.nist.gov/vuln/detail/CVE-2017-1000136"},
                    "vector": "AV:N/AC:L/Au:N/C:P/I:N/A:N",
                },
                {
                    "method": "CVSSv3",
                    "score": "5.3",
                    "source": {"url": "https://nvd.nist.gov/vuln/detail/CVE-2017-1000136"},
                    "vector": "AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N",
                },
            ]
        )

    def test_vulnerability_format_vcic_to_cyclonedx1(self):
        vul_data_path = os.path.join(os.path.dirname(__file__), "testfiles", "vcio_vul1.json")
        with open(vul_data_path) as f:
            vcio_vulnerability = json.load(f)

        vulnerability = vulnerability_format_vcio_to_cyclonedx(vcio_vulnerability, self.vex1)

        cyclonedx_vul_data_path = os.path.join(
            os.path.dirname(__file__), "testfiles", "cyclonedx_vul1.json"
        )
        with open(cyclonedx_vul_data_path) as f:
            cyclonedx_vul = json.load(f)

        assert json.dumps(
            vulnerability,
            cls=_SerializableJsonEncoder,
            view_=SchemaVersion1Dot4,
        ) == json.dumps(cyclonedx_vul)

    def test_vulnerability_format_vcic_to_cyclonedx2(self):
        vul_data_path = os.path.join(os.path.dirname(__file__), "testfiles", "vcio_vul2.json")
        with open(vul_data_path) as f:
            vcio_vulnerability = json.load(f)

        vulnerability = vulnerability_format_vcio_to_cyclonedx(vcio_vulnerability, self.vex1)

        cyclonedx_vul_data_path = os.path.join(
            os.path.dirname(__file__), "testfiles", "cyclonedx_vul2.json"
        )
        with open(cyclonedx_vul_data_path) as f:
            cyclonedx_vul = json.load(f)

        assert json.dumps(
            vulnerability,
            cls=_SerializableJsonEncoder,
            view_=SchemaVersion1Dot4,
        ) == json.dumps(cyclonedx_vul)

    def test_get_vex_document1(self):
        vul_data_path = os.path.join(os.path.dirname(__file__), "testfiles", "vcio_vul1.json")
        with open(vul_data_path) as f:
            vcio_vulnerability = json.load(f)

        vex_data_path = os.path.join(os.path.dirname(__file__), "testfiles", "vex1.json")
        with open(vex_data_path) as f:
            vex_data = json.load(f)

        assert get_vex_document([vcio_vulnerability], [self.vex1]) == json.dumps(vex_data)

    def test_get_vex_document2(self):
        vul_data_path = os.path.join(os.path.dirname(__file__), "testfiles", "vcio_vul2.json")
        with open(vul_data_path) as f:
            vcio_vulnerability = json.load(f)

        vex_data_path = os.path.join(os.path.dirname(__file__), "testfiles", "vex2.json")
        with open(vex_data_path) as f:
            vex_data = json.load(f)

        assert get_vex_document(
            [vcio_vulnerability], [self.vex2], spec_version="1.5"
        ) == json.dumps(vex_data)
