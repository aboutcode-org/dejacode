#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.test import TestCase

from component_catalog.tests import make_package
from dje.models import Dataspace
from license_library.models import License
from organization.models import Owner
from product_portfolio.filters import ProductPackageFilterSet
from product_portfolio.models import ProductPackage
from product_portfolio.tests import make_product


class ProductPackageFilterSetTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Reference")
        self.owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        self.license1 = License.objects.create(
            key="mit",
            name="MIT",
            short_name="MIT",
            owner=self.owner,
            dataspace=self.dataspace,
        )
        self.license2 = License.objects.create(
            key="apache-2.0",
            name="Apache 2.0",
            short_name="Apache 2.0",
            owner=self.owner,
            dataspace=self.dataspace,
        )

        self.product = make_product(self.dataspace)
        self.package1 = make_package(self.dataspace)
        self.package2 = make_package(self.dataspace)
        self.package3 = make_package(self.dataspace)

        self.pp1 = ProductPackage.objects.create(
            product=self.product,
            package=self.package1,
            license_expression=self.license1.key,
            dataspace=self.dataspace,
        )
        self.pp2 = ProductPackage.objects.create(
            product=self.product,
            package=self.package2,
            license_expression=self.license2.key,
            dataspace=self.dataspace,
        )
        self.pp3 = ProductPackage.objects.create(
            product=self.product,
            package=self.package3,
            license_expression="",
            dataspace=self.dataspace,
        )

    def test_product_package_filterset_licenses(self):
        data = {"licenses": [self.license1.key]}
        filterset = ProductPackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.pp1])

        data = {"licenses": [self.license2.key]}
        filterset = ProductPackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.pp2])

        data = {"licenses": [self.license1.key, self.license2.key]}
        filterset = ProductPackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.pp1, self.pp2], ordered=False)

    def test_product_package_filterset_has_licenses(self):
        data = {"has_licenses": "yes"}
        filterset = ProductPackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.pp1, self.pp2], ordered=False)

        data = {"has_licenses": "no"}
        filterset = ProductPackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.pp3])
