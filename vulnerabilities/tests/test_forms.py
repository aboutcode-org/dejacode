#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from pathlib import Path

from django.test import TestCase

from dje.models import Dataspace
from dje.tests import create_superuser
from product_portfolio.tests import make_product
from product_portfolio.tests import make_product_package
from vulnerabilities.forms import VulnerabilityAnalysisForm
from vulnerabilities.tests import make_vulnerability


class VulnerabilitiesFormsTestCase(TestCase):
    data = Path(__file__).parent / "data"

    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("super_user", self.dataspace)

    def test_vulnerability_forms_vulnerability_analysis_save(self):
        vulnerability1 = make_vulnerability(dataspace=self.dataspace)
        product_package1 = make_product_package(make_product(self.dataspace))

        data = {
            "product_package": product_package1,
            "vulnerability": vulnerability1,
        }

        form = VulnerabilityAnalysisForm(user=self.super_user, data=data)
        self.assertFalse(form.is_valid())
        msg = "At least one of state, justification, responses or detail must be provided."
        self.assertEqual({"__all__": [msg]}, form.errors)

        data["detail"] = "Analysis detail"
        form = VulnerabilityAnalysisForm(user=self.super_user, data=data)
        self.assertTrue(form.is_valid())
        analysis = form.save()
        self.assertEqual(vulnerability1, analysis.vulnerability)
        self.assertEqual(product_package1, analysis.product_package)
        self.assertEqual(product_package1.product, analysis.product)
        self.assertEqual(product_package1.package, analysis.package)
        self.assertEqual(data["detail"], analysis.detail)
