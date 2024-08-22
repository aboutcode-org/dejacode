#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.test import TestCase

from component_catalog.models import Component
from dje import urn
from dje import urn_resolver
from dje.models import Dataspace
from organization.models import Owner


class ComponentCatalogURNTestCase(TestCase):
    # See also the tests in dje.URNTestCase
    def setUp(self):
        self.dataspace1 = Dataspace.objects.create(name="Dataspace")
        self.owner1 = Owner.objects.create(
            name="CCAD - Combined Conditional Access Development, LLC.", dataspace=self.dataspace1
        )
        self.owner2 = Owner.objects.create(name="Organization2", dataspace=self.dataspace1)
        self.component1 = Component.objects.create(
            owner=self.owner1, name="Zlib.Ada", version="1.3", dataspace=self.dataspace1
        )
        self.component2 = Component.objects.create(
            owner=self.owner2, name="Component2", version="", dataspace=self.dataspace1
        )

    def test_component_get_run(self):
        expected = "urn:dje:component:Zlib.Ada:1.3"
        self.assertEqual(expected, self.component1.urn)

    def test_component_urn_resolve(self):
        # Using the output from Object.urn
        self.assertEqual(
            self.component1, urn_resolver.resolve(self.component1.urn, self.dataspace1)
        )

        # We are testing the several steps of validation for a given URN
        with self.assertRaises(urn.URNValidationError):
            urn_resolver.resolve("urn:dje:component:Component1", self.dataspace1)

        urn_component_no_version = "urn:dje:component:Component2:"
        self.assertEqual(
            self.component2, urn_resolver.resolve(urn_component_no_version, self.dataspace1)
        )

        # Same without the trailing colon, will raise the Validation error
        urn_component_no_version_wrong = "urn:dje:component:Component2"
        with self.assertRaises(urn.URNValidationError):
            urn_resolver.resolve(urn_component_no_version_wrong, self.dataspace1)

    def test_components_urns_with_colons_in_name_are_valid_urns(self):
        comp = Component.objects.create(name="a:na", version="a:ve", dataspace=self.dataspace1)
        self.assertEqual("urn:dje:component:a%3Ana:a%3Ave", comp.urn)
