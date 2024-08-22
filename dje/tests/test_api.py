#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import uuid

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from rest_framework import status

from dje.api import REFERENCE_VAR
from dje.api import ExternalReferenceViewSet
from dje.api_custom import TabPermission
from dje.copier import copy_object
from dje.models import Dataspace
from dje.models import DataspaceConfiguration
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.tests import MaxQueryMixin
from dje.tests import add_perm
from dje.tests import create_admin
from dje.tests import create_superuser
from dje.tests import create_user

Owner = apps.get_model("organization", "Owner")
Component = apps.get_model("component_catalog", "Component")


class RootAPITestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="alternate")

        self.base_user = create_user("base_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)
        self.super_user = create_superuser("super_user", self.dataspace)

        self.root_api_url = reverse("api_v2:api-root")
        self.docs_index_url = reverse("api-docs:docs-index")

    def test_api_urls_access(self):
        response = self.client.get(self.root_api_url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        response = self.client.get(self.docs_index_url)
        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.root_api_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.get(self.docs_index_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.root_api_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.get(self.docs_index_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.root_api_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.get(self.docs_index_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)

    def test_api_permissions_on_allowed_methods(self):
        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        owner_detail_url = reverse("api_v2:owner-detail", args=[owner.uuid])
        owner_list_url = reverse("api_v2:owner-list")
        put_data = json.dumps({"name": "Updated Name"})
        patch_data = json.dumps({"homepage_url": "http://url.com"})

        self.client.logout()
        response = self.client.get(self.root_api_url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        response = self.client.get(owner_list_url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        response = self.client.get(owner_detail_url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        response = self.client.head(owner_list_url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        response = self.client.options(owner_list_url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        response = self.client.post(owner_list_url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        response = self.client.put(owner_detail_url, data=put_data, content_type="application/json")
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        response = self.client.patch(
            owner_detail_url, data=patch_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.root_api_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.get(owner_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.get(owner_detail_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.head(owner_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.options(owner_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.post(owner_list_url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        response = self.client.put(owner_detail_url, data=put_data, content_type="application/json")
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        response = self.client.patch(
            owner_detail_url, data=patch_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.root_api_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.get(owner_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.get(owner_detail_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.head(owner_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.options(owner_detail_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.options(owner_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        response = self.client.post(owner_list_url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        add_perm(self.admin_user, "add_owner")
        response = self.client.post(owner_list_url, data={"name": "Owner2"})
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        response = self.client.put(owner_detail_url, data=put_data, content_type="application/json")
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        response = self.client.patch(
            owner_detail_url, data=patch_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        add_perm(self.admin_user, "change_owner")
        response = self.client.put(owner_detail_url, data=put_data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.patch(
            owner_detail_url, data=patch_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.root_api_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.get(owner_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.get(owner_detail_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.head(owner_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.options(owner_detail_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.options(owner_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.post(owner_list_url, data={"name": "Owner3"})
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        response = self.client.put(owner_detail_url, data=put_data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        response = self.client.patch(
            owner_detail_url, data=patch_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

    def test_api_method_sanity_check_permissions(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.generic("GET", self.root_api_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        response = self.client.generic("BAD_METHOD", self.root_api_url)
        self.assertEqual(status.HTTP_405_METHOD_NOT_ALLOWED, response.status_code)

        owner_list_url = reverse("api_v2:owner-list")
        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        owner_detail_url = reverse("api_v2:owner-detail", args=[owner.uuid])

        response = self.client.generic("BAD_METHOD", owner_list_url)
        self.assertEqual(status.HTTP_405_METHOD_NOT_ALLOWED, response.status_code)

        response = self.client.generic("BAD_METHOD", owner_detail_url)
        self.assertEqual(status.HTTP_405_METHOD_NOT_ALLOWED, response.status_code)

    def test_root_api_available_endpoints(self):
        self.client.login(username="super_user", password="secret")

        endpoint_urls = [
            "api_v2:owner-list",
            "api_v2:license-list",
            "api_v2:component-list",
            "api_v2:package-list",
            "api_v2:request-list",
            "api_v2:product-list",
            "api_v2:requesttemplate-list",
            "api_v2:report-list",
            "api_v2:externalreference-list",
        ]

        response = self.client.get(self.root_api_url)
        for url_name in endpoint_urls:
            self.assertContains(response, reverse(url_name))

        response = self.client.get(self.root_api_url + "?format=json")
        for url_name in endpoint_urls:
            self.assertContains(response, reverse(url_name))

    def test_api_owner_detail_endpoint_cross_dataspace(self):
        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        owner_detail_url = reverse("api_v2:owner-detail", args=[owner.uuid])
        alternate_owner = Owner.objects.create(name="Owner", dataspace=self.alternate_dataspace)
        alternate_owner_detail_url = reverse("api_v2:owner-detail", args=[alternate_owner.uuid])

        self.client.login(username="super_user", password="secret")
        response = self.client.get(owner_detail_url)
        self.assertEqual(200, response.status_code)
        response = self.client.get(alternate_owner_detail_url)
        self.assertEqual(404, response.status_code)

    @override_settings(REFERENCE_DATASPACE="alternate")
    def test_api_owner_endpoint_allow_reference_access(self):
        alternate_owner = Owner.objects.create(name="Alternate", dataspace=self.alternate_dataspace)
        alternate_owner_detail_url = reverse("api_v2:owner-detail", args=[alternate_owner.uuid])
        alternate_owner2 = Owner.objects.create(name="Alt2", dataspace=self.alternate_dataspace)

        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        owner_detail_url = reverse("api_v2:owner-detail", args=[owner.uuid])
        copied_owner = copy_object(alternate_owner2, self.dataspace, self.super_user)
        copied_owner.name = "Copied"
        copied_owner.save()

        another_dataspace = Dataspace.objects.create(name="Another")
        Owner.objects.create(name="Another", dataspace=another_dataspace)

        self.client.login(username="super_user", password="secret")
        owner_list_url = reverse("api_v2:owner-list")

        payload = {"format": "json"}
        response = self.client.get(owner_list_url, data=payload)
        json_content = json.loads(response.content)
        self.assertEqual(2, json_content["count"])
        self.assertEqual(copied_owner.name, json_content["results"][0]["name"])
        self.assertEqual(owner.name, json_content["results"][1]["name"])

        payload = {REFERENCE_VAR: 1, "format": "json"}
        response = self.client.get(owner_list_url, data=payload)
        json_content = json.loads(response.content)
        self.assertEqual(2, json_content["count"])
        self.assertEqual(alternate_owner2.name, json_content["results"][0]["name"])
        self.assertEqual(alternate_owner.name, json_content["results"][1]["name"])

        with override_settings(REFERENCE_DATASPACE=None):
            response = self.client.get(owner_list_url, data=payload)
        json_content = json.loads(response.content)
        self.assertEqual(2, json_content["count"])
        self.assertEqual(copied_owner.name, json_content["results"][0]["name"])
        self.assertEqual(owner.name, json_content["results"][1]["name"])

        response = self.client.get(owner_detail_url)
        self.assertEqual(200, response.status_code)
        response = self.client.get(alternate_owner_detail_url)
        self.assertEqual(404, response.status_code)

        payload = {REFERENCE_VAR: 1}
        response = self.client.get(owner_detail_url, data=payload)
        self.assertEqual(404, response.status_code)
        response = self.client.get(alternate_owner_detail_url, data=payload)
        self.assertEqual(200, response.status_code)

        with override_settings(REFERENCE_DATASPACE=None):
            response = self.client.get(alternate_owner_detail_url, data=payload)
        self.assertEqual(404, response.status_code)

        # `combine` value allows to return data from both Dataspaces
        payload = {REFERENCE_VAR: "combine", "format": "json"}
        response = self.client.get(owner_list_url, data=payload)
        json_content = json.loads(response.content)
        self.assertEqual(4, json_content["count"])
        self.assertEqual(alternate_owner2.name, json_content["results"][0]["name"])
        self.assertEqual(alternate_owner.name, json_content["results"][1]["name"])
        self.assertEqual(copied_owner.name, json_content["results"][2]["name"])
        self.assertEqual(owner.name, json_content["results"][3]["name"])

        with override_settings(REFERENCE_DATASPACE=None):
            response = self.client.get(owner_list_url, data=payload)
        json_content = json.loads(response.content)
        self.assertEqual(2, json_content["count"])
        self.assertEqual(copied_owner.name, json_content["results"][0]["name"])
        self.assertEqual(owner.name, json_content["results"][1]["name"])

        # `merge` value allows to return data from both Dataspaces without duplicate uuid.
        payload = {REFERENCE_VAR: "merge", "format": "json"}
        response = self.client.get(owner_list_url, data=payload)
        json_content = json.loads(response.content)
        self.assertEqual(3, json_content["count"])
        self.assertEqual(alternate_owner.name, json_content["results"][0]["name"])
        self.assertEqual(copied_owner.name, json_content["results"][1]["name"])
        self.assertEqual(owner.name, json_content["results"][2]["name"])

    def test_api_list_pagination_page_size(self):
        Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        Owner.objects.create(name="Owner2", dataspace=self.dataspace)
        owner_list_url = reverse("api_v2:owner-list")
        self.client.login(username="super_user", password="secret")

        payload = {"format": "json"}
        response = self.client.get(owner_list_url, data=payload)
        json_content = json.loads(response.content)
        self.assertEqual(2, json_content["count"])
        self.assertEqual(2, len(json_content["results"]))
        self.assertIsNone(json_content["next"])

        payload["page_size"] = 1
        response = self.client.get(owner_list_url, data=payload)
        json_content = json.loads(response.content)
        self.assertEqual(2, json_content["count"])
        self.assertEqual(1, len(json_content["results"]))

    def test_api_char_field_trim_whitespace(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.post(reverse("api_v2:owner-list"), data={"name": "  New Owner  "})
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        owner = Owner.objects.latest("id")
        self.assertEqual("New Owner", owner.name)

    def test_api_dataspaced_serializer_uuid_field(self):
        self.client.login(username="super_user", password="secret")
        owner_list_url = reverse("api_v2:owner-list")
        generated_uuid = uuid.uuid4()

        data = {
            "name": "Owner",
            "uuid": generated_uuid,
        }
        response = self.client.post(owner_list_url, data=data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        owner1 = Owner.objects.latest("id")
        self.assertEqual(generated_uuid, owner1.uuid)

        data = {"name": "Owner2"}
        response = self.client.post(owner_list_url, data=data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        owner2 = Owner.objects.latest("id")
        self.assertNotEqual(generated_uuid, owner2.uuid)

        data = {"uuid": "", "name": "Owner3"}
        response = self.client.post(owner_list_url, data=data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        owner3 = Owner.objects.latest("id")
        self.assertNotEqual(generated_uuid, owner3.uuid)
        self.assertNotEqual(owner2.uuid, owner3.uuid)

        # Edit
        url = reverse("api_v2:owner-detail", args=[owner3.uuid])
        patch_data = json.dumps({"uuid": str(generated_uuid)})
        response = self.client.patch(url, data=patch_data, content_type="application/json")
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertIn("duplicate key value violates unique constraint", response.data[0])

        generated_uuid = uuid.uuid4()
        patch_data = json.dumps({"uuid": str(generated_uuid)})
        response = self.client.patch(url, data=patch_data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        owner3.refresh_from_db()
        self.assertEqual(generated_uuid, owner3.uuid)

    def test_api_last_api_access_middleware(self):
        response = self.client.get(self.root_api_url)
        self.assertEqual(403, response.status_code)

        self.assertIsNone(self.super_user.last_api_access)
        self.client.login(username=self.super_user.username, password="secret")
        self.client.get(self.root_api_url)
        self.super_user.refresh_from_db()
        self.assertIsNotNone(self.super_user.last_api_access)
        last_api_access = self.super_user.last_api_access

        self.client.get(self.root_api_url)
        self.super_user.refresh_from_db()
        # Less than 1h, no update
        self.assertEqual(last_api_access, self.super_user.last_api_access)

        self.super_user.last_api_access = timezone.now() - timezone.timedelta(hours=2)
        self.super_user.save()
        self.client.get(self.root_api_url)
        self.super_user.refresh_from_db()
        self.assertNotEqual(last_api_access, self.super_user.last_api_access)

    def test_api_tab_permission(self):
        request = RequestFactory()

        self.assertFalse(self.dataspace.tab_permissions_enabled)
        request.user = self.super_user
        self.assertTrue(TabPermission().has_permission(request, None))
        request.user = self.admin_user
        self.assertTrue(TabPermission().has_permission(request, None))
        request.user = self.base_user
        self.assertTrue(TabPermission().has_permission(request, None))

        DataspaceConfiguration.objects.create(
            dataspace=self.dataspace, tab_permissions={"Enabled": True}
        )
        self.assertTrue(self.dataspace.tab_permissions_enabled)

        self.assertTrue(self.dataspace.tab_permissions_enabled)
        request.user = self.super_user
        self.assertTrue(TabPermission().has_permission(request, None))
        request.user = self.admin_user
        self.assertFalse(TabPermission().has_permission(request, None))
        request.user = self.base_user
        self.assertFalse(TabPermission().has_permission(request, None))


class ExternalReferenceAPITestCase(MaxQueryMixin, TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="alternate")

        self.base_user = create_user("base_user", self.dataspace)
        self.super_user = create_superuser("super_user", self.dataspace)

        self.external_reference_list_url = reverse("api_v2:externalreference-list")

        self.owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace, type="Person")

        self.ext_source1 = ExternalSource.objects.create(
            label="ExternalSource1", dataspace=self.dataspace
        )

        self.ext_ref1 = ExternalReference.objects.create_for_content_object(
            self.owner1, self.ext_source1, "REF1"
        )
        self.ext_ref1_detail_url = reverse(
            "api_v2:externalreference-detail", args=[self.ext_ref1.uuid]
        )
        self.ext_ref2 = ExternalReference.objects.create_for_content_object(
            self.owner1, self.ext_source1, "REF2"
        )
        self.ext_ref3 = ExternalReference.objects.create_for_content_object(
            self.owner1, self.ext_source1, "REF3"
        )

    def test_api_external_reference_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")

        with self.assertMaxQueries(9):
            response = self.client.get(self.external_reference_list_url)

        self.assertContains(response, '"count":3,')
        self.assertContains(response, self.ext_ref1_detail_url)
        self.assertEqual(3, response.data["count"])

    def test_api_external_reference_list_endpoint_search(self):
        self.client.login(username="super_user", password="secret")
        data = {"search": self.ext_ref1.external_id}
        response = self.client.get(self.external_reference_list_url, data)
        self.assertEqual(1, response.data["count"])

    def test_api_external_reference_list_endpoint_filters(self):
        self.client.login(username="super_user", password="secret")
        data = {
            "content_type": ContentType.objects.get_for_model(self.owner1).model,
            "external_source": self.ext_source1.label,
        }
        response = self.client.get(self.external_reference_list_url, data)
        self.assertEqual(3, response.data["count"])

    def test_api_external_reference_detail_endpoint(self):
        self.client.login(username="super_user", password="secret")
        with self.assertMaxQueries(8):
            response = self.client.get(self.ext_ref1_detail_url)

        self.assertContains(response, self.ext_ref1_detail_url)
        self.assertIn(self.ext_ref1_detail_url, response.data["api_url"])
        self.assertEqual(str(self.ext_ref1.uuid), response.data["uuid"])
        self.assertEqual(self.ext_source1.label, response.data["external_source"])
        self.assertIn(
            reverse("api_v2:owner-detail", args=[self.ext_ref1.content_object.uuid]),
            response.data["content_object"],
        )
        self.assertEqual(
            str(self.ext_ref1.content_object), response.data["content_object_display_name"]
        )
        self.assertEqual(self.ext_ref1.content_type.model, response.data["content_type"])
        self.assertEqual(self.ext_ref1.external_url, response.data["external_url"])
        self.assertEqual(self.ext_ref1.external_id, response.data["external_id"])
        self.assertEqual(32, len(response.data["created_date"]))
        self.assertEqual(32, len(response.data["last_modified_date"]))

    def test_api_external_reference_endpoint_create(self):
        self.client.login(username="super_user", password="secret")
        data = {
            "content_object": "",
            "external_source": "",
            "external_id": "",
            "external_url": "",
        }
        response = self.client.post(self.external_reference_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = (
            b'{"content_object":["This field may not be null."],'
            b'"external_source":["This field may not be null."]}'
        )
        self.assertEqual(expected, response.content)

        new_owner = Owner.objects.create(name="new_owner", dataspace=self.dataspace)
        owner_detail_url = reverse("api_v2:owner-detail", args=[new_owner.uuid])

        data = {
            "content_object": owner_detail_url,
            "external_source": self.ext_source1.label,
            "external_id": "dejacode",
            "external_url": "https://github.com/aboutcode-org/dejacode",
        }

        response = self.client.post(self.external_reference_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        new_ext_ref = ExternalReference.objects.latest("id")
        self.assertEqual(new_ext_ref.content_object, new_owner)
        self.assertEqual(new_ext_ref.content_type, ContentType.objects.get_for_model(new_owner))
        self.assertEqual(new_ext_ref.object_id, new_owner.id)
        self.assertEqual(new_ext_ref.dataspace, self.dataspace)
        self.assertEqual(new_ext_ref.external_url, "https://github.com/aboutcode-org/dejacode")
        self.assertEqual(new_ext_ref.external_id, "dejacode")

        # Non-supported object_type
        data["content_object"] = self.ext_ref1_detail_url
        response = self.client.post(self.external_reference_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"content_object": ["Invalid Object type."]}
        self.assertEqual(expected, response.data)

        # Dataspace scoping
        alternate_source = ExternalSource.objects.create(
            label="AlternateSource", dataspace=self.alternate_dataspace
        )
        alternate_owner = Owner.objects.create(name="Owner", dataspace=self.alternate_dataspace)

        data["external_source"] = alternate_source
        data["content_object"] = reverse("api_v2:owner-detail", args=[alternate_owner.uuid])

        response = self.client.post(self.external_reference_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {
            "external_source": ["Object with label=AlternateSource does not exist."],
            "content_object": ["Invalid hyperlink - Object does not exist."],
        }
        self.assertEqual(expected, response.data)

    def test_api_external_reference_endpoint_update_put(self):
        self.client.login(username="super_user", password="secret")

        component = Component.objects.create(name="c1", dataspace=self.dataspace)
        external_source2 = ExternalSource.objects.create(label="Source2", dataspace=self.dataspace)

        put_data = json.dumps(
            {
                "content_object": reverse("api_v2:component-detail", args=[component.uuid]),
                "external_source": external_source2.label,
                "external_id": "new_id",
                "external_url": "https://some.url",
            }
        )
        response = self.client.put(
            self.ext_ref1_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        self.ext_ref1.refresh_from_db()
        self.assertEqual(self.ext_ref1.content_object, component)
        self.assertEqual(self.ext_ref1.content_type, ContentType.objects.get_for_model(component))
        self.assertEqual(self.ext_ref1.object_id, component.id)
        self.assertEqual(self.ext_ref1.external_url, "https://some.url")
        self.assertEqual(self.ext_ref1.external_id, "new_id")

    def test_api_external_reference_serializer_on_content_object_recreate(self):
        self.client.login(username="super_user", password="secret")
        owner1_detail_url = reverse("api_v2:owner-detail", args=[self.owner1.uuid])
        response = self.client.get(owner1_detail_url)
        external_references = response.data["external_references"]
        self.assertEqual(3, len(external_references))

        # Reusing the data from the content_object endpoint to re-create the external reference
        external_reference1_data = external_references[0]
        ExternalReference.objects.all().delete()

        response = self.client.post(
            self.external_reference_list_url,
            data=json.dumps(external_reference1_data),
            content_type="application/json",
        )
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        del external_reference1_data["created_date"]
        del response.data["created_date"]
        del external_reference1_data["last_modified_date"]
        del response.data["last_modified_date"]
        self.assertEqual(external_reference1_data, response.data)

    def test_api_external_reference_endpoint_tab_permission(self):
        self.assertEqual((TabPermission,), ExternalReferenceViewSet.extra_permissions)

        self.assertFalse(self.dataspace.tab_permissions_enabled)
        response = self.client.get(self.external_reference_list_url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.external_reference_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.external_reference_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.external_reference_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        DataspaceConfiguration.objects.create(
            dataspace=self.dataspace, tab_permissions={"Enabled": True}
        )
        self.assertTrue(self.dataspace.tab_permissions_enabled)
        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.external_reference_list_url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.external_reference_list_url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.external_reference_list_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
