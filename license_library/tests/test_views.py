#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import resolve_url
from django.test import TestCase
from django.urls import reverse

from dje.copier import copy_object
from dje.models import Dataspace
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.tests import MaxQueryMixin
from license_library.models import License
from license_library.models import LicenseAnnotation
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseCategory
from license_library.models import LicenseProfile
from license_library.models import LicenseStyle
from license_library.models import LicenseTag
from license_library.models import LicenseTagGroup
from license_library.models import LicenseTagGroupAssignedTag
from organization.models import Owner
from organization.models import Subowner


class LicenseListViewTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(
            name="nexB",
            show_usage_policy_in_user_views=False,
            show_license_profile_in_license_list_view=True,
        )
        self.user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.other_dataspace = Dataspace.objects.create(name="Other")
        self.other_user = get_user_model().objects.create_superuser(
            "other_user", "other@test.com", "t3st", self.other_dataspace
        )
        self.owner1 = Owner.objects.create(name="Owner1", dataspace=self.nexb_dataspace)
        self.owner2 = Owner.objects.create(name="Owner2", dataspace=self.nexb_dataspace)
        self.category1 = LicenseCategory.objects.create(
            label="1: Category 1",
            text="Some text",
            dataspace=self.nexb_dataspace,
        )
        self.category2 = LicenseCategory.objects.create(
            label="2: Category 2",
            text="This is Category 2",
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
            name="The Best License",
            short_name="The Best License",
            category=self.category1,
            dataspace=self.nexb_dataspace,
            owner=self.owner1,
            license_style=self.license_style1,
            license_profile=self.license_profile1,
            full_text="abcdefghigklmnopqrstuvwxyz1234567890",
            # Publishing the license in the LL list view
            is_active=True,
        )
        self.license2 = License.objects.create(
            key="license2",
            name="The Worst License",
            short_name="The Worst License",
            category=self.category2,
            dataspace=self.nexb_dataspace,
            owner=self.owner1,
            full_text="abcdef",
            # Publishing the license in the LL list view
            is_active=True,
        )
        self.license3 = License.objects.create(
            key="license3",
            # use 'ZZZ' to make self.license3 come last in the sequence of licenses
            name="The ZZZ License",
            short_name="The ZZZ License",
            category=self.category2,
            dataspace=self.nexb_dataspace,
            owner=self.owner2,
            full_text="sometext",
            # Publishing the license in the LL list view
            is_active=True,
        )
        self.license_tag1 = LicenseTag.objects.create(
            label="Tag 1",
            text="Text for tag1",
            show_in_license_list_view=True,
            dataspace=self.nexb_dataspace,
        )
        self.license_assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        self.license_assigned_tag2 = LicenseAssignedTag.objects.create(
            license=self.license2,
            license_tag=self.license_tag1,
            value=False,
            dataspace=self.nexb_dataspace,
        )
        self.license_tag2 = LicenseTag.objects.create(
            label="Tag 2",
            text="Text for tag2",
            show_in_license_list_view=True,
            dataspace=self.nexb_dataspace,
        )
        LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag2,
            value=None,
            dataspace=self.nexb_dataspace,
        )
        self.group1 = LicenseTagGroup.objects.create(name="Group 1", dataspace=self.nexb_dataspace)
        self.license_tag_assigned_group1 = LicenseTagGroupAssignedTag.objects.create(
            license_tag_group=self.group1,
            license_tag=self.license_tag1,
            seq=1,
            dataspace=self.nexb_dataspace,
        )

    def test_license_library_list_view_access(self):
        url = resolve_url("license_library:license_list")

        response = self.client.get(url)
        self.assertRedirects(
            response, "{}?next={}".format(reverse("login"), reverse("license_library:license_list"))
        )

        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(url)

        licenses_links = [
            '<a href="{}">'.format(self.license1.get_absolute_url()),
            '<a href="{}#license-conditions">1: LicenseProfile1</a>'.format(
                self.license1.get_absolute_url()
            ),
            '<a href="{}">'.format(self.license2.get_absolute_url()),
        ]

        for link in licenses_links:
            self.assertContains(response, link)

        # Making sure the user can't see license outside his dataspace
        self.client.login(username="other_user", password="t3st")
        response = self.client.get(url)
        for link in licenses_links:
            self.assertNotContains(response, link)

    def test_license_library_list_view_search(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("license_library:license_list")

        # Empty search string
        data = {"q": ""}
        response = self.client.get(url, data)
        object_list = response.context["object_list"]
        self.assertIn(self.license1, object_list)
        self.assertIn(self.license2, object_list)
        self.assertIn(self.license3, object_list)

        # License1.owner name
        data = {"q": self.license1.owner.name}
        response = self.client.get(url, data)
        object_list = response.context["object_list"]
        self.assertIn(self.license1, object_list)
        self.assertIn(self.license2, object_list)
        self.assertNotIn(self.license3, object_list)

        # License1.key
        data = {"q": self.license1.key}
        response = self.client.get(url, data)
        object_list = response.context["object_list"]
        self.assertIn(self.license1, object_list)
        self.assertNotIn(self.license2, object_list)
        self.assertNotIn(self.license3, object_list)

    def test_license_library_list_view_license_text_search(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("license_library:license_list")

        # Empty search string
        data = {"text_search": ""}
        response = self.client.get(url, data)
        self.assertContains(response, self.license1.name)
        self.assertContains(response, self.license2.name)
        self.assertContains(response, self.license3.name)

        search_query = self.license1.full_text
        data = {"text_search": search_query}
        response = self.client.get(url, data)

        expected = (
            '<textarea maxlength="1500" rows="8" cols="10" id="text_search"'
            ' name="text_search" class="form-control"  style="width: 100%;">{}</textarea>'
        )
        self.assertContains(response, expected.format(search_query), html=True)
        self.assertContains(response, self.license1.name)
        self.assertNotContains(response, self.license2.name)
        self.assertNotContains(response, self.license3.name)

        search_query = "abc"
        data = {"text_search": search_query}
        response = self.client.get(url, data)

        self.assertContains(response, expected.format(search_query), html=True)
        self.assertContains(response, self.license1.name)
        self.assertContains(response, self.license2.name)
        self.assertNotContains(response, self.license3.name)

    def test_license_library_list_view_search_unicode(self):
        self.client.login(username="nexb_user", password="t3st")
        # Using Unicode chars in the search input
        data = {"q": ",\xe2\xc3"}
        response = self.client.get(reverse("license_library:license_list"), data)
        # Making sure a 500 is not raised
        self.assertEqual(200, response.status_code)

    def test_license_library_list_view_search_data_error_invalid_regular_expression(self):
        self.client.login(username="nexb_user", password="t3st")
        self.license1.name = "name with special chars c++"
        self.license1.save()
        data = {"q": "c++"}
        response = self.client.get(reverse("license_library:license_list"), data)
        self.assertEqual(200, response.status_code)

    def test_license_library_details_license_profile_tab(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.license1.get_absolute_url()
        response = self.client.get(url)

        self.assertContains(response, 'id="tab_license-conditions"')
        self.assertContains(response, f"{self.group1.name}")
        self.assertContains(response, f"<strong>{self.license_tag1.label}</strong>")
        self.assertContains(response, f"{self.license_tag1.text}</p>")

    def test_license_library_list_previous_next_license_link(self):
        self.client.login(username="nexb_user", password="t3st")
        # Call the list view to set the QS IDS in the session.  Order by name
        # so that it is predictable which license is the previous one and which
        # license is the next one.
        self.client.get(reverse("license_library:license_list") + "?o=name")
        # Calling the details view
        response = self.client.get(self.license2.get_absolute_url())
        self.assertIn("previous_object_url", response.context)
        self.assertIn("next_object_url", response.context)
        self.assertContains(
            response,
            f'<a class="btn btn-outline-secondary" href="{self.license1.get_absolute_url()}"'
            f' id="previous-button" data-bs-toggle="tooltip" title="Previous license"'
            f' aria-label="Previous object">',
        )
        self.assertContains(
            response,
            f'<a class="btn btn-outline-secondary" href="{self.license3.get_absolute_url()}"'
            f' id="next-button" data-bs-toggle="tooltip" title="Next license"'
            f' aria-label="Next object">',
        )

        self.license1.delete()
        self.license3.delete()
        response = self.client.get(self.license2.get_absolute_url())
        self.assertNotContains(response, "previous-button")
        self.assertNotContains(response, "next-button")
        self.assertNotIn("previous_object", response.context)
        self.assertNotIn("next_object", response.context)

    def test_license_library_list_view_num_queries(self):
        self.client.login(username="nexb_user", password="t3st")

        with self.assertNumQueries(16):
            self.client.get(reverse("license_library:license_list"))

    def test_license_profile_column_availability_in_license_list_view(self):
        self.assertTrue(self.nexb_dataspace.show_license_profile_in_license_list_view)
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("license_library:license_list")

        response = self.client.get(url)
        expected1 = '<option value="{name}">{name}</option>'.format(name=self.license_profile1.name)
        self.assertContains(response, expected1, html=True)

        # Switch the flag
        self.nexb_dataspace.show_license_profile_in_license_list_view = False
        self.nexb_dataspace.save()
        response = self.client.get(url)
        self.assertNotContains(response, expected1, html=True)

    def test_license_spdx_identifier_availability_in_license_list_view(self):
        self.assertFalse(self.nexb_dataspace.show_spdx_short_identifier_in_license_list_view)
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("license_library:license_list")
        self.license1.spdx_license_key = "SPDX Key"
        self.license1.save()

        response = self.client.get(url)
        expected = f'<code class="key ms-1">{self.license1.spdx_license_key}</code>'
        self.assertNotContains(response, expected, html=True)

        # Switch the flag
        self.nexb_dataspace.show_spdx_short_identifier_in_license_list_view = True
        self.nexb_dataspace.save()
        response = self.client.get(url)
        self.assertContains(response, expected, html=True)

    def test_license_library_list_tag_value_is_none(self):
        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(reverse("license_library:license_list"))
        expected = (
            '<td><a href="/licenses/nexB/license1/#license-conditions">1: LicenseProfile1</a></td>'
        )
        self.assertContains(response, expected, html=True)
        expected = (
            '<td class="text-center"><i class="fa-solid fa-circle-check color-true"></i></td>'
        )
        self.assertContains(response, expected, html=True)
        expected = '<td class="text-center"><i class="far fa-question-circle color-none"></i></td>'
        self.assertContains(response, expected, html=True)

    def test_license_library_list_client_data(self):
        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(reverse("license_library:license_list"))
        expected = {
            "license_categories": {
                self.category1.pk: "Some text",
                self.category2.pk: "This is Category 2",
            },
        }
        self.assertEqual(expected, response.context["client_data"])


class LicenseDetailsViewsTestCase(MaxQueryMixin, TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.other_dataspace = Dataspace.objects.create(name="Other")
        self.other_user = get_user_model().objects.create_superuser(
            "other_user", "other@test.com", "t3st", self.other_dataspace
        )

        self.owner1 = Owner.objects.create(name="Test Organization", dataspace=self.nexb_dataspace)
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
            owner=self.owner1,
            license_style=self.license_style1,
            license_profile=self.license_profile1,
            full_text="abcdefghigklmnopqrstuvwxyz1234567890",
            # Publishing the license in the LL list view
            is_active=True,
        )

    def test_license_library_detail_view(self):
        # We do not limit to is_license_library for the details view anymore.
        self.license1.key = "license-key-2.0"
        self.license1.is_active = False
        self.license1.save()
        expected = str(self.license1)
        url = self.license1.get_absolute_url()

        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(url)
        # Make sure it's accessible if not is_active
        self.assertContains(response, expected)

        # and Make sure it's accessible if is_active
        self.license1.is_active = True
        self.license1.save()
        response = self.client.get(url)
        self.assertContains(response, expected)

        # A user in any dataspace can look at reference data
        self.assertTrue(self.license1.dataspace.is_reference)
        self.client.login(username="other_user", password="t3st2")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)

        # Moving the component to a non-reference dataspace
        non_reference_dataspace = Dataspace.objects.create(name="NotReference")
        self.owner1.dataspace = non_reference_dataspace
        self.owner1.save()
        self.license1.dataspace = non_reference_dataspace
        self.license1.category = None
        self.license1.license_style = None
        self.license1.license_profile = None
        self.license1.save()
        response = self.client.get(url)
        self.assertContains(response, "Page not found", status_code=404)

    def test_license_library_detail_view_reference_data_label(self):
        url = self.license1.get_absolute_url()
        expected = '<span class="badge text-bg-warning reference-data-label"'
        self.assertTrue(self.license1.dataspace.is_reference)

        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(url)
        self.assertContains(response, expected)

        self.client.login(username="other_user", password="t3st2")
        response = self.client.get(url)
        self.assertContains(response, expected)

    def test_license_library_detail_view_is_user_dataspace(self):
        from workflow.models import Request
        from workflow.models import RequestTemplate

        request_template = RequestTemplate.objects.create(
            name="T",
            description="D",
            dataspace=self.user.dataspace,
            is_active=True,
            content_type=ContentType.objects.get_for_model(License),
        )
        Request.objects.create(
            title="Title",
            request_template=request_template,
            requester=self.user,
            content_object=self.license1,
            dataspace=self.nexb_dataspace,
        )

        from policy.models import UsagePolicy

        policy_approved = UsagePolicy.objects.create(
            label="Approved",
            icon="icon-ok-circle",
            content_type=ContentType.objects.get_for_model(License),
            dataspace=self.license1.dataspace,
        )
        self.license1.usage_policy = policy_approved
        self.license1.save()

        license_tag1 = LicenseTag.objects.create(
            label="Tag 1",
            text="Text for tag1",
            show_in_license_list_view=True,
            dataspace=self.nexb_dataspace,
        )
        license_assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        group1 = LicenseTagGroup.objects.create(name="Group 1", dataspace=self.nexb_dataspace)
        LicenseTagGroupAssignedTag.objects.create(
            license_tag_group=group1, license_tag=license_tag1, seq=1, dataspace=self.nexb_dataspace
        )

        LicenseAnnotation.objects.create(
            license=self.license1,
            text="annotation text",
            range_start_offset=1,
            range_end_offset=5,
            dataspace=self.nexb_dataspace,
            assigned_tag=license_assigned_tag1,
        )

        url = self.license1.get_absolute_url()
        self.assertTrue(self.license1.dataspace.is_reference)
        self.nexb_dataspace.show_usage_policy_in_user_views = True
        self.nexb_dataspace.save()
        self.other_dataspace.show_usage_policy_in_user_views = True
        self.other_dataspace.save()

        # The following are displayed or not depending if the user is looking
        # at Reference Data from a non-reference dataspace:
        # * Dataspace field in Essential tab
        expected0 = '<pre class="pre-bg-body-tertiary mb-1 field-dataspace">{}</pre>'.format(
            self.license1.dataspace
        )
        # * Activity tab
        expected1 = 'id="tab_activity"'
        # * Edit icon link as a superuser
        expected3 = '<i class="far fa-edit"></i>'
        # * Copy to my dataspace link
        expected4 = "Copy to my Dataspace"
        expected4_update = "Check for Updates"
        # * Usage policy respect the show_usage_policy_in_user_views
        # of the object.dataspace, rather than the user.dataspace
        expected5 = '<i class="icon-ok-circle" style="color: #000000;"></i>'
        #  * Annotation turned off when not is_user_dataspace
        expected6 = '<i class="fas fa-tag"></i>'
        expected7 = 'class="annotation_link"'

        self.assertTrue(self.user.is_superuser)
        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(url)
        self.assertContains(response, expected0, html=True)
        self.assertContains(response, expected1)
        self.assertContains(response, expected3)
        self.assertNotContains(response, expected4)
        self.assertNotContains(response, expected4_update)
        self.assertContains(response, expected5)
        self.assertContains(response, expected6)
        self.assertContains(response, expected7)

        self.nexb_dataspace.show_usage_policy_in_user_views = False
        self.nexb_dataspace.save()
        response = self.client.get(url)
        self.assertNotContains(response, expected5)

        self.assertTrue(self.other_user.is_superuser)
        self.client.login(username="other_user", password="t3st")
        response = self.client.get(url)
        self.assertContains(response, expected0, html=True)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected3)
        self.assertContains(response, expected4)
        self.assertNotContains(response, expected4_update)
        self.assertFalse(self.nexb_dataspace.show_usage_policy_in_user_views)
        self.assertTrue(self.other_dataspace.show_usage_policy_in_user_views)
        self.assertNotContains(response, expected5)
        self.assertNotContains(response, expected6)
        self.assertNotContains(response, expected7)

        copied_object = copy_object(self.license1, self.other_dataspace, self.other_user)
        response = self.client.get(url)
        self.assertNotContains(response, expected4)
        self.assertContains(response, expected4_update)

        response = self.client.get(copied_object.get_absolute_url())
        self.assertNotContains(response, expected4)
        self.assertContains(response, expected4_update)

        self.license1.delete()
        response = self.client.get(copied_object.get_absolute_url())
        self.assertNotContains(response, expected4)
        self.assertNotContains(response, expected4_update)

    def test_license_library_detail_view_num_queries(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.license1.get_absolute_url()
        with self.assertMaxQueries(21):
            self.client.get(url)

    def test_license_library_detail_edit_link_as_superuser(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.license1.get_absolute_url()
        html = f'<a href="{self.license1.get_admin_url()}"'
        response = self.client.get(url)
        # The admin link to edit page is only shown to superuser
        self.assertTrue(self.user.is_superuser)
        self.assertContains(response, html)
        # Let's make sure it's not displayed to regular users
        self.user.is_superuser = False
        self.user.save()
        response = self.client.get(url)
        self.assertNotContains(response, html)

    def test_license_library_detail_view_owner_tab_hierarchy_availability(self):
        # The js code related to the Owner hierarchy should is only embeded
        # is the Owner has relatives
        self.assertFalse(self.owner1.has_parent_or_child())
        self.client.login(username="nexb_user", password="t3st")
        url = self.license1.get_absolute_url()
        response = self.client.get(url)
        self.assertNotContains(response, "jsPlumb")
        self.assertNotContains(response, "Selected Owner")
        self.assertNotContains(response, "Child Owners")

        child_owner = Owner.objects.create(name="ChildOwner", dataspace=self.nexb_dataspace)
        Subowner.objects.create(
            parent=self.owner1, child=child_owner, dataspace=self.nexb_dataspace
        )

        response = self.client.get(url)
        self.assertContains(response, "jsPlumbHierarchy")
        self.assertContains(response, "Selected Owner")
        self.assertContains(response, "Child Owners")
        self.assertContains(response, child_owner.name)

        self.assertContains(
            response,
            '<div id="owner_{}" class="card bg-body-tertiary mb-2">'.format(self.owner1.id),
        )
        self.assertContains(
            response,
            '<div id="owner_{}" class="card bg-body-tertiary mb-2">'.format(child_owner.id),
        )
        self.assertContains(
            response, f"{{source: 'owner_{child_owner.id}', target: 'owner_{self.owner1.id}'}}"
        )

    def test_license_library_details_external_reference_tab(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.license1.get_absolute_url()

        response = self.client.get(url)
        expected = (
            '<button class="nav-link" id="tab_external-references-tab" data-bs-toggle="tab" '
            'data-bs-target="#tab_external-references" type="button" role="tab" '
            'aria-controls="tab_external-references" aria-selected="false">'
        )
        self.assertNotContains(response, expected)

        source1 = ExternalSource.objects.create(
            label="GitHub",
            dataspace=self.nexb_dataspace,
        )

        ext_ref1 = ExternalReference.objects.create_for_content_object(
            content_object=self.license1,
            external_source=source1,
            external_id="dejacode external id",
        )

        response = self.client.get(url)
        self.assertContains(response, expected)
        self.assertContains(response, ext_ref1.external_id)
        self.assertContains(response, source1.label)

    def test_license_library_details_properties_in_essentials_tab(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.license1.get_absolute_url()

        tag1 = LicenseTag.objects.create(label="Tag1", text="Text1", dataspace=self.nexb_dataspace)
        assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1, license_tag=tag1, value=False, dataspace=self.nexb_dataspace
        )

        expected1 = "Attribution required"
        expected2 = "Redistribution required"
        expected3 = "Change tracking required"

        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)

        tag1.attribution_required = True
        tag1.redistribution_required = True
        tag1.change_tracking_required = True
        tag1.save()
        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)

        assigned_tag1.value = True
        assigned_tag1.save()
        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)

    def test_license_library_download_text_view(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.license1.get_download_text_url()

        response = self.client.get(url)
        self.assertEqual(b"abcdefghigklmnopqrstuvwxyz1234567890", response.getvalue())
        self.assertEqual("text/plain", response["Content-Type"])
        self.assertEqual('attachment; filename="license1.LICENSE"', response["Content-Disposition"])
