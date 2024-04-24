#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.test import TestCase

from dejacode import __version__ as dejacode_version
from dje import outputs
from dje.models import Dataspace
from dje.tests import create_superuser
from dje.tests import create_user
from product_portfolio.models import Product


class OutputsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.basic_user = create_user("basic_user", self.dataspace)

        self.product1 = Product.objects.create(
            name="Product1 With Space", version="1.0", dataspace=self.dataspace
        )

    def test_outputs_get_spdx_document(self):
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
            "packages": [],
            "documentDescribes": [],
        }
        self.assertEqual(expected, document.as_dict())
