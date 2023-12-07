#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.test import TestCase

from dje.copier import copy_object
from dje.models import Dataspace
from organization.models import Owner
from organization.models import Subowner

# WARNING: Do not import from local DJE apps except 'dje' and 'organization'


class OwnerModelsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="other")
        self.user = get_user_model().objects.create_user(
            "test", "test@test.com", "t3st", self.dataspace
        )
        self.owner = Owner.objects.create(name="Owner", dataspace=self.dataspace)
        self.other_owner = Owner.objects.create(
            name="Other Organization", dataspace=self.other_dataspace
        )

    def test_user_natural_key(self):
        self.assertEqual((self.user.username,), self.user.natural_key())

    def test_user_get_by_natural_key(self):
        self.assertEqual(get_user_model().objects.get_by_natural_key("test"), self.user)

    def test_owner_unique_filters_for(self):
        selector = self.owner.unique_filters_for(self.other_dataspace)
        expected = {"name": self.owner.name, "dataspace": self.other_dataspace}
        self.assertEqual(expected, selector)

    def test_owner_models_get_identifier_fields(self):
        inputs = [
            (Owner, ["name"]),
            (Subowner, ["parent", "child", "start_date", "end_date"]),
        ]
        for model_class, expected in inputs:
            self.assertEqual(expected, model_class.get_identifier_fields())

    def test_get_admin_link(self):
        expected = f'<a href="{self.owner.get_admin_url()}">{self.owner}</a>'
        self.assertEqual(expected, self.owner.get_admin_link())

        expected = (
            f'<a href="{self.owner.get_admin_url()}" target="_blank" title="Title">{self.owner}</a>'
        )
        data = {"target": "_blank", "title": "Title"}
        self.assertEqual(expected, self.owner.get_admin_link(**data))


class OwnerCopyTestCase(TestCase):
    """
    Higher level end to end tests of the copy features, at the model level
    for owners only with no views involved.
    """

    def setUp(self):
        self.dataspace1 = Dataspace.objects.create(name="nexB")
        self.user = get_user_model().objects.create_superuser(
            "test", "test@test.com", "t3st", self.dataspace1
        )

        self.dataspace2 = Dataspace.objects.create(name="TestOwner")
        self.other_user = get_user_model().objects.create_superuser(
            "other_user", "test2@test.com", "t3st", self.dataspace2
        )

        self.owner1 = Owner.objects.create(name="owner1", dataspace=self.dataspace1)
        self.owner2 = Owner.objects.create(name="owner2", dataspace=self.dataspace1)

        self.person1 = Owner.objects.create(
            name="person1", type="Person", dataspace=self.dataspace1
        )

        self.subowner1 = Subowner.objects.create(
            parent=self.owner1,
            child=self.person1,
            start_date="2011-12-06",
            end_date="2011-12-08",
            notes="notes",
            dataspace=self.owner1.dataspace,
        )
        self.subowner2 = Subowner.objects.create(
            parent=self.owner1,
            child=self.person1,
            start_date="2011-12-07",
            end_date="2011-12-08",
            notes="notes",
            dataspace=self.owner1.dataspace,
        )

        self.person2 = Owner.objects.create(
            name="person2", type="Person", dataspace=self.dataspace1
        )

        self.subowner1 = Subowner.objects.create(
            parent=self.owner1,
            child=self.person2,
            start_date="2011-12-06",
            end_date="2011-12-08",
            notes="notes",
            dataspace=self.owner1.dataspace,
        )
        self.subowner2 = Subowner.objects.create(
            parent=self.owner2,
            child=self.person2,
            start_date="2011-12-03",
            end_date="2011-12-08",
            notes="notes",
            dataspace=self.owner2.dataspace,
        )

        self.target_dataspace = Dataspace.objects.create(name="target_dataspace")

    def _create_simple_owner(self):
        self.assertEqual(4, Owner.objects.count())
        owner = Owner.objects.create(
            name="owner_common",
            dataspace=self.dataspace1,
            contact_info="li@nxb.com",
            homepage_url="http://oracle.com",
            notes="notes",
        )
        self.assertEqual(5, Owner.objects.count())
        return owner

    def _obj_copy_basic_for_owner_fails_if_target_is_not_an_dataspace(self, update=False):
        """
        Setup and test with an expected failure to test copy, update and
        noop.
        """
        owner = self._create_simple_owner()
        expected_msg = '"Owner.dataspace" must be a "Dataspace" instance'
        try:
            copy_object(owner, self.target_dataspace.id, self.user, update)
        except ValueError as e:
            # check the content of the exception message
            self.assertIn(
                expected_msg,
                repr(e),
                f"Incorrect exception message: '{repr(e)}'. "
                f"Does not contain expected: '{expected_msg}'",
            )

    def test_obj_copy_basic_for_owner_fails_if_target_is_not_an_dataspace_copy(self):
        self._obj_copy_basic_for_owner_fails_if_target_is_not_an_dataspace()

    def test_obj_copy_basic_for_owner_fails_if_target_is_not_an_dataspace_update(self):
        self._obj_copy_basic_for_owner_fails_if_target_is_not_an_dataspace(update=True)

    def test_obj_copy_basic_for_owner_fails_if_target_is_not_an_dataspace_noop(self):
        self._obj_copy_basic_for_owner_fails_if_target_is_not_an_dataspace(None)

    def _check_that_copy_succeeded(self, owner):
        copied_owner_name = Owner.objects.get(
            dataspace=self.target_dataspace, contact_info=owner.contact_info, notes=owner.notes
        ).name
        expected_owner_name = owner.name
        self.assertEqual(expected_owner_name, copied_owner_name)

    def test_obj_copy_basic_owner_copy(self):
        # Simple test using copy_object
        owner = self._create_simple_owner()
        copy_object(owner, self.target_dataspace, self.user)
        self._check_that_copy_succeeded(owner)

    def test_deepcopy_for_owner(self):
        # Simple test using deepcopy
        owner = self._create_simple_owner()
        from copy import deepcopy

        owner2 = deepcopy(owner)
        owner2.id = None
        owner2.dataspace = self.target_dataspace
        owner2.save()

        self._check_that_copy_succeeded(owner)

    def _obj_copy_basic_owner_update(self, update=False):
        """Setup for a basic owner update operation"""
        owner = self._create_simple_owner()
        # pre-create an owner with the same name in the target dataspace to
        # trigger an update
        Owner.objects.create(
            name="owner_common",
            uuid=owner.uuid,
            dataspace=self.target_dataspace,
            contact_info="joe@nxb.com",
            homepage_url="http://sun.com",
            notes="notes2",
        )
        self.assertEqual(6, Owner.objects.count())
        copy_object(owner, self.target_dataspace, self.user, update=update)

    def test_obj_copy_basic_owner_update_noop(self):
        self._obj_copy_basic_owner_update(None)

        # for a noop no new owner should be created and no update of the data should take place
        self.assertEqual(6, Owner.objects.count())

        target_owner = Owner.objects.get(dataspace=self.target_dataspace, name="owner_common")
        # our owner fields should NOT have been updated
        self.assertEqual("joe@nxb.com", target_owner.contact_info)
        self.assertEqual("notes2", target_owner.notes)
        self.assertEqual("http://sun.com", target_owner.homepage_url)

    def test_obj_copy_basic_owner_update_update(self):
        self._obj_copy_basic_owner_update(True)

        # for an update no new owner should be created
        self.assertEqual(6, Owner.objects.count())

        target_owner = Owner.objects.get(dataspace=self.target_dataspace, name="owner_common")
        # our owner fields should be updated
        self.assertEqual("li@nxb.com", target_owner.contact_info)
        self.assertEqual("notes", target_owner.notes)
        self.assertEqual("http://oracle.com", target_owner.homepage_url)
