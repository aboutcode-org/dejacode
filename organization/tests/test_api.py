#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json

from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from rest_framework import status
from rest_framework.exceptions import ErrorDetail
from rest_framework.test import APIClient

from dje.models import Dataspace
from dje.models import DataspaceConfiguration
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.models import History
from dje.tests import MaxQueryMixin
from dje.tests import create_superuser
from dje.tests import create_user
from organization.models import Owner


@override_settings(
    EMAIL_HOST_USER="user",
    EMAIL_HOST_PASSWORD="password",
    EMAIL_HOST="localhost",
    EMAIL_PORT=25,
    DEFAULT_FROM_EMAIL="webmaster@localhost",
)
class OwnerAPITestCase(MaxQueryMixin, TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="alternate")

        self.base_user = create_user("base_user", self.dataspace)
        self.super_user = create_superuser(
            "super_user", self.dataspace, data_email_notification=True
        )

        self.owner_list_url = reverse("api_v2:owner-list")

        self.owner1 = Owner.objects.create(
            name="Owner1", alias="z", dataspace=self.dataspace, type="Person"
        )
        self.owner1_detail_url = reverse("api_v2:owner-detail", args=[self.owner1.uuid])
        self.owner2 = Owner.objects.create(name="Owner2", alias="a", dataspace=self.dataspace)
        self.owner2_detail_url = reverse("api_v2:owner-detail", args=[self.owner2.uuid])

        self.alternate_owner = Owner.objects.create(
            name="Owner1", dataspace=self.alternate_dataspace
        )
        self.alternate_owner_detail_url = reverse(
            "api_v2:owner-detail", args=[self.alternate_owner.uuid]
        )

        ext_source1 = ExternalSource.objects.create(label="GitHub", dataspace=self.dataspace)

        ExternalReference.objects.create_for_content_object(self.owner1, ext_source1, "REF1")
        ExternalReference.objects.create_for_content_object(self.owner1, ext_source1, "REF2")
        ExternalReference.objects.create_for_content_object(self.owner1, ext_source1, "REF3")

    def test_api_owner_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")
        for index in range(5):
            Owner.objects.create(name=f"Owner-{index}", dataspace=self.dataspace)

        with self.assertMaxQueries(12):
            response = self.client.get(self.owner_list_url)
        self.assertContains(response, '"count":7,')
        self.assertContains(response, self.owner1_detail_url)
        self.assertContains(response, self.owner2_detail_url)
        self.assertNotContains(response, self.alternate_owner_detail_url)
        self.assertEqual(7, response.data["count"])

    def test_api_owner_list_endpoint_options(self):
        client = APIClient()
        client.login(username="super_user", password="secret")
        response = client.options(self.owner_list_url, format="json")
        actions_post = response.data["actions"]["POST"]

        values = [choice.get("value") for choice in actions_post["type"].get("choices")]
        self.assertEqual(["Organization", "Person", "Project"], values)

    def test_api_owner_list_endpoint_search(self):
        self.client.login(username="super_user", password="secret")
        data = {"search": self.owner1.name}
        response = self.client.get(self.owner_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.owner1_detail_url)
        self.assertNotContains(response, self.owner2_detail_url)

        # Search is case in-sensitive
        data = {"search": self.owner1.name.upper()}
        response = self.client.get(self.owner_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.owner1_detail_url)
        self.assertNotContains(response, self.owner2_detail_url)

    def test_api_owner_list_endpoint_filters(self):
        self.client.login(username="super_user", password="secret")
        data = {"type": self.owner1.type}
        response = self.client.get(self.owner_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.owner1_detail_url)
        self.assertNotContains(response, self.owner2_detail_url)

        data = {"name": self.owner2.name}
        response = self.client.get(self.owner_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertNotContains(response, self.owner1_detail_url)
        self.assertContains(response, self.owner2_detail_url)

    def test_api_owner_list_endpoint_multiple_char_filters(self):
        self.client.login(username="super_user", password="secret")
        owner3 = Owner.objects.create(name="Own , er3", dataspace=self.dataspace)
        owner3_detail_url = reverse("api_v2:owner-detail", args=[owner3.uuid])

        filters = f"?name={self.owner1.name}&name={owner3.name}"
        response = self.client.get(self.owner_list_url + filters)
        self.assertEqual(2, response.data["count"])
        self.assertContains(response, self.owner1_detail_url)
        self.assertNotContains(response, self.owner2_detail_url)
        self.assertContains(response, owner3_detail_url)

        filters = f"?uuid={self.owner1.uuid}&uuid={owner3.uuid}"
        response = self.client.get(self.owner_list_url + filters)
        self.assertEqual(2, response.data["count"])
        self.assertContains(response, self.owner1_detail_url)
        self.assertNotContains(response, self.owner2_detail_url)
        self.assertContains(response, owner3_detail_url)

    def test_api_owner_list_endpoint_ordering(self):
        self.client.login(username="super_user", password="secret")

        data = {"ordering": "alias"}
        response = self.client.get(self.owner_list_url, data)
        self.assertEqual(self.owner2.name, response.data["results"][0].get("name"))
        self.assertEqual(self.owner1.name, response.data["results"][1].get("name"))

        data = {"ordering": "-alias"}
        response = self.client.get(self.owner_list_url, data)
        self.assertEqual(self.owner1.name, response.data["results"][0].get("name"))
        self.assertEqual(self.owner2.name, response.data["results"][1].get("name"))

    def test_api_owner_detail_endpoint(self):
        from license_library.models import License

        self.license = License.objects.create(
            key="key",
            owner=self.owner1,
            name="name",
            short_name="short_name",
            dataspace=self.dataspace,
        )
        from component_catalog.models import Component

        self.component = Component.objects.create(
            name="component", owner=self.owner1, dataspace=self.dataspace
        )

        self.client.login(username="super_user", password="secret")
        with self.assertMaxQueries(11):
            response = self.client.get(self.owner1_detail_url)

        self.assertContains(response, self.owner1_detail_url)
        self.assertIn(self.owner1_detail_url, response.data["api_url"])
        expected_url = f"http://testserver{self.owner1.get_absolute_url()}"
        self.assertEqual(expected_url, response.data["absolute_url"])
        self.assertEqual(str(self.owner1.uuid), response.data["uuid"])
        self.assertEqual(self.owner1.name, response.data["name"])
        self.assertEqual(self.owner1.type, response.data["type"])
        self.assertEqual("", response.data["contact_info"])
        self.assertEqual("", response.data["notes"])
        self.assertEqual("z", response.data["alias"])
        self.assertEqual("", response.data["homepage_url"])
        self.assertEqual("", response.data["notes"])
        self.assertEqual("nexB", response.data["dataspace"])
        self.assertEqual(26, len(response.data["created_date"]))
        self.assertEqual(26, len(response.data["last_modified_date"]))
        self.assertIn(
            reverse("api_v2:license-detail", args=[self.license.uuid]), response.data["licenses"][0]
        )
        self.assertIn(
            reverse("api_v2:component-detail", args=[self.component.uuid]),
            response.data["components"][0],
        )
        self.assertEqual(self.owner1.urn, response.data["urn"])
        self.assertEqual(3, len(response.data["external_references"]))
        external_references_fields = [
            "api_url",
            "uuid",
            "content_type",
            "content_object",
            "content_object_display_name",
            "external_source",
            "external_id",
            "external_url",
            "created_date",
            "dataspace",
            "last_modified_date",
        ]
        self.assertEqual(
            sorted(external_references_fields),
            sorted(response.data["external_references"][0].keys()),
        )

    def test_api_owner_endpoint_create(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.post(self.owner_list_url, data={"name": "NewOwner"})
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        owner = Owner.objects.get(name="NewOwner")
        self.assertFalse(History.objects.get_for_object(owner).exists())
        self.assertEqual(self.super_user, owner.created_by)
        self.assertTrue(owner.created_date)

        self.assertEqual('Added Owner: "NewOwner"', mail.outbox[0].subject)
        body = mail.outbox[0].body
        self.assertIn('Owner "NewOwner" in dataspace "nexB" added by', body)
        self.assertIn(owner.get_admin_url(), body)

        response = self.client.post(self.owner_list_url, data={"name": "NewOwner"})
        self.assertContains(
            response,
            "duplicate key value violates unique constraint",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def test_api_owner_endpoint_create_update_validate_case_insensitive_uniqueness(self):
        client = APIClient()
        client.login(username="super_user", password="secret")

        data = {"name": self.owner1.name.upper()}
        response = client.post(self.owner_list_url, data=data, format="json")
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {
            "name": [
                ErrorDetail(
                    string="The application object that you are creating already "
                    'exists as "Owner1". Note that a different case in the '
                    "object name is not sufficient to make it unique.",
                    code="invalid",
                )
            ]
        }
        self.assertEqual(expected, response.data)

        put_data = {"name": self.owner1.name.upper()}
        response = client.put(self.owner1_detail_url, data=put_data, format="json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.owner1.refresh_from_db()
        self.assertEqual(data["name"], self.owner1.name)

    def test_api_owner_endpoint_update_put(self):
        self.client.login(username="super_user", password="secret")

        put_data = json.dumps({"name": "Updated Name", "alias": "New Alias"})
        response = self.client.put(
            self.owner1_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        history = History.objects.get_for_object(self.owner1, action_flag=History.CHANGE).get()
        self.assertEqual("Changed name and alias.", history.get_change_message())

        self.client.put(self.owner1_detail_url, data=put_data, content_type="application/json")
        history = History.objects.get_for_object(self.owner1, action_flag=History.CHANGE).latest(
            "id"
        )
        self.assertEqual("No fields changed.", history.change_message)

        self.assertEqual('Updated Owner: "Updated Name"', mail.outbox[0].subject)
        body = mail.outbox[0].body
        self.assertIn('Owner "Updated Name" in dataspace "nexB" updated by', body)
        self.assertIn(self.owner1.get_admin_url(), body)
        self.assertIn("Changed name and alias.", body)
        self.assertIn('Changes details for Owner "Updated Name"', body)
        self.assertIn("Old value: Owner1", body)
        self.assertIn("New value: Updated Name", body)

    def test_api_owner_endpoint_apply_tabs_permission(self):
        expected = [
            "api_url",
            "absolute_url",
            "uuid",
            "name",
            "homepage_url",
            "contact_info",
            "notes",
            "alias",
            "type",
            "licenses",
            "components",
            "external_references",
            "urn",
            "created_date",
            "last_modified_date",
            "dataspace",
        ]

        self.assertFalse(self.dataspace.tab_permissions_enabled)
        self.client.login(username=self.base_user.username, password="secret")
        response_json = self.client.get(self.owner1_detail_url).json()
        self.assertEqual(expected, list(response_json.keys()))

        DataspaceConfiguration.objects.create(
            dataspace=self.dataspace, tab_permissions={"Group1": {"owner": ["licenses"]}}
        )
        self.assertTrue(self.dataspace.tab_permissions_enabled)
        self.client.login(username=self.base_user.username, password="secret")
        response_json = self.client.get(self.owner1_detail_url).json()
        self.assertEqual(
            ["api_url", "absolute_url", "uuid", "dataspace"], list(response_json.keys())
        )

        self.base_user.groups.add(Group.objects.create(name="Group1"))
        self.client.login(username=self.base_user.username, password="secret")
        response_json = self.client.get(self.owner1_detail_url).json()
        self.assertEqual(
            ["api_url", "absolute_url", "uuid", "licenses", "dataspace"], list(response_json.keys())
        )

        self.client.login(username=self.super_user.username, password="secret")
        response_json = self.client.get(self.owner1_detail_url).json()
        self.assertEqual(expected, list(response_json.keys()))
