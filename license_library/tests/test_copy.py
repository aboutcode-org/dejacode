#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.admin.options import IS_POPUP_VAR
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from dje.copier import SKIP
from dje.copier import copy_object
from dje.copier import copy_to
from dje.models import Dataspace
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.models import History
from dje.tests import create_superuser
from license_library.models import License
from license_library.models import LicenseAnnotation
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseCategory
from license_library.models import LicenseProfile
from license_library.models import LicenseProfileAssignedTag
from license_library.models import LicenseStatus
from license_library.models import LicenseStyle
from license_library.models import LicenseTag
from organization.models import Owner


class LicenseCopyTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.dataspace_target = Dataspace.objects.create(name="target_org")
        self.user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.owner = Owner.objects.create(name="Test Organization", dataspace=self.nexb_dataspace)
        self.target_owner = Owner.objects.create(
            name="Target Organization", dataspace=self.dataspace_target
        )
        self.category1 = LicenseCategory.objects.create(
            label="1: Category 1",
            text="Some text",
            dataspace=self.nexb_dataspace,
        )
        self.license_style1 = LicenseStyle.objects.create(
            name="style1", dataspace=self.nexb_dataspace
        )
        self.license_status1 = LicenseStatus.objects.create(
            code="code1", text="status1", dataspace=self.nexb_dataspace
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
            license_status=self.license_status1,
            license_style=self.license_style1,
            license_profile=self.license_profile1,
            full_text="abcdefghigklmnopqrstuvwxyz1234567890",
            homepage_url="http://www.nexb.com",
            text_urls="http://www.google.com",
        )
        self.license2 = License.objects.create(
            key="license2",
            name="License2",
            short_name="License2",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner,
            license_style=self.license_style1,
            license_profile=self.license_profile1,
            full_text="abcdefgh",
            homepage_url="http://www.gun.com",
            text_urls="http://www.gpl.com",
        )
        self.license3 = License.objects.create(
            key="license3",
            name="License3",
            short_name="License3",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner,
            license_style=self.license_style1,
            license_profile=self.license_profile1,
            full_text="123456789",
            homepage_url="http://www.opensource.com",
            text_urls="http://www.public.com",
        )
        self.license_tag1 = LicenseTag.objects.create(
            label="Tag 1", text="Text for tag1", dataspace=self.nexb_dataspace
        )

    def test_copy_license_unique_conflict_on_fks(self):
        original_license_count = License.objects.count()
        self.client.login(username="nexb_user", password="t3st")
        LicenseCategory.objects.create(
            uuid=self.category1.uuid,
            label="1: Category 1",
            text="Some text",
            dataspace=self.dataspace_target,
        )
        # Not the same UUID on purpose! origin of the conflict
        LicenseStyle.objects.create(name="style1", dataspace=self.dataspace_target)

        # Copy self.license1 in the target
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

        # The license was not copied because of a conflict on the Style
        self.assertEqual(original_license_count, License.objects.count())
        self.assertEqual(2, LicenseCategory.objects.count())
        self.assertEqual(2, LicenseStyle.objects.count())

    def test_copy_license_common_2(self):
        copied_license = copy_object(self.license1, self.dataspace_target, self.user)

        self.assertEqual(4, License.objects.count())
        self.assertEqual(2, LicenseCategory.objects.count())
        self.assertEqual(2, LicenseStyle.objects.count())
        self.assertEqual(2, LicenseProfile.objects.count())
        self.assertEqual("style1", copied_license.license_style.name)
        self.assertEqual(
            self.license1.name, License.objects.get(dataspace=self.dataspace_target).name
        )

        history = History.objects.get_for_object(copied_license).get()
        self.assertEqual(
            f'Copy object from "{self.nexb_dataspace}" dataspace to'
            f' "{self.dataspace_target.name}" dataspace.',
            history.change_message,
        )

        self.assertEqual(
            str(self.license1.category.label),
            str(License.objects.get(dataspace=self.dataspace_target).category.label),
        )
        self.assertNotEqual(
            self.license1.owner, License.objects.get(dataspace=self.dataspace_target).owner
        )
        self.assertEqual(
            self.license1.owner.name,
            License.objects.get(dataspace=self.dataspace_target).owner.name,
        )
        self.assertEqual(
            self.dataspace_target,
            License.objects.get(dataspace=self.dataspace_target).owner.dataspace,
        )
        self.assertEqual(
            str(self.license1.license_style.name),
            str(License.objects.get(dataspace=self.dataspace_target).license_style.name),
        )
        self.assertEqual(
            str(self.license1.license_profile.name),
            str(License.objects.get(dataspace=self.dataspace_target).license_profile.name),
        )
        self.assertEqual(
            self.license1.full_text, License.objects.get(dataspace=self.dataspace_target).full_text
        )
        self.assertEqual(
            self.license1.homepage_url,
            License.objects.get(dataspace=self.dataspace_target).homepage_url,
        )
        self.assertEqual(
            self.license1.text_urls, License.objects.get(dataspace=self.dataspace_target).text_urls
        )

    def test_copy_license_foreign_keys_no_exclude(self):
        license = License.objects.create(
            key="license_key",
            name="License",
            short_name="License",
            license_status=self.license_status1,
            owner=self.owner,
            dataspace=self.nexb_dataspace,
        )
        # Do not exclude anything on purpose
        exclude = {License: []}
        copied_object = copy_object(license, self.dataspace_target, self.user, exclude=exclude)

        self.assertEqual(license.uuid, copied_object.uuid)
        # The FK objects have been copied in the target too.
        self.assertEqual(self.dataspace_target, copied_object.owner.dataspace)
        self.assertEqual(self.dataspace_target, copied_object.license_status.dataspace)

    def test_copy_license(self):
        self.client.login(username="nexb_user", password="t3st")
        license1 = License.objects.create(
            key="license_1",
            short_name="1",
            owner=self.owner,
            dataspace=self.nexb_dataspace,
        )
        license2 = License.objects.create(
            name="license_1",
            short_name="2",
            owner=self.owner,
            dataspace=self.nexb_dataspace,
        )
        license3 = License.objects.create(
            key="license_1_3",
            name="license_1_2",
            short_name="3",
            owner=self.owner,
            dataspace=self.nexb_dataspace,
        )
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(license1.id) + "," + str(license2.id) + "," + str(license3.id),
            "source": license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        self.client.post(url, data)
        self.assertEqual(3, License.objects.scope(self.dataspace_target).count())

    def test_copy_license_2(self):
        self.client.login(username="nexb_user", password="t3st")
        license1 = License.objects.create(
            key="license_1",
            short_name="1",
            owner=self.owner,
            dataspace=self.nexb_dataspace,
        )
        license2 = License.objects.create(
            name="license_1",
            short_name="2",
            owner=self.owner,
            dataspace=self.nexb_dataspace,
        )
        license3 = License.objects.create(
            key="license_1_3",
            name="license_1_2",
            short_name="3",
            owner=self.owner,
            dataspace=self.nexb_dataspace,
        )
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(license1.id) + "," + str(license2.id) + "," + str(license3.id),
            "source": license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        self.client.post(url, data)
        self.assertEqual(3, License.objects.scope(self.dataspace_target).count())

    def test_copy_license_5(self):
        self.client.login(username="nexb_user", password="t3st")
        license1 = License.objects.create(
            key="license_1",
            short_name="1",
            owner=self.owner,
            dataspace=self.nexb_dataspace,
        )
        license2 = License.objects.create(
            name="license_1",
            short_name="2",
            owner=self.owner,
            dataspace=self.nexb_dataspace,
        )
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(license1.id) + "," + str(license2.id),
            "source": license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        self.client.post(url, data)
        self.assertEqual(2, License.objects.scope(self.dataspace_target).count())

    def test_update_license_1(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "exclude_copy": ["guidance", "guidance_url", "usage_policy"],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        self.client.post(url, data)  # This one is a copy
        copied_license = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )
        # Making sure the source obj have a license_status
        self.assertTrue(self.license1.license_status)

        # Preparation for an update
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "select_for_update": str(copied_license.id),
            "exclude_update": ["is_active", "reviewed", "guidance", "guidance_url", "usage_policy"],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        self.client.post(url, data)

        updated_license = License.objects.get(
            key=self.license1.key, dataspace=self.dataspace_target
        )
        # The license status has been updated as it's not part of the update
        # exclude
        self.assertEqual(self.license1.license_status.uuid, updated_license.license_status.uuid)
        self.assertEqual("style1", updated_license.license_style.name)

        history_license = History.objects.get_for_object(updated_license)
        self.assertEqual(2, len(history_license))
        expected_message = 'Updated object from "{}" dataspace to "{}" dataspace.'.format(
            self.nexb_dataspace, self.dataspace_target.name
        )
        self.assertEqual(expected_message, history_license.latest("id").change_message)
        self.assertEqual(History.CHANGE, history_license.latest("id").action_flag)

    def test_update_license_2(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "exclude_copy": ["guidance", "guidance_url", "usage_policy"],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        self.client.post(url, data)  # This one is a copy

        copied_license = License.objects.latest("id")
        # Preparation for an update
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "select_for_update": str(copied_license.id),
            "exclude_update": ["is_active", "reviewed", "guidance", "guidance_url", "usage_policy"],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        self.client.post(url, data)

        updated_license = License.objects.get(
            name=self.license1.name, dataspace=self.dataspace_target
        )

        # The license status has been updated as it's not part of the update
        # exclude
        self.assertEqual(self.license1.license_status.uuid, updated_license.license_status.uuid)
        self.assertEqual("style1", updated_license.license_style.name)

        history_license = History.objects.get_for_object(updated_license)
        self.assertEqual(2, len(history_license))
        expected_message = 'Updated object from "{}" dataspace to "{}" dataspace.'.format(
            self.nexb_dataspace, self.dataspace_target.name
        )
        self.assertEqual(expected_message, history_license.latest("id").change_message)
        self.assertEqual(History.CHANGE, history_license.latest("id").action_flag)

        self.assertEqual(4, License.objects.count())
        self.assertEqual(2, LicenseCategory.objects.count())
        self.assertEqual(2, LicenseStyle.objects.count())
        self.assertEqual(2, LicenseStatus.objects.count())
        self.assertEqual(2, LicenseProfile.objects.count())

    def test_update_license_fk_value_override(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "exclude_copy": ["guidance", "guidance_url", "usage_policy"],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        # Copying the license1 through the admin action.
        self.client.post(url, data)

        # Resetting the Style on the original license1
        self.license1.license_style = None
        self.license1.save()

        copied_license = License.objects.latest("id")
        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "select_for_update": str(copied_license.id),
            "exclude_update": ["is_active", "reviewed", "guidance", "guidance_url", "usage_policy"],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
        }
        # Re-doing the copy with the update option enabled.
        self.client.post(url, data)

        # Refreshing the new object instance
        copied_license = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )

        # The Style on the target instance was not overriden by None
        self.assertNotEqual(None, copied_license.license_style)

        history_license = History.objects.get_for_object(copied_license)
        self.assertEqual(2, len(history_license))
        expected_message = 'Updated object from "{}" dataspace to "{}" dataspace.'.format(
            self.nexb_dataspace, self.dataspace_target.name
        )
        self.assertEqual(expected_message, history_license.latest("id").change_message)
        self.assertEqual(History.CHANGE, history_license.latest("id").action_flag)

        self.assertEqual(4, License.objects.count())
        self.assertEqual(2, LicenseCategory.objects.count())
        self.assertEqual(2, LicenseStyle.objects.count())
        self.assertEqual(2, LicenseStatus.objects.count())
        self.assertEqual(2, LicenseProfile.objects.count())

    def test_license_compare_update_value(self):
        self.client.login(username="nexb_user", password="t3st")
        updated_target = copy_object(self.license1, self.dataspace_target, self.user)

        # To test the case the FK to copy is None
        self.license1.category = None
        self.license1.save()

        # Reset several values on the target object, category is left on purpose
        updated_target.license_style = None
        updated_target.license_profile = None
        updated_target.license_status = None
        updated_target.full_text = ""
        updated_target.guidance = "changenotes"
        updated_target.save()

        data = {
            "ids": str(self.license1.id),
            "target": self.dataspace_target.id,
            "post": "update",
            "checkbox_select": [
                "category",
                "license_style",
                "license_profile",
                "full_text",
            ],
        }

        url = "{url}?ids={ids}&target={target}".format(
            url=reverse("admin:license_library_license_compare"), **data
        )

        # Using the compare view to update value on the target object
        self.client.post(url, data)

        # Refresh the target object following the update
        updated_target = License.objects.get(
            name=self.license1.name, dataspace=self.dataspace_target
        )

        # FK fields
        self.assertEqual(self.license1.owner.uuid, updated_target.owner.uuid)
        self.assertEqual(self.license1.license_style.uuid, updated_target.license_style.uuid)
        self.assertEqual(self.license1.license_profile.uuid, updated_target.license_profile.uuid)
        self.assertEqual(self.license1.owner.uuid, updated_target.owner.uuid)
        self.assertEqual(None, updated_target.category)
        # Local fields
        self.assertEqual(self.license1.full_text, updated_target.full_text)
        self.assertEqual("changenotes", updated_target.guidance)

    def test_admin_compare_view_with_multiple_ids(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_compare")
        data = {
            "ids": "{},{}".format(self.license1.id, self.license2.id),
            "target": self.dataspace_target.id,
        }
        response = self.client.get(url, data, follow=True)
        self.assertRedirects(response, reverse("admin:license_library_license_changelist"))
        self.assertContains(
            response, "Compare allows 1 object only. Please select 1 object to compare."
        )

    def test_admin_compare_view_with_non_existing_object_id(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_compare")
        data = {
            "ids": 99999,
            "target": self.dataspace_target.id,
        }
        response = self.client.get(url, data, follow=True)
        self.assertRedirects(response, reverse("admin:license_library_license_changelist"))

    def test_license_compare_views_include_preserved_filters(self):
        self.client.login(username="nexb_user", password="t3st")
        copied_object = copy_object(self.license1, self.dataspace_target, self.user)
        changelist_url = reverse("admin:license_library_license_changelist")
        compare_url = reverse("admin:license_library_license_compare")
        changelist_filters = "?o=-3"  # order by name reversed
        preserved_filters = "?_changelist_filters=o%3D-3"
        license_id = str(self.license1.id)
        target_id = str(self.dataspace_target.id)

        data = {
            "_selected_action": license_id,
            "action": "compare_with",
        }
        # simulate selecting the action from the changelist
        response = self.client.post(changelist_url + changelist_filters, data, follow=True)
        redirect_url = "{}{}&ids={}".format(compare_url, preserved_filters, license_id)
        self.assertRedirects(response, redirect_url)
        expected = '<a href="{}{}">Licenses</a>'.format(changelist_url, changelist_filters)
        self.assertContains(response, expected)
        expected = (
            '<input id="id__changelist_filters" name="_changelist_filters"'
            ' type="hidden" value="o=-3" />'
        )
        self.assertContains(response, expected, html=True)
        expected = '<a href="{}{}">License1 (license1)</a>'.format(
            self.license1.get_admin_url(), preserved_filters
        )
        self.assertContains(response, expected)
        expected = '<a class="grp-button cancel-link" href="{}{}">Return to list</a>'.format(
            changelist_url, changelist_filters
        )
        self.assertContains(response, expected)

        # compare view
        response = self.client.get(redirect_url + "&target=" + target_id)
        expected = '<a href="{}{}">Licenses</a>'.format(changelist_url, changelist_filters)
        self.assertContains(response, expected)
        expected = '<a href="{}{}" target="_blank">License1 (license1)</a>'.format(
            self.license1.get_admin_url(), preserved_filters
        )
        self.assertContains(response, expected)
        expected = '<a href="{}{}" target="_blank">License1 (license1)</a>'.format(
            copied_object.get_admin_url(), preserved_filters
        )
        self.assertContains(response, expected)
        expected = '<a class="grp-button cancel-link" href="{}{}">Return to list</a>'.format(
            changelist_url, changelist_filters
        )
        self.assertContains(response, expected)

        response = self.client.post(redirect_url + "&target=" + target_id)
        self.assertRedirects(response, "{}{}".format(changelist_url, changelist_filters))

    def test_license_copy_views_include_preserved_filters(self):
        self.client.login(username="nexb_user", password="t3st")
        changelist_url = reverse("admin:license_library_license_changelist")
        copy_url = reverse("admin:license_library_license_copy")
        changelist_filters = "?o=-3"  # order by name reversed
        preserved_filters = "?_changelist_filters=o%3D-3"
        license_id = str(self.license1.id)
        target_id = str(self.dataspace_target.id)

        data = {
            "_selected_action": license_id,
            "action": "copy_to",
        }
        # simulate selecting the action from the changelist
        response = self.client.post(changelist_url + changelist_filters, data, follow=True)
        redirect_url = "{}{}&ids={}".format(copy_url, preserved_filters, license_id)
        self.assertRedirects(response, redirect_url)
        expected = '<a href="{}{}">Licenses</a>'.format(changelist_url, changelist_filters)
        self.assertContains(response, expected)
        expected = (
            '<input id="id__changelist_filters" name="_changelist_filters"'
            ' type="hidden" value="o=-3" />'
        )
        self.assertContains(response, expected, html=True)
        expected = '<a class="grp-button cancel-link" href="{}{}">Return to list</a>'.format(
            changelist_url, changelist_filters
        )
        self.assertContains(response, expected)

        # copy view
        response = self.client.get(redirect_url + "&target=" + target_id)
        expected = '<a href="{}{}">Licenses</a>'.format(changelist_url, changelist_filters)
        self.assertContains(response, expected)
        expected = '<a href="{}{}">License1 (license1)</a>'.format(
            self.license1.get_admin_url(), preserved_filters
        )
        self.assertContains(response, expected)
        expected = '<a class="grp-button cancel-link" href="{}{}">Return to list</a>'.format(
            changelist_url, changelist_filters
        )
        self.assertContains(response, expected)

        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 0,
            "form-INITIAL_FORMS": 0,
        }
        response = self.client.post(redirect_url + "&target=" + target_id, data)
        self.assertContains(response, "Copy and update results")
        expected = '<a href="{}{}">License1 (license1) (nexB)</a>'.format(
            self.license1.get_admin_url(), preserved_filters
        )
        self.assertContains(response, expected)
        expected = '<a class="grp-button cancel-link" href="{}{}">Return to list</a>'.format(
            changelist_url, changelist_filters
        )
        self.assertContains(response, expected)

    def test_license_copy_views_popup_mode(self):
        self.client.login(username="nexb_user", password="t3st")
        copy_url = reverse("admin:license_library_license_copy")
        data = {"ids": str(self.license1.id)}

        # Choose the Target Dataspace view.
        response = self.client.get(copy_url, data=data)
        expected = 'onclick="window.history.back(); return false;">Return to list</a>'
        self.assertNotContains(response, expected)
        data[IS_POPUP_VAR] = 1
        response = self.client.get(copy_url, data=data)
        self.assertContains(response, expected)

        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 0,
            "form-INITIAL_FORMS": 0,
        }
        response = self.client.post(copy_url + "?{}=1".format(IS_POPUP_VAR), data=data)
        copied_license = License.objects.latest("id")
        self.assertContains(
            response, "opener.dismissRelatedLookupPopup(window, {});".format(copied_license.id)
        )

    def test_obj_copy_integrity_error(self):
        license1 = License.objects.create(
            key="key-1",
            name="Apache 2.0",
            short_name="Apache 2.0",
            owner=self.owner,
            dataspace=self.nexb_dataspace,
        )
        # Create another License in the dataspace_target with the same name as
        # license1 but a different key
        License.objects.create(
            key="key-2",
            name=license1.name,
            short_name="A",
            owner=self.target_owner,
            dataspace=self.dataspace_target,
        )
        # Now let's try to copy license1 in the dataspace_target
        # As the license1.key is not present in dataspace2 the Match
        # for update will not return anything, so it will consider the copy
        # as an ADDITION.
        # Although, as the field "name" is unique_together in an
        # Dataspace, an IntegrityError is raised during the save(),
        # caught by copy_object() to add some info in the exception and raise it
        # again.
        with self.assertRaises(IntegrityError):
            copy_object(license1, self.dataspace_target, self.user)

    def test_obj_update_integrity_error(self):
        license1 = License.objects.create(
            key="key-1",
            name="Apache 2.0",
            short_name="Apache 2.0",
            owner=self.owner,
            dataspace=self.nexb_dataspace,
        )
        # Create 2 other Licenses in the dataspace_target:
        # One with the same key, so it match for update
        # One with the same name, so the copy of the first raise an IntegrityError
        License.objects.create(
            key=license1.key,
            name="Some Name",
            short_name="Some Name",
            owner=self.target_owner,
            dataspace=self.dataspace_target,
        )
        License.objects.create(
            key="nay-key",
            name=license1.name,
            short_name="A",
            owner=self.target_owner,
            dataspace=self.dataspace_target,
        )
        # We are now make a copy, which is an update in that case of the license1
        # into the dataspace_target. A match is done on the key, so we ask for an update
        # As the name already exist in the dataspace_target on another License, here
        # it's license3, an error is raised
        with self.assertRaises(IntegrityError):
            copy_object(license1, self.dataspace_target, self.user, True)

    def test_license_update_excluded_fields(self):
        # Those fields should not be updated during an update process:
        # update_excludes = ['is_active', 'reviewed', 'guidance']
        license1 = License.objects.create(
            key="key-1",
            name="Apache 2.0",
            short_name="Apache 2.0",
            owner=self.owner,
            is_active=True,
            reviewed=True,
            guidance="Some user notes",
            request_count=1,  # This should always be excluded by default
            dataspace=self.nexb_dataspace,
        )
        # Creating a Licenses with the same uuid (for match) in the dataspace_target:
        License.objects.create(
            uuid=license1.uuid,
            key=license1.key,
            name="Different name",
            short_name="Different name",
            owner=self.target_owner,
            is_active=False,
            reviewed=False,
            guidance="Different notes",
            request_count=0,
            dataspace=self.dataspace_target,
        )

        # Making the update
        updated_obj = copy_object(license1, self.dataspace_target, self.user, update=True)
        # Let's make sure field like name are updated while excluded fields are not
        self.assertEqual(license1.name, updated_obj.name)
        self.assertNotEqual(license1.dataspace, updated_obj.dataspace)
        self.assertEqual(license1.is_active, updated_obj.is_active)
        self.assertEqual(license1.reviewed, updated_obj.reviewed)
        self.assertNotEqual(license1.guidance, updated_obj.guidance)
        self.assertNotEqual(license1.request_count, updated_obj.request_count)
        self.assertEqual(0, updated_obj.request_count)

    def test_license_copy_missing_m2m_on_update(self):
        # No m2m tags on our self.license1 at the moment
        self.assertEqual(0, self.license1.tags.count())
        # Let's copy our license in the target
        copied_license = copy_object(self.license1, self.dataspace_target, self.user)
        # No m2m tags on our copied license neither
        self.assertEqual(0, copied_license.tags.count())

        # Now let's add an AssignedTag to the reference self.license1
        assigned_tag = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        # And copy it again with update activated
        copy_object(self.license1, self.dataspace_target, self.user, update=True)

        # The m2m relation and the related object were copied during the update
        copied_tag = LicenseTag.objects.get(
            uuid=self.license_tag1.uuid, dataspace=self.dataspace_target
        )
        copied_assigned_tag = LicenseAssignedTag.objects.get(
            uuid=assigned_tag.uuid, dataspace=self.dataspace_target
        )

        self.assertEqual(self.license_tag1.label, copied_tag.label)
        self.assertEqual(assigned_tag.value, copied_assigned_tag.value)

    def test_license_update_m2m(self):
        assigned_tag = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )

        # Let's copy our license in the target
        copy_object(self.license1, self.dataspace_target, self.user)

        # The tag was copied along and the assigned value should be the same
        copied_tag = LicenseTag.objects.get(
            uuid=self.license_tag1.uuid, dataspace=self.dataspace_target
        )
        copied_assigned_tag = LicenseAssignedTag.objects.get(
            uuid=assigned_tag.uuid, dataspace=self.dataspace_target
        )

        self.assertEqual(self.license_tag1.label, copied_tag.label)
        self.assertEqual(assigned_tag.value, copied_assigned_tag.value)

        # Change the self.license_tag1.label and assigned_tag.value
        self.license_tag1.label = "NEW LABEL"
        self.license_tag1.save()
        assigned_tag.value = False
        assigned_tag.save()

        # We want to update the relation but never the object at the end!
        # Copy again forcing an update
        # Do not exclude anything on purpose, otherwise the assigned_tag.value
        # is exclude by default.
        exclude = {LicenseAssignedTag: []}
        copy_object(self.license1, self.dataspace_target, self.user, update=True, exclude=exclude)

        # Refresh instances
        copied_tag = LicenseTag.objects.get(
            uuid=self.license_tag1.uuid, dataspace=self.dataspace_target
        )
        copied_assigned_tag = LicenseAssignedTag.objects.get(
            uuid=assigned_tag.uuid, dataspace=self.dataspace_target
        )

        # The label will not be updated, as it's at the end of the relation
        self.assertNotEqual(self.license_tag1.label, copied_tag.label)
        # The value on the assigned_tag is updated to False as it's the relation
        # table (through) and we explicitly do not exclude any field.
        self.assertEqual(assigned_tag.value, copied_assigned_tag.value)

        # Now setting an Unknown (None) value on the reference assigned tag
        assigned_tag.value = None
        assigned_tag.save()

        # Copy again forcing an update
        copy_object(self.license1, self.dataspace_target, self.user, update=True)
        # Unknown value on BooleanField.null=True are never propagated to the target
        # on update.
        copied_assigned_tag = LicenseAssignedTag.objects.get(
            uuid=assigned_tag.uuid, dataspace=self.dataspace_target
        )
        self.assertEqual(False, copied_assigned_tag.value)
        self.assertEqual(None, assigned_tag.value)

    def test_license_related_models_update_m2m_exclude(self):
        license_assigned_tag = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )

        profile_assigned_tag = LicenseProfileAssignedTag.objects.create(
            license_profile=self.license_profile1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )

        # Let's copy our license in the target, self.license_profile1 and its
        # m2m are copied too.
        copy_object(self.license1, self.dataspace_target, self.user)

        copied_license_assigned_tag = LicenseAssignedTag.objects.get(
            uuid=license_assigned_tag.uuid, dataspace=self.dataspace_target
        )
        copied_profile_assigned_tag = LicenseProfileAssignedTag.objects.get(
            uuid=profile_assigned_tag.uuid, dataspace=self.dataspace_target
        )

        self.assertEqual(license_assigned_tag.value, copied_license_assigned_tag.value)
        self.assertEqual(profile_assigned_tag.value, copied_profile_assigned_tag.value)

        # Changing the assigned value of the tags
        license_assigned_tag.value = False
        license_assigned_tag.save()
        profile_assigned_tag.value = False
        profile_assigned_tag.save()

        # Copy the self.license1 again forcing an update
        exclude = {
            LicenseAssignedTag: ["value"],
            LicenseProfileAssignedTag: ["value"],
        }
        copy_object(self.license1, self.dataspace_target, self.user, update=True, exclude=exclude)
        # The value on the target assigned tag was left as is, as "value" is
        # exclude on update by default.
        copied_license_assigned_tag = LicenseAssignedTag.objects.get(
            uuid=license_assigned_tag.uuid, dataspace=self.dataspace_target
        )
        self.assertEqual(True, copied_license_assigned_tag.value)

        # Same if copying the self.license_profile1
        copy_object(
            self.license_profile1, self.dataspace_target, self.user, update=True, exclude=exclude
        )
        copied_profile_assigned_tag = LicenseProfileAssignedTag.objects.get(
            uuid=profile_assigned_tag.uuid, dataspace=self.dataspace_target
        )
        self.assertEqual(True, copied_profile_assigned_tag.value)

    def test_copy_license_with_annotation_as_one2many(self):
        self.assertEqual(
            ["annotations", "external_references"], License.get_extra_relational_fields()
        )

        assignedtag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        annotation1 = LicenseAnnotation.objects.create(
            license=self.license1,
            assigned_tag=assignedtag1,
            quote="Quote",
            text="nexb copyright",
            range_start_offset=3,
            range_end_offset=5,
            dataspace=self.nexb_dataspace,
        )

        self.assertTrue(self.license1.annotations.count())
        copied_license = copy_object(self.license1, self.dataspace_target, self.user)
        self.assertTrue(copied_license.annotations.count())

        # Nothing is excluded by default on the LicenseAnnotation Model.
        copied_annotation = LicenseAnnotation.objects.get(
            uuid=annotation1.uuid, dataspace=self.dataspace_target
        )
        self.assertEqual(annotation1.quote, copied_annotation.quote)
        self.assertEqual(annotation1.text, copied_annotation.text)
        self.assertEqual(annotation1.range_start_offset, copied_annotation.range_start_offset)
        self.assertEqual(annotation1.range_end_offset, copied_annotation.range_end_offset)

    def test_copy_license_one2many_exclude(self):
        assignedtag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        annotation1 = LicenseAnnotation.objects.create(
            license=self.license1,
            assigned_tag=assignedtag1,
            quote="Quote",
            text="nexb copyright",
            range_start_offset=3,
            range_end_offset=5,
            dataspace=self.nexb_dataspace,
        )

        exclude_choices = [f.name for f in LicenseAnnotation().get_exclude_candidates_fields()]
        self.assertEqual(["assigned_tag", "text", "quote"], exclude_choices)

        # Let's exclude all the available fields on the LicenseAnnotation
        exclude = {License: [], LicenseAnnotation: exclude_choices}

        copy_object(self.license1, self.dataspace_target, self.user, exclude=exclude)

        # Nothing is excluded by default on the LicenseAnnotation Model.
        copied_annotation = LicenseAnnotation.objects.get(
            uuid=annotation1.uuid, dataspace=self.dataspace_target
        )
        self.assertFalse(copied_annotation.quote)
        self.assertFalse(copied_annotation.text)
        self.assertFalse(copied_annotation.assigned_tag)
        # Those were not excluded
        self.assertEqual(annotation1.range_start_offset, copied_annotation.range_start_offset)
        self.assertEqual(annotation1.range_end_offset, copied_annotation.range_end_offset)

    def test_copy_update_license_with_annotation_and_exclude(self):
        assignedtag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        LicenseAnnotation.objects.create(
            license=self.license1,
            assigned_tag=assignedtag1,
            quote="Quote",
            text="nexb copyright",
            range_start_offset=3,
            range_end_offset=5,
            dataspace=self.nexb_dataspace,
        )

        copy_object(self.license1, self.dataspace_target, self.user)

        # Adding 1 new annotation to our reference license
        annotation2 = LicenseAnnotation.objects.create(
            license=self.license1,
            assigned_tag=assignedtag1,
            quote="Quote2",
            text="nexb copyright2",
            range_start_offset=3,
            range_end_offset=5,
            dataspace=self.nexb_dataspace,
        )

        # Copy again without the update activated
        copy_object(self.license1, self.dataspace_target, self.user)
        copied_license = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )
        self.assertEqual(2, self.license1.annotations.count())
        # The new annotation was not copied
        self.assertEqual(1, copied_license.annotations.count())

        # Copy again with update and exclude
        exclude = {LicenseAnnotation: ["quote"]}
        copy_object(self.license1, self.dataspace_target, self.user, update=True, exclude=exclude)
        copied_license = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )
        self.assertEqual(2, copied_license.annotations.count())
        copied_annotation2 = LicenseAnnotation.objects.get(
            uuid=annotation2.uuid, dataspace=self.dataspace_target
        )
        self.assertFalse(copied_annotation2.quote)
        self.assertEqual(annotation2.text, copied_annotation2.text)

    def test_copy_license_m2m_fields_exclude(self):
        assignedtag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )

        exclude = {LicenseAssignedTag: ["value"]}
        copy_object(self.license1, self.dataspace_target, self.user, exclude=exclude)
        copied_assignedtag = LicenseAssignedTag.objects.get(
            uuid=assignedtag1.uuid, dataspace=self.dataspace_target
        )
        self.assertFalse(copied_assignedtag.value)

        # Copy again with update and no exclude on the value
        exclude = {LicenseAssignedTag: []}
        copy_object(self.license1, self.dataspace_target, self.user, update=True, exclude=exclude)
        copied_assignedtag = LicenseAssignedTag.objects.get(
            uuid=assignedtag1.uuid, dataspace=self.dataspace_target
        )
        self.assertTrue(copied_assignedtag.value)

    def test_copy_license_m2m_instances_exclude(self):
        LicenseAnnotation.objects.create(
            license=self.license1,
            quote="Quote",
            text="nexb copyright",
            range_start_offset=3,
            range_end_offset=5,
            dataspace=self.nexb_dataspace,
        )
        LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )

        self.assertEqual(1, self.license1.annotations.count())
        self.assertEqual(1, self.license1.licenseassignedtag_set.count())

        exclude = {
            LicenseAssignedTag: SKIP,
            LicenseAnnotation: SKIP,
        }
        copied_object = copy_object(
            self.license1, self.dataspace_target, self.user, exclude=exclude
        )

        self.assertEqual(0, copied_object.annotations.count())
        self.assertEqual(0, copied_object.licenseassignedtag_set.count())

        # Remove the copied object and copy without the instance exclusion
        copied_object.delete()
        exclude[LicenseAssignedTag] = []
        exclude[LicenseAnnotation] = []

        copied_object = copy_object(
            self.license1, self.dataspace_target, self.user, exclude=exclude
        )

        self.assertEqual(1, copied_object.annotations.count())
        self.assertEqual(1, copied_object.licenseassignedtag_set.count())

    def test_copy_license_m2m_instances_exclude_entire_relationship_on_copy(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        original_license_count = License.objects.count()

        LicenseAnnotation.objects.create(
            license=self.license1,
            quote="Quote",
            text="nexb copyright",
            range_start_offset=3,
            range_end_offset=5,
            dataspace=self.nexb_dataspace,
        )
        LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )

        self.assertEqual(1, self.license1.annotations.count())
        self.assertEqual(1, self.license1.licenseassignedtag_set.count())

        data = {
            "ids": str(self.license1.id),
            "target": self.dataspace_target.id,
        }
        response = self.client.get(url, data)
        self.assertContains(
            response,
            '<label for="id_form-0-skip_on_copy">Exclude this relationship entirely:</label>',
        )
        self.assertContains(
            response,
            '<input id="id_form-0-skip_on_copy" name="form-0-skip_on_copy" type="checkbox" />',
            html=True,
        )
        self.assertContains(
            response,
            '<label for="id_form-1-skip_on_copy">Exclude this relationship entirely:</label>',
        )
        self.assertContains(
            response,
            '<input id="id_form-1-skip_on_copy" name="form-1-skip_on_copy" type="checkbox" />',
            html=True,
        )

        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 2,
            "form-INITIAL_FORMS": 2,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
            "form-1-ct": ContentType.objects.get_for_model(LicenseAnnotation).pk,
            "form-0-skip_on_copy": True,
            "form-1-skip_on_copy": True,
        }
        response = self.client.post(url, data)
        self.assertContains(response, "<h2>The following Licenses have been copied</h2>")

        self.assertEqual(original_license_count + 1, License.objects.count())
        copied_license = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )

        self.assertEqual(0, copied_license.annotations.count())
        self.assertEqual(0, copied_license.licenseassignedtag_set.count())

    def test_copy_license_m2m_instances_exclude_entire_relationship_on_update(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")

        copied_license = copy_object(self.license1, self.dataspace_target, self.user)
        self.assertEqual(0, copied_license.annotations.count())
        self.assertEqual(0, copied_license.licenseassignedtag_set.count())

        LicenseAnnotation.objects.create(
            license=self.license1,
            quote="Quote",
            text="nexb copyright",
            range_start_offset=3,
            range_end_offset=5,
            dataspace=self.nexb_dataspace,
        )
        LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )

        self.assertEqual(1, self.license1.annotations.count())
        self.assertEqual(1, self.license1.licenseassignedtag_set.count())

        self.license1.full_text = "UPDATED TEXT"
        self.license1.save()

        data = {
            "ids": str(self.license1.id),
            "target": self.dataspace_target.id,
        }
        response = self.client.get(url, data)
        self.assertContains(
            response,
            '<label for="id_form-0-skip_on_update">Exclude this relationship entirely:</label>',
        )
        self.assertContains(
            response,
            '<input id="id_form-0-skip_on_update" name="form-0-skip_on_update" type="checkbox" />',
            html=True,
        )
        self.assertContains(
            response,
            '<label for="id_form-1-skip_on_update">Exclude this relationship entirely:</label>',
        )
        self.assertContains(
            response,
            '<input id="id_form-1-skip_on_update" name="form-1-skip_on_update" type="checkbox" />',
            html=True,
        )

        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "select_for_update": str(copied_license.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 2,
            "form-INITIAL_FORMS": 2,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
            "form-1-ct": ContentType.objects.get_for_model(LicenseAnnotation).pk,
            "form-0-skip_on_update": True,
            "form-1-skip_on_update": True,
        }
        response = self.client.post(url, data)
        self.assertContains(response, "<h2>The following Licenses have been updated.</h2>")

        copied_license.refresh_from_db()
        self.assertEqual(0, copied_license.annotations.count())
        self.assertEqual(0, copied_license.licenseassignedtag_set.count())
        self.assertEqual(self.license1.full_text, copied_license.full_text)

    def test_copy_license_including_external_reference(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")

        ext_source1 = ExternalSource.objects.create(
            label="GitHub",
            dataspace=self.nexb_dataspace,
        )

        ext_ref1 = ExternalReference.objects.create(
            content_type=ContentType.objects.get_for_model(self.license1),
            object_id=self.license1.pk,
            external_source=ext_source1,
            external_id="dejacode",
            external_url="http://url.com",
            dataspace=self.nexb_dataspace,
        )

        data = {
            "ids": str(self.license1.id),
            "target": self.dataspace_target.id,
        }
        response = self.client.get(url, data)
        self.assertContains(response, "<strong>External reference</strong>")

        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "copy_candidates": str(self.license1.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 3,
            "form-INITIAL_FORMS": 3,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
            "form-1-ct": ContentType.objects.get_for_model(LicenseAnnotation).pk,
            "form-2-ct": ContentType.objects.get_for_model(ExternalReference).pk,
        }
        response = self.client.post(url, data)
        self.assertContains(response, "The following Licenses have been copied")
        copied_license = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )
        copied_ext_source = ExternalSource.objects.get(
            uuid=ext_source1.uuid, dataspace=self.dataspace_target
        )

        self.assertEqual(1, copied_license.external_references.count())
        copied_ext_ref = copied_license.external_references.latest("id")
        self.assertEqual(ext_ref1.external_id, copied_ext_ref.external_id)
        self.assertEqual(ext_ref1.external_url, copied_ext_ref.external_url)
        self.assertEqual(ext_ref1.content_type, copied_ext_ref.content_type)
        self.assertEqual(self.license1.pk, ext_ref1.object_id)
        self.assertEqual(copied_license.pk, copied_ext_ref.object_id)
        self.assertEqual(copied_ext_source, copied_ext_ref.external_source)

        # Making sure we can skip the GenericRelation copy
        copied_ext_ref.delete()
        copied_ext_source.delete()
        copied_license.delete()
        data["form-2-skip_on_copy"] = True
        response = self.client.post(url, data)
        self.assertContains(response, "The following Licenses have been copied")
        copied_license = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )
        self.assertEqual(0, copied_license.external_references.count())

    def test_update_license_including_external_reference(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        self.assertEqual(0, ExternalReference.objects.count())

        copied_license = copy_object(self.license1, self.dataspace_target, self.user)
        self.assertEqual(0, copied_license.external_references.count())

        ext_source1 = ExternalSource.objects.create(
            label="GitHub",
            dataspace=self.nexb_dataspace,
        )

        ext_ref1 = ExternalReference.objects.create(
            content_type=ContentType.objects.get_for_model(self.license1),
            object_id=self.license1.pk,
            external_source=ext_source1,
            external_id="dejacode",
            external_url="http://url.com",
            dataspace=self.nexb_dataspace,
        )

        data = {
            "ids": str(self.license1.id),
            "target": self.dataspace_target.id,
        }
        response = self.client.get(url, data)
        self.assertContains(response, "<strong>External reference</strong>")
        self.assertContains(response, "The Licenses identified below already exist in the")

        data = {
            "ct": str(ContentType.objects.get_for_model(License).pk),
            "select_for_update": str(copied_license.id),
            "source": self.license1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 3,
            "form-INITIAL_FORMS": 3,
            "form-0-ct": ContentType.objects.get_for_model(LicenseAssignedTag).pk,
            "form-1-ct": ContentType.objects.get_for_model(LicenseAnnotation).pk,
            "form-2-ct": ContentType.objects.get_for_model(ExternalReference).pk,
        }
        response = self.client.post(url, data)
        self.assertContains(response, "The following Licenses have been updated.")
        copied_ext_source = ExternalSource.objects.get(
            uuid=ext_source1.uuid, dataspace=self.dataspace_target
        )

        self.assertEqual(2, ExternalReference.objects.count())
        self.assertEqual(1, self.license1.external_references.count())
        self.assertEqual(1, copied_license.external_references.count())
        copied_ext_ref = copied_license.external_references.latest("id")
        self.assertEqual(ext_ref1.external_id, copied_ext_ref.external_id)
        self.assertEqual(ext_ref1.external_url, copied_ext_ref.external_url)
        self.assertEqual(ext_ref1.content_type, copied_ext_ref.content_type)
        self.assertEqual(self.license1.pk, ext_ref1.object_id)
        self.assertEqual(copied_license.pk, copied_ext_ref.object_id)
        self.assertEqual(copied_ext_source, copied_ext_ref.external_source)

        # Re-update now that the external_reference already exists.
        ext_ref1.external_id = "new id"
        ext_ref1.save()
        response = self.client.post(url, data)
        self.assertContains(response, "The following Licenses have been updated.")
        copied_license = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )
        self.assertEqual(2, ExternalReference.objects.count())
        self.assertEqual(1, self.license1.external_references.count())
        self.assertEqual(1, copied_license.external_references.count())
        # The field was updated on the ExternalReference
        self.assertEqual(
            ext_ref1.external_id, copied_license.external_references.latest("id").external_id
        )

        # Making sure we can skip the GenericRelation copy
        copied_ext_ref.delete()
        copied_ext_source.delete()
        data["form-2-skip_on_update"] = True
        response = self.client.post(url, data)
        self.assertContains(response, "The following Licenses have been updated")
        copied_license = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )
        self.assertEqual(0, copied_license.external_references.count())

    def test_copy_update_license_contains_compare_link(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("admin:license_library_license_copy")
        copy_object(self.license1, self.dataspace_target, self.user)
        data = {
            "ids": str(self.license1.id),
            "target": self.dataspace_target.id,
        }
        response = self.client.get(url, data)
        compare_url = reverse("admin:license_library_license_compare")
        expected = '(<a target="_blank" href="{}?ids={}&target={}">compare</a>)'.format(
            compare_url, data["ids"], data["target"]
        )
        self.assertContains(response, expected)

    def test_copy_update_license_created_by_last_modified_date(self):
        self.license1.created_by = self.user
        self.license1.last_modified_by = self.user
        self.license1.save()

        # History fields are only set when the user copy to his dataspace
        self.assertNotEqual(self.dataspace_target, self.user.dataspace)

        copied_license = copy_object(self.license1, self.dataspace_target, self.user)
        self.assertIsNone(copied_license.created_by)
        self.assertIsNone(copied_license.last_modified_by)

        copied_license = copy_object(self.license1, self.dataspace_target, self.user, update=True)
        self.assertIsNone(copied_license.created_by)
        self.assertIsNone(copied_license.last_modified_by)

        copied_license.delete()
        self.alternate_user = create_superuser("alternate_user", self.dataspace_target)
        copied_license = copy_object(self.license1, self.dataspace_target, self.alternate_user)
        self.assertEqual(self.alternate_user, copied_license.created_by)
        self.assertEqual(self.alternate_user, copied_license.last_modified_by)

        copied_license.created_by = None
        copied_license.last_modified_by = None
        copied_license.save()
        copied_license = copy_object(
            self.license1, self.dataspace_target, self.alternate_user, update=True
        )
        self.assertIsNone(copied_license.created_by)
        self.assertEqual(self.alternate_user, copied_license.last_modified_by)

    def test_copy_update_m2m_skip_through_another_relation(self):
        assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1, license_tag=self.license_tag1, dataspace=self.nexb_dataspace
        )
        LicenseAnnotation.objects.create(
            license=self.license1,
            assigned_tag=assigned_tag1,
            range_start_offset=3,
            range_end_offset=5,
            dataspace=self.nexb_dataspace,
        )

        exclude = {LicenseAssignedTag: SKIP}
        copy_to(self.license1, self.dataspace_target, self.user, exclude=exclude)
