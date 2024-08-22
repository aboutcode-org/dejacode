#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase

from dje import urn
from dje import urn_resolver
from dje.models import Dataspace
from license_library.models import License
from organization.models import Owner


class LicenseLibraryURNTestCase(TestCase):
    def setUp(self):
        self.decoded_urn1 = "urn:dje:jboss-community:Mobicents SIP Servlets (MSS):v 1.4.0.FINAL"
        self.encoded_urn1 = "urn:dje:jboss-community:Mobicents+SIP+Servlets+%28MSS%29:v+1.4.0.FINAL"

        self.dataspace1 = Dataspace.objects.create(name="Dataspace")
        self.user = get_user_model().objects.create_superuser(
            "test", "test@test.com", "t3st", self.dataspace1
        )
        self.other_dataspace = Dataspace.objects.create(name="Other")
        self.other_user = get_user_model().objects.create_superuser(
            "other_user", "other@test.com", "t3st2", self.other_dataspace
        )

        self.owner1 = Owner.objects.create(
            name="CCAD - Combined Conditional Access Development, LLC.", dataspace=self.dataspace1
        )
        self.owner2 = Owner.objects.create(name="Organization2", dataspace=self.dataspace1)
        self.license1 = License.objects.create(
            key="apache-2.0",
            name="License1",
            short_name="License1",
            dataspace=self.dataspace1,
            owner=self.owner1,
        )

    def test_license_get_urn(self):
        expected = "urn:dje:license:apache-2.0"
        self.assertEqual(expected, self.license1.urn)

    def test_urn_resolve(self):
        # Using the output from Object.urn
        self.assertEqual(self.license1, urn_resolver.resolve(self.license1.urn, self.dataspace1))
        self.assertEqual(self.owner1, urn_resolver.resolve(self.owner1.urn, self.dataspace1))

        # We are testing the several steps of validation for a given URN
        with self.assertRaises(urn.URNValidationError):
            urn_resolver.resolve("a:a", self.dataspace1)
        with self.assertRaises(urn.URNValidationError):
            urn_resolver.resolve("url:djc:license:apache-2.0", self.dataspace1)

        with self.assertRaises(urn.URNValidationError):
            urn_resolver.resolve("urn:dje:not-a-model:apache-2.0", self.other_dataspace)

        urn_object_does_not_exist = "urn:dje:license:apache-1337.0"
        with self.assertRaises(ObjectDoesNotExist):
            urn_resolver.resolve(urn_object_does_not_exist, self.other_dataspace)

    def test_license_urn_resolve_view(self):
        self.client.login(username="test", password="t3st")
        # Using a correct URN as input, redirect to the license details page
        url = "/urn/{}/".format(self.license1.urn)
        response = self.client.get(url)
        self.assertRedirects(response, self.license1.get_absolute_url())
        # Submitted by the form
        url = "/urn/?urn={}".format(self.license1.urn)
        response = self.client.get(url)
        self.assertRedirects(response, self.license1.get_absolute_url())
