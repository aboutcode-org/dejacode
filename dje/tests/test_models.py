#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import override_settings

from dje.models import Dataspace
from dje.models import DataspaceConfiguration
from dje.models import DataspacedModel
from dje.models import DejacodeUser
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.models import History
from dje.models import get_unsecured_manager
from dje.models import is_dataspace_related
from dje.models import is_secured
from organization.models import Owner
from organization.models import Subowner


class DataspacedModelTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="alternate")
        self.other_dataspace = Dataspace.objects.create(name="other")

        self.nexb_user = get_user_model().objects.create_user(
            "nexb", "test@test.com", "t3st", self.dataspace
        )
        self.alternate_user = get_user_model().objects.create_user(
            "alternate", "test@test.com", "t3st", self.alternate_dataspace
        )

        self.source_nexb = ExternalSource.objects.create(label="nexb", dataspace=self.dataspace)
        self.source_alternate = ExternalSource.objects.create(
            label="alternate", dataspace=self.alternate_dataspace
        )

    def test_dataspace_get_reference(self):
        # REFERENCE_DATASPACE is empty string, nexB is reference
        with override_settings(REFERENCE_DATASPACE=""):
            self.assertEqual("nexB", Dataspace.objects.get_reference().name)

        # REFERENCE_DATASPACE is None, nexB is reference
        with override_settings(REFERENCE_DATASPACE=None):
            self.assertEqual("nexB", Dataspace.objects.get_reference().name)

        # Set the REFERENCE_DATASPACE to another existing Org
        with override_settings(REFERENCE_DATASPACE=self.other_dataspace.name):
            self.assertEqual("other", Dataspace.objects.get_reference().name)

        # Set the REFERENCE_DATASPACE to a non-existing Org
        with override_settings(REFERENCE_DATASPACE="not"):
            self.assertEqual(None, Dataspace.objects.get_reference())

    def test_dataspace_is_reference(self):
        # Note: We have to refresh to dataspace objects after each settings
        # change as the is_reference value is memoized on the dataspace instance.

        # REFERENCE_DATASPACE is not set, nexB is the reference
        with override_settings(REFERENCE_DATASPACE=""):
            nexb_dataspace = Dataspace.objects.get(name="nexB")
            self.assertTrue(nexb_dataspace.is_reference)
            self.assertFalse(self.other_dataspace.is_reference)

        # Set the REFERENCE_DATASPACE to another existing Dataspace
        with override_settings(REFERENCE_DATASPACE=self.other_dataspace.name):
            nexb_dataspace = Dataspace.objects.get(name="nexB")
            other_dataspace = Dataspace.objects.get(name="other")
            self.assertFalse(nexb_dataspace.is_reference)
            self.assertTrue(other_dataspace.is_reference)

        # Set the REFERENCE_DATASPACE to another non-existing Dataspace
        with override_settings(REFERENCE_DATASPACE="not"):
            nexb_dataspace = Dataspace.objects.get(name="nexB")
            other_dataspace = Dataspace.objects.get(name="other")
            self.assertFalse(nexb_dataspace.is_reference)
            self.assertFalse(other_dataspace.is_reference)

    def test_dataspace_get_by_natural_key(self):
        self.assertEqual(Dataspace.objects.get_by_natural_key("nexB"), self.dataspace)

    def test_dataspace_natural_key(self):
        self.assertEqual((self.dataspace.name,), self.dataspace.natural_key())

    def test_is_dataspace_related_model(self):
        not_related = [
            Dataspace,
        ]

        related = [
            DataspacedModel,
            DejacodeUser,
            History,
            ExternalReference,
            ExternalSource,
            DejacodeUser,
            Owner,
            Subowner,
        ]

        for model_class in not_related:
            self.assertFalse(is_dataspace_related(model_class))

        for model_class in related:
            self.assertTrue(is_dataspace_related(model_class))

    def test_dataspace_related_manager_scope(self):
        self.assertTrue(self.dataspace.is_reference)

        qs = ExternalSource.objects.scope(self.dataspace)
        self.assertIn(self.source_nexb, qs)
        self.assertNotIn(self.source_alternate, qs)

        qs = ExternalSource.objects.scope(self.dataspace, include_reference=True)
        self.assertIn(self.source_nexb, qs)
        self.assertNotIn(self.source_alternate, qs)

        qs = ExternalSource.objects.scope(self.alternate_dataspace)
        self.assertNotIn(self.source_nexb, qs)
        self.assertIn(self.source_alternate, qs)

        qs = ExternalSource.objects.scope(self.alternate_dataspace, include_reference=True)
        self.assertIn(self.source_nexb, qs)
        self.assertIn(self.source_alternate, qs)

    def test_dataspace_related_manager_scope_by_name(self):
        qs = ExternalSource.objects.scope_by_name(self.dataspace.name)
        self.assertIn(self.source_nexb, qs)
        self.assertNotIn(self.source_alternate, qs)

        qs = ExternalSource.objects.scope_by_name(self.alternate_dataspace.name)
        self.assertNotIn(self.source_nexb, qs)
        self.assertIn(self.source_alternate, qs)

        # Providing a str() to `scope` will call scope_by_name behind the scene
        qs = ExternalSource.objects.scope(self.dataspace.name)
        self.assertIn(self.source_nexb, qs)
        self.assertNotIn(self.source_alternate, qs)

    def test_dataspace_related_manager_scope_by_id(self):
        qs = ExternalSource.objects.scope_by_id(self.dataspace.id)
        self.assertIn(self.source_nexb, qs)
        self.assertNotIn(self.source_alternate, qs)

        qs = ExternalSource.objects.scope_by_id(self.alternate_dataspace.id)
        self.assertNotIn(self.source_nexb, qs)
        self.assertIn(self.source_alternate, qs)

    def test_dataspace_related_manager_scope_for_user(self):
        third_dataspace = Dataspace.objects.create(name="third")
        third_user = get_user_model().objects.create_user(
            "third", "test@test.com", "t3st", third_dataspace
        )
        source_third = ExternalSource.objects.create(label="third", dataspace=third_dataspace)

        qs = ExternalSource.objects.scope_for_user_in_admin(self.nexb_user)
        self.assertIn(self.source_nexb, qs)
        self.assertIn(self.source_alternate, qs)
        self.assertIn(source_third, qs)

        qs = ExternalSource.objects.scope_for_user_in_admin(self.alternate_user)
        self.assertIn(self.source_nexb, qs)
        self.assertIn(self.source_alternate, qs)
        self.assertNotIn(source_third, qs)

        qs = ExternalSource.objects.scope_for_user_in_admin(third_user)
        self.assertIn(self.source_nexb, qs)
        self.assertNotIn(self.source_alternate, qs)
        self.assertIn(source_third, qs)

    def test_dataspace_related_manager_is_secured_and_get_unsecured_manager(self):
        self.assertFalse(is_secured(Owner.objects))
        self.assertEqual("organization.Owner.objects", str(get_unsecured_manager(Owner)))

        from product_portfolio.models import Product

        self.assertTrue(is_secured(Product.objects))
        self.assertEqual(
            "product_portfolio.Product.unsecured_objects", str(get_unsecured_manager(Product))
        )

    def test_external_reference_model_local_foreign_fields_property(self):
        expected = [
            "dataspace",
            "created_by",
            "last_modified_by",
            "content_type",
            "external_source",
        ]
        # 'content_object' is not returned as not a concrete field by GenericForeignKey
        self.assertEqual(expected, [f.name for f in ExternalReference().local_foreign_fields])

    def test_dataspace_get_configuration(self):
        self.assertIsNone(self.dataspace.get_configuration())
        self.assertIsNone(self.dataspace.get_configuration("tab_permissions"))
        self.assertIsNone(self.dataspace.get_configuration("copy_defaults"))

        configuration = DataspaceConfiguration.objects.create(
            dataspace=self.dataspace, tab_permissions={"Enabled": True}
        )
        self.assertEqual(configuration, self.dataspace.get_configuration())
        self.assertEqual({"Enabled": True}, self.dataspace.get_configuration("tab_permissions"))
        # DataspaceConfiguration exists but `copy_defaults` is NULL
        self.assertIsNone(self.dataspace.get_configuration("copy_defaults"))

        self.assertIsNone(self.dataspace.get_configuration("non_available_field"))

    def test_dataspace_has_configuration(self):
        self.assertFalse(self.dataspace.has_configuration)
        DataspaceConfiguration.objects.create(dataspace=self.dataspace)
        self.assertTrue(self.dataspace.has_configuration)

    def test_dataspace_tab_permissions_enabled(self):
        self.assertFalse(self.dataspace.tab_permissions_enabled)

        configuration = DataspaceConfiguration.objects.create(
            dataspace=self.dataspace, tab_permissions=[]
        )
        self.assertFalse(self.dataspace.tab_permissions_enabled)

        configuration.tab_permissions = {}
        configuration.save()
        self.assertFalse(self.dataspace.tab_permissions_enabled)

        configuration.tab_permissions = ""
        configuration.save()
        self.assertFalse(self.dataspace.tab_permissions_enabled)

        configuration.tab_permissions = {"Enabled": True}
        configuration.save()
        self.assertTrue(self.dataspace.tab_permissions_enabled)

    def test_dataspaced_model_clean_extra_spaces_in_identifier_fields(self):
        owner = Owner.objects.create(name="contains  extra     spaces", dataspace=self.dataspace)
        self.assertEqual("contains extra spaces", owner.name)
