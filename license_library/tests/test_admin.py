#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import datetime
from unittest.mock import patch

from django.contrib.admin.options import IS_POPUP_VAR
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import resolve_url
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from dje.copier import copy_object
from dje.filters import DataspaceFilter
from dje.models import Dataspace
from dje.models import History
from dje.tests import create_superuser
from license_library.admin import LicenseAdmin
from license_library.models import License
from license_library.models import LicenseAnnotation
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseCategory
from license_library.models import LicenseChoice
from license_library.models import LicenseProfile
from license_library.models import LicenseProfileAssignedTag
from license_library.models import LicenseStatus
from license_library.models import LicenseStyle
from license_library.models import LicenseTag
from license_library.models import LicenseTagGroup
from license_library.models import LicenseTagGroupAssignedTag
from license_library.models import validate_slug_plus
from organization.models import Owner


class LicenseAdminCopyViewTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="Other")
        self.dataspace_target = Dataspace.objects.create(name="target_org")
        self.user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.other_user = get_user_model().objects.create_superuser(
            "other_user", "other@test.com", "t3st", self.other_dataspace
        )

        self.owner = Owner.objects.create(name="Test Organization", dataspace=self.nexb_dataspace)
        self.owner_other = Owner.objects.create(
            name="Organization_Other", dataspace=self.other_dataspace
        )
        self.owner_target = Owner.objects.create(
            name="Organization_Target", dataspace=self.dataspace_target
        )
        self.category1 = LicenseCategory.objects.create(
            label="1: Category 1",
            text="Some text",
            dataspace=self.nexb_dataspace,
        )
        self.license_style1 = LicenseStyle.objects.create(
            name="style1", dataspace=self.nexb_dataspace
        )
        self.license_profile1 = LicenseProfile.objects.create(
            name="1: LicenseProfile1", dataspace=self.nexb_dataspace
        )
        self.license1 = License.objects.create(
            key="license1",
            name="License1",
            short_name="License1",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner,
            license_style=self.license_style1,
            license_profile=self.license_profile1,
            full_text="abcdefghigklmnopqrstuvwxyz1234567890",
        )
        self.license2 = License.objects.create(
            key="license2",
            name="License2",
            short_name="License2",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner,
            full_text="abcdef",
        )
        self.license3 = License.objects.create(
            key="license3",
            name="License3",
            short_name="License3",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner,
        )

        self.license_tag1 = LicenseTag.objects.create(
            label="Tag 1", text="Text for tag1", dataspace=self.nexb_dataspace
        )
        self.license_tag2 = LicenseTag.objects.create(
            label="Tag 2", text="Text for tag2", dataspace=self.nexb_dataspace
        )
        self.license_assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        self.tag_group1 = LicenseTagGroup.objects.create(
            name="Group1", dataspace=self.nexb_dataspace
        )
        self.tag_group_assigned_tag1 = LicenseTagGroupAssignedTag.objects.create(
            license_tag_group=self.tag_group1,
            license_tag=self.license_tag1,
            dataspace=self.nexb_dataspace,
        )

        LicenseProfileAssignedTag.objects.create(
            license_profile=self.license_profile1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        LicenseProfileAssignedTag.objects.create(
            license_profile=self.license_profile1,
            license_tag=self.license_tag2,
            value=True,
            dataspace=self.nexb_dataspace,
        )

    def test_license_copy_proper(self):
        original_count = License.objects.count()
        # Copy the Category
        category1_copy = self.category1
        category1_copy.id = None  # Force an insert
        category1_copy.dataspace = self.dataspace_target
        category1_copy.save()

        # Copy the LicenseProfile
        license_profile1_copy = self.license_profile1
        license_profile1_copy.id = None  # Force an insert
        license_profile1_copy.dataspace = self.dataspace_target
        license_profile1_copy.save()

        # Copy the LicenseStyle
        license_style1_copy = self.license_style1
        license_style1_copy.id = None  # Force an insert
        license_style1_copy.dataspace = self.dataspace_target
        license_style1_copy.save()

        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        self.client.post(url, data)

        self.assertEqual(original_count + 1, License.objects.count())
        new_license = License.objects.get(name=self.license1.name, dataspace=self.dataspace_target)
        self.assertTrue(self.license1.category.label, new_license.category.label)
        self.assertTrue(self.license1.owner.name, new_license.owner.name)
        self.assertTrue(self.license1.license_profile.name, new_license.license_profile.name)
        self.assertTrue(self.license1.license_style.name, new_license.license_style.name)

        history = History.objects.get_for_object(new_license).get()
        self.assertEqual(
            'Copy object from "nexB" dataspace to "target_org" dataspace.',
            history.get_change_message(),
        )

    def test_license_copy_with_m2m(self):
        license_temp = License.objects.create(
            key="license_temp",
            name="License_temp",
            short_name="License_temp",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner,
            license_style=self.license_style1,
            license_profile=self.license_profile1,
            full_text="abcdefghigklmnopqrstuvwxyz1234567890",
        )
        license_tag1 = LicenseTag.objects.create(
            label="Tag temp", text="Text for tag1", dataspace=self.nexb_dataspace
        )
        LicenseAssignedTag.objects.create(
            license=license_temp,
            license_tag=license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        license_temp.save()
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(license_temp.id),
            "source": license_temp.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        self.client.post(url, data)
        self.assertEqual(
            1,
            len(
                LicenseTag.objects.filter(
                    label="Tag temp", text="Text for tag1", dataspace=self.dataspace_target
                )
            ),
        )
        new_tag = LicenseTag.objects.get(
            label="Tag temp", text="Text for tag1", dataspace=self.dataspace_target
        )
        self.assertEqual(
            1,
            len(
                LicenseAssignedTag.objects.filter(
                    license_tag=new_tag, dataspace=self.dataspace_target
                )
            ),
        )

        history = History.objects.get_for_object(new_tag).get()
        self.assertEqual(
            'Copy object from "nexB" dataspace to "target_org" dataspace.',
            history.get_change_message(),
        )

    def test_license_copy_to_multiple_targets(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id, self.other_dataspace.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        response = self.client.post(url, data)
        self.assertContains(response, "<h2>The following Licenses have been copied</h2>")
        license_in_target = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )
        license_in_other = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.other_dataspace
        )
        self.assertContains(
            response, "{} ({})".format(license_in_other, license_in_other.dataspace)
        )
        self.assertContains(
            response, "{} ({})".format(license_in_target, license_in_target.dataspace)
        )

        history = History.objects.get_for_object(license_in_target).get()
        self.assertEqual(
            'Copy object from "nexB" dataspace to "target_org" dataspace.',
            history.get_change_message(),
        )

        history = History.objects.get_for_object(license_in_other).get()
        self.assertEqual(
            'Copy object from "nexB" dataspace to "Other" dataspace.', history.get_change_message()
        )

    def test_license_copy_update_to_multiple_targets(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")

        target_license = copy_object(self.license1, self.dataspace_target, self.user)

        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": ",".join([str(self.license1.id), str(self.license2.id)]),
            "select_for_update": str(target_license.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id, self.other_dataspace.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        response = self.client.post(url, data)
        self.assertContains(response, "<h2>The following Licenses have been copied</h2>")
        self.assertContains(response, "<h2>The following Licenses have been updated.</h2>")

        self.assertEqual(3, len(response.context["copied"]))
        self.assertEqual(1, len(response.context["updated"]))
        self.assertEqual(0, len(response.context["errors"]))

    def test_license_copy_with_issue_on_related_organization(self):
        # Creating a new Owner in the target using the unique name
        # of self.owner but a different uuid, for future integrity error
        Owner.objects.create(name=self.license1.owner.name, dataspace=self.dataspace_target)
        # We now copy the License in the target
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        response = self.client.post(url, data)
        # ... License copy fail as the Owner cannot be match nor copy.
        self.assertContains(response, "<h2>Errors for the following Licenses.</h2>", html=True)

    def test_license_copy_update_into_self_dataspace(self):
        # Here we are trying to copy an object in its current Dataspace
        # This will raise an error on purpose, to prevent from doing it.
        license = self.license1
        dataspace = self.license1.dataspace

        # Using the high_level copy function, the object is matched, and as
        # we don't force update, nothing happen, None is returned
        self.assertIsNone(copy_object(license, dataspace, self.user))

        # Now with update=True, the AssertionError is raised
        with self.assertRaises(AssertionError):
            copy_object(license, dataspace, self.user, update=True)

        from dje.copier import copy_to
        from dje.copier import update_to

        # Also error if using the low level copy method
        with self.assertRaises(AssertionError):
            copy_to(license, dataspace, self.user)

        # Also error if using the low level update method
        with self.assertRaises(AssertionError):
            update_to(license, license, self.user)

    def test_license_copy_with_tag_uuid_reconciliation(self):
        # Create a copy of the license_tag1 in the target with a different
        # name.
        tag_in_target = LicenseTag.objects.create(
            label="STAMP",
            text=self.license_tag1.text,
            uuid=self.license_tag1.uuid,
            dataspace=self.other_dataspace,
        )
        # Also let make sure a tag with the original label already exist
        # under another uuid.
        LicenseTag.objects.create(label=self.license_tag1.label, dataspace=self.other_dataspace)

        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.other_dataspace.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        self.client.post(url, data)

        copied_license = License.objects.get(key=self.license1.key, dataspace=self.other_dataspace)
        copied_assigned_tag = LicenseAssignedTag.objects.get(
            license=copied_license, license_tag=tag_in_target
        )

        self.assertEqual(self.license_assigned_tag1.value, copied_assigned_tag.value)

    def test_license_copy_with_annotation(self):
        license_temp = License.objects.create(
            key="license_temp",
            name="License_temp",
            short_name="License_temp",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner,
            license_style=self.license_style1,
            license_profile=self.license_profile1,
            full_text="abcdefghigklmnopqrstuvwxyz1234567890",
        )
        license_tag1 = LicenseTag.objects.create(
            label="Tag temp", text="Text for tag1", dataspace=self.nexb_dataspace
        )
        licenseassignedtag = LicenseAssignedTag.objects.create(
            license=license_temp,
            license_tag=license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        LicenseAnnotation.objects.create(
            license=license_temp,
            assigned_tag=licenseassignedtag,
            text="nexb copyright",
            range_start_offset=3,
            range_end_offset=5,
            dataspace=self.nexb_dataspace,
        )

        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(license_temp.id),
            "source": license_temp.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        self.client.post(url, data)

        copied_license = License.objects.get(
            uuid=license_temp.uuid, dataspace=self.dataspace_target
        )
        # Making sure the License was properly copied
        self.assertTrue(copied_license)
        # Now looking at the copied annotation
        self.assertEqual(2, len(LicenseAnnotation.objects.all()))
        new_annotation = LicenseAnnotation.objects.get(dataspace=self.dataspace_target)
        self.assertEqual("nexb copyright", new_annotation.text)
        self.assertEqual(5, new_annotation.range_end_offset)
        self.assertEqual(3, new_annotation.range_start_offset)
        history = History.objects.get_for_object(new_annotation).get()
        self.assertEqual(
            'Copy object from "nexB" dataspace to "target_org" dataspace.',
            history.get_change_message(),
        )

    def test_license_copy_update_annotation(self):
        license_temp = License.objects.create(
            key="license_temp",
            name="License_temp",
            short_name="License_temp",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner,
            license_style=self.license_style1,
            license_profile=self.license_profile1,
            full_text="abcdefghigklmnopqrstuvwxyz1234567890",
        )
        license_tag1 = LicenseTag.objects.create(
            label="Tag temp", text="Text for tag1", dataspace=self.nexb_dataspace
        )
        licenseassignedtag = LicenseAssignedTag.objects.create(
            license=license_temp,
            license_tag=license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        LicenseAnnotation.objects.create(
            license=license_temp,
            assigned_tag=licenseassignedtag,
            text="nexb copyright",
            range_start_offset=3,
            range_end_offset=5,
            dataspace=self.nexb_dataspace,
        )

        # Copy the license into the target, 1 annotation attached
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(license_temp.id),
            "source": license_temp.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        self.client.post(url, data)

        copied_license = License.objects.get(
            uuid=license_temp.uuid, dataspace=self.dataspace_target
        )
        # Making sure the License was properly copied
        self.assertTrue(copied_license)
        # and that the annotation was copied along
        self.assertEqual(1, copied_license.annotations.count())

        # Attach a new annotation on the reference License
        license_annotation = LicenseAnnotation.objects.create(
            license=license_temp,
            assigned_tag=licenseassignedtag,
            text="nexb license",
            range_start_offset=7,
            range_end_offset=9,
            dataspace=self.nexb_dataspace,
        )
        license_annotation.save()

        # Run the same copy with update activated
        data["select_for_update"] = str(copied_license.id)
        self.client.post(url, data)

        self.assertEqual(4, len(LicenseAnnotation.objects.all()))
        new_annotation = LicenseAnnotation.objects.get(
            dataspace=self.dataspace_target, uuid=license_annotation.uuid
        )
        self.assertEqual(license_annotation.text, new_annotation.text)
        self.assertEqual(license_annotation.range_end_offset, new_annotation.range_end_offset)
        self.assertEqual(license_annotation.range_start_offset, new_annotation.range_start_offset)

    def test_license_update_with_m2m(self):
        license_temp = License.objects.create(
            key="license_temp",
            name="License_temp",
            short_name="License_temp",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner,
            license_style=self.license_style1,
            license_profile=self.license_profile1,
            full_text="abcdefghigklmnopqrstuvwxyz1234567890",
        )
        license_tag1 = LicenseTag.objects.create(
            label="Tag temp", text="Text for tag1", dataspace=self.nexb_dataspace
        )
        LicenseAssignedTag.objects.create(
            license=license_temp,
            license_tag=license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )

        copied_license = copy_object(license_temp, self.dataspace_target, self.user)
        self.client.login(username="nexb_user", password="t3st")

        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "select_for_update": str(copied_license.id),
            "source": license_temp.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }

        response = self.client.post(url, data)
        self.assertContains(response, "<h2>The following Licenses have been updated.</h2>")
        self.assertEqual(
            1,
            len(
                LicenseTag.objects.filter(
                    label="Tag temp", text="Text for tag1", dataspace=self.dataspace_target
                )
            ),
        )
        new_tag = LicenseTag.objects.get(
            label="Tag temp", text="Text for tag1", dataspace=self.dataspace_target
        )
        self.assertEqual(
            1,
            len(
                LicenseAssignedTag.objects.filter(
                    license_tag=new_tag, dataspace=self.dataspace_target
                )
            ),
        )

    def test_attribute_error_change_view(self):
        self.client.login(username="nexb_user", password="t3st")
        URLS = [
            "admin:license_library_license_changelist",
            "admin:license_library_licensetaggroup_changelist",
            "admin:license_library_licenseprofile_changelist",
            # No issue with the LicenseCategory but testing it too for consistency
            "admin:license_library_licensecategory_changelist",
        ]

        # Testing with several kind of ids: non-existent, chars, special chars
        for id in ["99999", "aaaa", "!$%%5E@"]:
            for url in URLS:
                response = self.client.get(url + id + "/")
                self.assertEqual(404, response.status_code)

    def test_object_copy_view_wrong_request(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        response = self.client.get(url)
        # Requesting the view without giving the required parameters
        self.assertContains(response, "The requested page could not be found.", status_code=404)

    def test_object_copy_view_maximum_ids_limit(self):
        # Testing the limitation of Object we can copy at one time
        # Maximum is currently 100
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "ids": ",".join([str(x) for x in range(101)]),
        }
        response = self.client.get(url, data)
        self.assertRedirects(response, reverse("admin:license_library_license_changelist"))

    def test_object_copy_view_non_existing_id(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        # Using a ContentType that does not exist
        data = {"ids": "300000"}
        response = self.client.get(url, data)
        # Redirecting the user to the list view
        self.assertRedirects(response, reverse("admin:license_library_license_changelist"))

    def test_object_copy_view_as_reference_target_form(self):
        self.assertTrue(self.user.dataspace.is_reference)
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")

        # Proper request as member of the Reference Dataspace
        # The target_dataspace is not in the param at that stage
        # the response should be the "ToDataspace" form page
        response = self.client.get(url, {"ids": str(self.license1.id)})
        self.assertTemplateUsed(response, "admin/object_copy_dataspace_form.html")

        self.assertContains(response, "<h1>Choose the target Dataspace(s).</h1>")
        expected = (
            f'<label for="id_target_0"><input type="checkbox" name="target"'
            f' value="{self.other_dataspace.id}" id="id_target_0" />'
            f" {self.other_dataspace.name}</label>"
        )
        self.assertContains(response, expected, html=True)
        expected = (
            f'<label for="id_target_1"><input type="checkbox" name="target"'
            f' value="{self.dataspace_target.id}" id="id_target_1" />'
            f" {self.dataspace_target.name}</label>"
        )
        self.assertContains(response, expected, html=True)
        # Making sure my Dataspace is not a choice of the Form
        self.assertNotContains(response, f'name="target" value="{self.nexb_dataspace.id}"')

    def test_object_copy_update_view_as_reference_pre_copy(self):
        self.assertTrue(self.user.dataspace.is_reference)
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        # Copying license2 so we have 1 object candidate for copy and one for update
        copy_object(self.license2, self.dataspace_target, self.user)

        # This time, the target is provided in the GET data
        data = {
            "ids": "{}, {}".format(self.license1.id, self.license2.id),
            "target": str(self.dataspace_target.id),
        }
        response = self.client.get(url, data)

        # The request is correct, presenting the confirmation page to the user
        self.assertContains(response, "<h2>The following Licenses will be copied.</h2>")
        expected = "<li>{} from {} to {}</li>".format(
            self.license1.get_admin_link(), self.license1.dataspace, self.dataspace_target
        )
        self.assertContains(response, expected, html=True)

        # Checking the exclude fields options
        exclude1 = (
            '<input id="id_exclude_copy_0" name="exclude_copy" type="checkbox"'
            ' value="admin_notes" />'
        )
        # The usage_policy is always checked by default for exclusion
        exclude2 = (
            '<input type="checkbox" name="exclude_copy" value="usage_policy"'
            ' id="id_exclude_copy_26" checked />'
        )
        self.assertContains(response, exclude1, html=True)
        self.assertContains(response, exclude2, html=True)

        self.assertContains(
            response,
            '<input id="id_form-0-exclude_copy_0" name="form-0-exclude_copy" type="checkbox"'
            ' value="value" />',
            html=True,
        )
        self.assertContains(
            response,
            '<input id="id_form-0-exclude_update_0" name="form-0-exclude_update" type="checkbox"'
            ' value="value" />',
            html=True,
        )

        # Let's make sure we do not have the following fields
        self.assertNotContains(response, "uuid")
        self.assertNotContains(response, "created_date")
        self.assertNotContains(response, "created_by")
        self.assertNotContains(response, "last_modified_date")
        self.assertNotContains(response, "last_modified_by")
        self.assertNotContains(response, "request_count")

    def test_object_copy_with_fields_exclude(self):
        self.assertTrue(self.license1.category)
        self.assertTrue(self.license1.license_style)
        self.assertTrue(self.license1.license_profile)
        self.assertTrue(self.license1.full_text)

        excluded_fields = ["category", "license_style", "license_profile", "full_text"]
        exclude = {self.license1.__class__: excluded_fields}

        copied_object = copy_object(
            self.license1, self.dataspace_target, self.user, exclude=exclude
        )

        self.assertFalse(copied_object.category)
        self.assertFalse(copied_object.license_style)
        self.assertFalse(copied_object.license_profile)
        self.assertFalse(copied_object.full_text)

    def test_object_update_with_fields_exclude(self):
        self.license1.curation_level = 0  # Just in case
        self.license1.save()

        copied_object = copy_object(self.license1, self.dataspace_target, self.user)

        copied_object.full_text = "New full_text"
        copied_object.short_name = "New short_name"
        copied_object.is_active = True
        copied_object.save()

        # Refresh the self.license1 instance
        self.license1 = License.objects.get(uuid=self.license1.uuid, dataspace=self.nexb_dataspace)
        self.license1.curation_level = 99
        self.license1.save()

        excluded_fields = ["full_text", "short_name", "is_active"]
        exclude = {self.license1.__class__: excluded_fields}
        # Force update including fields exclude
        copied_object = copy_object(
            self.license1, self.dataspace_target, self.user, update=True, exclude=exclude
        )

        # Making sure the exclude fields were properly ignored
        self.assertEqual("New full_text", copied_object.full_text)
        self.assertEqual("New short_name", copied_object.short_name)
        self.assertTrue(copied_object.is_active)
        # And the others properly updated
        self.assertEqual(99, copied_object.curation_level)

    def test_object_copy_view_pre_copy_including_update(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_licensecategory_copy")
        copied_object = copy_object(self.category1, self.dataspace_target, self.user)
        self.assertEqual(self.category1.uuid, copied_object.uuid)
        self.assertNotEqual(self.category1.dataspace, copied_object.dataspace)

        # Copied category will be matched and be a candidate for an update
        data = {
            "ids": str(self.category1.id),
            "target": str(self.dataspace_target.id),
        }
        response = self.client.get(url, data)

        # The request is correct, presenting the confirmation page to the user
        # Offering the option the update the match
        self.assertContains(response, "Select the ones that you would like to apply data changes.")
        self.assertContains(
            response,
            '<input type="checkbox" name="select_for_update" value="{}">'.format(copied_object.id),
        )
        self.assertContains(response, "Make the Copy and Update")

    def test_object_copy_view_as_non_reference(self):
        self.assertFalse(self.other_user.dataspace.is_reference)
        self.client.login(username="other_user", password="t3st")
        url = reverse("admin:license_library_licensecategory_copy")
        # Using a Object that is not from the Reference Dataspace
        category = LicenseCategory.objects.create(
            label="4: Category 5", text="Some text", dataspace=self.other_dataspace
        )
        self.assertFalse(category.dataspace.is_reference)
        data = {"ids": str(category.id)}
        response = self.client.get(url, data)
        # As you cannot copy from a non Reference Dataspace you are redirected
        self.assertRedirects(response, reverse("admin:license_library_licensecategory_changelist"))

        # Now, Using a Category from the Reference Dataspace
        self.assertTrue(self.category1.dataspace.is_reference)
        data["ids"] = str(self.category1.id)
        response = self.client.get(url, data)
        # The request is correct, presenting the confirmation page to the user
        self.assertContains(response, "<h2>The following License categories will be copied.</h2>")
        expected = "<li><strong>{}</strong> from {} to {}</li>".format(
            self.category1, self.nexb_dataspace, self.other_user.dataspace
        )
        self.assertContains(response, expected, html=True)

    def test_object_copy_view_as_non_reference_source_target_validity(self):
        self.assertFalse(self.other_user.dataspace.is_reference)
        self.client.login(username="other_user", password="t3st")
        url = reverse("admin:license_library_licensecategory_copy")
        # Using a Object that is not from the Reference Dataspace
        category = LicenseCategory.objects.create(
            label="4: Category 5", text="Some text", dataspace=self.other_dataspace
        )
        self.assertFalse(category.dataspace.is_reference)
        data = {
            "ct": str(ContentType.objects.get_for_model(LicenseCategory).pk),
            "copy_candidates": str(category.id),
            "source": "",
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        # Source and target are not valid IDs, User is redirected
        response = self.client.post(url, data)
        self.assertContains(response, "The requested page could not be found.", status_code=404)

        # Same thing using a name that do not exist in the DB
        data["source"] = "SOME NAME"
        response = self.client.post(url, data)
        self.assertContains(response, "The requested page could not be found.", status_code=404)

        # Now using proper source and target
        data["source"] = category.dataspace
        data["target"] = self.dataspace_target
        response = self.client.post(url, data)
        # Fail and redirect because if the User Dataspace is not
        # the Reference:
        # - Source must be the Reference Dataspace
        # - Target must be the User Dataspace
        self.assertFalse(category.dataspace.is_reference)
        self.assertContains(response, "The requested page could not be found.", status_code=404)

        # Making sure the copy did not happen
        self.assertFalse(
            LicenseCategory.objects.filter(label=category.label, dataspace=self.dataspace_target)
        )

    def test_object_copy_view_results(self):
        # Testing copy, update and error
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")

        # Creating a license in the target with same uuid for match/update
        license_for_update = License.objects.create(
            uuid=self.license2.uuid,
            key=self.license2.key,
            name="Some Name",
            short_name="Some Name",
            owner=self.owner_target,
            dataspace=self.dataspace_target,
        )

        # Creating 2 license with different uuid but same name, in both
        # Dataspaces to generate an IntegrityError on the copy
        license_for_error1 = License.objects.create(
            key="any-key",
            name="Apache 3.0",
            short_name="Apache 3.0",
            owner=self.owner,
            dataspace=self.nexb_dataspace,
        )
        License.objects.create(
            key="other-key",
            owner=self.owner_target,
            name=license_for_error1.name,
            short_name=license_for_error1.name,
            dataspace=self.dataspace_target,
        )

        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": ",".join([str(self.license1.id), str(license_for_error1.id)]),
            "select_for_update": str(license_for_update.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }

        response = self.client.post(url, data)

        # Getting the added license during the copy
        new_license = License.objects.get(key=self.license1.key, dataspace=self.dataspace_target)
        # Making sure the correct template is returned
        self.assertTemplateUsed(response, "admin/object_copy_results.html")
        # Copy results
        self.assertContains(response, "<h2>The following Licenses have been copied</h2>")
        self.assertContains(response, new_license.get_admin_url())
        # Update results
        self.assertContains(response, "<h2>The following Licenses have been updated.</h2>")
        self.assertContains(response, license_for_update.get_admin_url())
        # Errors results
        self.assertContains(response, "<h2>Errors for the following Licenses.</h2>")
        self.assertContains(response, license_for_error1.get_admin_url())
        self.assertContains(response, "duplicate key value violates unique constraint")

    def test_license_copy_and_update_configuration_get_view(self):
        # Testing the copy configuration view regarding m2m and one2m fields
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")

        data = {"ids": str(self.license1.id), "target": self.dataspace_target.pk}

        response = self.client.get(url, data)
        self.assertContains(response, "<strong>License assigned tag</strong>")
        expected = (
            '<input type="checkbox" name="exclude_copy" value="admin_notes"'
            ' id="id_exclude_copy_0" />'
        )
        self.assertContains(response, expected, html=True)
        self.assertContains(response, "<strong>License annotation</strong>")
        expected = (
            '<input type="checkbox" name="form-1-exclude_copy" value="assigned_tag"'
            ' id="id_form-1-exclude_copy_0" />'
        )
        self.assertContains(response, expected, html=True)
        expected = (
            '<input type="checkbox" name="form-1-exclude_copy" value="quote"'
            ' id="id_form-1-exclude_copy_1" />'
        )
        self.assertContains(response, expected, html=True)
        expected = (
            '<input type="checkbox" name="form-1-exclude_copy" value="text"'
            ' id="id_form-1-exclude_copy_2" />'
        )
        self.assertContains(response, expected, html=True)

        # Copy the object to simulation the update configuration view
        copied_object = copy_object(self.license1, self.dataspace_target, self.user)
        self.assertTrue(copied_object)

        response = self.client.get(url, data)
        self.assertContains(response, "<strong>License assigned tag</strong>")
        expected = (
            '<input type="checkbox" name="form-0-exclude_update" value="value"'
            ' id="id_form-0-exclude_update_0" />'
        )
        self.assertContains(response, expected, html=True)
        self.assertContains(response, "<strong>License annotation</strong>")
        expected = (
            '<input type="checkbox" name="form-1-exclude_update" value="assigned_tag"'
            ' id="id_form-1-exclude_update_0" />'
        )
        self.assertContains(response, expected, html=True)
        expected = (
            '<input type="checkbox" name="form-1-exclude_update" value="quote"'
            ' id="id_form-1-exclude_update_1" />'
        )
        self.assertContains(response, expected, html=True)
        expected = (
            '<input type="checkbox" name="form-1-exclude_update" value="text"'
            ' id="id_form-1-exclude_update_2" />'
        )
        self.assertContains(response, expected, html=True)

    def test_license_copy_configuration_post_view(self):
        # Testing the copy configuration view regarding m2m and one2m fields
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")

        annotation1 = LicenseAnnotation.objects.create(
            license=self.license1,
            assigned_tag=self.license_assigned_tag1,
            text="nexb copyright",
            range_start_offset=3,
            range_end_offset=5,
            quote="quote",
            dataspace=self.nexb_dataspace,
        )

        # Checking the pre-requisites
        self.assertEqual(1, self.license1.tags.count())
        self.assertTrue(self.license_assigned_tag1.value)
        self.assertTrue(self.license1.full_text)

        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "exclude_copy": "full_text",
            "form-TOTAL_FORMS": 2,
            "form-INITIAL_FORMS": 2,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
            "form-0-exclude_copy": "value",
            "form-1-ct": ContentType.objects.get_for_model(LicenseAnnotation).pk,
            "form-1-exclude_copy": ["assigned_tag", "quote", "text"],
        }

        response = self.client.post(url, data)
        self.assertContains(response, "<h2>The following Licenses have been copied</h2>")

        # Getting the objects created in the target dataspace
        copied_license = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )
        copied_assigned_tag = LicenseAssignedTag.objects.get(
            uuid=self.license_assigned_tag1.uuid, dataspace=self.dataspace_target
        )
        copied_annotation = LicenseAnnotation.objects.get(
            uuid=annotation1.uuid, dataspace=self.dataspace_target
        )

        self.assertEqual(self.license1.key, copied_license.key)
        # Excluded field on copy on regular fields, m2m and one2m
        self.assertFalse(copied_license.full_text)
        self.assertFalse(copied_assigned_tag.value)
        self.assertFalse(copied_annotation.assigned_tag)
        self.assertFalse(copied_annotation.text)
        self.assertFalse(copied_annotation.quote)

    def test_license_update_configuration_post_view(self):
        # Testing the update configuration view regarding m2m and one2m fields
        # Similar to test_license_copy_configuration_post_view
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")

        annotation1 = LicenseAnnotation.objects.create(
            license=self.license1,
            assigned_tag=self.license_assigned_tag1,
            text="nexb copyright",
            range_start_offset=3,
            range_end_offset=5,
            quote="quote",
            dataspace=self.nexb_dataspace,
        )

        # Checking the pre-requisites
        self.assertEqual(1, self.license1.tags.count())
        self.assertTrue(self.license_assigned_tag1.value)
        self.assertTrue(self.license1.full_text)

        # Manual copy without any exclusion
        exclude = {License: [], LicenseAnnotation: [], LicenseAssignedTag: []}
        copied_license = copy_object(
            self.license1, self.dataspace_target, self.user, exclude=exclude
        )
        copied_assigned_tag = LicenseAssignedTag.objects.get(
            uuid=self.license_assigned_tag1.uuid, dataspace=self.dataspace_target
        )
        copied_annotation = LicenseAnnotation.objects.get(
            uuid=annotation1.uuid, dataspace=self.dataspace_target
        )

        self.assertEqual(1, copied_license.tags.count())
        self.assertEqual(self.license1.full_text, copied_license.full_text)
        self.assertEqual(self.license_assigned_tag1.value, copied_assigned_tag.value)
        self.assertEqual(annotation1.assigned_tag.uuid, copied_annotation.assigned_tag.uuid)
        self.assertEqual(annotation1.text, copied_annotation.text)
        self.assertEqual(annotation1.quote, copied_annotation.quote)

        # Updating some value on the original objects to be excluded on update
        self.license1.full_text = "new text"
        self.license1.save()
        self.license_assigned_tag1.value = False
        self.license_assigned_tag1.save()
        annotation1.assigned_tag = None
        annotation1.quote = "new quote"
        annotation1.text = ""
        annotation1.save()

        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "select_for_update": str(copied_license.id),
            "exclude_update": "full_text",
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 2,
            "form-INITIAL_FORMS": 2,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
            "form-0-exclude_update": "value",
            "form-1-ct": ContentType.objects.get_for_model(LicenseAnnotation).pk,
            "form-1-exclude_update": ["assigned_tag", "quote", "text"],
        }

        response = self.client.post(url, data)
        self.assertContains(response, "<h2>The following Licenses have been updated.</h2>")

        # Getting the objects updated in the target dataspace
        copied_license = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )
        copied_assigned_tag = LicenseAssignedTag.objects.get(
            uuid=self.license_assigned_tag1.uuid, dataspace=self.dataspace_target
        )
        copied_annotation = LicenseAnnotation.objects.get(
            uuid=annotation1.uuid, dataspace=self.dataspace_target
        )

        # Making sure the excluded field were not updated
        self.assertEqual("abcdefghigklmnopqrstuvwxyz1234567890", copied_license.full_text)
        self.assertEqual(True, copied_assigned_tag.value)
        self.assertEqual(self.license_assigned_tag1.uuid, copied_annotation.assigned_tag.uuid)
        self.assertEqual("nexb copyright", copied_annotation.text)
        self.assertEqual("quote", copied_annotation.quote)


class LicenseAdminViewsTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="Other")
        self.dataspace_target = Dataspace.objects.create(name="target_org")
        self.user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.other_user = get_user_model().objects.create_superuser(
            "other_user", "other@test.com", "t3st", self.other_dataspace
        )

        self.owner = Owner.objects.create(name="Test Organization", dataspace=self.nexb_dataspace)
        self.owner_other = Owner.objects.create(
            name="Organization_Other", dataspace=self.other_dataspace
        )
        self.owner_target = Owner.objects.create(
            name="Organization_Target", dataspace=self.dataspace_target
        )
        self.category1 = LicenseCategory.objects.create(
            label="1: Category 1",
            text="Some text",
            dataspace=self.nexb_dataspace,
        )
        self.license_style1 = LicenseStyle.objects.create(
            name="style1", dataspace=self.nexb_dataspace
        )
        self.license_profile1 = LicenseProfile.objects.create(
            name="1: LicenseProfile1", dataspace=self.nexb_dataspace
        )
        self.license1 = License.objects.create(
            key="license1",
            name="License1",
            short_name="License1",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner,
            license_style=self.license_style1,
            license_profile=self.license_profile1,
            full_text="abcdefghigklmnopqrstuvwxyz1234567890",
        )
        self.license2 = License.objects.create(
            key="license2",
            name="License2",
            short_name="License2",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner,
            full_text="abcdef",
        )
        self.license3 = License.objects.create(
            key="license3",
            name="License3",
            short_name="License3",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner,
        )

        self.license_tag1 = LicenseTag.objects.create(
            label="Tag 1", text="Text for tag1", dataspace=self.nexb_dataspace
        )
        self.license_tag2 = LicenseTag.objects.create(
            label="Tag 2", text="Text for tag2", dataspace=self.nexb_dataspace
        )
        self.license_assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        self.tag_group1 = LicenseTagGroup.objects.create(
            name="Group1", dataspace=self.nexb_dataspace
        )
        self.tag_group_assigned_tag1 = LicenseTagGroupAssignedTag.objects.create(
            license_tag_group=self.tag_group1,
            license_tag=self.license_tag1,
            dataspace=self.nexb_dataspace,
        )

        self.license_profile_assigned_tag1 = LicenseProfileAssignedTag.objects.create(
            license_profile=self.license_profile1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        self.license_profile_assigned_tag2 = LicenseProfileAssignedTag.objects.create(
            license_profile=self.license_profile1,
            license_tag=self.license_tag2,
            value=True,
            dataspace=self.nexb_dataspace,
        )

    def test_license_admin_change_view_next_license(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_changelist")
        changelist_filters = "?o=-3"  # order by name reversed
        preserved_filters = "?_changelist_filters=o%3D-3"

        response = self.client.get(url + changelist_filters)
        result_list = response.context_data["cl"].result_list
        expected_qs = License.objects.scope(self.user.dataspace).order_by("-name")
        self.assertEqual(list(expected_qs), list(result_list))

        response = self.client.get(self.license1.get_admin_url() + preserved_filters)
        expected = '<a class="grp-state-focus" href="{}{}">&larr; Previous License</a>'.format(
            self.license2.get_admin_url(), preserved_filters
        )
        self.assertContains(response, expected)

        response = self.client.get(self.license2.get_admin_url() + preserved_filters)
        expected = '<a class="grp-state-focus" href="{}{}">&larr; Previous License</a>'.format(
            self.license3.get_admin_url(), preserved_filters
        )
        self.assertContains(response, expected)
        expected = '<a class="grp-state-focus" href="{}{}">Next License &rarr;</a>'.format(
            self.license1.get_admin_url(), preserved_filters
        )
        self.assertContains(response, expected)
        expected = '<input type="hidden" name="next_id" id="next_id" value="{}"/>'.format(
            self.license1.id
        )
        self.assertContains(response, expected)

        response = self.client.get(self.license3.get_admin_url() + preserved_filters)
        expected = '<a class="grp-state-focus" href="{}{}">Next License &rarr;</a>'.format(
            self.license2.get_admin_url(), preserved_filters
        )
        self.assertContains(response, expected)
        self.assertContains(
            response, '<input type="submit" value="Save and go to next" name="_next" />'
        )
        expected = '<input type="hidden" name="next_id" id="next_id" value="{}"/>'.format(
            self.license2.id
        )
        self.assertContains(response, expected)

        # No request.GET
        response = self.client.get(self.license2.get_admin_url())
        self.assertNotContains(response, "Previous License")
        self.assertNotContains(response, "Next License")
        self.assertNotContains(response, 'name="next_id"')

        # Wrong filters
        response = self.client.get(
            self.license2.get_admin_url() + "?_changelist_filters=reviewed__nonvalid%3D1"
        )
        self.assertNotContains(response, "Previous License")
        self.assertNotContains(response, "Next License")
        self.assertNotContains(response, 'name="next_id"')

    def test_license_admin_change_view_response_with_next_license(self):
        self.client.login(username="nexb_user", password="t3st")
        # POSTing a change using the "Save and go to next" link
        url = reverse("admin:license_library_license_change", args=[self.license1.pk])
        data = {
            "key": self.license1.key,
            "name": self.license1.name,
            "short_name": self.license1.short_name,
            "owner": self.license1.owner.id,
            "curation_level": self.license1.curation_level,
            "popularity": self.license1.popularity,
            "next_id": self.license2.id,
            "_next": "Save and go to next",
            "licenseassignedtag_set-INITIAL_FORMS": 0,
            "licenseassignedtag_set-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        preserved_filters = "?_changelist_filters=o%3D-3"
        response = self.client.post(url + preserved_filters, data, follow=True)
        # Making sure we are redirected on the "next" license
        self.assertRedirects(response, self.license2.get_admin_url() + preserved_filters)
        # Preserve filters
        expected = '<a href="{}?o=-3" class="grp-button cancel-link">Return to list</a>'.format(
            reverse("admin:license_library_license_changelist")
        )
        self.assertContains(response, expected)

    def test_license_curation_level_validation(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_change", args=[self.license1.pk])

        data = {
            "key": self.license1.key,
            "name": self.license1.name,
            "short_name": self.license1.short_name,
            "owner": self.license1.owner.id,
            "curation_level": 101,  # Using a value greater than the max
            "popularity": 0,
            "licenseassignedtag_set-INITIAL_FORMS": 0,
            "licenseassignedtag_set-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertContains(response, "Ensure this value is less than or equal to 100.")

        data["curation_level"] = 99
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("admin:license_library_license_changelist"))

    def test_license_annotation_view(self):
        self.client.login(username="nexb_user", password="t3st")
        # Calling the view with a non existing id
        url = reverse("admin:license_library_license_annotation", args=[9999])
        response = self.client.get(url)
        self.assertContains(response, "The requested page could not be found.", status_code=404)

        # Now, with a proper license id
        url = reverse("admin:license_library_license_annotation", args=[self.license1.id])
        response = self.client.get(url)
        self.assertContains(response, f"<h1>Annotate: {self.license1.name}</h1>")
        self.assertContains(response, "<h2>Group1</h2>")
        self.assertContains(response, "<strong>Tag 1</strong>")

        # Login as a user in another dataspace, the view is protected.
        self.assertTrue(self.client.login(username="other_user", password="t3st"))
        response = self.client.get(url)

        self.assertContains(response, "The requested page could not be found.", status_code=404)

    def test_licenseprofile_details_view(self):
        self.client.login(username="nexb_user", password="t3st")
        url = resolve_url(
            "admin:license_library_license_licenseprofile_detail", self.license_profile1.id
        )
        response = self.client.get(url)
        self.assertContains(response, f"<h2>{self.license_profile1}</h2>")
        self.assertContains(response, f"{self.license_tag1}</strong>")
        self.assertContains(response, f"{self.license_tag2}</strong>")

    def test_short_and_long_descriptions(self):
        self.client.login(username="nexb_user", password="t3st")
        short_desc_html = (
            f'<div id="short_description">{escape(LicenseAdmin.short_description)}</div>'
        )
        long_desc_html = f'<div id="long_description">{escape(LicenseAdmin.long_description)}</div>'

        url = reverse("admin:license_library_license_changelist")
        response = self.client.get(url)
        self.assertContains(response, short_desc_html, html=True)
        self.assertContains(response, long_desc_html, html=True)

        url = self.license1.get_admin_url()
        response = self.client.get(url)
        self.assertContains(response, short_desc_html, html=True)
        self.assertContains(response, long_desc_html, html=True)

    def test_history_list_filter(self):
        with patch("dje.filters.timezone") as mock_timezone:
            fake_now = datetime.datetime(year=2012, month=8, day=1)
            # patch timezone.now() so that it Return a consistent date
            mock_timezone.now.return_value = fake_now

            self.client.login(username="nexb_user", password="t3st")
            url = reverse("admin:license_library_licensetag_changelist")

            # History.action_time is automatically set to the current
            # time *anytime* the model is saved, so to set a custom value for
            # action_time we use QuerySet.update()
            def add_history_entry(licensetag, action_flag, days_back):
                history_entry = History.objects.log_action(self.user, licensetag, action_flag)
                History.objects.filter(pk=history_entry.pk).update(
                    action_time=fake_now - datetime.timedelta(days=days_back)
                )

            # create LogEntry objects for the licenses
            # license_tag1 was added 20 days ago
            add_history_entry(self.license_tag1, History.ADDITION, days_back=20)
            add_history_entry(self.license_tag1, History.CHANGE, days_back=7)

            # license_tag2 was added 100 days ago
            add_history_entry(self.license_tag2, History.ADDITION, days_back=100)
            add_history_entry(self.license_tag2, History.CHANGE, days_back=30)

            # no licenses were created in the last 7 days
            response = self.client.get(url, {"created_date": "past_7_days"})
            self.assertNotContains(response, self.license_tag1.label)
            self.assertNotContains(response, self.license_tag2.label)

            # 1 license was created in the last 30 days
            response = self.client.get(url, {"created_date": "past_30_days"})
            self.assertContains(response, self.license_tag1.label)
            self.assertNotContains(response, self.license_tag2.label)

            # 1 license was modified in the last 7 days
            response = self.client.get(url, {"modified_date": "past_7_days"})
            self.assertContains(response, self.license_tag1.label)
            self.assertNotContains(response, self.license_tag2.label)

            # test that a licensetag of another Dataspace will not show up
            # when using this list filter
            other_licensetag = LicenseTag.objects.create(
                label="otherlicensetag", dataspace=self.other_dataspace
            )
            response = self.client.get(url, {"created_date": "past_7_days"})
            self.assertNotContains(response, other_licensetag.label)
            response = self.client.get(url, {"created_date": "past_30_days"})
            self.assertNotContains(response, other_licensetag.label)
            response = self.client.get(url, {"modified_date": "past_7_days"})
            self.assertNotContains(response, other_licensetag.label)

    def test_activity_log_activated(self):
        self.client.login(username="nexb_user", password="t3st")
        for url in [
            reverse("admin:license_library_licensestatus_changelist"),
            reverse("admin:license_library_license_changelist"),
            reverse("admin:license_library_licenseprofile_changelist"),
        ]:
            response = self.client.get(url)
            self.assertContains(response, "activity_log_link")

    def test_formfield_for_foreignkey_on_object_from_target_dataspace(self):
        self.client.login(username="nexb_user", password="t3st")
        # Create an object in another dataspace target
        license_in_target = License.objects.create(
            key=self.license1.key,
            name=self.license1.name,
            short_name=self.license1.name,
            owner=self.owner_target,
            uuid=self.license1.uuid,
            dataspace=self.dataspace_target,
        )

        # None of those exists in self.dataspace_target
        self.assertFalse(LicenseProfile.objects.scope(self.dataspace_target))
        self.assertFalse(LicenseStatus.objects.scope(self.dataspace_target))
        self.assertFalse(LicenseStyle.objects.scope(self.dataspace_target))

        # Looking at our target object
        url = license_in_target.get_admin_url()
        response = self.client.get(url)
        # Making sure the values for related object are not the one from the
        # user.dataspace
        self.assertNotContains(response, self.category1)
        self.assertNotContains(response, self.license_style1)
        self.assertNotContains(response, self.license_profile1)

    def test_license_tag_group_get_assigned_tags_label(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_licensetaggroup_changelist")
        # Create another assigned_tag in the same group, with a higher seq
        # but a lower alphabetical value for the tag label, to check the order
        new_tag = LicenseTag.objects.create(label="aaa", dataspace=self.nexb_dataspace)
        LicenseTagGroupAssignedTag.objects.create(
            license_tag_group=self.tag_group1,
            license_tag=new_tag,
            seq=9,
            dataspace=self.nexb_dataspace,
        )
        response = self.client.get(url)
        expected = f"<ul><li>{self.license_tag1.label}</li><li>{new_tag.label}</li></ul>"
        self.assertContains(response, expected, html=True)

    def test_license_addition_save_and_continue_editing(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_add")
        data = {
            "key": "a-key",
            "name": "A-name",
            "owner": self.owner.id,
            "curation_level": 45,
            "popularity": 0,
            "spdx_license_key": "",
            "short_name": "A-name",
            "licenseassignedtag_set-INITIAL_FORMS": 0,
            "licenseassignedtag_set-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
            "_continue": True,  # Important for this test.
        }

        response = self.client.post(url, data)
        license = License.objects.get(key="a-key", dataspace=self.nexb_dataspace)
        self.assertRedirects(
            response, reverse("admin:license_library_license_change", args=[license.id])
        )

    def test_license_key_field_validation(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_add")
        # key is a Slug like field with support for dots "."
        data = {
            "key": "!@#$^&*",
            "name": "A-name",
            "owner": self.owner.id,
            "curation_level": 45,
            "popularity": 0,
            "short_name": "A-name",
            "licenseassignedtag_set-INITIAL_FORMS": 0,
            "licenseassignedtag_set-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        response = self.client.post(url, data)
        self.assertContains(response, escape(validate_slug_plus.message))

        data["key"] = "valid.key"
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("admin:license_library_license_changelist"))

    def test_license_admin_views_view_on_site(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_changelist")
        response = self.client.get(url)
        # View on site link
        self.assertContains(response, '<div class="grp-text"><span>View</span></div>')
        self.assertContains(
            response,
            '<a href="{}" target="_blank">View</a>'.format(self.license1.get_absolute_url()),
        )
        # Details view
        url = self.license1.get_admin_url()
        response = self.client.get(url)
        self.assertContains(
            response,
            '<a href="{}" class="grp-state-focus" target="_blank">View</a>'.format(
                self.license1.get_absolute_url()
            ),
        )

    def test_admin_license_changelist_preserve_filters_in_links(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_changelist")
        response = self.client.get(url + "?q=" + self.license1.key)
        annotation_url = reverse(
            "admin:license_library_license_annotation", args=[self.license1.pk]
        )
        self.assertContains(
            response,
            '<a href="{}?_changelist_filters=q%3Dlicense1">Annotations</a>'.format(annotation_url),
        )
        self.assertContains(
            response,
            '<a href="{}?_changelist_filters=q%3Dlicense1">license1</a>'.format(
                self.license1.get_admin_url()
            ),
        )

    def test_admin_license_changelist_get_list_display_hide_display_links(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_changelist")
        copied_license = copy_object(self.license1, self.other_dataspace, self.user)

        expected1 = 'class="column-changelist_view_on_site"'
        expected2 = self.license1.get_admin_url()
        expected3 = copied_license.get_admin_url()
        expected4 = "Copy to my Dataspace"

        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, expected4)

        response = self.client.get(url, data={IS_POPUP_VAR: 1})
        self.assertNotContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, expected4)

        self.client.login(username=self.other_user.username, password="t3st")
        response = self.client.get(url, data={IS_POPUP_VAR: 1})
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertNotContains(response, expected4)

        data = {
            IS_POPUP_VAR: 1,
            DataspaceFilter.parameter_name: self.nexb_dataspace.id,
        }
        response = self.client.get(url, data=data)
        self.assertNotContains(response, expected1)
        # Present in the annotation url
        # self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertContains(response, expected4)

        copy_url = reverse("admin:license_library_license_copy")
        self.assertContains(
            response, "{}?ids={}&{}=1".format(copy_url, self.license1.id, IS_POPUP_VAR)
        )

    def test_license_admin_changeform_views_key_is_readonly(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.license1.get_admin_url()
        response = self.client.get(url)
        expected = '<div class="grp-readonly">{}</div>'.format(self.license1.key)
        self.assertContains(response, expected)

    def test_license_profile_changeform_assigned_tags_value_update(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.license_profile1.get_admin_url()
        self.assertEqual(2, self.license_profile1.licenseprofileassignedtag_set.count())
        self.assertTrue(self.license_profile_assigned_tag1.value)
        self.assertTrue(self.license_profile_assigned_tag2.value)

        response = self.client.get(url)
        for index in [0, 1]:
            expected = f"""
            <select id="id_licenseprofileassignedtag_set-{index}-value"
                    name="licenseprofileassignedtag_set-{index}-value">
                <option value="">No</option>
                <option value="True" selected="selected">Yes</option>
            </select>
            """
            self.assertContains(response, expected, html=True)

        license_tag_id1 = self.license_profile_assigned_tag1.license_tag.id
        license_tag_id2 = self.license_profile_assigned_tag2.license_tag.id
        data = {
            "name": self.license_profile1.name,
            "licenseprofileassignedtag_set-TOTAL_FORMS": 2,
            "licenseprofileassignedtag_set-INITIAL_FORMS": 2,
            "licenseprofileassignedtag_set-0-license_tag": license_tag_id1,
            "licenseprofileassignedtag_set-0-value": "",
            "licenseprofileassignedtag_set-0-license_profile": self.license_profile1.id,
            "licenseprofileassignedtag_set-0-id": self.license_profile_assigned_tag1.id,
            "licenseprofileassignedtag_set-1-license_tag": license_tag_id2,
            "licenseprofileassignedtag_set-1-value": "",
            "licenseprofileassignedtag_set-1-license_profile": self.license_profile1.id,
            "licenseprofileassignedtag_set-1-id": self.license_profile_assigned_tag2.id,
        }

        self.client.post(url, data=data)
        for assigned_tag in self.license_profile1.licenseprofileassignedtag_set.all():
            self.assertFalse(assigned_tag.value)

        data["licenseprofileassignedtag_set-0-value"] = "True"
        data["licenseprofileassignedtag_set-1-value"] = "True"
        self.client.post(url, data=data)
        for assigned_tag in self.license_profile1.licenseprofileassignedtag_set.all():
            self.assertTrue(assigned_tag.value)

    def test_admin_licensetag_changeform_annotation_examples(self):
        self.client.login(username="nexb_user", password="t3st")

        annotation = LicenseAnnotation.objects.create(
            license=self.license1,
            assigned_tag=self.license_assigned_tag1,
            text="a",
            range_start_offset=1,
            range_end_offset=2,
            quote="Quote",
            dataspace=self.nexb_dataspace,
        )

        url = reverse("admin:license_library_licensetag_change", args=[self.license_tag1.id])
        response = self.client.get(url)
        expected = '<div class="grp-td">{}</div>'.format(
            self.license1.get_admin_link(target="_blank")
        )
        self.assertContains(response, expected)
        expected = '<div class="grp-td"><img src="/static/img/icon-yes.png" alt="True"></div>'
        self.assertContains(response, expected)
        self.assertContains(response, "&ldquo;{}&rdquo;".format(annotation.quote))

    def test_license_admin_form_prevent_changing_full_text_when_annotations_exists(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_change", args=[self.license1.pk])

        annotation = LicenseAnnotation.objects.create(
            license=self.license1,
            assigned_tag=self.license_assigned_tag1,
            text="a",
            range_start_offset=1,
            range_end_offset=2,
            quote="Quote",
            dataspace=self.nexb_dataspace,
        )

        data = {
            "key": self.license1.key,
            "name": self.license1.name,
            "short_name": self.license1.short_name,
            "owner": self.license1.owner.id,
            "curation_level": self.license1.curation_level,
            "popularity": self.license1.popularity,
            "full_text": self.license1.full_text,
            "licenseassignedtag_set-INITIAL_FORMS": 0,
            "licenseassignedtag_set-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

        data["full_text"] = "new text"
        expected = {
            "full_text": [
                "Existing Annotations are defined on this license text. "
                "You need to manually delete all those Annotations first to "
                "be able to update the license text."
            ]
        }
        response = self.client.post(url, data)
        self.assertEqual(expected, response.context_data["adminform"].form.errors)

        annotation.delete()
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_license_full_text_normalize_newlines(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_change", args=[self.license1.pk])

        data = {
            "key": self.license1.key,
            "name": self.license1.name,
            "short_name": self.license1.short_name,
            "owner": self.license1.owner.id,
            "curation_level": self.license1.curation_level,
            "popularity": self.license1.popularity,
            "licenseassignedtag_set-INITIAL_FORMS": 0,
            "licenseassignedtag_set-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        expected = "aaa\nbbb"

        data["full_text"] = "aaa\r\nbbb"
        self.client.post(url, data)
        self.license1.refresh_from_db()
        self.assertEqual(expected, self.license1.full_text)

        data["full_text"] = "aaa\rbbb"
        self.client.post(url, data)
        self.license1.refresh_from_db()
        self.assertEqual(expected, self.license1.full_text)

        data["full_text"] = "aaa\nbbb"
        self.client.post(url, data)
        self.license1.refresh_from_db()
        self.assertEqual(expected, self.license1.full_text)

    def test_license_spdx_license_key_validation(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_change", args=[self.license1.pk])

        data = {
            "key": self.license1.key,
            "name": self.license1.name,
            "short_name": self.license1.short_name,
            "owner": self.license1.owner.id,
            "curation_level": self.license1.curation_level,
            "popularity": self.license1.popularity,
            "licenseassignedtag_set-INITIAL_FORMS": 0,
            "licenseassignedtag_set-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        data["spdx_license_key"] = "spdx_key_with_underscore"
        response = self.client.post(url, data)
        expected = [["Enter a valid value consisting of letters, numbers, dots or hyphens."]]
        self.assertEqual(expected, response.context["errors"])

        data["spdx_license_key"] = "key"
        data["is_active"] = False
        response = self.client.post(url, data)
        expected = [["A deprecated license must not have an SPDX license key."]]
        self.assertEqual(expected, response.context["errors"])

        data["is_active"] = True
        response = self.client.post(url, data, follow=True)
        self.assertEqual(200, response.status_code)
        self.license1.refresh_from_db()
        self.assertEqual("key", self.license1.spdx_license_key)

        response = self.client.post(url, data, follow=True)
        self.assertEqual(200, response.status_code)
        self.license1.refresh_from_db()
        self.assertEqual("key", self.license1.spdx_license_key)

        self.license2.spdx_license_key = "license2-spdx-key"
        self.license2.save()
        data["spdx_license_key"] = self.license2.spdx_license_key
        response = self.client.post(url, data)
        expected = [["License with this Dataspace and SPDX short identifier already exists."]]
        self.assertEqual(expected, response.context["errors"])


class LicenseChoiceAdminTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="Alternate")
        self.super_user = create_superuser("super_user", self.dataspace)

    def test_license_choice_admin_changelist_view(self):
        self.client.login(username="super_user", password="secret")
        changelist_url = reverse("admin:license_library_licensechoice_changelist")

        LicenseChoice.objects.create(
            from_expression="bsd", to_expression="mit", dataspace=self.dataspace
        )

        response = self.client.get(changelist_url)
        expected = """
        <form id="grp-changelist-test-choices" method="get">
            <label for="test_expression">Test license choice for an expression:</label>
            <input type="text" name="test_expression" id="test_expression" value="">
            <button type="submit" class="submit-inline-button">Test</button>
        </form>
        """
        self.assertContains(response, expected, html=True)

        response = self.client.get(changelist_url + "?test_expression=bsd")
        expected = """
        <form id="grp-changelist-test-choices" method="get">
            <label for="test_expression">Test license choice for an expression:</label>
            <input type="text" name="test_expression" id="test_expression" value="bsd">
            <button type="submit" class="submit-inline-button">Test</button>
        </form>
        &rArr; <code class="license_expression">mit</code>
        """
        self.assertContains(response, expected, html=True)

        data = {DataspaceFilter.parameter_name: self.alternate_dataspace.id}
        response = self.client.get(changelist_url, data)
        self.assertNotContains(response, "test_expression")
