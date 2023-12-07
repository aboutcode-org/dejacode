# -*- coding: utf-8 -*-
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from dje.admin import EXTERNAL_SOURCE_LOOKUP
from dje.models import Dataspace
from dje.models import ExternalReference
from dje.models import ExternalSource
from organization.models import Owner


class ExternalReferenceModelTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.nexb_user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.owner1 = Owner.objects.create(name="DejaCode", dataspace=self.nexb_dataspace)
        self.owner2 = Owner.objects.create(
            name="Apache Software Foundation", dataspace=self.nexb_dataspace
        )

        self.ext_source1 = ExternalSource.objects.create(
            label="GitHub",
            dataspace=self.nexb_dataspace,
        )

        self.ext_ref1 = ExternalReference.objects.create(
            content_type=ContentType.objects.get_for_model(self.owner1),
            object_id=self.owner1.pk,
            external_source=self.ext_source1,
            external_id="dejacode",
            dataspace=self.nexb_dataspace,
        )

    def test_external_reference_manager_get_content_object(self):
        returned = ExternalReference.objects.get_content_object(self.ext_source1, "dejacode")
        self.assertEqual(self.owner1, returned)

    def test_external_reference_manager_get_for_content_object(self):
        expected = ExternalReference.objects.filter(
            content_type=ContentType.objects.get_for_model(self.owner1), object_id=self.owner1.pk
        )
        returned = ExternalReference.objects.get_for_content_object(self.owner1)
        self.assertEqual(list(expected), list(returned))

        ExternalReference.objects.create(
            content_type=ContentType.objects.get_for_model(self.owner1),
            object_id=self.owner1.pk,
            external_source=self.ext_source1,
            external_id="dejacode2",
        )

        expected = ExternalReference.objects.filter(
            content_type=ContentType.objects.get_for_model(self.owner1), object_id=self.owner1.pk
        )
        returned = ExternalReference.objects.get_for_content_object(self.owner1)
        self.assertEqual(2, len(returned))
        self.assertEqual(list(expected), list(returned))

    def test_external_reference_manager_create_for_content_object(self):
        ExternalReference.objects.create_for_content_object(
            self.owner2, external_source=self.ext_source1, external_id="Apache"
        )
        result = ExternalReference.objects.get(
            content_type=ContentType.objects.get_for_model(self.owner2), object_id=self.owner2.pk
        )
        self.assertEqual("Apache", result.external_id)

    def test_external_reference_delete_content_object(self):
        # The ext_ref is deleted as well
        content_object = self.ext_ref1.content_object
        content_object.delete()
        self.assertFalse(ExternalReference.objects.filter(pk=self.ext_ref1.pk).exists())


class ExternalReferenceAdminTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.nexb_user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.owner1 = Owner.objects.create(name="DejaCode", dataspace=self.nexb_dataspace)
        self.owner2 = Owner.objects.create(
            name="Apache Software Foundation", dataspace=self.nexb_dataspace
        )

        self.ext_source1 = ExternalSource.objects.create(
            label="GitHub",
            dataspace=self.nexb_dataspace,
        )

        self.ext_ref1 = ExternalReference.objects.create(
            content_type=ContentType.objects.get_for_model(self.owner1),
            object_id=self.owner1.pk,
            external_source=self.ext_source1,
            external_id="owner1",
            dataspace=self.nexb_dataspace,
        )

        self.ext_ref1_duplicate = ExternalReference.objects.create(
            content_type=ContentType.objects.get_for_model(self.owner1),
            object_id=self.owner1.pk,
            external_source=self.ext_source1,
            external_id="owner1_dup",
            dataspace=self.nexb_dataspace,
        )

        self.ext_ref2 = ExternalReference.objects.create(
            content_type=ContentType.objects.get_for_model(self.owner1),
            object_id=self.owner2.pk,
            external_source=self.ext_source1,
            external_id="owner2",
            dataspace=self.nexb_dataspace,
        )

    def test_external_source_changelist_links_in_changelist_view(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:dje_externalsource_changelist")
        response = self.client.get(url)
        expected = 'See the <a href="{}?{}={}" target="_blank">2 owners</a> in changelist'.format(
            reverse("admin:organization_owner_changelist"),
            EXTERNAL_SOURCE_LOOKUP,
            self.ext_source1.id,
        )
        self.assertContains(response, expected)
