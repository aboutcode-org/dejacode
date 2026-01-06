#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from dje.copier import copy_object
from dje.filters import DataspaceFilter
from dje.filters import MissingInFilter
from dje.models import Dataspace
from dje.models import History
from dje.search import advanced_search
from dje.tests import add_perm
from dje.tests import create
from dje.tests import create_admin
from dje.tests import create_superuser
from dje.tests import create_user
from organization.models import Owner


class DataspacedModelAdminTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="other_dataspace")

        self.base_user = create_user("base_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)
        self.super_user = create_superuser("super_user", self.dataspace)
        self.other_user = create_superuser("other", self.other_dataspace)

        self.owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)

    def test_admin_history_view_dataspace_security(self):
        url_history = reverse("admin:organization_owner_history", args=[self.owner1.pk])

        # Not logged-in
        self.assertEqual(302, self.client.get(url_history).status_code)

        self.assertTrue(self.client.login(username=self.super_user.username, password="secret"))
        self.assertEqual(200, self.client.get(url_history).status_code)

        self.assertTrue(self.client.login(username="other", password="secret"))
        self.assertEqual(403, self.client.get(url_history).status_code)

    def test_admin_history_view_content(self):
        url_history = reverse("admin:organization_owner_history", args=[self.owner1.pk])
        self.client.login(username=self.super_user.username, password="secret")

        response = self.client.get(url_history)
        self.assertContains(response, "<h1>Change history: Owner1</h1>")
        self.assertContains(response, "<td>Added.</td>")

        History.log_change(self.super_user, self.owner1, "Changed name.")
        response = self.client.get(url_history)
        self.assertContains(response, "<h1>Change history: Owner1</h1>")
        self.assertContains(response, "<td>Added.</td>")
        self.assertContains(response, "<td>Changed name.</td>")

    def test_admin_docs_models_view(self):
        url_docs_models = reverse("admin:docs_models")
        response = self.client.get(url_docs_models)
        self.assertEqual(302, response.status_code)
        self.assertRedirects(response, f"/login/?next={url_docs_models}")

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(url_docs_models)
        self.assertContains(response, "Models documentation")

    def test_dataspaced_admin_advanced_search_method(self):
        search_fields = ["f1", "f2"]

        terms = [
            ("a", [("f1__icontains", "a"), ("f2__icontains", "a")]),
            ("^a", [("f1__istartswith", "a"), ("f2__istartswith", "a")]),
            ("=a", [("f1__iexact", "a"), ("f2__iexact", "a")]),
            (
                "a b",
                [
                    ("f1__icontains", "a"),
                    ("f2__icontains", "a"),
                    ("f1__icontains", "b"),
                    ("f2__icontains", "b"),
                ],
            ),
            ("f1:a", [("f1__icontains", "a")]),
            ("f1=a", [("f1__iexact", "a")]),
            ("f1^a", [("f1__istartswith", "a")]),
            ("a f2=b", [("f1__icontains", "a"), ("f2__icontains", "a"), ("f2__iexact", "b")]),
            ("f1:a f2:b", [("f1__icontains", "a"), ("f2__icontains", "b")]),
            ("f1=a f2^b", [("f1__iexact", "a"), ("f2__istartswith", "b")]),
            ("a", [("f1__icontains", "a"), ("f2__icontains", "a")]),
            ("^a", [("f1__istartswith", "a"), ("f2__istartswith", "a")]),
            ("=a", [("f1__iexact", "a"), ("f2__iexact", "a")]),
            # Wrong syntax
            ("f1", [("f1__icontains", "f1"), ("f2__icontains", "f1")]),
            ("f1a", [("f1__icontains", "f1a"), ("f2__icontains", "f1a")]),
            (
                "f1 = a",
                [
                    ("f1__icontains", "f1"),
                    ("f2__icontains", "f1"),
                    ("f1__icontains", "a"),
                    ("f2__icontains", "a"),
                ],
            ),
            (
                'f1 = "a"',
                [
                    ("f1__icontains", "f1"),
                    ("f2__icontains", "f1"),
                    ("f1__icontains", "a"),
                    ("f2__icontains", "a"),
                ],
            ),
        ]

        for search_term, expected in terms:
            filters = advanced_search(search_term, search_fields)
            self.assertEqual(expected, filters.children)

        with self.assertRaises(ValueError):
            advanced_search('="google toolkit', search_fields)

    def test_dataspace_admin_changelist_list_display_item_column_name(self):
        self.client.login(username=self.super_user.username, password="secret")
        url = reverse("admin:dje_dataspace_changelist")
        response = self.client.get(url)
        self.assertNotContains(response, "AsURL")
        self.assertContains(response, "column-homepage_url")

    def test_dataspace_admin_changeform_readonly_fields(self):
        dataspace_change_url = reverse("admin:dje_dataspace_change", args=[self.other_dataspace.pk])
        self.assertFalse(self.other_user.dataspace.is_reference)
        self.client.login(username=self.other_user.username, password="secret")
        response = self.client.get(dataspace_change_url)
        self.assertContains(response, '<div class="grp-readonly">other_dataspace</div>', html=True)

        self.assertTrue(self.super_user.dataspace.is_reference)
        self.assertTrue(self.super_user.is_superuser)
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(dataspace_change_url)
        expected = (
            f'<input type="text" name="name" value="{self.other_dataspace.name}" '
            f'class="vTextField" maxlength="20" required aria-describedby="id_name_helptext" '
            f'id="id_name">'
        )
        self.assertContains(response, expected, html=True)

    def test_dataspace_admin_changeform_scope_homepage_layout_choices(self):
        url = reverse("admin:dje_dataspace_change", args=[self.dataspace.pk])
        self.client.login(username=self.super_user.username, password="secret")

        card_layout_nexb = create("CardLayout", self.dataspace)
        card_layout_other = create("CardLayout", self.other_dataspace)

        response = self.client.get(url)
        expected = '<select name="configuration-__prefix__-homepage_layout"'
        self.assertContains(response, expected)
        self.assertContains(response, card_layout_nexb.name)
        self.assertNotContains(response, card_layout_other.name)

    def test_dataspace_admin_changeform_update_packages_from_scan_field_validation(self):
        self.client.login(username=self.other_user.username, password="secret")
        url = reverse("admin:dje_dataspace_change", args=[self.other_dataspace.pk])

        data = {
            "name": self.other_dataspace.name,
            "enable_package_scanning": False,
            "update_packages_from_scan": True,
            "configuration-TOTAL_FORMS": 0,
            "configuration-INITIAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        expected = "Package scanning needs to be enabled to use the automatic updates."
        self.assertContains(response, expected)

        data["enable_package_scanning"] = True
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "was changed successfully.")

    def test_dataspace_admin_changeform_hide_dataspace_fk_on_addition(self):
        self.client.login(username=self.super_user.username, password="secret")

        expected1 = "homepage_layout"
        expected2 = "Homepage layout"

        url = reverse("admin:dje_dataspace_add")
        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        url = reverse("admin:dje_dataspace_change", args=[self.other_dataspace.pk])
        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

    def test_dataspace_admin_changeform_dataspace_fk_read_only_when_other_dataspace(self):
        self.client.login(username=self.super_user.username, password="secret")

        expected = "configuration-0-homepage_layout"

        url = reverse("admin:dje_dataspace_change", args=[self.other_dataspace.pk])
        response = self.client.get(url)
        self.assertNotContains(response, expected)

        url = reverse("admin:dje_dataspace_change", args=[self.dataspace.pk])
        response = self.client.get(url)
        self.assertContains(response, expected)

    def test_dataspace_admin_changelist_missing_in_filter_availability(self):
        # MissingInFilter is only available to superusers
        url = reverse("admin:organization_owner_changelist")

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(302, response.status_code)

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

        add_perm(self.admin_user, "change_owner")
        response = self.client.get(url)
        self.assertNotContains(response, MissingInFilter.parameter_name)

        data = {MissingInFilter.parameter_name: self.other_dataspace}
        response = self.client.get(url, data=data)
        self.assertEqual(302, response.status_code)
        self.assertIn("?e=1", response["Location"])

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, MissingInFilter.parameter_name)

    def test_dataspace_admin_changelist_missing_in_filter_dataspace_value_validation(self):
        url = reverse("admin:organization_owner_changelist")
        self.client.login(username=self.super_user.username, password="secret")

        data = {MissingInFilter.parameter_name: self.other_dataspace.id}
        response = self.client.get(url, data=data)
        self.assertEqual(200, response.status_code)

        data = {MissingInFilter.parameter_name: "wrong"}
        response = self.client.get(url, data=data)
        self.assertEqual(302, response.status_code)
        self.assertIn("?e=1", response["Location"])

        data = {MissingInFilter.parameter_name: 999999}
        response = self.client.get(url, data=data)
        self.assertEqual(302, response.status_code)
        self.assertIn("?e=1", response["Location"])

        data = {
            MissingInFilter.parameter_name: self.other_dataspace.id,
            DataspaceFilter.parameter_name: 999999,
        }
        response = self.client.get(url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertEqual(0, response.context_data["cl"].result_count)

    @override_settings(REFERENCE_DATASPACE="nexB")
    def test_dataspace_admin_changelist_missing_in_filter_dataspace_choices_validation(self):
        customer_dataspace = Dataspace.objects.create(name="customer")

        url = reverse("admin:organization_owner_changelist")
        self.client.login(username=self.other_user.username, password="secret")

        response = self.client.get(url)
        for filtr in response.context_data["cl"].filter_specs:
            if isinstance(filtr, MissingInFilter):
                missing_in_filter = filtr

        valid_ids = [value for value, _ in missing_in_filter.lookup_choices]
        self.assertIn(self.dataspace.id, valid_ids)
        self.assertIn(self.other_dataspace.id, valid_ids)
        self.assertNotIn(customer_dataspace.id, valid_ids)

        data = {MissingInFilter.parameter_name: self.other_dataspace.id}
        response = self.client.get(url, data=data)
        self.assertEqual(200, response.status_code)

        data = {MissingInFilter.parameter_name: self.dataspace.id}
        response = self.client.get(url, data=data)
        self.assertEqual(200, response.status_code)

        data = {MissingInFilter.parameter_name: customer_dataspace.id}
        response = self.client.get(url, data=data)
        self.assertEqual(302, response.status_code)
        self.assertIn("?e=1", response["Location"])

        data = {
            MissingInFilter.parameter_name: self.other_dataspace.id,
            DataspaceFilter.parameter_name: self.other_dataspace.id,
        }
        response = self.client.get(url, data=data)
        self.assertEqual(200, response.status_code)

        data[DataspaceFilter.parameter_name] = self.dataspace.id
        response = self.client.get(url, data=data)
        self.assertEqual(200, response.status_code)

        data[DataspaceFilter.parameter_name] = customer_dataspace.id
        response = self.client.get(url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertEqual(0, response.context_data["cl"].result_count)

    def test_dataspace_admin_changelist_missing_in_filter_proper(self):
        # Same UUID, not a diff
        copied_owner1 = copy_object(self.owner1, self.other_dataspace, self.super_user)
        owner2 = Owner.objects.create(name="Owner2", dataspace=self.dataspace)
        other_owner3 = Owner.objects.create(name="Owner3", dataspace=self.other_dataspace)

        url = reverse("admin:organization_owner_changelist")
        self.client.login(username=self.super_user.username, password="secret")

        data = {
            MissingInFilter.parameter_name: self.other_dataspace.id,
        }
        response = self.client.get(url, data=data)
        queryset = response.context_data["cl"].queryset
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertNotIn(self.owner1, queryset)
        self.assertNotIn(copied_owner1, queryset)
        self.assertIn(owner2, queryset)
        self.assertNotIn(other_owner3, queryset)

        data = {
            MissingInFilter.parameter_name: self.dataspace.id,
            DataspaceFilter.parameter_name: self.other_dataspace.id,
        }

        response = self.client.get(url, data=data)
        queryset = response.context_data["cl"].queryset
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertNotIn(self.owner1, queryset)
        self.assertNotIn(copied_owner1, queryset)
        self.assertNotIn(owner2, queryset)
        self.assertIn(other_owner3, queryset)


class PermissionsTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.dataspace = Dataspace.objects.create(name="some_org")

        self.super_user = get_user_model().objects.create_superuser(
            "super_user", "super@test.com", "t3st", self.dataspace
        )

        self.staff_user = get_user_model().objects.create_user(
            "staff_user", "staff@test.com", "t3st", self.dataspace
        )
        self.staff_user.is_superuser = False
        self.staff_user.is_staff = True
        self.staff_user.save()

        self.dumb_user = get_user_model().objects.create_user(
            "dumb_user", "dumb@test.com", "t3st", self.dataspace
        )
        self.dumb_user.is_superuser = False
        self.dumb_user.is_staff = False
        self.dumb_user.save()

        self.nexb_user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.nexb_dataspace
        )

    def test_show_admin_link_in_header_navbar(self):
        self.assertFalse(self.staff_user.is_superuser)
        self.assertTrue(self.staff_user.is_staff)
        license_library_url = reverse("license_library:license_list")
        dashboard_url = reverse("admin:index")
        license_changelist_url = reverse("admin:license_library_license_changelist")

        self.client.login(username=self.super_user.username, password="t3st")
        self.assertTrue(self.super_user.has_perm("license_library.change_license"))
        response = self.client.get(license_library_url)
        self.assertContains(response, dashboard_url)
        self.assertContains(response, license_changelist_url)

        self.client.login(username=self.staff_user.username, password="t3st")
        self.assertFalse(self.staff_user.has_perm("license_library.change_license"))
        response = self.client.get(license_library_url)
        self.assertContains(response, dashboard_url)
        self.assertNotContains(response, license_changelist_url)

        change_license_perm = Permission.objects.get_by_natural_key(
            "change_license", "license_library", "license"
        )
        change_license_group = Group.objects.create(name="change_license")
        change_license_group.permissions.add(change_license_perm)
        self.staff_user.groups.add(change_license_group)
        self.staff_user = get_user_model().objects.get(username=self.staff_user.username)
        self.assertTrue(self.staff_user.has_perm("license_library.change_license"))
        response = self.client.get(license_library_url)
        self.assertContains(response, dashboard_url)
        self.assertContains(response, license_changelist_url)

        self.client.login(username="dumb_user", password="t3st")
        response = self.client.get(license_library_url)
        self.assertNotContains(response, dashboard_url)
        self.assertNotContains(response, license_changelist_url)

    def test_dataspace_changelist_queryset(self):
        dataspace_changelist_url = reverse("admin:dje_dataspace_changelist")
        # User is in the Reference dataspace, all the dataspaces are in the QS
        self.assertTrue(self.nexb_user.dataspace.is_reference)
        self.client.login(username=self.nexb_user.username, password="t3st")
        response = self.client.get(dataspace_changelist_url)
        self.assertContains(response, f"{self.dataspace.name}</a>")
        self.assertContains(response, f"{self.nexb_dataspace.name}</a>")

        # User is not in the Reference dataspace, only his dataspace is in the QS
        self.assertFalse(self.super_user.dataspace.is_reference)
        self.client.login(username=self.super_user.username, password="t3st")
        response = self.client.get(dataspace_changelist_url)
        self.assertContains(response, f"{self.dataspace.name}</a>")
        self.assertNotContains(response, f"{self.nexb_dataspace.name}</a>")

        # Staff user cannot access the Dataspace changelist
        self.assertFalse(self.staff_user.is_superuser)
        self.client.login(username=self.staff_user.username, password="t3st")
        response = self.client.get(dataspace_changelist_url)
        self.assertEqual(403, response.status_code)

    def test_dataspace_modeladmin_available_actions(self):
        dataspace_changelist_url = reverse("admin:dje_dataspace_changelist")

        self.assertTrue(self.nexb_user.dataspace.is_reference)
        self.client.login(username=self.nexb_user.username, password="t3st")
        response = self.client.get(dataspace_changelist_url)
        self.assertNotContains(response, "delete_selected")

        self.assertFalse(self.super_user.dataspace.is_reference)
        self.client.login(username=self.super_user.username, password="t3st")
        response = self.client.get(dataspace_changelist_url)
        self.assertNotContains(response, "delete_selected")

    def test_dataspace_related_modeladmin_available_actions(self):
        url = reverse("admin:license_library_license_changelist")

        # User is in the Reference dataspace
        self.assertTrue(self.nexb_user.dataspace.is_reference)
        self.client.login(username=self.nexb_user.username, password="t3st")
        response = self.client.get(url)
        self.assertContains(response, "copy_to")
        self.assertContains(response, "compare_with")
        self.assertContains(response, "delete_selected")
        self.assertContains(response, "mass_update")

        # User is not in the Reference dataspace
        self.assertFalse(self.super_user.dataspace.is_reference)
        self.client.login(username=self.super_user.username, password="t3st")
        response = self.client.get(url)
        self.assertNotContains(response, "copy_to")
        self.assertNotContains(response, "compare_with")
        self.assertContains(response, "delete_selected")
        self.assertContains(response, "mass_update")

        # User is not in the Reference dataspace and looking at reference data
        self.assertFalse(self.super_user.dataspace.is_reference)
        self.client.login(username=self.super_user.username, password="t3st")
        data = {DataspaceFilter.parameter_name: self.nexb_dataspace.id}
        response = self.client.get(url, data)
        self.assertContains(response, "copy_to")
        self.assertContains(response, "compare_with")
        self.assertNotContains(response, "delete_selected")
        self.assertNotContains(response, "mass_update")

    def test_dataspace_modeladmin_permissions(self):
        dataspace_change_url = reverse("admin:dje_dataspace_change", args=[self.dataspace.pk])
        dataspace_delete_url = reverse("admin:dje_dataspace_delete", args=[self.dataspace.pk])
        dataspace_changelist_url = reverse("admin:dje_dataspace_changelist")
        dataspace_add_url = reverse("admin:dje_dataspace_add")

        self.assertTrue(self.nexb_user.dataspace.is_reference)
        self.client.login(username=self.nexb_user.username, password="t3st")
        response = self.client.get(dataspace_changelist_url)
        self.assertContains(response, 'href="{}"'.format(dataspace_add_url))
        response = self.client.get(dataspace_change_url)
        self.assertContains(response, 'href="{}"'.format(dataspace_delete_url))
        response = self.client.get(dataspace_add_url)
        self.assertEqual(200, response.status_code)
        response = self.client.get(dataspace_delete_url)
        self.assertEqual(200, response.status_code)

        self.assertFalse(self.super_user.dataspace.is_reference)
        self.client.login(username=self.super_user.username, password="t3st")
        response = self.client.get(dataspace_changelist_url)
        self.assertNotContains(response, 'href="add/"')
        response = self.client.get(dataspace_change_url)
        self.assertNotContains(response, 'href="delete/"')
        response = self.client.get(dataspace_add_url)
        self.assertEqual(403, response.status_code)
        response = self.client.get(dataspace_delete_url)
        self.assertEqual(403, response.status_code)


class GroupAdminTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="other_dataspace")
        self.nexb_user = get_user_model().objects.create_superuser(
            "user", "test@test.com", "secret", self.nexb_dataspace
        )
        self.other_user = get_user_model().objects.create_superuser(
            "other", "test2@test.com", "secret", self.other_dataspace
        )

        self.add_url = reverse("admin:auth_group_add")
        self.changelist_url = reverse("admin:auth_group_changelist")

    def test_admin_group_views_availability_to_reference_dataspace_only(self):
        self.assertTrue(self.nexb_user.dataspace.is_reference)
        self.client.login(username=self.nexb_user.username, password="secret")
        response = self.client.get(self.changelist_url)
        self.assertEqual(200, response.status_code)
        response = self.client.get(self.add_url)
        self.assertEqual(200, response.status_code)

        self.assertFalse(self.other_user.dataspace.is_reference)
        self.client.login(username=self.other_user.username, password="secret")
        response = self.client.get(self.add_url)
        self.assertEqual(403, response.status_code)
        response = self.client.get(self.add_url)
        self.assertEqual(403, response.status_code)

    def test_admin_group_available_permissions(self):
        from dje.admin import GroupAdmin

        self.client.login(username=self.nexb_user.username, password="secret")
        response = self.client.get(self.add_url)
        permissions_field = response.context_data["adminform"].form.fields["permissions"]

        codenames = permissions_field.queryset.values_list("codename", flat=True)
        self.assertIn("add_component", codenames)
        self.assertIn("change_component", codenames)
        self.assertIn("delete_component", codenames)

        models = permissions_field.queryset.values_list("content_type__model", flat=True)
        self.assertIn("component", models)

        app_labels = permissions_field.queryset.values_list("content_type__app_label", flat=True)
        for app_label in set(app_labels):
            self.assertIn(app_label, GroupAdmin.allowed_app_label)

    def test_admin_group_permission_details_view(self):
        url = reverse("admin:auth_group_permission_details")

        change_license_perm = Permission.objects.get_by_natural_key(
            "change_license", "license_library", "license"
        )
        group = Group.objects.create(name="change_license")
        group.permissions.add(change_license_perm)

        self.client.login(username=self.nexb_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)

        self.client.login(username=self.other_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)

        expected = """
        <table class="grp-table">
            <thead>
                <tr>
                    <th></th>
                    <th><strong>change_license</strong></th>
                </tr>
            </thead>
            <tbody>
                <tr class="grp-row grp-row-even">
                    <td><strong>change license</strong></td>
                    <td>X</td>
                </tr>
            <tbody>
        </table>
        """
        self.assertContains(response, expected, html=True)

    def test_admin_group_permission_export_csv(self):
        self.client.login(username=self.nexb_user.username, password="secret")

        change_license_perm = Permission.objects.get_by_natural_key(
            "change_license", "license_library", "license"
        )
        group = Group.objects.create(name="change_license")
        group.permissions.add(change_license_perm)

        url = reverse("admin:auth_group_changelist")
        response = self.client.get(url)
        export_url = reverse("admin:auth_group_permission_export_csv")
        expected = f'<a class="grp-state-focus" href="{export_url}">Export as CSV</a>'
        self.assertContains(response, expected, html=True)

        response = self.client.get(export_url)
        self.assertEqual("text/csv", response["Content-Type"])
        self.assertEqual(
            'attachment; filename="dejacode_group_permission.csv"', response["Content-Disposition"]
        )
        self.assertEqual(b",change_license\r\nchange license,X\r\n", response.content)
