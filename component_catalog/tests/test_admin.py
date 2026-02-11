#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import datetime
import json
import urllib
import uuid
from unittest import mock

from django.contrib.admin.options import IS_POPUP_VAR
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import NON_FIELD_ERRORS
from django.test import TestCase
from django.test import TransactionTestCase
from django.test.utils import override_settings
from django.urls import NoReverseMatch
from django.urls import reverse

from guardian.shortcuts import assign_perm

from component_catalog.admin import ComponentAdmin
from component_catalog.models import AcceptableLinkage
from component_catalog.models import Component
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import ComponentKeyword
from component_catalog.models import ComponentStatus
from component_catalog.models import ComponentType
from component_catalog.models import Package
from component_catalog.models import PackageAssignedLicense
from component_catalog.models import Subcomponent
from component_catalog.tests import make_package
from dje.copier import copy_object
from dje.filters import DataspaceFilter
from dje.models import Dataspace
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.models import History
from dje.tests import add_perm
from dje.tests import create_admin
from dje.tests import create_superuser
from license_library.models import License
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseTag
from organization.models import Owner
from policy.models import AssociatedPolicy
from policy.models import UsagePolicy
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductPackage


class ComponentAdminViewsTestCase(TestCase):
    def setUp(self):
        self.dataspace1 = Dataspace.objects.create(name="Dataspace")
        self.alternate_dataspace = Dataspace.objects.create(name="Alternate")

        self.user = get_user_model().objects.create_superuser(
            "test", "test@test.com", "secret", self.dataspace1
        )
        self.admin_user = create_admin("admin_user", self.dataspace1)
        self.alternate_super_user = create_superuser("alternate_user", self.alternate_dataspace)

        self.type1 = ComponentType.objects.create(
            label="Type1", notes="notes", dataspace=self.dataspace1
        )
        self.status1 = ComponentStatus.objects.create(
            label="Status1", default_on_addition=False, dataspace=self.dataspace1
        )
        self.owner1 = Owner.objects.create(
            name="owner1",
            dataspace=self.dataspace1,
        )
        self.license1 = License.objects.create(
            key="license1",
            name="License1",
            short_name="License1",
            is_active=True,
            owner=self.owner1,
            dataspace=self.dataspace1,
        )
        self.license2 = License.objects.create(
            key="license2",
            name="License2",
            short_name="License2",
            is_active=True,
            owner=self.owner1,
            dataspace=self.dataspace1,
        )
        self.component1 = Component.objects.create(
            name="Component1",
            version="0.1",
            type=self.type1,
            owner=self.owner1,
            homepage_url="http://localhost.com",
            dataspace=self.dataspace1,
        )
        self.component2 = Component.objects.create(
            name="Component2",
            version="0.2",
            type=self.type1,
            owner=self.owner1,
            homepage_url="http://localhost.com",
            dataspace=self.dataspace1,
        )
        self.component3 = Component.objects.create(
            name="Component3",
            version="r1",
            type=self.type1,
            owner=self.owner1,
            dataspace=self.dataspace1,
        )
        self.component4 = Component.objects.create(
            name="Component4",
            version="r3",
            type=self.type1,
            owner=self.owner1,
            dataspace=self.dataspace1,
        )
        self.component5 = Component.objects.create(
            name="Component5",
            version="r4",
            type=self.type1,
            owner=self.owner1,
            dataspace=self.dataspace1,
        )
        self.component6 = Component.objects.create(
            name="Component6",
            version="r5",
            type=self.type1,
            owner=self.owner1,
            dataspace=self.dataspace1,
        )

        self.sub_component1 = Subcomponent.objects.create(
            parent=self.component6,
            child=self.component5,
            dataspace=self.component6.dataspace,
            notes="I have a parent 6, and child 5",
        )
        self.sub_component2 = Subcomponent.objects.create(
            parent=self.component5,
            child=self.component4,
            dataspace=self.component5.dataspace,
            notes="I have a parent 5, and child 4",
        )
        self.sub_component3 = Subcomponent.objects.create(
            parent=self.component4,
            child=self.component3,
            dataspace=self.component4.dataspace,
            notes="I have a parent 4, and child 3",
        )
        self.sub_component4 = Subcomponent.objects.create(
            parent=self.component3,
            child=self.component2,
            dataspace=self.component3.dataspace,
            notes="I have a parent 3, and child 2",
        )
        self.sub_component5 = Subcomponent.objects.create(
            parent=self.component2,
            child=self.component1,
            dataspace=self.component2.dataspace,
            notes="I have a parent 2, and child 1",
        )
        self.dataspace_target = Dataspace.objects.create(name="target_org")

        self.product1 = Product.objects.create(
            name="MyProduct", version="1.0", dataspace=self.dataspace1
        )

    def test_component_admin_views(self):
        self.client.login(username="test", password="secret")
        # List view
        url = reverse("admin:component_catalog_component_changelist")
        response = self.client.get(url)
        self.assertContains(response, "Component1</a>")
        # View on site link
        self.assertContains(response, '<div class="grp-text"><span>View</span></div>')
        self.assertContains(
            response,
            '<a href="{}" target="_blank">View</a>'.format(self.component1.get_absolute_url()),
        )
        # Details view
        url = self.component1.get_admin_url()
        response = self.client.get(url)
        # Check if the Inlines are present
        self.assertContains(response, '<h2 class="grp-collapse-handler">Child Components</h2>')
        self.assertContains(
            response,
            '<a href="{}" class="grp-state-focus" target="_blank">View</a>'.format(
                self.component1.get_absolute_url()
            ),
        )

    def test_component_admin_form_clean(self):
        self.client.login(username="test", password="secret")
        url = self.component1.get_admin_url()

        # Using the name, organization and version from component2, to make
        # sure POSTing this is raising the proper error and message.
        data = {
            "name": self.component2.name,
            "version": self.component2.version,
            "type": self.type1.id,
            "curation_level": 0,
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertContains(response, '<p class="errornote">Please correct the error below.</p>')
        self.assertContains(
            response, "Component with this Dataspace, Name and Version already exists."
        )
        expected = {
            NON_FIELD_ERRORS: ["Component with this Dataspace, Name and Version already exists."]
        }
        self.assertEqual(expected, response.context_data["adminform"].form.errors)

        # Removing one of the required field and POST again
        del data["name"]
        response = self.client.post(url, data)
        self.assertContains(response, '<p class="errornote">Please correct the error below.</p>')
        self.assertContains(
            response,
            '<ul class="errorlist" id="id_name_error"><li>This field is required.</li></ul>',
        )

    @override_settings(REFERENCE_DATASPACE="Dataspace")
    def test_component_admin_form_clean_validate_against_reference_data(self):
        self.client.login(username=self.alternate_super_user, password="secret")
        url = reverse("admin:component_catalog_component_add")

        data = {
            "name": self.component1.name,
            "version": self.component1.version,
            "curation_level": 0,
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)

        absolute_link = self.component1.get_absolute_link(target="_blank")
        copy_link = self.component1.get_html_link(
            self.component1.get_copy_url(), value="Copy to my Dataspace", target="_blank"
        )
        error = (
            f"The application object that you are creating already exists as "
            f"{absolute_link} in the reference dataspace. {copy_link}"
        )

        expected = {
            "version": [error],
            "name": [error],
        }
        self.assertEqual(expected, response.context_data["adminform"].form.errors)

    @override_settings(REFERENCE_DATASPACE="Dataspace")
    def test_component_admin_changelist_reference_data_link(self):
        url = reverse("admin:component_catalog_component_changelist")

        reference_params = "?{}={}".format(DataspaceFilter.parameter_name, self.dataspace1.id)
        reference_link = '<a href="{}" class="reference-data-link">View Reference Data</a>'.format(
            reference_params
        )
        my_dataspace_link = '<a href="?" class="reference-data-link">View My Data</a>'

        self.client.login(username=self.alternate_super_user, password="secret")
        response = self.client.get(url)
        self.assertContains(response, reference_link)
        self.assertNotContains(response, my_dataspace_link)
        self.assertFalse(getattr(response.context_data["cl"], "my_dataspace_link", None))
        self.assertEqual(
            reference_params, getattr(response.context_data["cl"], "reference_params", None)
        )

        # Not displayed in popup mode
        response = self.client.get("{}?{}=1".format(url, IS_POPUP_VAR))
        self.assertNotContains(response, reference_link)
        self.assertNotContains(response, my_dataspace_link)
        self.assertFalse(getattr(response.context_data["cl"], "my_dataspace_link", None))
        self.assertFalse(getattr(response.context_data["cl"], "reference_params", None))

        response = self.client.get("{}{}".format(url, reference_params))
        self.assertNotContains(response, reference_link)
        self.assertContains(response, my_dataspace_link)
        self.assertTrue(getattr(response.context_data["cl"], "my_dataspace_link", None))
        self.assertFalse(getattr(response.context_data["cl"], "reference_params", None))

        with override_settings(REFERENCE_DATASPACE=""):
            response = self.client.get(url)
            self.assertNotContains(response, reference_link)
            self.assertNotContains(response, my_dataspace_link)

        self.client.login(username=self.user.username, password="secret")
        response = self.client.get(url)
        self.assertNotContains(response, reference_link)
        self.assertNotContains(response, my_dataspace_link)

        url = reverse("admin:component_catalog_subcomponent_changelist")
        self.client.login(username=self.alternate_super_user, password="secret")
        response = self.client.get("{}{}".format(url, reference_params))
        self.assertNotContains(response, "copy_to")

    def test_subcomponent_inline_admin_form_edit_clean(self):
        # This is an EDITION case
        self.client.login(username="test", password="secret")
        url = self.component1.get_admin_url()

        dataspace = Dataspace.objects.create(name="Other")
        other_org = Owner.objects.create(name="Other Org", dataspace=dataspace)
        other_type = ComponentType.objects.create(
            label="Other Type", notes="notes", dataspace=dataspace
        )
        other_component = Component.objects.create(
            name="Component1", version="0.1", type=other_type, owner=other_org, dataspace=dataspace
        )

        data = {
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 1,
            "related_children-0-notes": "Notes",
            "related_children-0-parent": self.component1.id,
            "related_children-0-child": other_component.id,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        error = "Select a valid choice. That choice is not one of the available choices."
        self.assertContains(response, error)

        other_component.name = "New Component Name"
        other_component.dataspace = self.component1.dataspace
        other_component.owner = self.component1.owner
        other_component.type = self.component1.type
        other_component.save()

        response = self.client.post(url, data)
        self.assertNotContains(response, error)

    def test_component_available_actions(self):
        delete_input = '<option value="delete_selected">Delete selected components</option>'
        compare_input = '<option value="compare_with">Compare the selected object</option>'
        copy_input = '<option value="copy_to">Copy the selected objects</option>'
        add_to_product_input = (
            '<option value="add_to_product">Add the selected components to a product</option>'
        )
        set_policy = '<option value="set_policy">Set usage policy from licenses</option>'

        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_changelist")

        # Looking at my own Dataspace data (default)
        response = self.client.get(url)
        self.assertContains(response, delete_input)
        self.assertNotContains(response, compare_input)
        self.assertNotContains(response, copy_input)
        self.assertContains(response, add_to_product_input)
        self.assertContains(response, set_policy)

        # Looking at data from another Dataspace
        data = {DataspaceFilter.parameter_name: self.alternate_dataspace.id}
        response = self.client.get(url, data)
        self.assertNotContains(response, delete_input)
        self.assertContains(response, compare_input)
        self.assertContains(response, copy_input)
        self.assertNotContains(response, add_to_product_input)
        self.assertNotContains(response, set_policy)

    def test_edit_component_assigned_package_replacement(self):
        self.client.login(username="test", password="secret")
        url = self.component1.get_admin_url()

        # Making sure we have unicode char in the name
        package1 = Package.objects.create(
            filename="\u02a0package1.zip", dataspace=self.component1.dataspace
        )
        assigned_package1 = ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.component1.dataspace
        )

        params = {
            "name": self.component1.name,
            "curation_level": self.component1.curation_level,
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": "0",
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": "0",
            "componentassignedpackage_set-TOTAL_FORMS": 1,
            "componentassignedpackage_set-INITIAL_FORMS": 1,
            "componentassignedpackage_set-0-id": assigned_package1.id,
            "componentassignedpackage_set-0-component": self.component1.id,
            "componentassignedpackage_set-0-package": package1.id,
        }

        response = self.client.post(url, params, follow=True)
        self.assertRedirects(response, reverse("admin:component_catalog_component_changelist"))
        component = Component.objects.get(pk=self.component1.pk)
        # Save went through, nothing changed so far.
        self.assertEqual(package1, component.componentassignedpackage_set.get().package)

        # Replacing the existing file by a another one
        package2 = Package.objects.create(
            filename="\u02a0package2.zip", dataspace=self.component1.dataspace
        )
        params["componentassignedpackage_set-0-package"] = package2.id
        self.client.post(url, params)
        component.refresh_from_db()
        self.assertEqual(package2, component.componentassignedpackage_set.get().package)

    def test_component_admin_form_inline_formsets_data_tampered(self):
        self.client.login(username="test", password="secret")
        url = self.component1.get_admin_url()

        package1 = Package.objects.create(filename="p1.zip", dataspace=self.component1.dataspace)
        assigned_package1 = ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.component1.dataspace
        )

        response = self.client.get(url)
        self.assertContains(response, "componentassignedpackage_set-0")
        self.assertContains(
            response,
            '<input type="hidden" name="componentassignedpackage_set-TOTAL_FORMS" value="1"'
            ' id="id_componentassignedpackage_set-TOTAL_FORMS" />',
            html=True,
        )
        self.assertContains(
            response,
            '<input type="hidden" name="componentassignedpackage_set-INITIAL_FORMS" value="1"'
            ' id="id_componentassignedpackage_set-INITIAL_FORMS" />',
            html=True,
        )

        # Calling the changeform view, componentassignedpackage_set-0 are properly set
        data = {
            "name": self.component1.name,
            "curation_level": 0,
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": "0",
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": "0",
            "componentassignedpackage_set-TOTAL_FORMS": 1,
            "componentassignedpackage_set-INITIAL_FORMS": 1,
            "componentassignedpackage_set-0-id": assigned_package1.id,
            "componentassignedpackage_set-0-component": self.component1.id,
            "componentassignedpackage_set-0-package": package1.id,
        }

        # Deletes the assigned_package1 relation, so the componentassignedpackage_set-0 are
        # not valid anymore.
        assigned_package1.delete()

        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, url)
        self.assertNotContains(response, "componentassignedpackage_set-0")

        self.assertContains(
            response,
            '<input type="hidden" name="componentassignedpackage_set-TOTAL_FORMS" value="0"'
            ' id="id_componentassignedpackage_set-TOTAL_FORMS" />',
            html=True,
        )
        self.assertContains(
            response,
            '<input type="hidden" name="componentassignedpackage_set-INITIAL_FORMS" value="0"'
            ' id="id_componentassignedpackage_set-INITIAL_FORMS" />',
            html=True,
        )
        self.assertContains(response, "Form data outdated or inconsistent.")
        self.assertContains(response, "The form data has been refreshed.")

        messages = list(response.context["messages"])
        expected = "Form data outdated or inconsistent. The form data has been refreshed."
        self.assertEqual(expected, str(messages[0]))

    def test_activity_log_activated(self):
        self.client.login(username="test", password="secret")
        response = self.client.get(reverse("admin:component_catalog_component_changelist"))
        self.assertContains(response, "activity_log_link")

    def test_component_admin_changelist_list_display_as_popup(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_changelist")
        expect1 = '<input type="checkbox" id="action-toggle"'
        expect2 = "get_hierarchy_link"
        expect3 = "<span>View</span>"
        expect4 = '<td class="action-checkbox">'
        expect5 = 'title="Hierarchy"'
        expect6 = "view_on_site"

        response = self.client.get(url)
        self.assertContains(response, expect1)
        self.assertContains(response, expect2)
        self.assertContains(response, expect3)
        self.assertContains(response, expect4)
        self.assertContains(response, expect5)
        self.assertContains(response, expect6)

        response = self.client.get(url + "?{}=1".format(IS_POPUP_VAR))
        self.assertNotContains(response, expect1)
        self.assertNotContains(response, expect2)
        self.assertNotContains(response, expect3)
        self.assertNotContains(response, expect4)
        self.assertNotContains(response, expect5)
        self.assertNotContains(response, expect6)

    def test_component_unicity_in_form_validation_on_addition(self):
        # Let's take an existing Component an try to save a new one using the
        # unique_together value from the existing one.
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_add")
        data = {
            "name": self.component1.name,
            "owner": self.component1.owner.id,
            "version": self.component1.version,
            "curation_level": 0,
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        # Error a the Field level in the Form
        self.assertContains(response, "Please correct the error below.")
        # Global Formset error
        self.assertContains(
            response, "Component with this Dataspace, Name and Version already exists."
        )
        expected = {
            NON_FIELD_ERRORS: ["Component with this Dataspace, Name and Version already exists."]
        }
        self.assertEqual(expected, response.context_data["adminform"].form.errors)

    def test_component_admin_add_is_active_true_by_default(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_add")
        data = {
            "name": "new component",
            "curation_level": 0,
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        self.client.post(url, data)
        component = Component.objects.get(name=data["name"])
        self.assertTrue(component.is_active)

    def test_component_adminform_validate_case_insensitive_uniqueness(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_add")
        data = {
            "name": self.component1.name.upper(),
            "curation_level": 0,
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        expected = {
            "name": [
                "The application object that you are creating already exists as "
                '"Component1". Note that a different case in the object name is not '
                "sufficient to make it unique."
            ],
        }
        self.assertEqual(expected, response.context_data["adminform"].form.errors)

        url = self.component2.get_admin_url()
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

        data["name"] = self.component1.name
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

        url = self.component1.get_admin_url()
        data["version"] = self.component1.version
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_component_adminform_validate_version(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_add")
        data = {
            "name": "c:o:m:p",
            "version": "1:0",
            "curation_level": 0,
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        expected = {
            "version": [
                "Enter a valid value consisting of spaces, periods, letters, numbers, "
                "or !#\"',&()+_-."
            ]
        }
        self.assertEqual(expected, response.context_data["adminform"].form.errors)

    def test_component_curation_level_validation(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_add")
        data = {
            "name": "some name",
            "curation_level": 101,  # Using a value greater than the max
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertContains(response, "Ensure this value is less than or equal to 100.")

        data["curation_level"] = 99
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("admin:component_catalog_component_changelist"))

    def test_component_save_as_proper(self):
        # Setting some value for further validation
        self.component1.configuration_status = self.status1
        self.component1.save()

        self.client.login(username="test", password="secret")
        url = self.component1.get_admin_url()
        response = self.client.get(url)
        # Save as button is present on the Edit page
        save_as_input_html = (
            '<input type="submit" value="Save as new" class="grp-button" name="_saveasnew" />'
        )
        self.assertContains(response, save_as_input_html, html=True)

        # We need to set a different Component.name to avoid raising validation
        # errors
        new_name = "THIS IS A NEW NAME"
        data = {
            "name": new_name,
            "owner": self.component1.owner.id,
            "type": self.component1.type.id,
            "curation_level": 0,
            "configuration_status": self.component1.configuration_status.id,
            "_saveasnew": "Save as new",
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        response = self.client.post(url, data)
        # A new Component was created
        new_component = Component.objects.get(name=new_name)
        self.assertRedirects(response, new_component.get_admin_url())
        # Making sure the values of the Original Component were preserved
        self.assertEqual(self.component1.owner, new_component.owner)
        self.assertEqual(self.component1.type, new_component.type)
        self.assertEqual(self.component1.is_active, new_component.is_active)
        self.assertEqual(self.component1.configuration_status, new_component.configuration_status)

    def test_component_save_as_with_failing_validation(self):
        self.client.login(username="test", password="secret")
        url = self.component1.get_admin_url()
        response = self.client.get(url)
        self.assertContains(response, 'name="_saveasnew"')
        # Since request.GET is empty
        self.assertNotContains(response, 'value="Save and go to next"')

        response = self.client.get(url + "?_changelist_filters=o%3D3.4")
        self.assertContains(response, 'name="_saveasnew"')
        self.assertContains(response, 'value="Save and go to next"')

        data = {
            "name": self.component1.name,
            "owner": self.component1.owner.id,
            "version": self.component1.version,
            "type": self.component1.type.id,
            "curation_level": 0,
            "_saveasnew": "Save as new",
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        # Save as new with no data modification, raise a form validation error
        response = self.client.post(url, data)
        context_data = response.context_data
        self.assertContains(
            response, "Component with this Dataspace, Name and Version already exists."
        )
        expected = {
            NON_FIELD_ERRORS: ["Component with this Dataspace, Name and Version already exists."]
        }
        self.assertEqual(expected, context_data["adminform"].form.errors)
        # We are now on a form that works like an ADDITION form
        # Save as button is the only button present
        self.assertContains(response, 'name="_saveasnew"')
        self.assertNotContains(response, 'value="Save and go to next"')
        self.assertEqual(context_data["save_as"], True)
        self.assertEqual(context_data["add"], False)
        self.assertEqual(context_data["change"], True)

    def test_component_save_as_with_external_reference(self):
        self.client.login(username="test", password="secret")
        url = self.component1.get_admin_url()

        ext_source1 = ExternalSource.objects.create(
            label="GitHub",
            dataspace=self.dataspace1,
        )

        er = ExternalReference.objects.create_for_content_object(
            content_object=self.component1, external_source=ext_source1, external_id="external_id"
        )

        # We need to set a different Component.name to avoid raising validation errors
        new_name = "THIS IS A NEW NAME"
        data = {
            "name": new_name,
            "curation_level": 0,
            "_saveasnew": "Save as new",
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 1,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 1,
            "dje-externalreference-content_type-object_id-0-id": er.id,
            "dje-externalreference-content_type-object_id-0-external_source": er.external_source.id,
            "dje-externalreference-content_type-object_id-0-external_id": er.external_id,
        }

        response = self.client.post(url, data)
        # A new Component was created
        new_component = Component.objects.get(name=new_name)
        self.assertRedirects(response, new_component.get_admin_url())
        # Making sure the values of the Original Component were preserved
        self.assertEqual(self.component1.owner, self.owner1)

        er1 = ExternalReference.objects.get_for_content_object(self.component1).get()
        er2 = ExternalReference.objects.get_for_content_object(new_component).get()
        # Making sure a new ExternalReference was created
        self.assertNotEqual(er1.id, er2.id)

    def test_component_edit_save_as_delete_inline(self):
        self.client.login(username="test", password="secret")
        url = self.component6.get_admin_url()

        extra_subcomponent = Subcomponent.objects.create(
            parent=self.component6, child=self.component1, dataspace=self.component6.dataspace
        )

        self.assertEqual(2, self.component6.related_children.count())

        new_name = "THIS IS A NEW NAME"
        data = {
            "name": new_name,
            "curation_level": 0,
            "_saveasnew": "Save+as+new",
            "related_children-0-id": self.sub_component1.pk,
            "related_children-0-DELETE": "1",
            "related_children-1-id": extra_subcomponent.pk,
            "related_children-1-child": extra_subcomponent.child.pk,
            "related_children-1-parent": extra_subcomponent.parent.pk,
            "related_children-INITIAL_FORMS": "2",
            "related_children-TOTAL_FORMS": "2",
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        # Started with 2 children, one was deleted.
        self.assertEqual(Component.objects.latest("id").related_children.count(), 1)

    @override_settings(REFERENCE_DATASPACE="Dataspace")
    def test_component_save_as_deactivated_for_dataspace(self):
        # The 'Save as' button is not available when editing an object from
        # another Dataspace
        dataspace = Dataspace.objects.create(name="Other")
        other_org = Owner.objects.create(name="Other Org", dataspace=dataspace)
        other_type = ComponentType.objects.create(
            label="Other Type", notes="notes", dataspace=dataspace
        )
        other_component = Component.objects.create(
            name="Component1", version="0.1", type=other_type, owner=other_org, dataspace=dataspace
        )

        self.client.login(username="test", password="secret")
        url = other_component.get_admin_url()
        response = self.client.get(url)
        # 'Save as' is not exposed in this case.
        self.assertNotContains(response, 'name="_saveasnew"')
        self.assertContains(response, "_addanother")

    def test_component_save_as_with_inlines(self):
        self.client.login(username="test", password="secret")

        package1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace1)
        assigned_package = ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.dataspace1
        )

        package_count = Package.objects.count()
        assigned_package_count = ComponentAssignedPackage.objects.count()

        self.component1.license_expression = self.license1.key
        self.component1.save()

        url = self.component1.get_admin_url()
        response = self.client.get(url)  # Make a GET request to get the csrf token

        # We need to set a different Component.name to avoid raising validation errors
        new_name = "THIS IS A NEW NAME"
        data = {
            "csrfmiddlewaretoken": str(response.context["csrf_token"]),
            "name": new_name,
            "version": self.component1.version,
            "curation_level": 0,
            "license_expression": self.component1.license_expression,
            "_saveasnew": "Save as new",
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 1,
            "componentassignedpackage_set-INITIAL_FORMS": 1,
            "componentassignedpackage_set-0-package": assigned_package.package.id,
            "componentassignedpackage_set-0-component": assigned_package.component.id,
            "componentassignedpackage_set-0-id": assigned_package.id,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

        new_component = Component.objects.get(name=new_name, dataspace=self.dataspace1)
        self.assertRedirects(response, new_component.get_admin_url())
        self.assertEqual(1, new_component.packages.count())
        self.assertEqual(package_count, Package.objects.count())
        self.assertEqual(assigned_package_count + 1, ComponentAssignedPackage.objects.count())
        # The assigned license was copied too
        self.assertEqual(1, new_component.licenses.count())
        self.assertEqual(self.component1.license_expression, new_component.license_expression)

    def test_add_to_product_action_proper_component(self):
        self.client.login(username=self.user.username, password="secret")

        self.component1.license_expression = self.license1.key
        self.component1.save()

        ids = ",".join([str(self.component1.pk), str(self.component2.pk), str(self.component3.pk)])
        add_to_product_url = reverse("admin:component_catalog_component_add_to_product")

        # Simulate displaying the page
        response = self.client.get("{}?ids={}".format(add_to_product_url, ids))
        self.assertEqual(200, response.status_code)
        self.assertTrue("form" in response.context)

        response = self.client.post(
            add_to_product_url, {"product": self.product1.pk, "ids": ids}, follow=True
        )
        self.assertRedirects(response, reverse("admin:component_catalog_component_changelist"))
        self.assertEqual(3, self.product1.productcomponents.count())

        # pc.license_expression is taken from the Component
        pc = ProductComponent.objects.get(product=self.product1, component=self.component1)
        self.assertEqual(self.license1.key, pc.license_expression)
        self.assertEqual(self.user, pc.created_by)
        self.assertEqual(self.user, pc.last_modified_by)
        self.assertEqual(32, len(str(pc.created_date)))
        self.assertEqual(32, len(str(pc.last_modified_date)))

        self.assertFalse(History.objects.get_for_object(pc).exists())
        self.assertEqual(self.user, pc.created_by)
        self.assertTrue(pc.created_date)

        expected = "3 component(s) added to MyProduct."
        self.assertEqual(expected, list(response.context["messages"])[0].message)

        response = self.client.post(
            add_to_product_url, {"product": self.product1.pk, "ids": ids}, follow=True
        )
        expected = "0 component(s) added to MyProduct. 3 component(s) were already assigned."
        self.assertEqual(expected, list(response.context["messages"])[0].message)

        self.product1.refresh_from_db()
        history_entries = History.objects.get_for_object(self.product1)
        expected_messages = sorted(
            [
                'Added component "Component3 r1"',
                'Added component "Component2 0.2"',
                'Added component "Component1 0.1"',
            ]
        )
        self.assertEqual(
            expected_messages, sorted([entry.change_message for entry in history_entries])
        )
        self.assertEqual(self.user, self.product1.last_modified_by)

    def test_add_to_product_action_proper_package(self):
        self.client.login(username=self.user.username, password="secret")
        package1 = Package.objects.create(
            filename="p1.zip", dataspace=self.dataspace1, license_expression=self.license1.key
        )

        ids = str(package1.pk)
        add_to_product_url = reverse("admin:component_catalog_package_add_to_product")

        # Simulate displaying the page
        response = self.client.get("{}?ids={}".format(add_to_product_url, ids))
        self.assertEqual(200, response.status_code)
        self.assertTrue("form" in response.context)

        response = self.client.post(
            add_to_product_url, {"product": self.product1.pk, "ids": ids}, follow=True
        )
        self.assertRedirects(response, reverse("admin:component_catalog_package_changelist"))
        self.assertEqual(1, self.product1.productpackages.count())

        # pc.license_expression is taken from the Package
        pp = ProductPackage.objects.get(product=self.product1, package=package1)
        self.assertEqual(self.license1.key, pp.license_expression)
        self.assertEqual(self.user, pp.created_by)
        self.assertEqual(self.user, pp.last_modified_by)
        self.assertEqual(32, len(str(pp.created_date)))
        self.assertEqual(32, len(str(pp.last_modified_date)))

        self.assertFalse(History.objects.get_for_object(pp).exists())
        self.assertEqual(self.user, pp.created_by)
        self.assertTrue(pp.created_date)

        expected = "1 package(s) added to MyProduct."
        self.assertEqual(expected, list(response.context["messages"])[0].message)

        response = self.client.post(
            add_to_product_url, {"product": self.product1.pk, "ids": ids}, follow=True
        )
        expected = "0 package(s) added to MyProduct. 1 package(s) were already assigned."
        self.assertEqual(expected, list(response.context["messages"])[0].message)

        self.product1.refresh_from_db()
        history_entries = History.objects.get_for_object(self.product1)
        expected_messages = ['Added package "p1.zip"']
        self.assertEqual(expected_messages, [entry.change_message for entry in history_entries])
        self.assertEqual(self.user, self.product1.last_modified_by)

    def test_add_to_product_action_permission(self):
        self.client.login(username=self.user.username, password="secret")

        ids = ",".join([str(self.component1.pk), str(self.component2.pk), str(self.component3.pk)])
        add_to_product_url = reverse("admin:component_catalog_component_add_to_product")
        component_changelist_url = reverse("admin:component_catalog_component_changelist")

        self.user.is_superuser = False
        self.user.save()

        self.assertFalse(self.user.has_perm("product_portfolio.add_productcomponent"))
        response = self.client.get("{}?ids={}".format(add_to_product_url, ids))
        self.assertEqual(404, response.status_code)
        self.user = add_perm(self.user, "change_component")
        self.assertNotContains(self.client.get(component_changelist_url), "add_to_product")

        self.user = add_perm(self.user, "add_productcomponent")
        self.assertTrue(self.user.has_perm("product_portfolio.add_productcomponent"))
        response = self.client.get("{}?ids={}".format(add_to_product_url, ids))
        self.assertEqual(200, response.status_code)
        self.assertContains(self.client.get(component_changelist_url), "add_to_product")

    def test_add_to_product_action_omitting_ids_returns_404(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_add_to_product")
        response = self.client.post(url, {"product": self.product1.pk})
        self.assertEqual(404, response.status_code)

    def test_add_to_product_action_submitting_no_product_shows_error(self):
        self.client.login(username="test", password="secret")
        ids = ",".join([str(self.component1.pk), str(self.component2.pk), str(self.component3.pk)])
        url = reverse("admin:component_catalog_component_add_to_product")
        response = self.client.post(url, {"ids": ids})
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "This field is required.")

    def test_add_to_product_action_when_product_already_contains_component_has_no_effect(self):
        self.client.login(username="test", password="secret")
        ProductComponent.objects.create(
            product=self.product1, component=self.component1, dataspace=self.component1.dataspace
        )

        ids = ",".join([str(self.component1.pk), str(self.component2.pk), str(self.component3.pk)])
        url = reverse("admin:component_catalog_component_add_to_product")
        response = self.client.post(url, {"product": self.product1.pk, "ids": ids})
        self.assertRedirects(response, reverse("admin:component_catalog_component_changelist"))
        self.assertTrue(
            ProductComponent.objects.get(product=self.product1, component=self.component1)
        )

    def test_add_to_product_action_checks_dataspace(self):
        component = Component.objects.create(
            name="A Component", version="1.0", dataspace=self.alternate_dataspace
        )

        self.client.login(username="test", password="secret")
        ids = ",".join([str(component.pk)])
        url = reverse("admin:component_catalog_component_add_to_product")
        response = self.client.post(url, {"product": self.product1.pk, "ids": ids}, follow=True)
        self.assertRedirects(response, reverse("admin:component_catalog_component_changelist"))
        self.assertEqual(
            "The dataspace of the selected objects did not match your dataspace.",
            list(response.context["messages"])[0].message,
        )

    def test_add_to_product_action_product_secured_qs(self):
        component = Component.objects.create(name="c", version="1.0", dataspace=self.dataspace1)
        ids = ",".join([str(component.pk)])
        add_to_product_url = reverse("admin:component_catalog_component_add_to_product")

        self.admin_user = add_perm(self.admin_user, "change_component")
        self.admin_user = add_perm(self.admin_user, "add_productcomponent")

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.get("{}?ids={}".format(add_to_product_url, ids))
        self.assertEqual(200, response.status_code)
        self.assertEqual(0, response.context_data["form"].fields["product"]._queryset.count())

        assign_perm("view_product", self.admin_user, self.product1)
        assign_perm("change_product", self.admin_user, self.product1)
        response = self.client.get("{}?ids={}".format(add_to_product_url, ids))
        self.assertEqual(1, response.context_data["form"].fields["product"]._queryset.count())
        self.assertIn(self.product1, response.context_data["form"].fields["product"]._queryset)

    def test_add_package_page_has_no_inlines_when_it_is_a_popup(self):
        self.client.login(username="test", password="secret")

        url = reverse("admin:component_catalog_package_add")
        response = self.client.get(url)
        self.assertContains(response, "Associated Components")

        params = "?" + urllib.parse.urlencode({IS_POPUP_VAR: "1"})
        response = self.client.get(url + params)
        self.assertNotContains(response, "Associated Components")
        response = self.client.post(url + params, data={"filename": "AAA"})
        self.assertEqual(response.status_code, 302)

        params = "?" + urllib.parse.urlencode({"_changelist_filters": "_to_field=id&_popup=1"})
        response = self.client.get(url + params)
        self.assertNotContains(response, "Associated Components")
        response = self.client.post(url + params, data={"filename": "BBB"})
        self.assertEqual(response.status_code, 302)

    def test_component_changelist_set_policy_action_proper(self):
        self.client.login(username=self.user.username, password="secret")

        license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            dataspace=self.dataspace1,
        )
        component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.dataspace1,
        )
        AssociatedPolicy.objects.create(
            from_policy=license_policy,
            to_policy=component_policy,
            dataspace=self.dataspace1,
        )

        self.license1.usage_policy = license_policy
        self.license1.save()

        self.component1.license_expression = "{} AND {}".format(
            self.license1.key, self.license2.key
        )
        self.component1.save()
        self.assertEqual(component_policy, self.component1.get_policy_from_primary_license())

        ids = str(self.component1.pk)
        set_policy_url = reverse("admin:component_catalog_component_set_policy")

        response = self.client.get("{}?ids={}".format(set_policy_url, ids))
        self.assertEqual(200, response.status_code)
        self.assertTrue("form" in response.context)
        expected = """
        <tr class="grp-row-even">
            <td><a href="{}" target="_blank">Component1 0.1</a></td>
            <td></td>
            <td>ComponentPolicy</td>
            <td>license1</td>
            <td>license1 AND license2</td>
            <td><input type="checkbox" name="checked_id_{}" class="enabler"></td>
        </tr>""".format(self.component1.get_admin_url(), self.component1.id)
        self.assertContains(response, expected, html=True)

        self.assertIsNone(self.component1.usage_policy)
        data = {
            "checked_id_{}".format(self.component1.id): "on",
            "ids": ids,
        }
        response = self.client.post(set_policy_url, data)
        self.assertRedirects(response, reverse("admin:component_catalog_component_changelist"))
        self.component1 = Component.objects.get(id=self.component1.id)
        self.assertEqual(component_policy, self.component1.usage_policy)

    def test_component_name_cannot_contain_slash(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_add")
        data = {
            "name": "Name with /",
            "owner": self.owner1.id,
            "type": self.type1.id,
            "curation_level": 0,
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        expected = (
            "Enter a valid value consisting of spaces, periods, letters, numbers,"
            " or !#&quot;&#x27;:,&amp;()+_-."
        )
        self.assertContains(response, expected)

    def test_component_external_reference_inline_in_changeform(self):
        self.client.login(username="test", password="secret")
        ext_source1 = ExternalSource.objects.create(label="GitHub", dataspace=self.dataspace1)
        url = self.component1.get_admin_url()
        data = {
            "name": self.component1.name,
            "curation_level": 0,
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 1,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-0-external_source": ext_source1.id,
            "dje-externalreference-content_type-object_id-0-external_id": "external_id",
            "dje-externalreference-content_type-object_id-0-external_url": "",
            "dje-externalreference-content_type-object_id-0-id": "",
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        self.assertTrue(ExternalReference.objects.get_for_content_object(self.component1).exists())

    def test_component_external_reference_inline_dataspace_scope(self):
        self.client.login(username="test", password="secret")

        ext_source1 = ExternalSource.objects.create(
            label="GitHub",
            dataspace=self.dataspace1,
        )
        ext_source2 = ExternalSource.objects.create(
            label="GitHubCopy",
            dataspace=self.alternate_dataspace,
        )

        url = self.component1.get_admin_url()
        response = self.client.get(url)
        self.assertContains(response, ext_source1.label)
        self.assertNotContains(response, ext_source2.label)

    def test_error_when_duplicate_component_assigned_package(self):
        self.client.login(username="test", password="secret")
        package1 = Package.objects.create(filename="file.zip", dataspace=self.dataspace1)
        url = reverse("admin:component_catalog_component_add")
        params = {
            "name": "My Component",
            "owner": self.owner1.id,
            "is_active": 1,
            "curation_level": 0,
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 2,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "componentassignedpackage_set-0-package": package1.id,
            "componentassignedpackage_set-1-package": package1.id,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": "0",
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": "0",
        }

        response = self.client.post(url, params)
        error_msg = "Please correct the duplicate data for package."
        self.assertContains(response, error_msg)

        # Same from the Package addition form.
        url = reverse("admin:component_catalog_package_add")
        params = {
            "name": "some-file.zip",
            "componentassignedpackage_set-TOTAL_FORMS": 2,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "componentassignedpackage_set-0-component": self.component1.id,
            "componentassignedpackage_set-1-component": self.component1.id,
        }

        response = self.client.post(url, params)
        error_msg = "Please correct the duplicate data for component."
        self.assertContains(response, error_msg)

    def test_component_admin_form_clean_license_expression_add(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_add")
        data = {
            "name": "ComponentName",
            "owner": self.owner1.id,
            "type": self.type1.id,
            "curation_level": 0,
            "license_expression": "invalid",
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        expected_errors = [["Unknown license key(s): invalid"]]
        self.assertEqual(expected_errors, response.context_data["errors"])

        data["license_expression"] = "{} AND {}".format(self.license1.key, self.license2.key)
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

        # Lower-case operators are normalized
        data["license_expression"] = "{} and {}".format(self.license1.key, self.license2.key)
        data["name"] = "SomethingElse"
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        component = Component.objects.latest("id")
        self.assertEqual("license1 AND license2", component.license_expression)
        self.assertEqual(2, component.licenses.count())
        self.assertIn(self.license1, component.licenses.all())
        self.assertIn(self.license2, component.licenses.all())

    def test_component_admin_form_clean_license_expression_change(self):
        self.client.login(username="test", password="secret")
        url = self.component1.get_admin_url()

        data = {
            "name": self.component1.name,
            "owner": self.component1.owner.id,
            "curation_level": "0",
            "license_expression": "invalid",
            "related_children-INITIAL_FORMS": "0",
            "related_children-TOTAL_FORMS": "0",
            "componentassignedpackage_set-TOTAL_FORMS": "0",
            "componentassignedpackage_set-INITIAL_FORMS": "0",
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        expected_errors = [["Unknown license key(s): invalid"]]
        self.assertEqual(expected_errors, response.context_data["errors"])

        data["license_expression"] = self.license1.key
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        self.assertEqual(1, self.component1.licenses.count())
        self.assertEqual(self.license1, self.component1.licenses.get())

    def test_component_admin_form_license_expression_change_impact_on_relation(self):
        self.client.login(username="test", password="secret")
        url = self.component1.get_admin_url()

        self.assertTrue(self.component1.related_parents.exists())
        subcomponent_relation = self.component1.related_parents.all()[0]
        subcomponent_relation.license_expression = self.license1.key
        subcomponent_relation.save()

        data = {
            "name": self.component1.name,
            "curation_level": "0",
            "license_expression": "",
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data, follow=True)
        expected = """
        <li class="grp-warning">
            This license change impacts component usage in a Product or in another Component.<br>
            <strong>
                See the <a href="/admin/component_catalog/subcomponent/?id__in={}" target="_blank">
                    1 subcomponent relationships
                </a> in changelist
            </strong>
        </li>
        """.format(subcomponent_relation.id)
        self.assertContains(response, expected, html=True)

    def test_component_admin_form_subcomponent_inline_clean_license_expression(self):
        self.client.login(username="test", password="secret")
        url = self.component6.get_admin_url()
        self.component6.related_children.all().delete()

        data = {
            "name": self.component6.name,
            "curation_level": "0",
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 1,
            "related_children-0-child": self.component1.id,
            "related_children-0-license_expression": "invalid",
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        expected_errors = [["Unknown license key(s): invalid"]]
        self.assertEqual(expected_errors, response.context_data["errors"])

        self.assertFalse(self.component1.licenses.exists())
        data["related_children-0-license_expression"] = self.license1.key
        self.client.post(url, data)
        subcomponent = Subcomponent.objects.latest("id")
        self.assertEqual(1, subcomponent.licenses.count())
        self.assertEqual(self.license1, subcomponent.licenses.get())

        self.component6.related_children.all().delete()
        self.component1.license_expression = self.license1.key
        self.component1.save()
        data["related_children-0-license_expression"] = self.license2.key
        response = self.client.post(url, data)
        expected_errors = [["Unknown license key(s): license2<br>Available licenses: license1"]]
        self.assertEqual(expected_errors, response.context_data["errors"])

    @override_settings(REFERENCE_DATASPACE="Dataspace")
    def test_component_admin_form_license_expression_builder_data_scoping(self):
        self.client.login(username="test", password="secret")

        License.objects.create(
            key="l3", name="l3", short_name="l3", dataspace=self.dataspace1, owner=self.owner1
        )

        response = self.client.get(self.component1.get_admin_url())
        self.assertContains(response, "awesomplete-1.1.5.css")
        self.assertContains(response, "awesomplete-1.1.5.min.js")
        self.assertContains(response, "license_expression_builder.js")
        expected = [("License1 (license1)", "license1"), ("License2 (license2)", "license2")]
        self.assertEqual(expected, response.context["client_data"]["license_data"])

        copied_component = copy_object(self.component1, self.dataspace_target, self.user)
        response = self.client.get(copied_component.get_admin_url())
        self.assertEqual([], response.context["client_data"]["license_data"])
        copied_license = copy_object(self.license1, self.dataspace_target, self.user)
        copied_license.short_name = "Copied"
        copied_license.save()
        response = self.client.get(copied_component.get_admin_url())
        expected = [("Copied (license1)", "license1")]
        self.assertEqual(expected, response.context["client_data"]["license_data"])

        self.assertContains(response, 'related_model_name="Component" ')
        self.assertContains(response, 'related_api_url="/api/v2/components/"')

    def test_subcomponent_admin_license_expression_and_reference_notes_from_child_component(self):
        self.client.login(username="test", password="secret")

        url = reverse("admin:component_catalog_subcomponent_add")
        data = {
            "parent": self.component6.id,
            "child": self.component1.id,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        sub = Subcomponent.objects.latest("id")
        self.assertEqual("", self.component1.license_expression)
        self.assertEqual("", sub.license_expression)
        self.assertFalse(self.component1.licenses.exists())
        self.assertFalse(sub.licenses.exists())
        sub.delete()

        self.component1.license_expression = self.license1.key
        self.component1.reference_notes = "Reference notes"
        self.component1.save()

        # license_expression empty, value taken from Component
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.license1.key, self.component1.license_expression)
        sub = Subcomponent.objects.latest("id")
        self.assertEqual(self.license1.key, self.component1.license_expression)
        self.assertEqual(self.license1.key, sub.license_expression)
        self.assertTrue(self.component1.licenses.exists())
        self.assertTrue(sub.licenses.exists())
        self.assertEqual(self.component1.license_expression, sub.license_expression)
        self.assertEqual(self.component1.reference_notes, sub.reference_notes)
        sub.delete()

    def test_subcomponent_admin_license_expression_validation(self):
        self.client.login(username="test", password="secret")

        url = reverse("admin:component_catalog_subcomponent_add")
        data = {
            "parent": self.component6.id,
            "child": self.component1.id,
            "license_expression": "invalid",
        }

        response = self.client.post(url, data)
        expected = {"license_expression": ["Unknown license key(s): invalid"]}
        self.assertEqual(expected, response.context_data["adminform"].form.errors)

        data["license_expression"] = self.license1.key
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        sub = Subcomponent.objects.latest("id")
        self.assertEqual(self.license1.key, sub.license_expression)
        self.assertFalse(self.component1.licenses.exists())
        self.assertTrue(sub.licenses.exists())

        sub.delete()
        self.component1.license_expression = self.license1.key
        self.component1.save()
        self.client.post(url, data)
        sub = Subcomponent.objects.latest("id")
        self.assertEqual(self.license1.key, self.component1.license_expression)
        self.assertEqual(self.license1.key, sub.license_expression)
        self.assertTrue(self.component1.licenses.exists())
        self.assertTrue(sub.licenses.exists())
        self.assertEqual(self.component1.license_expression, sub.license_expression)

        sub.delete()
        data["license_expression"] = self.license2.key
        response = self.client.post(url, data)
        expected = {
            "license_expression": [
                "Unknown license key(s): license2<br>Available licenses: license1"
            ]
        }
        self.assertEqual(expected, response.context_data["adminform"].form.errors)

    def test_subcomponent_mass_update_action(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_subcomponent_changelist")
        data = {
            "_selected_action": self.sub_component1.id,
            "action": "mass_update",
            "select_across": 0,
        }
        response = self.client.post(url, data)
        self.assertContains(response, "<h1>Mass update Subcomponent relationships</h1>")
        self.assertContains(response, '<label for="id_purpose">Purpose:</label>')
        self.assertContains(response, '<label for="id_usage_policy">Usage policy:</label>')

    def test_subcomponent_changelist_parent_related_lookup_list_filter(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_subcomponent_changelist")

        response = self.client.get(url)
        expected1 = (
            '<input id="id_parent-autocomplete" type="text" class="ui-autocomplete-input"'
            ' value="" autocomplete="off" readonly="readonly">'
        )
        expected2 = (
            '<input class="grp-autocomplete-hidden-field" id="id_parent" type="text" '
            'value="None" '
            'data-lookup-kwarg="parent__id__exact" tabindex="-1" readonly="readonly">'
        )
        expected3 = (
            '<a href="/admin/component_catalog/component/?_to_field=id&amp;'
            'children__isnull=False&amp;_filter_lookup=1" class="related-lookup" '
            'id="lookup_id_parent" title="Lookup"></a>'
        )
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertEqual(5, response.context_data["cl"].result_count)

        data = {"parent__id__exact": self.sub_component1.parent.id}
        response = self.client.get(url, data)
        expected1 = (
            f'<input id="id_parent-autocomplete" type="text" class="ui-autocomplete-input"'
            f' value="{self.sub_component1.parent}" autocomplete="off" readonly="readonly">'
        )
        expected2 = (
            '<input class="grp-autocomplete-hidden-field" id="id_parent" type="text" '
            'value="{}" data-lookup-kwarg="parent__id__exact" tabindex="-1" '
            'readonly="readonly">'.format(self.sub_component1.parent.id)
        )
        expected3 = (
            '<a href="/admin/component_catalog/component/?_to_field=id&amp;'
            'children__isnull=False&amp;_filter_lookup=1" class="related-lookup" '
            'id="lookup_id_parent" title="Lookup"></a>'
        )
        expected4 = '<a class="grp-related-remove" href="?"></a>'
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertContains(response, expected4)
        self.assertEqual(1, response.context_data["cl"].result_count)

        data = {DataspaceFilter.parameter_name: self.alternate_dataspace.id}
        response = self.client.get(url, data)
        expected1 = '<input type="hidden" name="{}" value="{}"/>'.format(
            DataspaceFilter.parameter_name, self.alternate_dataspace.id
        )
        expected2 = (
            '<a href="/admin/component_catalog/component/?_to_field=id&amp;'
            'children__isnull=False&amp;_filter_lookup=1&amp;{}={}" class="related-lookup" '
            'id="lookup_id_parent" title="Lookup"></a>'.format(
                DataspaceFilter.parameter_name, self.alternate_dataspace.id
            )
        )
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

        url = reverse("admin:component_catalog_component_changelist")
        response = self.client.get(url + "?_filter_lookup=1")
        self.assertNotContains(response, reverse("admin:component_catalog_component_add"))

    def test_package_changelist_component_hierarchy_related_lookup_list_filter(self):
        self.client.login(username="test", password="secret")
        package1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace1)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.dataspace1
        )
        package2 = Package.objects.create(filename="p2.zip", dataspace=self.dataspace1)
        ComponentAssignedPackage.objects.create(
            component=self.component2, package=package2, dataspace=self.dataspace1
        )
        package3 = Package.objects.create(filename="p3.zip", dataspace=self.dataspace1)
        ComponentAssignedPackage.objects.create(
            component=self.component3, package=package3, dataspace=self.dataspace1
        )

        self.assertEqual(1, self.component2.children.count())
        self.assertIn(self.component1, self.component2.children.all())

        url = reverse("admin:component_catalog_package_changelist")
        response = self.client.get(url)
        self.assertEqual(3, response.context_data["cl"].result_count)

        response = self.client.get(url, {"component__id__exact": self.component1.id})
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(package1, response.context_data["cl"].queryset)
        self.assertNotIn(package2, response.context_data["cl"].queryset)
        self.assertNotIn(package3, response.context_data["cl"].queryset)

        response = self.client.get(url, {"component__id__exact": self.component2.id})
        self.assertEqual(2, response.context_data["cl"].result_count)
        self.assertIn(package1, response.context_data["cl"].queryset)
        self.assertIn(package2, response.context_data["cl"].queryset)
        self.assertNotIn(package3, response.context_data["cl"].queryset)

        response = self.client.get(url, {"component__id__exact": self.component3.id})
        self.assertEqual(2, response.context_data["cl"].result_count)
        self.assertNotIn(package1, response.context_data["cl"].queryset)
        self.assertIn(package2, response.context_data["cl"].queryset)
        self.assertIn(package3, response.context_data["cl"].queryset)

        # A proper related_lookup was set then the dataspace filter changed
        data = {
            "component__id__exact": self.component1.id,
            DataspaceFilter.parameter_name: self.alternate_dataspace.id,
        }
        response = self.client.get(url, data, follow=True)
        expected = [("/admin/component_catalog/package/?e=1", 302)]
        self.assertEqual(expected, response.redirect_chain)
        expected = (
            '<li class="grp-warning">Set the Dataspace filter before using the'
            " Component lookup filter</li>"
        )
        self.assertContains(response, expected)

    def test_package_changelist_has_component_list_filter(self):
        self.client.login(username="test", password="secret")

        package1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace1)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.dataspace1
        )

        package2 = Package.objects.create(filename="p2.zip", dataspace=self.dataspace1)

        url = reverse("admin:component_catalog_package_changelist")
        response = self.client.get(url)
        self.assertEqual(2, response.context_data["cl"].result_count)

        expected = """
        <div class="grp-row">
            <label>Has component</label>
            <select class="grp-filter-choice" data-field-name="component">
                <option value="?" selected='selected'>All</option>
                <option value="?component__isnull=0">Yes</option>
                <option value="?component__isnull=1">No</option>
            </select>
        </div>
        """
        self.assertContains(response, expected, html=True)

        response = self.client.get(url, {"component__isnull": 0})
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(package1, response.context_data["cl"].queryset)
        self.assertNotIn(package2, response.context_data["cl"].queryset)

        response = self.client.get(url, {"component__isnull": 1})
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertNotIn(package1, response.context_data["cl"].queryset)
        self.assertIn(package2, response.context_data["cl"].queryset)

    def test_package_changelist_advanced_search_on_protocol(self):
        Package.objects.create(filename="p1.zip", dataspace=self.dataspace1)
        p2 = Package.objects.create(
            filename="p2", download_url="https://url.com/p2.zip", dataspace=self.dataspace1
        )
        package_url = "pkg:pypi/django@5.0"
        package3 = make_package(self.dataspace1, package_url)

        self.client.login(username="test", password="secret")
        changelist_url = reverse("admin:component_catalog_package_changelist")
        response = self.client.get(changelist_url + "?q=https://url.com/")
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(p2, response.context_data["cl"].result_list)

        response = self.client.get(changelist_url + "?q=download_url=https://url.com/p2.zip")
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(p2, response.context_data["cl"].result_list)

        response = self.client.get(changelist_url + f"?q={package_url}")
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(package3, response.context_data["cl"].result_list)

        response = self.client.get(changelist_url + "?q=pypi/django")
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(package3, response.context_data["cl"].result_list)

    def test_package_changelist_set_policy_action_proper(self):
        self.client.login(username=self.user.username, password="secret")
        p1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace1)

        license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            dataspace=self.dataspace1,
        )
        package_policy = UsagePolicy.objects.create(
            label="PackagePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Package),
            dataspace=self.dataspace1,
        )
        AssociatedPolicy.objects.create(
            from_policy=license_policy,
            to_policy=package_policy,
            dataspace=self.dataspace1,
        )

        self.license1.usage_policy = license_policy
        self.license1.save()

        p1.license_expression = "{} AND {}".format(self.license1.key, self.license2.key)
        p1.save()
        self.assertEqual(package_policy, p1.get_policy_from_primary_license())

        ids = str(p1.pk)
        set_policy_url = reverse("admin:component_catalog_package_set_policy")

        response = self.client.get("{}?ids={}".format(set_policy_url, ids))
        self.assertEqual(200, response.status_code)
        self.assertTrue("form" in response.context)
        expected = """
        <tr class="grp-row-even">
            <td><a href="{}" target="_blank">{}</a></td>
            <td></td>
            <td>PackagePolicy</td>
            <td>license1</td>
            <td>license1 AND license2</td>
            <td><input type="checkbox" name="checked_id_{}" class="enabler"></td>
        </tr>""".format(p1.get_admin_url(), p1.filename, p1.id)
        self.assertContains(response, expected, html=True)

        self.assertIsNone(p1.usage_policy)
        data = {
            "checked_id_{}".format(p1.id): "on",
            "ids": ids,
        }
        response = self.client.post(set_policy_url, data)
        self.assertRedirects(response, reverse("admin:component_catalog_package_changelist"))
        p1 = Package.objects.get(id=p1.id)
        self.assertEqual(package_policy, p1.usage_policy)

    def test_package_changelist_set_purl_action(self):
        self.client.login(username=self.user.username, password="secret")
        package = Package.objects.create(dataspace=self.dataspace1, filename="p1.zip")
        package.download_url = "http://repo1.maven.org/maven2/jdbm/jdbm/0.20-dev/"
        package.save()
        self.assertEqual("", package.package_url)

        changelist_url = reverse("admin:component_catalog_package_changelist")
        data = {
            "_selected_action": [package.id],
            "action": "set_purl",
        }

        response = self.client.post(changelist_url, data, follow=True)
        expected = "1 Package(s) updated with a Package URL."
        self.assertContains(response, expected)

        package.refresh_from_db()
        self.assertEqual("pkg:maven/jdbm/jdbm@0.20-dev", package.package_url)

        history_entry = History.objects.get_for_object(package).get()
        expected_messages = "Set Package URL from Download URL"
        self.assertEqual(expected_messages, history_entry.change_message)

    def test_package_admin_changeform_usage_policy_widget_wrapper(self):
        self.client.login(username="test", password="secret")
        p1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace1)

        license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            dataspace=self.dataspace1,
        )
        package_policy = UsagePolicy.objects.create(
            label="PackagePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Package),
            dataspace=self.dataspace1,
        )
        AssociatedPolicy.objects.create(
            from_policy=license_policy,
            to_policy=package_policy,
            dataspace=self.dataspace1,
        )

        self.license1.usage_policy = license_policy
        self.license1.save()
        p1.license_expression = self.license1.key
        p1.save()

        self.assertEqual(package_policy, p1.get_policy_from_primary_license())
        self.assertEqual(package_policy, p1.policy_from_primary_license)
        self.assertIsNone(p1.usage_policy)

        response = self.client.get(p1.get_admin_url())
        expected = (
            '<div class="grp-readonly">Value from primary license license1: PackagePolicy</div>'
        )
        self.assertContains(response, expected, html=True)

    def test_package_admin_changeform_usage_policy_on_license_expression_changed(self):
        self.client.login(username="test", password="secret")
        p1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace1)

        license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            dataspace=self.dataspace1,
        )
        package_policy = UsagePolicy.objects.create(
            label="PackagePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Package),
            dataspace=self.dataspace1,
        )
        package_policy2 = UsagePolicy.objects.create(
            label="PackagePolicy2",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Package),
            dataspace=self.dataspace1,
        )
        AssociatedPolicy.objects.create(
            from_policy=license_policy,
            to_policy=package_policy,
            dataspace=self.dataspace1,
        )

        self.license1.usage_policy = license_policy
        self.license1.save()
        p1.usage_policy = package_policy2
        p1.save()

        self.assertIsNone(p1.get_policy_from_primary_license())
        self.assertIsNone(p1.policy_from_primary_license)

        data = {
            "filename": p1.filename,
            "license_expression": self.license1.key,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(p1.get_admin_url(), data, follow=True)
        expected = (
            "The changed license assignment does not match the currently assigned usage "
            'policy: "PackagePolicy2" != "PackagePolicy" from license1'
        )
        self.assertEqual(expected, list(response.context["messages"])[0].message)

    def test_package_changeform_inline_component_trigger_update_completion_level(self):
        self.client.login(username="test", password="secret")
        package1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace1)
        url = package1.get_admin_url()

        self.assertEqual(0, package1.componentassignedpackage_set.count())
        self.assertEqual(0, self.component1.componentassignedpackage_set.count())
        self.assertEqual(0, self.component2.componentassignedpackage_set.count())
        self.assertEqual(15, self.component1.compute_completion_level())
        self.component1.update_completion_level()
        self.component1.refresh_from_db()
        self.assertEqual(15, self.component1.completion_level)

        # Addition
        data = {
            "filename": "a.zip",
            "componentassignedpackage_set-0-component": self.component1.id,
            "componentassignedpackage_set-TOTAL_FORMS": "1",
            "componentassignedpackage_set-INITIAL_FORMS": "0",
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        self.assertEqual(1, package1.componentassignedpackage_set.count())
        self.assertEqual(1, self.component1.componentassignedpackage_set.count())
        self.component1.refresh_from_db()
        self.assertEqual(22, self.component1.completion_level)

        # Edition
        data["componentassignedpackage_set-INITIAL_FORMS"] = "1"
        data["componentassignedpackage_set-0-id"] = package1.componentassignedpackage_set.get().id
        data["componentassignedpackage_set-0-component"] = (self.component2.id,)
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        self.assertEqual(1, package1.componentassignedpackage_set.count())
        self.assertEqual(0, self.component1.componentassignedpackage_set.count())
        self.component1.refresh_from_db()
        self.assertEqual(15, self.component1.completion_level)
        self.assertEqual(1, self.component2.componentassignedpackage_set.count())
        self.component2.refresh_from_db()
        self.assertEqual(22, self.component2.completion_level)

        # Deletion
        data["componentassignedpackage_set-0-DELETE"] = "on"
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        self.assertEqual(0, package1.componentassignedpackage_set.count())
        self.assertEqual(0, self.component2.componentassignedpackage_set.count())
        self.component2.refresh_from_db()
        self.assertEqual(15, self.component2.completion_level)

    def test_package_changeform_inline_remove_component_value_and_save_as(self):
        self.client.login(username="test", password="secret")
        package1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace1)
        url = package1.get_admin_url()

        data = {
            "filename": "a.zip",
            "_saveasnew": "Save as new",
            "componentassignedpackage_set-0-component": "",
            "componentassignedpackage_set-0-id": "",
            "componentassignedpackage_set-0-package": "",
            "componentassignedpackage_set-TOTAL_FORMS": "1",
            "componentassignedpackage_set-INITIAL_FORMS": "0",
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_package_changeform_unique_constraint_validation(self):
        self.client.login(username="test", password="secret")
        package1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace1)
        add_url = reverse("admin:component_catalog_package_add")

        data = {
            "filename": package1.filename,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(add_url, data)
        self.assertEqual(200, response.status_code)
        error = (
            "Package with this Dataspace, Type, Namespace, Name, Version, Qualifiers,"
            " Subpath, Download URL and Filename already exists."
        )
        expected = f"<li>{error}</li>"
        self.assertContains(response, expected, html=True)
        errors = {"__all__": [error]}
        self.assertEqual(errors, response.context_data["adminform"].form.errors)

        package1.download_url = "http://url.com/p1.zip"
        package1.save()

        data["download_url"] = package1.download_url
        response = self.client.post(add_url, data)
        self.assertEqual(200, response.status_code)
        expected = f"<li>{error}</li>"
        self.assertContains(response, expected, html=True)
        errors = {"__all__": [error]}
        self.assertEqual(errors, response.context_data["adminform"].form.errors)

        # Making sure the validation is scoped by dataspace
        other_package = Package.objects.create(
            filename="p2.zip", download_url="http://url2.zip", dataspace=self.dataspace_target
        )
        data["filename"] = other_package.filename
        data["download_url"] = other_package.download_url
        response = self.client.post(add_url, data)
        self.assertEqual(302, response.status_code)
        Package.objects.get(
            filename=data["filename"], download_url=data["download_url"], dataspace=self.dataspace1
        )

    def test_package_changeform_filename_validation(self):
        self.client.login(username="test", password="secret")
        add_url = reverse("admin:component_catalog_package_add")

        data = {
            "filename": "pack/age.zip",
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(add_url, data)
        self.assertEqual(200, response.status_code)
        errors = {
            "filename": ["Enter a valid filename: slash, backslash, or colon are not allowed."]
        }
        self.assertEqual(errors, response.context_data["adminform"].form.errors)

        data["filename"] = "pack\\age.zip"
        response = self.client.post(add_url, data)
        self.assertEqual(200, response.status_code)
        self.assertEqual(errors, response.context_data["adminform"].form.errors)

        data["filename"] = "pack:age.zip"
        response = self.client.post(add_url, data)
        self.assertEqual(200, response.status_code)
        self.assertEqual(errors, response.context_data["adminform"].form.errors)

    @mock.patch("vulnerabilities.models.AffectedByVulnerabilityMixin.fetch_vulnerabilities")
    def test_package_changeform_fetch_vulnerabilities(self, mock_fetch_vulnerabilities):
        mock_fetch_vulnerabilities.return_value = None
        self.dataspace1.enable_vulnerablecodedb_access = True
        self.dataspace1.save()
        self.client.login(username="test", password="secret")
        add_url = reverse("admin:component_catalog_package_add")

        data = {
            "filename": "package.zip",
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        self.client.post(add_url, data)
        mock_fetch_vulnerabilities.assert_called()

    def test_component_changelist_advanced_search_on_empty_space(self):
        self.client.login(username="test", password="secret")
        changelist_url = reverse("admin:component_catalog_component_changelist")
        # '?q=+' + means empty space
        response = self.client.get(changelist_url + "?q=+")
        self.assertEqual(200, response.status_code)
        expected = Component.objects.scope(self.dataspace1).count()
        self.assertEqual(expected, response.context_data["cl"].result_count)

    def test_component_changelist_advanced_search_with_apostrophe(self):
        self.client.login(username="test", password="secret")
        changelist_url = reverse("admin:component_catalog_component_changelist")

        self.component1.name = "Programmer's Notepad"
        self.component1.save()
        response = self.client.get(changelist_url + "?q=Programmer%27s+Notepad")
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(self.component1, response.context_data["cl"].queryset)

        response = self.client.get(changelist_url + '?q=%3D"google+toolkit')
        self.assertEqual(200, response.status_code)
        expected = '<li class="grp-error">Search terms error: No closing quotation</li>'
        self.assertContains(response, expected)

    def test_component_changelist_search_distinct_applied_on_m2m_fields(self):
        self.client.login(username="test", password="secret")
        changelist_url = reverse("admin:component_catalog_component_changelist")

        package1 = Package.objects.create(filename="package1.zip", dataspace=self.dataspace1)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.dataspace1
        )
        package2 = Package.objects.create(filename="package2.zip", dataspace=self.dataspace1)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package2, dataspace=self.dataspace1
        )

        self.assertEqual(2, self.component1.packages.count())
        self.assertIn("packages__filename", ComponentAdmin.search_fields)  # m2m field in search

        response = self.client.get(changelist_url + f"?q={self.component1.name}")
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.context_data["cl"].result_count)

    def test_component_changelist_reporting_query_list_filter(self):
        from reporting.models import OrderField
        from reporting.models import Query

        component_ct = ContentType.objects.get_for_model(Component)
        query1 = Query.objects.create(
            dataspace=self.dataspace1, name="Q1", content_type=component_ct, operator="and"
        )
        OrderField.objects.create(
            dataspace=self.dataspace1, query=query1, field_name="license_expression", seq=0
        )
        query2 = Query.objects.create(
            dataspace=self.dataspace1, name="Q2", content_type=component_ct, operator="and"
        )

        self.client.login(username=self.user.username, password="secret")
        url = reverse("admin:component_catalog_component_changelist")
        response = self.client.get(url)

        expected = f"""
        <select class="grp-filter-choice" data-field-name="reporting_query">
            <option value="?" selected='selected'>All</option>
            <option value="?o=6&amp;reporting_query={query1.id}">Q1</option>
            <option value="?reporting_query={query2.id}">Q2</option>
        </select>
        """
        self.assertContains(response, expected, html=True)

    def test_component_admin_changeform_usage_policy_widget_wrapper(self):
        self.client.login(username="test", password="secret")

        license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            dataspace=self.dataspace1,
        )
        component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.dataspace1,
        )
        AssociatedPolicy.objects.create(
            from_policy=license_policy,
            to_policy=component_policy,
            dataspace=self.dataspace1,
        )

        self.license1.usage_policy = license_policy
        self.license1.save()
        self.component1.license_expression = self.license1.key
        self.component1.save()

        self.assertEqual(component_policy, self.component1.get_policy_from_primary_license())
        self.assertEqual(component_policy, self.component1.policy_from_primary_license)
        self.assertIsNone(self.component1.usage_policy)

        response = self.client.get(self.component1.get_admin_url())
        expected = (
            '<div class="grp-readonly">Value from primary license license1: ComponentPolicy</div>'
        )
        self.assertContains(response, expected, html=True)

    def test_component_admin_changeform_usage_policy_on_license_expression_changed(self):
        self.client.login(username="test", password="secret")

        license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            dataspace=self.dataspace1,
        )
        component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.dataspace1,
        )
        component_policy2 = UsagePolicy.objects.create(
            label="ComponentPolicy2",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.dataspace1,
        )
        AssociatedPolicy.objects.create(
            from_policy=license_policy,
            to_policy=component_policy,
            dataspace=self.dataspace1,
        )

        self.license1.usage_policy = license_policy
        self.license1.save()
        self.component1.usage_policy = component_policy2
        self.component1.save()

        self.assertIsNone(self.component1.get_policy_from_primary_license())
        self.assertIsNone(self.component1.policy_from_primary_license)

        data = {
            "name": self.component1.name,
            "curation_level": "0",
            "license_expression": self.license1.key,
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        response = self.client.post(self.component1.get_admin_url(), data, follow=True)
        expected = (
            "The changed license assignment does not match the currently assigned usage "
            'policy: "ComponentPolicy2" != "ComponentPolicy" from license1'
        )
        self.assertEqual(expected, list(response.context["messages"])[0].message)

    def test_subcomponent_admin_changelist_available_actions(self):
        self.client.login(username="test", password="secret")

        url = reverse("admin:component_catalog_subcomponent_changelist")
        response = self.client.get(url)
        expected = [
            ("", "---------"),
            ("set_policy", "Set usage policy from components"),
            ("mass_update", "Mass update"),
        ]
        self.assertEqual(expected, response.context_data["action_form"].fields["action"].choices)

        with self.assertRaises(NoReverseMatch):
            reverse("admin:component_catalog_subcomponent_copy")

        with self.assertRaises(NoReverseMatch):
            reverse("admin:component_catalog_subcomponent_compare")

    def test_component_admin_delete_confirmation_include_associated_packages(self):
        self.client.login(username="test", password="secret")
        delete_url = reverse("admin:component_catalog_component_delete", args=[self.component1.pk])
        self.assertFalse(self.component1.packages.exists())
        response = self.client.get(delete_url)
        expected = "Would you also like to delete Packages associated with this Component"
        self.assertNotContains(response, expected)

        package1 = make_package(dataspace=self.dataspace1, filename="package1.zip")
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.dataspace1
        )
        package2 = make_package(dataspace=self.dataspace1, filename="package2.zip")
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package2, dataspace=self.dataspace1
        )
        self.assertEqual(2, self.component1.packages.count())

        response = self.client.get(delete_url)
        self.assertContains(response, expected)
        field = '<input type="checkbox" name="enable_delete_packages" id="enable_delete_packages">'
        self.assertContains(response, field)

        data = {
            "post": "yes",
            "delete_packages": "yes",
        }
        response = self.client.post(delete_url, data=data, follow=True)
        self.assertContains(response, "was deleted successfully.")
        self.assertFalse(Component.objects.filter(pk=self.component1.pk).exists())
        package_qs = Package.objects.filter(pk__in=[package1.pk, package2.pk])
        self.assertFalse(package_qs.exists())

        package3 = make_package(dataspace=self.dataspace1, filename="package3.zip")
        ComponentAssignedPackage.objects.create(
            component=self.component2, package=package3, dataspace=self.dataspace1
        )
        data = {
            "post": "yes",
        }
        delete_url = reverse("admin:component_catalog_component_delete", args=[self.component2.pk])
        response = self.client.post(delete_url, data=data, follow=True)
        self.assertContains(response, "was deleted successfully.")
        self.assertFalse(Component.objects.filter(pk=self.component2.pk).exists())
        self.assertTrue(Package.objects.filter(pk=package3.pk).exists())

    def test_component_admin_delete_selected_action_include_associated_packages(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_changelist")

        package1 = Package.objects.create(filename="package1.zip", dataspace=self.dataspace1)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.dataspace1
        )
        package2 = Package.objects.create(filename="package2.zip", dataspace=self.dataspace1)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package2, dataspace=self.dataspace1
        )

        data = {
            "_selected_action": [self.component1.id],
            "action": "delete_selected",
        }

        response = self.client.post(url, data)
        expected = "Would you also like to delete Packages associated with these Components"
        self.assertContains(response, expected)

        data.update(
            {
                "post": "yes",
                "delete_packages": "yes",
            }
        )

        response = self.client.post(url, data, follow=True)
        msg = '<li class="grp-success">Successfully deleted 1 component.</li>'
        self.assertContains(response, msg)
        self.assertFalse(Component.objects.filter(pk=self.component1.pk).exists())
        self.assertFalse(Package.objects.filter(pk__in=[package1.pk, package2.pk]).exists())

    def test_component_changeform_primary_language_autocomplete_field(self):
        self.client.login(username="test", password="secret")
        url = self.component1.get_admin_url()
        response = self.client.get(url)

        expected = (
            '<script id="client_data" type="application/json">'
            '{"awesomplete_data": {"primary_language"'
        )
        self.assertContains(response, expected)

        expected = (
            '<link href="/static/awesomplete/awesomplete-1.1.5.css" media="all" rel="stylesheet">'
        )
        self.assertContains(response, expected, html=True)

        expected = '<script src="/static/awesomplete/awesomplete-1.1.5.min.js"></script>'
        self.assertContains(response, expected, html=True)

        expected = '<script src="/static/js/awesomplete_fields.js"></script>'
        self.assertContains(response, expected, html=True)

    def test_component_changeform_package_inline_autocomplete_field(self):
        Package.objects.create(
            type="pypi",
            namespace="djangoproject",
            name="django",
            version="3.1",
            dataspace=self.dataspace1,
        )

        self.client.login(username="test", password="secret")
        url = reverse("grp_autocomplete_lookup")
        url += "?app_label=component_catalog&model_name=package"

        search_queries = [
            "pkg:pypi/djangoproject/django@3.1",
            "pypi/django@3.1",
            "django@3.1",
            "django 3.1",
            "pypi django 3.1",
        ]

        for term in search_queries:
            response = self.client.get(url + f"&term={term}")
            results = json.loads(response.content.decode())
            self.assertEqual("pkg:pypi/djangoproject/django@3.1", results[0].get("label"))

    def test_component_admin_get_initial_from_related_instance(self):
        release_date = datetime.datetime(2018, 6, 21, 3, 38, 24, 139528)
        package1 = Package.objects.create(
            filename="p1.zip",
            release_date=release_date,
            primary_language="Python",
            project="Project",
            license_expression="bsd",
            copyright="Copyright",
            notice_text="Notice",
            homepage_url="http://url.com",
            reference_notes="Reference notes",
            dataspace=self.dataspace1,
        )
        initial = ComponentAdmin._get_initial_from_related_instance(package1)
        expected = {
            "release_date": release_date,
            "primary_language": "Python",
            "project": "Project",
            "license_expression": "bsd",
            "copyright": "Copyright",
            "notice_text": "Notice",
            "homepage_url": "http://url.com",
            "reference_notes": "Reference notes",
        }
        self.assertEqual(expected, initial)

    def test_component_admin_get_changeform_initial_data(self):
        self.client.login(username="test", password="secret")

        package1 = Package.objects.create(
            filename="p1.zip",
            copyright="Copyright from Package",
            dataspace=self.dataspace1,
        )

        expected = package1.copyright
        component_add_url = reverse("admin:component_catalog_component_add")

        response = self.client.get(component_add_url)
        self.assertNotContains(response, expected)

        response = self.client.get(component_add_url, HTTP_REFERER=package1.get_admin_url())
        self.assertContains(response, expected)

    def test_component_admin_form_acceptable_linkages(self):
        self.client.login(username="test", password="secret")

        AcceptableLinkage.objects.create(label="linkage1", dataspace=self.dataspace1)
        AcceptableLinkage.objects.create(label="linkage2", dataspace=self.dataspace1)
        AcceptableLinkage.objects.create(label="linkage3", dataspace=self.dataspace_target)

        expected_choices = [
            ("linkage1", "linkage1"),
            ("linkage2", "linkage2"),
        ]

        component_add_url = reverse("admin:component_catalog_component_add")
        response = self.client.get(component_add_url)
        form = response.context_data["adminform"].form
        self.assertEqual(expected_choices, form.fields["acceptable_linkages"].choices)

        component_edit_url = self.component1.get_admin_url()
        response = self.client.get(component_edit_url)
        form = response.context_data["adminform"].form
        self.assertEqual(expected_choices, form.fields["acceptable_linkages"].choices)

        # Edit
        data = {
            "name": self.component1.name,
            "curation_level": "0",
            "acceptable_linkages": "linkage1",
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        self.client.post(component_edit_url, data, follow=True)
        self.component1.refresh_from_db()
        self.assertEqual(["linkage1"], self.component1.acceptable_linkages)

        data.update(
            {
                "name": "new",
                "acceptable_linkages": "not valid",
            }
        )
        response = self.client.post(component_add_url, data)
        expected = "<li>Select a valid choice. not valid is not one of the available choices.</li>"
        self.assertContains(response, expected, html=True)

        data["acceptable_linkages"] = ["linkage1", "linkage2"]
        response = self.client.post(component_add_url, data)
        added_component = Component.objects.latest("id")
        self.assertEqual(data["acceptable_linkages"], added_component.acceptable_linkages)

    def test_component_admin_form_configuration_setting(self):
        self.client.login(username="test", password="secret")
        component_add_url = reverse("admin:component_catalog_component_add")
        component_edit_url = self.component1.get_admin_url()

        response = self.client.get(component_add_url)
        form = response.context_data["adminform"].form
        self.assertIn("project", form.fields)
        self.assertIn("is_active", form.fields)

        response = self.client.get(component_edit_url)
        form = response.context_data["adminform"].form
        self.assertIn("project", form.fields)
        self.assertIn("is_active", form.fields)

        component_form_config = {
            "component": {
                "exclude": ["project", "is_active"],
            },
        }
        with override_settings(ADMIN_FORMS_CONFIGURATION=component_form_config):
            response = self.client.get(component_add_url)
            form = response.context_data["adminform"].form
            self.assertNotIn("project", form.fields)
            self.assertNotIn("is_active", form.fields)

            response = self.client.get(component_edit_url)
            form = response.context_data["adminform"].form
            self.assertNotIn("project", form.fields)
            self.assertNotIn("is_active", form.fields)


class PackageDataCollectionTestCase(TransactionTestCase):
    """
    Using a TransactionTestCase since we want to test the results of an on_commit() callback.
    https://docs.djangoproject.com/en/dev/topics/db/transactions/#use-in-tests
    """

    def setUp(self):
        # Workaround a side effect of running test_component_save_as_with_external_reference
        # Before a TransactionTestCase test.
        # https://code.djangoproject.com/ticket/10827#comment:19
        ContentType.objects.clear_cache()

        self.dataspace1 = Dataspace.objects.create(name="Dataspace")
        self.user = get_user_model().objects.create_superuser(
            "test", "test@test.com", "secret", self.dataspace1
        )

    @mock.patch("requests.get")
    def test_package_changeform_save_and_collect_data_on_addition(self, mock_get):
        self.client.login(username="test", password="secret")

        add_url = reverse("admin:component_catalog_package_add")
        response = self.client.get(add_url)
        expected = "Save and collect data"
        self.assertContains(response, expected)

        package1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace1)
        response = self.client.get(package1.get_admin_url())
        self.assertContains(response, expected)

        data = {
            "filename": "a.zip",
            "download_url": "http://domain.com/a.zip",
            "_collectdata": "Save and collect data",
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        mock_get.return_value = mock.Mock(
            content=b"\x00",
            headers={"content-length": 1},
            status_code=200,
            url="http://domain.com/a.zip",
        )

        response = self.client.post(add_url, data, follow=True)
        expected = (
            f"The SHA1, MD5, and Size fields collection from {data['download_url']} is in progress."
        )
        self.assertEqual(expected, list(response.context["messages"])[0].message)

        package1 = Package.objects.get(filename=data["filename"])
        self.assertEqual("93b885adfe0da089cdf634904fd59f71", package1.md5)
        self.assertEqual("5ba93c9db0cff93f52b521d7420e43f6eda2784f", package1.sha1)
        self.assertEqual(1, package1.size)

        data["download_url"] = "ftp://ftp.denx.de/pub/u-boot/u-boot-2017.11.tar.bz2"
        response = self.client.post(add_url, data, follow=True)
        expected = (
            'The SHA1, MD5, and Size fields collection is not supported for the "ftp" scheme.'
        )
        self.assertEqual(expected, list(response.context["messages"])[0].message)

        data["download_url"] = "git://github.com:nexB/aboutcode-toolkit.git"
        response = self.client.post(add_url, data, follow=True)
        expected = (
            'The SHA1, MD5, and Size fields collection is not supported for the "git" scheme.'
        )
        self.assertEqual(expected, list(response.context["messages"])[0].message)


class ComponentKeywordAdminViewsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="otherOO")
        self.owner = Owner.objects.create(name="Owner", dataspace=self.dataspace)
        self.owner2 = Owner.objects.create(name="Organization2", dataspace=self.other_dataspace)
        self.component = Component.objects.create(
            owner=self.owner, name="a", dataspace=self.dataspace
        )
        self.component_keyword = ComponentKeyword.objects.create(
            dataspace=self.dataspace, label="the_keyword", description="Blah blah blah"
        )
        self.component_keyword2 = ComponentKeyword.objects.create(
            dataspace=self.other_dataspace, label="foobar", description=""
        )

        self.user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "secret", self.dataspace
        )

    def test_keywords_do_not_cross_dataspaces(self):
        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(self.component.get_admin_url())
        expected = (
            '<input type="text" name="keywords" class="vTextField awesomplete" data-minchars="1" '
            'data-maxitems="10" data-autofirst="true"'
            ' placeholder="Start typing for suggestions..." '
            'data-list="the_keyword" id="id_keywords">'
        )
        self.assertContains(response, expected, html=True)
        self.assertNotContains(response, self.component_keyword2.label)

    def test_keywords_addition_and_duplicate_validation(self):
        self.client.login(username="nexb_user", password="secret")

        url = reverse("admin:component_catalog_componentkeyword_add")

        data = {"label": "A Keyword"}
        response = self.client.post(url, data)
        self.assertRedirects(
            response, reverse("admin:component_catalog_componentkeyword_changelist")
        )

        # Post the same label again
        response = self.client.post(url, data)
        self.assertContains(
            response, "<li>Component keyword with this Dataspace and Label already exists.</li>"
        )
        expected = {
            NON_FIELD_ERRORS: ["Component keyword with this Dataspace and Label already exists."]
        }
        self.assertEqual(expected, response.context_data["adminform"].form.errors)


class ComponentCopyTestCase(TestCase):
    def setUp(self):
        self.dataspace1 = Dataspace.objects.create(name="nexB")
        self.dataspace_target = Dataspace.objects.create(name="target_org")
        self.user = get_user_model().objects.create_superuser(
            "test", "test@test.com", "secret", self.dataspace1
        )

        self.type1 = ComponentType.objects.create(
            label="Type1", notes="notes", dataspace=self.dataspace1
        )
        self.status1 = ComponentStatus.objects.create(
            label="Status1", default_on_addition=False, dataspace=self.dataspace1
        )
        self.owner1 = Owner.objects.create(name="owner1", dataspace=self.dataspace1)
        self.license1 = License.objects.create(
            key="license1",
            name="License1",
            short_name="License1",
            dataspace=self.dataspace1,
            owner=self.owner1,
        )

        self.license_tag1 = LicenseTag.objects.create(
            label="Tag 1", text="Text for tag1", dataspace=self.dataspace1
        )
        self.license_assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.dataspace1,
        )

        self.component1 = Component.objects.create(
            name="Component1",
            version="0.1",
            type=self.type1,
            owner=self.owner1,
            homepage_url="http://localhost.com",
            dataspace=self.dataspace1,
        )
        self.component2 = Component.objects.create(
            name="Component2",
            version="0.2",
            type=self.type1,
            owner=self.owner1,
            dataspace=self.dataspace1,
        )
        self.component3 = Component.objects.create(
            name="Component3",
            version="r1",
            type=self.type1,
            owner=self.owner1,
            dataspace=self.dataspace1,
        )
        self.component4 = Component.objects.create(
            name="Component4",
            version="r3",
            type=self.type1,
            owner=self.owner1,
            dataspace=self.dataspace1,
        )
        self.component5 = Component.objects.create(
            name="Component5",
            version="r4",
            type=self.type1,
            owner=self.owner1,
            dataspace=self.dataspace1,
        )
        self.component6 = Component.objects.create(
            name="Component6",
            version="r5",
            type=self.type1,
            owner=self.owner1,
            dataspace=self.dataspace1,
        )

        self.sub_component1 = Subcomponent.objects.create(
            parent=self.component6,
            child=self.component5,
            dataspace=self.component6.dataspace,
            notes="I have a parent 6, and child 5",
        )
        self.sub_component2 = Subcomponent.objects.create(
            parent=self.component5,
            child=self.component4,
            dataspace=self.component5.dataspace,
            notes="I have a parent 5, and child 4",
        )
        self.sub_component3 = Subcomponent.objects.create(
            parent=self.component4,
            child=self.component3,
            dataspace=self.component4.dataspace,
            notes="I have a parent 4, and child 3",
        )
        self.sub_component4 = Subcomponent.objects.create(
            parent=self.component3,
            child=self.component2,
            dataspace=self.component3.dataspace,
            notes="I have a parent 3, and child 2",
        )
        self.sub_component5 = Subcomponent.objects.create(
            parent=self.component2,
            child=self.component1,
            dataspace=self.component2.dataspace,
            notes="I have a parent 2, and child 1",
        )

    def test_copy_component_type(self):
        component_type_original_count = ComponentType.objects.count()
        copied_object = copy_object(self.type1, self.dataspace_target, self.user)
        self.assertEqual(component_type_original_count + 1, ComponentType.objects.count())
        self.assertEqual("Type1", copied_object.label)
        self.assertEqual("notes", copied_object.notes)

    def test_copy_component_exclude_request_count(self):
        from workflow.models import Request
        from workflow.models import RequestTemplate

        component_ct = ContentType.objects.get(app_label="component_catalog", model="component")
        request_template1 = RequestTemplate.objects.create(
            name="T1", description="Desc1", dataspace=self.dataspace1, content_type=component_ct
        )
        Request.objects.create(
            title="Title1",
            request_template=request_template1,
            requester=self.user,
            content_object=self.component1,
            dataspace=self.dataspace1,
            content_type=component_ct,
        )
        self.assertEqual(1, self.component1.count_requests())
        self.component1.refresh_from_db()
        self.assertEqual(1, self.component1.request_count)

        copied_object = copy_object(self.component1, self.dataspace_target, self.user)
        self.assertIsNone(copied_object.request_count)
        self.assertEqual(0, copied_object.count_requests())

    def test_copy_component_common(self):
        copied_object = copy_object(self.component1, self.dataspace_target, self.user)

        # Making sure the Type was copied too.
        self.assertEqual(self.component1.type.uuid, copied_object.type.uuid)
        self.assertEqual("0.1", copied_object.version)
        self.assertEqual(self.dataspace_target, copied_object.owner.dataspace)
        self.assertEqual("owner1", copied_object.owner.name)
        self.assertTrue(copied_object.is_active)

    def test_copy_component_no_default_status(self):
        # There is no default status set in the target dataspace
        self.assertFalse(ComponentStatus.objects.get_default_on_addition_qs(self.dataspace_target))
        copied_object = copy_object(self.component1, self.dataspace_target, self.user)
        self.assertFalse(copied_object.configuration_status)

    def test_copy_component_with_default_status(self):
        # Creating a default status in the target dataspace
        default_in_target = ComponentStatus.objects.create(
            label="Default",
            text="This is the default status.",
            default_on_addition=True,
            dataspace=self.dataspace_target,
        )
        copied_object = copy_object(self.component1, self.dataspace_target, self.user)
        self.assertEqual(default_in_target, copied_object.configuration_status)

    def test_copy_component_with_assigned_licenses(self):
        self.component1.license_expression = self.license1.key
        self.component1.save()
        self.assertEqual(1, self.component1.licenses.count())

        copied_object = copy_object(self.component1, self.dataspace_target, self.user)
        copied_license = copied_object.licenses.all()[0]
        self.assertEqual(self.license1.key, copied_license.key)
        # Object are not the same DB entry but they share the same UUID
        self.assertNotEqual(self.license1.id, copied_license.id)
        self.assertEqual(self.license1.uuid, copied_license.uuid)

    def test_copy_component_with_license_expression_and_assigned_licenses(self):
        # Same referenced license in both expression
        self.component1.license_expression = self.license1.key
        self.component1.save()
        self.assertEqual(1, self.component1.licenses.count())
        self.component2.license_expression = self.license1.key
        self.component2.save()
        self.assertEqual(1, self.component2.licenses.count())

        # No license in the the target
        self.assertFalse(License.objects.scope(self.dataspace_target).exists())

        copied_object = copy_object(self.component1, self.dataspace_target, self.user)
        copied_license = copied_object.licenses.all()[0]
        self.assertEqual(self.license1.key, copied_license.key)
        # Object are not the same DB entry but they share the same UUID
        self.assertNotEqual(self.license1.id, copied_license.id)
        self.assertEqual(self.license1.uuid, copied_license.uuid)

        copy_object(self.component2, self.dataspace_target, self.user)
        matched_license = copied_object.licenses.all()[0]
        self.assertNotEqual(self.license1.id, matched_license.id)
        self.assertEqual(self.license1.uuid, matched_license.uuid)

    def test_copy_update_component_with_license_expression_and_assigned_licenses(self):
        self.assertFalse(self.component1.license_expression)
        copied_component = copy_object(self.component1, self.dataspace_target, self.user)
        copied_license = copy_object(self.license1, self.dataspace_target, self.user)

        # Same referenced license in both expression
        self.component1.license_expression = self.license1.key
        self.component1.save()
        self.assertEqual(1, self.component1.licenses.count())

        copied_component.license_expression = copied_license.key
        copied_component.save()
        self.assertEqual(1, copied_component.licenses.count())

        # It is important that the ComponentAssignedLicense do not share the same UUID
        # for the purpose of this test.
        self.assertNotEqual(
            self.component1.componentassignedlicense_set.get().uuid,
            copied_component.componentassignedlicense_set.get().uuid,
        )

        license2 = License.objects.create(
            key="l2", name="l2", short_name="l2", dataspace=self.dataspace1, owner=self.owner1
        )
        self.component1.license_expression = license2.key
        self.component1.save()
        # License is not available in the target, will be copy along update.
        updated_component = copy_object(
            self.component1, self.dataspace_target, self.user, update=True
        )
        # License is copied along the update.
        self.assertEqual(1, updated_component.licenses.count())
        copied_license = updated_component.licenses.all()[0]
        self.assertEqual(license2.uuid, copied_license.uuid)
        self.assertEqual(self.component1.license_expression, updated_component.license_expression)

        license3 = License.objects.create(
            key="l3", name="l3", short_name="l3", dataspace=self.dataspace1, owner=self.owner1
        )
        self.component1.license_expression = license3.key
        self.component1.save()
        # Copy the license in the target before running the update
        copy_object(license3, self.dataspace_target, self.user)
        updated_component = copy_object(
            self.component1, self.dataspace_target, self.user, update=True
        )
        self.assertEqual(1, updated_component.licenses.count())
        self.assertEqual(license3.uuid, updated_component.licenses.all()[0].uuid)
        self.assertEqual(self.component1.license_expression, updated_component.license_expression)

    def test_copy_update_subcomponent_with_license_expression_and_uuid_conflict(self):
        self.assertFalse(Component.objects.scope(self.dataspace_target).exists())
        self.assertFalse(Subcomponent.objects.scope(self.dataspace_target).exists())

        self.sub_component1.license_expression = self.license1.key
        self.sub_component1.save()

        copy_object(self.sub_component1.parent, self.dataspace_target, self.user)
        copied_sub = Subcomponent.objects.latest("id")
        self.assertEqual(self.dataspace_target, copied_sub.dataspace)
        self.assertEqual(self.sub_component1.license_expression, copied_sub.license_expression)
        self.assertEqual(self.license1.uuid, copied_sub.licenses.get().uuid)
        self.assertEqual(
            self.sub_component1.subcomponentassignedlicense_set.get().uuid,
            copied_sub.subcomponentassignedlicense_set.get().uuid,
        )

        # Same UUID: update runs fine
        copy_object(self.sub_component1.parent, self.dataspace_target, self.user, update=True)

        copied_assigned_license = copied_sub.subcomponentassignedlicense_set.get()
        copied_assigned_license.uuid = uuid.uuid4()
        copied_assigned_license.save()

        copy_object(self.sub_component1.parent, self.dataspace_target, self.user, update=True)

    def test_object_copy_component_with_fields_exclude_propagation(self):
        # We want to make sure that a child Component copied during a Component
        # copy inherit from the same excluded_field as its parent.
        self.component1.admin_notes = "Admin notes 1"
        self.component1.configuration_status = self.status1
        self.component1.guidance = "Guidance 1"
        self.component1.save()

        self.component2.admin_notes = "Admin notes 2"
        self.component2.configuration_status = self.status1
        self.component2.guidance = "Guidance 2"
        self.component2.save()

        excluded_fields = ["configuration_status", "guidance"]
        exclude = {self.component1.__class__: excluded_fields}

        # self.sub_component5 is (parent=self.component2, child=self.component1)
        # so component1 is copied as the child of component2
        copied_object = copy_object(
            self.component2, self.dataspace_target, self.user, exclude=exclude
        )

        self.assertFalse(copied_object.configuration_status)
        self.assertFalse(copied_object.guidance)
        self.assertEqual("Admin notes 2", copied_object.admin_notes)

        # Now let's make sure those exclude were propagated to the m2m copy
        copied_child = Component.objects.get(
            uuid=self.component1.uuid, dataspace=self.dataspace_target
        )

        self.assertFalse(copied_child.configuration_status)
        self.assertFalse(copied_child.guidance)
        self.assertEqual("Admin notes 1", copied_child.admin_notes)

    def test_copy_component_with_assigned_licenses_m2m_already_in_target_with_different_uuid(self):
        self.client.login(username="test", password="secret")

        # Remove the type to limit the cascade copy
        self.component1.type = None
        self.component1.license_expression = self.license1.key
        self.component1.save()

        owner1_in_target = Owner.objects.create(
            uuid=self.owner1.uuid, name=self.owner1.name, dataspace=self.dataspace_target
        )

        # Also creating a License in the target, using the license1 unique
        # key but not sharing the same UUID
        License.objects.create(
            key=self.license1.key,
            name="License1",
            short_name="License1",
            owner=owner1_in_target,
            dataspace=self.dataspace_target,
        )

        url = reverse("admin:component_catalog_component_copy")
        data = {
            "ct": str(ContentType.objects.get_for_model(Component).pk),
            "copy_candidates": str(self.component1.id),
            "source": self.component1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(Subcomponent).pk,
        }

        response = self.client.post(url, data)
        self.assertContains(response, "<h2>Errors for the following Components.</h2>", html=True)
        self.assertContains(response, "duplicate key value violates unique constraint")

    def test_copy_component_with_assigned_licenses_m2m_not_in_target(self):
        self.client.login(username="test", password="secret")

        self.component1.license_expression = self.license1.key
        self.component1.save()

        self.assertFalse(License.objects.scope(self.dataspace_target).exists())
        url = reverse("admin:component_catalog_component_copy")

        data = {
            "ct": str(ContentType.objects.get_for_model(Component).pk),
            "copy_candidates": str(self.component1.id),
            "source": self.component1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(Subcomponent).pk,
        }

        self.client.post(url, data)
        copied_object = Component.objects.get(
            uuid=self.component1.uuid, dataspace=self.dataspace_target
        )
        self.assertEqual(self.component1.license_expression, copied_object.license_expression)
        self.assertEqual(self.component1.licenses.count(), copied_object.licenses.count())

    def test_copy_component_with_parentchild1(self):
        children_count = self.component3.get_children().count()
        parents_count = self.component3.get_parents().count()
        # Making sure the Component is involve in a Subcomponent relations as
        # a parent and as a child.
        self.assertTrue(children_count)
        self.assertTrue(parents_count)

        copied_object = copy_object(self.component3, self.dataspace_target, self.user)

        # We do not copied parents along Component copy
        self.assertFalse(copied_object.get_parents())
        self.assertEqual(children_count, copied_object.get_children().count())

    def test_copy_component_ticket6635(self):
        component_type_original_count = ComponentType.objects.count()
        owner_original_count = Owner.objects.count()

        Component.objects.create(
            name="Component_duplicate1",
            version="0.1",
            type=self.type1,
            owner=self.owner1,
            dataspace=self.dataspace1,
        )
        type1_duplicate = ComponentType.objects.create(
            label="Type1", notes="notes", dataspace=self.dataspace_target, uuid=self.type1.uuid
        )
        owner1_duplicate = Owner.objects.create(
            name="owner1", dataspace=self.dataspace_target, uuid=self.owner1.uuid
        )
        Component.objects.create(
            name="Component_duplicate1",
            version="0.1",
            type=type1_duplicate,
            owner=owner1_duplicate,
            dataspace=self.dataspace_target,
        )

        copy_object(self.component1, self.dataspace_target, self.user)
        self.assertEqual(component_type_original_count + 1, ComponentType.objects.count())
        self.assertEqual(owner_original_count + 1, Owner.objects.count())

    def test_copy_component_with_uuid_matching_type(self):
        # The purpose of thus is to copy a Component which has a Type that will
        # be matched in the target as it share the same UUID
        self.client.login(username="test", password="secret")

        # The copied Type needs to have the same UUID as the reference one
        ComponentType.objects.create(
            label="Type1", notes="notes", uuid=self.type1.uuid, dataspace=self.dataspace_target
        )

        type_original_count = ComponentType.objects.count()
        owner_original_count = Owner.objects.count()

        copy_object(self.component1, self.dataspace_target, self.user)

        # Same as it was matched and not copied
        self.assertEqual(type_original_count, ComponentType.objects.count())
        # +1 as the Owner was copied along the Component
        self.assertEqual(owner_original_count + 1, Owner.objects.count())

    def test_copy_component_with_assigned_package(self):
        package1 = Package.objects.create(filename="file.zip", dataspace=self.component2.dataspace)
        ComponentAssignedPackage.objects.create(
            component=self.component2, package=package1, dataspace=self.component2.dataspace
        )

        package_original_count = Package.objects.count()
        assigned_package_original_count = ComponentAssignedPackage.objects.count()

        copied_object = copy_object(self.component2, self.dataspace_target, self.user)

        self.assertTrue(copied_object.packages.all())
        self.assertEqual(package_original_count + 1, Package.objects.count())
        self.assertEqual(
            assigned_package_original_count + 1, ComponentAssignedPackage.objects.count()
        )

    def test_component_copy_m2m_update_depth(self):
        self.component1.license_expression = self.license1.key
        self.component1.save()

        # Let's copy self.component1 in the target
        copied_object = copy_object(self.component1, self.dataspace_target, self.user)
        self.assertEqual(copied_object.licenses.count(), self.component1.licenses.count())
        # The License, LicenseTag, LicenseAssignedTag were copied along.
        copied_assigned_tag = LicenseAssignedTag.objects.get(
            uuid=self.license_assigned_tag1.uuid, dataspace=self.dataspace_target
        )
        self.assertEqual(self.license_assigned_tag1.value, copied_assigned_tag.value)

        # Changing the reference License and AssignedTag
        self.license1.name = "NEW NAME"
        self.license1.save()
        self.license_assigned_tag1.value = False
        self.license_assigned_tag1.save()

        # Copy again with update
        copy_object(self.component1, self.dataspace_target, self.user, update=True)
        copied_license = License.objects.get(
            uuid=self.license1.uuid, dataspace=self.dataspace_target
        )
        copied_assigned_tag = LicenseAssignedTag.objects.get(
            uuid=self.license_assigned_tag1.uuid, dataspace=self.dataspace_target
        )

        # Change on m2m related object was not impacted
        self.assertEqual("License1", copied_license.name)
        # No impact on deeper m2m relation neither
        self.assertEqual(True, copied_assigned_tag.value)

    def test_copy_package_excluding_identifier(self):
        self.client.login(username="test", password="secret")

        package1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace1)
        url = reverse("admin:component_catalog_package_copy")

        data = {
            "ct": str(ContentType.objects.get_for_model(Package).pk),
            "copy_candidates": str(package1.id),
            "source": package1.dataspace.id,
            "targets": [self.dataspace_target.id],
            "exclude_copy": ["filename"],
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-ct": ContentType.objects.get_for_model(PackageAssignedLicense).pk,
        }

        response = self.client.post(url, data)
        self.assertContains(
            response, '<li class="grp-error">1 object was not copied/updated.</li>', html=True
        )
        self.assertContains(response, "<li>['package_url or filename required']</li>", html=True)
