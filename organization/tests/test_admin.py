#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.admin.options import IS_POPUP_VAR
from django.contrib.auth import get_user_model
from django.core.exceptions import NON_FIELD_ERRORS
from django.test import TestCase
from django.urls import reverse

from dje.copier import copy_object
from dje.filters import DataspaceFilter
from dje.filters import LimitToDataspaceListFilter
from dje.models import Dataspace
from dje.models import History
from dje.tests import create_user
from organization.models import Owner
from organization.models import Subowner

# WARNING: Do not import from local DJE apps except 'dje' and 'organization'


class OwnerAdminViewsTestCase(TestCase):
    def setUp(self):
        self.dataspace1 = Dataspace.objects.create(name="nexB")
        self.user = get_user_model().objects.create_superuser(
            "test", "test@test.com", "t3st", self.dataspace1
        )

        self.dataspace2 = Dataspace.objects.create(name="TestOrg")
        get_user_model().objects.create_superuser(
            "other_user", "test2@test.com", "t3st", self.dataspace2
        )

        self.dataspace_target = Dataspace.objects.create(name="target_dataspace")

        self.owner1 = Owner.objects.create(name="org1", dataspace=self.dataspace1)
        self.owner2 = Owner.objects.create(name="org2", dataspace=self.dataspace1)

        self.person1 = Owner.objects.create(
            name="person1", type="Person", dataspace=self.dataspace1
        )
        self.person2 = Owner.objects.create(
            name="person2", type="Person", dataspace=self.dataspace1
        )

        self.org1_person1 = Subowner.objects.create(
            parent=self.owner1,
            child=self.person1,
            start_date="2011-12-06",
            end_date="2011-12-08",
            notes="notes",
            dataspace=self.owner1.dataspace,
        )
        self.org1_person1_other_dates = Subowner.objects.create(
            parent=self.owner1,
            child=self.person1,
            start_date="2011-12-07",
            end_date="2011-12-08",
            notes="notes",
            dataspace=self.owner1.dataspace,
        )

        self.org1_person2 = Subowner.objects.create(
            parent=self.owner1,
            child=self.person2,
            start_date="2011-12-06",
            end_date="2011-12-08",
            notes="notes",
            dataspace=self.owner1.dataspace,
        )
        self.org2_person2 = Subowner.objects.create(
            parent=self.owner2,
            child=self.person2,
            start_date="2011-12-03",
            end_date="2011-12-08",
            notes="notes",
            dataspace=self.owner2.dataspace,
        )

    def test_copy_owner_common(self):
        owner = Owner.objects.create(
            name="org_common",
            dataspace=self.dataspace1,
            type="Organization",
            contact_info="li@nxb.com",
            notes="notes",
        )
        copied_object = copy_object(owner, self.dataspace_target, self.user)
        self.assertEqual(6, Owner.objects.count())
        self.assertEqual(owner.name, copied_object.name)

    def test_copy_owner_with_update(self):
        # Creation of a simple Owner in oo1
        oracle_in_dataspace1 = Owner.objects.create(
            name="Oracle",
            dataspace=self.dataspace1,
            notes="notes",
            contact_info="contact info",
            homepage_url="http://oracle.com",
        )

        # Copy this Owner in oo2
        copy_object(oracle_in_dataspace1, self.dataspace2, self.user)

        # Retrieving the new object
        oracle_in_dataspace2 = Owner.objects.get(
            uuid=oracle_in_dataspace1.uuid, dataspace=self.dataspace2
        )
        # Refreshing the original one
        oracle_in_dataspace1 = Owner.objects.get(
            uuid=oracle_in_dataspace1.uuid, dataspace=self.dataspace1
        )

        # Making sure each field was copied along
        self.assertEqual(oracle_in_dataspace1.name, oracle_in_dataspace2.name)
        self.assertEqual(oracle_in_dataspace1.contact_info, oracle_in_dataspace2.contact_info)
        self.assertEqual(oracle_in_dataspace1.notes, oracle_in_dataspace2.notes)
        self.assertEqual(oracle_in_dataspace1.homepage_url, oracle_in_dataspace2.homepage_url)

        # Let's change some data on oracle_in_dataspace1
        oracle_in_dataspace1.notes = "New Notes"
        oracle_in_dataspace1.save()

        # Copy again with update
        copy_object(oracle_in_dataspace1, self.dataspace2, self.user, update=True)

        # Refresh the both instances
        oracle_in_dataspace1 = Owner.objects.get(
            uuid=oracle_in_dataspace1.uuid, dataspace=self.dataspace1
        )
        oracle_in_dataspace2 = Owner.objects.get(
            uuid=oracle_in_dataspace1.uuid, dataspace=self.dataspace2
        )

        # Making sure the notes were updated
        self.assertEqual(oracle_in_dataspace1.notes, oracle_in_dataspace2.notes)

    def test_copy_owner_with_m2m(self):
        owner_count = Owner.objects.count()
        copied_object = copy_object(self.owner1, self.dataspace_target, self.user)

        # Only self.owner1 and its relation was copied
        # We do copy child owner m2m only, not parents.
        self.assertEqual(owner_count + 3, Owner.objects.count())
        m2m_objs = Subowner.objects.filter(parent=copied_object)
        self.assertEqual(3, len(m2m_objs))

        for m2m_obj in m2m_objs:
            self.assertTrue(m2m_obj.start_date)
            self.assertTrue(m2m_obj.end_date)
            self.assertTrue(m2m_obj.notes)

        copied_object2 = copy_object(self.owner2, self.dataspace_target, self.user)

        self.assertEqual(owner_count + 4, Owner.objects.count())
        history = History.objects.get_for_object(copied_object2).get()
        change_message = (
            f'Copy object from "{self.dataspace1}" dataspace to '
            f'"{self.dataspace_target}" dataspace.'
        )
        self.assertEqual(change_message, history.change_message)

        m2m_objs = Subowner.objects.filter(parent=copied_object2)
        self.assertEqual(1, len(m2m_objs))
        for m2m_obj in m2m_objs:
            self.assertTrue(m2m_obj.start_date)
            self.assertTrue(m2m_obj.end_date)
            self.assertTrue(m2m_obj.notes)

    def test_owner_add_validate_unique_in_dataspace(self):
        url = reverse("admin:organization_owner_add")
        data = {
            "name": self.owner1.name,
            "type": "Organization",
            "related_children-TOTAL_FORMS": 0,
            "related_children-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        self.client.login(username="test", password="t3st")
        # Trying to create an new Owner with a name that already exist
        response = self.client.post(url, data)
        error1 = '<p class="errornote">Please correct the error below.</p>'
        error2 = "<li>Owner with this Dataspace and Name already exists.</li>"
        self.assertContains(response, error1)
        self.assertContains(response, error2)
        expected = {NON_FIELD_ERRORS: ["Owner with this Dataspace and Name already exists."]}
        self.assertEqual(expected, response.context_data["adminform"].form.errors)

        alternate_owner = Owner.objects.create(name="other_owner", dataspace=self.dataspace2)
        # Edit an Owner that belongs to another Dataspace
        # Note that the Dataspace of test user needs to be the Reference
        url = alternate_owner.get_admin_url()
        response = self.client.get(url)

        dataspace_admin_url = alternate_owner.dataspace.get_admin_url()
        dataspace_readonly = (
            f"<label>Dataspace</label></div>"
            f'<div class="c-2">'
            f'<div class="grp-readonly">'
            f'<a href="{dataspace_admin_url}">{alternate_owner.dataspace}</a>'
            f"</div>"
        )
        self.assertContains(response, dataspace_readonly)

        # Creating a new Owner in Dataspace2
        new_owner2 = Owner.objects.create(name="AAA", dataspace=self.dataspace2)
        data["name"] = new_owner2.name
        # Trying to update with a name that already exists in Dataspace2
        response = self.client.post(url, data)
        self.assertContains(response, error1)
        self.assertContains(response, error2)
        self.assertEqual(expected, response.context_data["adminform"].form.errors)

    def test_owner_admin_form_clean_whitespace(self):
        self.client.login(username="test", password="t3st")

        url = reverse("admin:organization_owner_add")
        data = {
            "name": " leading",
            "type": "Organization",
            "related_children-TOTAL_FORMS": 0,
            "related_children-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        self.assertEqual("leading", Owner.objects.latest("id").name)

        data["name"] = "trailing "
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        self.assertEqual("trailing", Owner.objects.latest("id").name)

        data["name"] = "  both    "
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        self.assertEqual("both", Owner.objects.latest("id").name)

    def test_save_owner_with_deleted_inline(self):
        # Saving an existing Owner with a existing Subowner to be DELETED
        # through the Inline
        self.client.login(username="test", password="t3st")
        url = self.owner1.get_admin_url()
        data = {
            "name": self.owner1.name,
            "type": "Organization",
            "related_children-TOTAL_FORMS": 1,
            "related_children-INITIAL_FORMS": 1,
            "related_children-0-id": self.org1_person2.id,
            "related_children-0-DELETE": "on",
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        self.assertFalse(Subowner.objects.filter(id=self.org1_person2.id))

    def test_activity_log_activated(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:organization_owner_changelist")
        response = self.client.get(url)
        self.assertContains(response, "activity_log_link")

    def test_admin_changelist_view_from_action(self):
        # Make sure the POSTed action go through without error
        org = Owner.objects.create(name="SomeOrg", dataspace=self.dataspace1)
        self.client.login(username="test", password="t3st")
        url = reverse("admin:organization_owner_changelist")
        data = {"_selected_action": org.id, "action": "delete_selected", "select_across": 0}

        response = self.client.post(url, data)
        self.assertContains(response, "<h2>Are you sure you want to delete")

        # Let's confirm the deletion
        data["post"] = "yes"
        response = self.client.post(url, data, follow=True)
        error = '<li class="grp-success">Successfully deleted 1 owner.</li>'
        self.assertContains(response, error)

    def test_owner_changelist_has_filters_activated(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:organization_owner_changelist")
        response = self.client.get(url)
        self.assertFalse(response.context["cl"].has_filters_activated)
        response = self.client.post(url)
        self.assertFalse(response.context["cl"].has_filters_activated)

        params = "?created_date__gte=2017-01-25+00%3A00%3A00Z"
        response = self.client.get(url + params)
        self.assertTrue(response.context["cl"].has_filters_activated)
        response = self.client.post(url + params)
        self.assertTrue(response.context["cl"].has_filters_activated)

        params = f"?{DataspaceFilter.parameter_name}={self.dataspace2.id}"
        response = self.client.get(url + params)
        self.assertTrue(response.context["cl"].has_filters_activated)
        response = self.client.post(url + params)
        self.assertTrue(response.context["cl"].has_filters_activated)

    def test_owner_changelist_filters(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:organization_owner_changelist")
        response = self.client.get(url)
        expected = ("created_by", LimitToDataspaceListFilter)
        self.assertIn(expected, response.context["cl"].list_filter)

    def test_owner_changelist_licenses_and_components_columns(self):
        from license_library.models import License

        license1 = License.objects.create(
            name="License1",
            short_name="License1",
            owner=self.owner1,
            key="license-1",
            dataspace=self.owner1.dataspace,
        )
        self.client.login(username="test", password="t3st")
        url = reverse("admin:organization_owner_changelist")
        response = self.client.get(url)
        license_link = "<li>{}</li>".format(license1.get_admin_link(target="_blank"))
        self.assertContains(response, license_link)

        from component_catalog.models import Component

        component1 = Component.objects.create(
            name="Component1", owner=self.owner1, dataspace=self.owner1.dataspace
        )
        response = self.client.get(url)
        component_link = "<li>{}</li>".format(component1.get_admin_link(target="_blank"))
        self.assertContains(response, component_link)

    def test_dataspace_readonly_field_value_on_addition(self):
        # See the hack in DataspacedAdmin.render_change_form
        self.client.login(username="test", password="t3st")
        url = reverse("admin:organization_owner_add")
        response = self.client.get(url)

        dataspace = self.user.dataspace
        admin_url = dataspace.get_admin_url()
        expected = f'<div class="grp-readonly"><a href="{admin_url}">{dataspace}</a></div>'
        self.assertContains(response, expected)

    def test_dataspace_readonly_field_value_on_change(self):
        # The current user is looking at an Owner in his dataspace
        self.client.login(username="test", password="t3st")
        self.assertEqual(self.owner1.dataspace, self.user.dataspace)
        url = self.owner1.get_admin_url()
        response = self.client.get(url)

        dataspace = self.user.dataspace
        admin_url = dataspace.get_admin_url()
        expected = f'<div class="grp-readonly"><a href="{admin_url}">{dataspace}</a></div>'
        self.assertContains(response, expected)

    def test_dataspace_readonly_field_value_on_change_in_another_dataspace(self):
        # The current user is looking at an Owner in another dataspace
        self.client.login(username="test", password="t3st")
        owner = Owner.objects.create(name="Owner2", dataspace=self.dataspace2)
        self.assertNotEqual(owner.dataspace, self.user.dataspace)
        url = owner.get_admin_url()
        response = self.client.get(url)

        dataspace = owner.dataspace
        admin_url = dataspace.get_admin_url()
        expected = f'<div class="grp-readonly"><a href="{admin_url}">{dataspace}</a></div>'
        self.assertContains(response, expected)

    def test_owner_admin_changelist_popup_permission(self):
        simple_user = create_user("simple", self.dataspace1)
        simple_user.is_staff = True
        simple_user.save()
        self.assertFalse(simple_user.has_perm("organization.change_owner"))

        self.client.login(username=simple_user.username, password="secret")
        changelist_url = reverse("admin:organization_owner_changelist")
        response = self.client.get(changelist_url)
        self.assertEqual(403, response.status_code)

        # Available thanks to ChangelistPopupPermissionMixin
        response = self.client.get(changelist_url, data={IS_POPUP_VAR: 1})
        self.assertEqual(200, response.status_code)

        # Form view is never available though
        changeform_url = self.owner1.get_admin_url()
        response = self.client.get(changeform_url)
        self.assertEqual(403, response.status_code)

        # Available thanks to ChangelistPopupPermissionMixin
        response = self.client.get(changeform_url, data={IS_POPUP_VAR: 1})
        self.assertEqual(403, response.status_code)

    def test_owner_changeform_save_created_by_last_modified_by_fields(self):
        url = reverse("admin:organization_owner_add")
        data = {
            "name": "A new Owner",
            "type": "Organization",
            "related_children-TOTAL_FORMS": 0,
            "related_children-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        self.client.login(username=self.user.username, password="t3st")
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        new_owner = Owner.objects.latest("id")
        self.assertEqual(self.user, new_owner.created_by)
        self.assertEqual(self.user, new_owner.last_modified_by)

        user2 = get_user_model().objects.create_superuser(
            "test2", "test@test.com", "t3st", self.dataspace1
        )
        self.client.login(username=user2.username, password="t3st")
        response = self.client.post(new_owner.get_admin_url(), data)
        self.assertEqual(302, response.status_code)
        new_owner = Owner.objects.latest("id")
        self.assertEqual(self.user, new_owner.created_by)
        self.assertEqual(user2, new_owner.last_modified_by)

    def test_owner_changeform_name_with_unicode(self):
        name = "Vázquez Araújo"
        url = reverse("admin:organization_owner_add")
        data = {
            "name": name,
            "type": "Organization",
            "related_children-TOTAL_FORMS": 0,
            "related_children-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        self.client.login(username=self.user.username, password="t3st")
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        new_owner = Owner.objects.latest("id")
        self.assertEqual(name, new_owner.name)

        changelist_url = reverse("admin:organization_owner_changelist")
        response = self.client.get(changelist_url + f"?q={name}")
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertEqual(new_owner, response.context_data["cl"].result_list[0])

        response = self.client.get(new_owner.get_admin_url())
        expected = (
            f'<input type="text" name="name" value="{name}" class="vTextField" '
            'maxlength="70" required aria-describedby="id_name_helptext" id="id_name">'
        )
        self.assertContains(response, expected, html=True)


class SubownerTestCase(TestCase):
    def setUp(self):
        self.dataspace1 = Dataspace.objects.create(name="nexB")
        self.user = get_user_model().objects.create_superuser(
            "test", "test@test.com", "t3st", self.dataspace1
        )

        self.dataspace2 = Dataspace.objects.create(name="TestOrg")
        self.owner = Owner.objects.create(name="Test Organization", dataspace=self.dataspace1)

        self.owner1 = Owner.objects.create(name="org1", dataspace=self.dataspace1)
        self.owner2 = Owner.objects.create(name="org2", dataspace=self.dataspace1)

        self.person1 = Owner.objects.create(
            name="person1", type="Person", dataspace=self.dataspace1
        )

        self.org_person1 = Subowner.objects.create(
            parent=self.owner1,
            child=self.person1,
            start_date="2011-12-06",
            end_date="2011-12-08",
            dataspace=self.owner1.dataspace,
        )
        self.org_person2 = Subowner.objects.create(
            parent=self.owner1,
            child=self.person1,
            start_date="2011-12-07",
            end_date="2011-12-08",
            dataspace=self.owner2.dataspace,
        )

        self.person2 = Owner.objects.create(
            name="person2", type="Person", dataspace=self.dataspace1
        )

        self.org_person1 = Subowner.objects.create(
            parent=self.owner1,
            child=self.person2,
            start_date="2011-12-06",
            end_date="2011-12-08",
            dataspace=self.owner1.dataspace,
        )
        self.org_person2 = Subowner.objects.create(
            parent=self.owner2,
            child=self.person2,
            start_date="2011-12-03",
            end_date="2011-12-08",
            dataspace=self.owner1.dataspace,
        )

        self.dataspace_target = Dataspace.objects.create(name="target_dataspace")

    def test_copy_owner_type_person_common(self):
        person = Owner.objects.create(
            name="person_common",
            dataspace=self.dataspace1,
            notes="notes",
            contact_info="li@nexb.com",
            type="Person",
        )

        copied_object = copy_object(person, self.dataspace_target, self.user)
        self.assertEqual(person.name, copied_object.name)

    def test_subowner_with_null_dates(self):
        subowner_count = Subowner.objects.count()
        self.client.login(username="test", password="t3st")
        url = reverse("admin:organization_owner_add")
        org_id = Owner.objects.get(name="org1").id  # this is because #6719
        # Addition of a new Owner including a child subowner
        params = {
            "name": "new_person1",
            "type": "Organization",
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 1,
            "related_children-0-child": org_id,
            "related_children-0-start_date": "",
            "related_children-0-end_date": "",
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        self.client.post(url, params)
        self.assertEqual(subowner_count + 1, Subowner.objects.count())

    def test_subowner_with_end_date_earlier_start_date(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:organization_owner_add")
        org_id = (Owner.objects.get(name="org1").id,)
        params = {
            "name": "new_person1",
            "type": "Organization",
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 1,
            "related_children-0-child": org_id,
            "related_children-0-start_date": "2011-12-10",
            "related_children-0-end_date": "2011-12-09",
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        response = self.client.post(url, params)
        self.assertContains(response, "The Start date must be older than the End date.")

    def test_owner_copy_with_subowner_m2m(self):
        # Note that the Owner copy is copying the children Subowner only.
        owner_count = Owner.objects.count()
        copied_object = copy_object(self.owner1, self.dataspace_target, self.user)

        self.assertEqual(owner_count + 3, Owner.objects.count())

        # Children m2m are not copied along the Owner.
        self.assertFalse(copied_object.get_parents().count())
        self.assertEqual(2, copied_object.get_children().count())

    def test_save_subowner_with_different_dataspace(self):
        # Save a Subowner object with a parent in dataspace1 and a child in
        # dataspace2, it should not be possible
        owner1 = self.owner1
        owner2 = Owner.objects.create(name="o2", dataspace=self.dataspace2)
        self.assertNotEqual(owner1.dataspace, owner2.dataspace)

        subowner = Subowner(parent=owner1, child=owner2, dataspace=owner1.dataspace)
        with self.assertRaises(ValueError):
            subowner.save()

    def test_owner_changeform_non_unicode_changelist_filters(self):
        self.client.login(username="test", password="t3st")
        url = self.owner1.get_admin_url()
        changelist_filters = "?_changelist_filters=q%3Dosi%25C5%2584s"
        response = self.client.get(url + changelist_filters)
        self.assertEqual(200, response.status_code)
