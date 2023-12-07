#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from component_catalog.models import Component
from dje.models import Dataspace
from dje.tests import create_superuser
from license_library.models import License
from organization.models import Owner
from policy.models import UsagePolicy


class UsagePolicyInAdminViewsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Dataspace")
        self.other_dataspace = Dataspace.objects.create(name="other")

        self.user = create_superuser("test", self.dataspace)

        self.license_ct = ContentType.objects.get_for_model(License)
        self.component_ct = ContentType.objects.get_for_model(Component)

        self.license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=self.license_ct,
            dataspace=self.dataspace,
        )

        self.component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=self.component_ct,
            dataspace=self.dataspace,
        )

        self.other_component_policy = UsagePolicy.objects.create(
            label="OtherComponent",
            icon="icon",
            content_type=self.component_ct,
            dataspace=self.other_dataspace,
        )

    def test_usage_policy_scoped_by_content_type_in_change_form(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_add")

        response = self.client.get(url)

        usage_policy_field = response.context_data["adminform"].form.fields["usage_policy"]
        self.assertIn(self.component_policy, usage_policy_field.queryset)
        self.assertNotIn(self.license_policy, usage_policy_field.queryset)
        self.assertNotIn(self.other_component_policy, usage_policy_field.queryset)

        self.assertContains(response, self.component_policy.label)
        self.assertNotContains(response, self.license_policy.label)
        self.assertNotContains(response, self.other_component_policy.label)

    def test_usage_policy_scoped_by_content_type_in_change_list_filters(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:component_catalog_component_changelist")

        response = self.client.get(url)
        self.assertContains(response, self.component_policy.label)
        self.assertNotContains(response, self.license_policy.label)
        self.assertNotContains(response, self.other_component_policy.label)

    def test_mass_update_usage_policy_scope_to_content_type(self):
        self.client.login(username="test", password="secret")
        component = Component.objects.create(name="c1", dataspace=self.dataspace)
        url = reverse("admin:component_catalog_component_changelist")
        data = {"_selected_action": [component.pk], "action": "mass_update", "select_across": 0}

        response = self.client.post(url, data)
        self.assertContains(response, self.component_policy.label)
        self.assertNotContains(response, self.license_policy.label)
        self.assertNotContains(response, self.other_component_policy.label)

    def test_usage_policy_deletion_protected(self):
        self.client.login(username="test", password="secret")

        Component.objects.create(
            name="c1", dataspace=self.dataspace, usage_policy=self.component_policy
        )

        url = reverse("admin:policy_usagepolicy_delete", args=[self.component_policy.pk])

        response = self.client.post(url, {"post": "yes"})
        expected = "would require deleting the following protected related objects"
        self.assertContains(response, expected)
        self.assertNotContains(response, 'type="submit"')

    def test_usage_policy_changeform_update_content_type_once_assigned(self):
        self.client.login(username="test", password="secret")
        url = self.component_policy.get_admin_url()

        component = Component.objects.create(
            name="c1", dataspace=self.dataspace, usage_policy=self.component_policy
        )

        self.assertTrue(self.component_policy.get_object_set().exists())
        self.assertNotEqual(self.license_ct, self.component_policy.content_type)

        data = {
            "label": self.component_policy.label,
            "icon": self.component_policy.icon,
            "content_type": self.license_ct.pk,
            "to_policies-INITIAL_FORMS": 0,
            "to_policies-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = {
            "content_type": [
                "The content type cannot be modified since this object is assigned "
                "to a least one instance."
            ]
        }
        self.assertEqual(expected, response.context_data["adminform"].form.errors)

        component.delete()
        self.assertFalse(self.component_policy.get_object_set().exists())
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        self.component_policy.refresh_from_db()
        self.assertEqual(self.license_ct, self.component_policy.content_type)

    def test_usage_policy_changeform_color_code_as_color_input(self):
        self.client.login(username="test", password="secret")
        response = self.client.get(self.component_policy.get_admin_url())
        expected = '<input id="id_color_code" maxlength="7" name="color_code" type="color" />'
        self.assertContains(response, expected, html=True)

    def test_usage_policy_changeform_clean_color_code(self):
        self.client.login(username="test", password="secret")
        url = self.component_policy.get_admin_url()

        data = {
            "label": self.component_policy.label,
            "icon": self.component_policy.icon,
            "content_type": self.license_ct.pk,
            "color_code": "111111",
            "to_policies-INITIAL_FORMS": 0,
            "to_policies-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        self.component_policy.refresh_from_db()
        self.assertEqual("#111111", self.component_policy.color_code)

    def test_usage_policy_download_license_dump_view(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:policy_usagepolicy_license_dump")

        # Link in Admin dashboard
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, url)

        # Link in UsagePolicy changelist
        response = self.client.get(reverse("admin:policy_usagepolicy_changelist"))
        self.assertContains(response, url)

        self.assertFalse(License.objects.count())
        response = self.client.get(url)
        self.assertEqual(response["Content-Type"], "application/x-yaml")
        expected = b"license_policies: []\n"
        self.assertEqual(expected, response.content)

        owner = Owner.objects.create(name="Owner ABC", dataspace=self.dataspace)
        License.objects.create(
            key="l1",
            name="L1",
            short_name="L1",
            dataspace=self.dataspace,
            owner=owner,
            usage_policy=self.license_policy,
        )
        License.objects.create(
            key="l2",
            name="L2",
            short_name="L2",
            dataspace=self.dataspace,
            owner=owner,
            usage_policy=self.license_policy,
        )

        self.assertEqual(2, License.objects.count())
        response = self.client.get(url)
        expected = (
            b"license_policies:\n"
            b"-   license_key: l1\n"
            b"    label: LicensePolicy\n"
            b"    color_code: '#000000'\n"
            b"    icon: icon\n"
            b"    compliance_alert: ''\n"
            b"-   license_key: l2\n"
            b"    label: LicensePolicy\n"
            b"    color_code: '#000000'\n"
            b"    icon: icon\n"
            b"    compliance_alert: ''\n"
        )
        self.assertEqual(expected, response.content)
