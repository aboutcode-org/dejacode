#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from urllib.parse import quote_plus

from django.apps import apps
from django.test import TestCase
from django.urls import reverse

from dje.models import Dataspace
from dje.tests import add_perm
from dje.tests import create_superuser
from dje.tests import create_user
from dje.views import TabSetMixin
from organization.models import Owner
from organization.models import Subowner

License = apps.get_model("license_library", "License")
Component = apps.get_model("component_catalog", "Component")


class OwnerUserViewsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Dataspace")
        self.super_user = create_superuser("super_user", self.dataspace)
        self.basic_user = create_user("basic_user", self.dataspace)
        self.owner1 = Owner.objects.create(
            name="Owner1", dataspace=self.dataspace)
        self.owner2 = Owner.objects.create(
            name="Owner2", dataspace=self.dataspace)
        Subowner.objects.create(
            parent=self.owner1, child=self.owner2, dataspace=self.dataspace)

        self.license1 = License.objects.create(
            key="l1", name="L1", short_name="L1", dataspace=self.dataspace, owner=self.owner1
        )
        self.component1 = Component.objects.create(
            name="C1", dataspace=self.dataspace, owner=self.owner1
        )

    def test_object_details_view_tab_owner(self):
        expected_fields = [
            (
                "Name",
                self.owner1.get_absolute_link(),
                "The unique user-maintained name of the author, custodian, or provider of one or "
                "more software objects (licenses, components, products).",
                None,
            ),
            ("Homepage URL", "", "The homepage URL of the owner.", None),
            (
                "Type",
                "Organization",
                "An owner type differentiates individuals, ongoing businesses, and dynamic "
                "organizations (such as software projects). An owner of any type can be associated "
                "with a license, component, or product. An owner can also be the parent of any "
                "other owner.",
                None,
            ),
            (
                "Contact information",
                "",
                "Information, frequently a dedicated email address, about contacting an owner "
                "for license clarifications and permissions.",
                None,
            ),
            (
                "Alias",
                "",
                "Alternative spellings of the name of the owner as a comma-separated list.",
                None,
            ),
            ("Notes", "", "Extended notes about an owner.", None),
        ]

        fake_view = TabSetMixin()
        fake_view.object = self.component1
        owner_tab = fake_view.tab_owner()
        self.assertEqual(expected_fields, owner_tab["fields"])

        extra = owner_tab["extra"]
        hierarchy_dict = extra["context"]
        hierarchy_template = extra["template"]

        # Use ``list()`` to make the ``QuerySet`` instances comparable
        self.assertEqual(list(hierarchy_dict["owner_children"]), [self.owner2])
        self.assertEqual(list(hierarchy_dict["owner_parents"]), [])

        self.assertEqual(hierarchy_dict["owner_verbose_name"], "owner")
        self.assertEqual(hierarchy_dict["owner_verbose_name_plural"], "owners")
        self.assertEqual(
            "organization/tabs/tab_hierarchy.html", hierarchy_template)

    def test_owner_list_view_num_queries(self):
        self.client.login(username=self.super_user.username, password="secret")
        with self.assertNumQueries(13):
            self.client.get(reverse("organization:owner_list"))

    def test_owner_details_view_num_queries(self):
        self.client.login(username=self.super_user.username, password="secret")
        with self.assertNumQueries(18):
            self.client.get(self.owner1.get_absolute_url())

    def test_owner_list_view_search_unicode_utf8_name_support(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.owner1.name = "Vázquez Araújo"
        self.owner1.save()
        owner_list_url = reverse("organization:owner_list")
        response = self.client.get(owner_list_url)
        self.assertContains(response, self.owner1.get_absolute_link())

        search = quote_plus("Araújo")
        response = self.client.get(owner_list_url + f"?q={search}")
        self.assertContains(response, self.owner1.name)
        self.assertContains(response, self.owner1.get_absolute_url())

    def test_owner_details_view_unicode_utf8_name_support(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.owner1.name = "Gómez"
        self.owner1.save()
        response = self.client.get(self.owner1.get_absolute_url())
        self.assertContains(
            response, '<pre class="pre-bg-body-tertiary mb-1 field-name">Gómez</pre>'
        )
        self.assertContains(response, "<strong>Gómez</strong>")
        expected_urn = '<a href="/urn/urn:dje:owner:G%25C3%25B3mez/">urn:dje:owner:G%C3%B3mez</a>'
        self.assertContains(response, expected_urn)

    def test_owner_details_view_content(self):
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.owner1.get_absolute_url())

        self.assertContains(response, f"{self.owner1}")
        self.assertContains(response, self.owner1.get_change_url())
        self.assertContains(response, 'id="tab_essentials"')
        self.assertContains(response, 'id="tab_licenses"')
        self.assertContains(response, 'id="tab_components"')
        self.assertContains(response, 'id="tab_hierarchy"')

    def test_owner_list_view_content(self):
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(reverse("organization:owner_list"))

        self.assertContains(response, self.owner1.get_absolute_link())
        self.assertContains(response, self.owner2.get_absolute_link())
        self.assertContains(response, self.license1.key)
        self.assertContains(response, self.license1.short_name)
        self.assertContains(response, self.component1)

    def test_organization_owner_add_view_permission_access(self):
        add_url = reverse("organization:owner_add")
        response = self.client.get(add_url)
        self.assertEqual(302, response.status_code)
        self.assertRedirects(response, f"/login/?next={add_url}")

        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(add_url)
        self.assertEqual(403, response.status_code)

        self.basic_user = add_perm(self.basic_user, "add_owner")
        response = self.client.get(add_url)
        self.assertEqual(200, response.status_code)

    def test_organization_owner_update_view_permission_access(self):
        change_url = self.owner1.get_change_url()
        response = self.client.get(change_url)
        self.assertEqual(302, response.status_code)
        self.assertRedirects(response, f"/login/?next={change_url}")

        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(change_url)
        self.assertEqual(403, response.status_code)

        self.nexb_user = add_perm(self.basic_user, "change_owner")
        response = self.client.get(change_url)
        self.assertEqual(200, response.status_code)

    def test_organization_owner_add_view_create_proper(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.assertTrue(self.super_user.is_superuser)
        add_url = reverse("organization:owner_add")

        data = {
            "name": "name",
            "alias": "alias",
            "contact_info": "contact_info",
            "homepage_url": "http://url.com",
            "type": "Organization",
            "notes": "notes",
            "submit": "Add Owner",
        }

        response = self.client.post(add_url, data, follow=True)
        owner = Owner.objects.get(name=data["name"])
        self.assertEqual(data["name"], owner.name)
        self.assertEqual(data["alias"], owner.alias)
        self.assertEqual(data["contact_info"], owner.contact_info)
        self.assertEqual(data["homepage_url"], owner.homepage_url)
        self.assertEqual(data["type"], owner.type)
        self.assertEqual(data["notes"], owner.notes)
        expected = "Owner &quot;name&quot; was successfully created."
        self.assertContains(response, expected)

    def test_organization_owner_add_view_create_duplicate_name(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.assertTrue(self.super_user.is_superuser)
        add_url = reverse("organization:owner_add")

        data = {
            "name": self.owner1.name,
            "type": "Organization",
            "submit": "Add Owner",
        }

        response = self.client.post(add_url, data, follow=True)
        self.assertContains(response, "Please correct the error below.")
        self.assertContains(
            response, "Owner with this Dataspace and Name already exists.")

        # Case-insensitive validation
        data["name"] = self.owner1.name.upper()
        response = self.client.post(add_url, data, follow=True)
        self.assertContains(response, "Please correct the error below.")
        error = (
            f"The application object that you are creating already exists as "
            f"&quot;{self.owner1.name}&quot;. "
            f"Note that a different case in the object name is not sufficient "
            f"to make it unique."
        )
        self.assertContains(response, error)

    def test_organization_owner_update_view_proper(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.assertTrue(self.super_user.is_superuser)
        change_url = self.owner1.get_change_url()

        data = {
            "name": "name",
            "alias": "alias",
            "contact_info": "contact_info",
            "homepage_url": "http://url.com",
            "type": "Organization",
            "notes": "notes",
            "submit": "Update Owner",
        }

        response = self.client.post(change_url, data, follow=True)
        owner = Owner.objects.get(name=data["name"])
        self.assertEqual(data["name"], owner.name)
        self.assertEqual(data["alias"], owner.alias)
        self.assertEqual(data["contact_info"], owner.contact_info)
        self.assertEqual(data["homepage_url"], owner.homepage_url)
        self.assertEqual(data["type"], owner.type)
        self.assertEqual(data["notes"], owner.notes)
        expected = "Owner &quot;name&quot; was successfully updated."
        self.assertContains(response, expected)

    def test_organization_owner_update_view_no_changes(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.assertTrue(self.super_user.is_superuser)
        change_url = self.owner1.get_change_url()

        data = {
            "name": self.owner1.name,
            "type": self.owner1.type,
            "submit": "Update Owner",
        }

        response = self.client.post(change_url, data, follow=True)
        expected = "No fields changed."
        self.assertContains(response, expected)

    def test_organization_owner_delete_view(self):
        delete_url = self.owner1.get_delete_url()
        details_url = self.owner1.details_url
        self.client.login(username=self.basic_user.username, password="secret")

        response = self.client.get(details_url)
        self.assertEqual(200, response.status_code)
        self.assertNotContains(response, delete_url)

        response = self.client.get(delete_url)
        self.assertEqual(403, response.status_code)

        self.basic_user = add_perm(self.basic_user, "delete_owner")
        response = self.client.get(details_url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, delete_url)

        response = self.client.get(delete_url)
        self.assertTrue(self.owner1.license_set.exists())
        self.assertEqual(200, response.status_code)
        self.assertContains(response, f"Delete {self.owner1}")
        expected = (
            "You do not have all the permissions required to delete this owner and "
            "its relationships."
        )
        self.assertContains(response, expected, html=True)
        response = self.client.post(delete_url)
        self.assertEqual(404, response.status_code)

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(delete_url)
        expected = "You cannot delete this owner because it is already used by other objects."
        self.assertContains(response, expected, html=True)
        response = self.client.post(delete_url)
        self.assertEqual(404, response.status_code)

        self.client.login(username=self.basic_user.username, password="secret")
        owner2_id = self.owner2.id
        delete_url = self.owner2.get_delete_url()
        self.assertFalse(self.owner2.license_set.exists())
        response = self.client.get(delete_url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, f"Delete {self.owner2}")
        expected = f'Are you sure you want to delete "{self.owner2}"?'
        self.assertContains(response, expected, html=True)
        expected = '<input type="submit" class="btn btn-danger" value="Confirm deletion">'
        self.assertContains(response, expected, html=True)
        response = self.client.post(delete_url, follow=True)
        self.assertRedirects(response, reverse("organization:owner_list"))
        self.assertContains(response, "was successfully deleted.")
        self.assertFalse(Owner.objects.filter(id=owner2_id).exists())
