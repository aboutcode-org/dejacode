#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json

from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from rest_framework import status
from rest_framework.exceptions import ErrorDetail

from dje.models import Dataspace
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.models import History
from dje.tests import MaxQueryMixin
from dje.tests import create_admin
from dje.tests import create_superuser
from dje.tests import create_user
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
from policy.models import UsagePolicy


@override_settings(ANONYMOUS_USERS_DATASPACE=None)
class LicenseAnnotationAPITestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

        self.base_user = create_user("base_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)
        self.super_user = create_superuser("super_user", self.dataspace)

        self.root_api_url = reverse("api_v2:api-root")
        self.annotation_list_url = reverse("api_v2:licenseannotation-list")

        self.owner = Owner.objects.create(name="Owner", dataspace=self.dataspace)
        self.license1 = License.objects.create(
            key="license1",
            name="License1",
            short_name="License1",
            dataspace=self.dataspace,
            owner=self.owner,
        )
        self.license_tag1 = LicenseTag.objects.create(
            label="Tag 1", text="Text for tag1", dataspace=self.dataspace
        )
        self.license_assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.dataspace,
        )

        self.annotation1 = LicenseAnnotation.objects.create(
            license=self.license1,
            assigned_tag=self.license_assigned_tag1,
            range_start_offset="1",
            range_end_offset="2",
            text="Text.",
            dataspace=self.license1.dataspace,
        )
        self.annotation1_detail_url = reverse(
            "api_v2:licenseannotation-detail", args=[self.annotation1.id]
        )

        self.base_post_data = {
            "text": "Some comments",
            "tags": [self.license_tag1.label],
            "ranges": [{"start": "/pre", "startOffset": 244, "end": "/pre", "endOffset": 265}],
            "quote": "Permission is granted",
            "license": self.license1.id,
        }

    def test_api_licenseannotation_endpoint_not_list_in_api_root(self):
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.root_api_url + "?format=api")
        self.assertNotContains(response, "annotation")
        self.assertContains(response, "license")

    def test_api_licenseannotation_endpoint_permission(self):
        json_data = json.dumps(self.base_post_data)
        # Unauthorized if the user is not logged in Django
        response = self.client.get(self.annotation_list_url)
        self.assertEqual(403, response.status_code)
        # Unless ANONYMOUS_USERS_DATASPACE is enabled
        with override_settings(ANONYMOUS_USERS_DATASPACE=self.dataspace):
            response = self.client.get(self.annotation_list_url)
            self.assertEqual(200, response.status_code)

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.get(self.annotation_list_url)
        # Annotations are read-only for non-administrator users
        self.assertEqual(200, response.status_code)
        response = self.client.post(self.annotation_list_url)
        self.assertEqual(403, response.status_code)
        response = self.client.put(self.annotation_list_url)
        self.assertEqual(403, response.status_code)
        response = self.client.patch(self.annotation_list_url)
        self.assertEqual(403, response.status_code)
        response = self.client.delete(self.annotation_list_url)
        self.assertEqual(403, response.status_code)

        # Not the proper DjangoModelPermissions as admin user
        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.get(self.annotation_list_url)
        self.assertEqual(200, response.status_code)
        response = self.client.post(self.annotation_list_url, json_data, "application/json")
        self.assertEqual(403, response.status_code)
        response = self.client.put(self.annotation1_detail_url, json_data, "application/json")
        self.assertEqual(403, response.status_code)
        response = self.client.patch(self.annotation1_detail_url, json_data, "application/json")
        self.assertEqual(403, response.status_code)
        response = self.client.delete(self.annotation1_detail_url)
        self.assertEqual(403, response.status_code)

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.annotation_list_url)
        self.assertEqual(200, response.status_code)
        response = self.client.post(self.annotation_list_url, json_data, "application/json")
        self.assertEqual(201, response.status_code)
        response = self.client.put(self.annotation1_detail_url, json_data, "application/json")
        self.assertEqual(200, response.status_code)
        response = self.client.patch(self.annotation1_detail_url, json_data, "application/json")
        self.assertEqual(200, response.status_code)
        response = self.client.delete(self.annotation1_detail_url)
        self.assertEqual(204, response.status_code)

    def test_api_licenseannotation_get(self):
        annotations_count = LicenseAnnotation.objects.count()
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.annotation_list_url)

        self.assertEqual(200, response.status_code)
        self.assertEqual(annotations_count, response.data["count"])
        expected = {
            "api_url": "http://testserver/api/v2/license_annotations/{}/".format(
                self.annotation1.id
            ),
            "id": self.annotation1.id,
            "text": self.annotation1.text,
            "quote": "",
            "ranges": [
                {
                    "start": "/pre",
                    "end": "/pre",
                    "startOffset": 1,
                    "endOffset": 2,
                }
            ],
            "tags": ["Tag 1"],
            "dataspace": "nexB",
        }
        self.assertEqual([expected], response.data["rows"])

        # GET request on a specific Annotation given the id
        response = self.client.get(self.annotation1_detail_url)
        self.assertEqual(dict(expected), response.data)

    def test_api_licenseannotation_post(self):
        annotations_count = LicenseAnnotation.objects.count()
        # Login and send a POST request to create an annotation
        self.client.login(username=self.super_user.username, password="secret")

        response = self.client.post(
            self.annotation_list_url, json.dumps(self.base_post_data), "application/json"
        )

        # Making sure the data is added in the Database
        self.assertEqual(annotations_count + 1, LicenseAnnotation.objects.count())
        new_annotation = LicenseAnnotation.objects.latest("id")
        self.assertEqual(self.base_post_data["text"], new_annotation.text)
        self.assertEqual(self.base_post_data["quote"], new_annotation.quote)
        self.assertEqual(self.base_post_data["license"], new_annotation.license_id)
        self.assertEqual(244, new_annotation.range_start_offset)
        self.assertEqual(265, new_annotation.range_end_offset)
        self.assertEqual(self.license_assigned_tag1, new_annotation.assigned_tag)

        # Making sure the History entry on the License was created
        history = History.objects.get_for_object(self.license1, action_flag=History.CHANGE).get()
        self.assertEqual(
            'Added a license annotation for tag: "Tag 1: True".', history.get_change_message()
        )

        # Making sure the response return a json of the added object
        self.assertEqual(201, response.status_code)
        self.assertEqual(response.data["text"], "Some comments")
        self.assertEqual(response.data["quote"], "Permission is granted")

    def test_api_licenseannotation_put(self):
        data = {
            "text": "New text",
            "tags": [],
            "ranges": [
                {
                    "start": "/pre",
                    "startOffset": 244,
                    "end": "/pre",
                    "endOffset": 265,
                }
            ],
            "quote": "Permission is granted",
            "license": self.license1.id,
        }

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.put(
            self.annotation1_detail_url, json.dumps(data), "application/json"
        )
        self.assertEqual(200, response.status_code)

        # Let's see if the object was properly updated
        self.annotation1.refresh_from_db()
        self.assertEqual("New text", self.annotation1.text)
        self.assertEqual("Permission is granted", self.annotation1.quote)
        self.assertEqual(244, self.annotation1.range_start_offset)

        history = History.objects.get_for_object(self.license1, action_flag=History.CHANGE).get()
        self.assertEqual(
            'Changed a license annotation for tag: "Tag 1: True".', history.get_change_message()
        )

    def test_api_licenseannotation_delete(self):
        annotations_count = LicenseAnnotation.objects.count()
        self.client.login(username=self.super_user.username, password="secret")

        self.client.delete(self.annotation1_detail_url)
        self.assertEqual(annotations_count - 1, LicenseAnnotation.objects.count())

        history = History.objects.get_for_object(self.license1, action_flag=History.CHANGE).get()
        self.assertEqual(
            'Deleted a license annotation for tag: "Tag 1: True".', history.get_change_message()
        )

    def test_api_licenseannotation_get_filters(self):
        self.client.login(username=self.super_user.username, password="secret")

        license2 = License.objects.create(
            key="l2", name="L2", short_name="L2", owner=self.owner, dataspace=self.dataspace
        )

        annotation2 = LicenseAnnotation.objects.create(
            license=license2,
            range_start_offset=3,
            range_end_offset=4,
            dataspace=license2.dataspace,
        )

        response = self.client.get(self.annotation_list_url)
        self.assertEqual(2, response.data["count"])

        data = {"license": "mit"}
        response = self.client.get(self.annotation_list_url, data=data)
        expected = {"license": [ErrorDetail(string="Enter a number.", code="invalid")]}
        self.assertEqual(expected, response.data)

        data = {"license": annotation2.license_id}
        response = self.client.get(self.annotation_list_url, data=data)
        self.assertEqual(1, response.data["count"])
        self.assertEqual(annotation2.id, response.data["rows"][0]["id"])


@override_settings(
    EMAIL_HOST_USER="user",
    EMAIL_HOST_PASSWORD="password",
    EMAIL_HOST="localhost",
    EMAIL_PORT=25,
    DEFAULT_FROM_EMAIL="webmaster@localhost",
    SITE_URL="server.dejacode.nexb",
)
class LicenseAPITestCase(MaxQueryMixin, TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

        self.base_user = create_user("base_user", self.dataspace)
        self.super_user = create_superuser(
            "super_user", self.dataspace, data_email_notification=True
        )

        self.license_list_url = reverse("api_v2:license-list")

        self.owner1 = Owner.objects.create(name="Owner", dataspace=self.dataspace)

        self.category1 = LicenseCategory.objects.create(
            label="1: Category 1",
            text="Some text",
            dataspace=self.dataspace,
        )
        self.license_style1 = LicenseStyle.objects.create(name="style1", dataspace=self.dataspace)
        self.license_status1 = LicenseStatus.objects.create(
            code="status1", text="Approved", dataspace=self.dataspace
        )

        self.license1 = License.objects.create(
            key="l1",
            name="L1",
            short_name="L1",
            owner=self.owner1,
            dataspace=self.dataspace,
            is_active=True,
        )
        self.license1_detail_url = reverse("api_v2:license-detail", args=[self.license1.uuid])

        self.license2 = License.objects.create(
            key="l2", name="L2", short_name="L2", owner=self.owner1, dataspace=self.dataspace
        )
        self.license2_detail_url = reverse("api_v2:license-detail", args=[self.license2.uuid])

        self.license_tag1 = LicenseTag.objects.create(
            label="Tag 1", text="Text for tag1", dataspace=self.dataspace
        )
        self.assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.dataspace,
        )

        self.license_tag2 = LicenseTag.objects.create(
            label="Tag 2", text="Text for tag2", dataspace=self.dataspace
        )
        self.assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag2,
            value=False,
            dataspace=self.dataspace,
        )

        self.license_profile1 = LicenseProfile.objects.create(
            name="1: LicenseProfile1", dataspace=self.dataspace
        )
        LicenseProfileAssignedTag.objects.create(
            license_profile=self.license_profile1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.dataspace,
        )
        LicenseProfileAssignedTag.objects.create(
            license_profile=self.license_profile1,
            license_tag=self.license_tag2,
            value=False,
            dataspace=self.dataspace,
        )

        ext_source1 = ExternalSource.objects.create(label="GitHub", dataspace=self.dataspace)

        ExternalReference.objects.create_for_content_object(self.license1, ext_source1, "REF1")
        ExternalReference.objects.create_for_content_object(self.license1, ext_source1, "REF2")
        ExternalReference.objects.create_for_content_object(self.license1, ext_source1, "REF3")

    def test_api_license_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")
        # with self.assertNumQueries(9):
        response = self.client.get(self.license_list_url)

        self.assertContains(response, '"count":2,')
        self.assertContains(response, self.license1_detail_url)
        self.assertContains(response, self.license2_detail_url)
        self.assertEqual(2, response.data["count"])

    def test_api_license_list_endpoint_search(self):
        self.client.login(username="super_user", password="secret")
        data = {"search": self.license1.name}
        response = self.client.get(self.license_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.license1_detail_url)
        self.assertNotContains(response, self.license2_detail_url)

        # Search is case in-sensitive
        data = {"search": self.license1.name.upper()}
        response = self.client.get(self.license_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.license1_detail_url)
        self.assertNotContains(response, self.license2_detail_url)

    def test_api_license_list_endpoint_filters(self):
        self.client.login(username="super_user", password="secret")
        data = {"is_active": True}
        response = self.client.get(self.license_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.license1_detail_url)
        self.assertNotContains(response, self.license2_detail_url)

    def test_api_license_list_endpoint_num_queries(self):
        self.client.login(username="super_user", password="secret")
        for index in range(5):
            License.objects.create(
                key=f"license-{index}",
                name=f"license-{index}",
                short_name=f"license-{index}",
                owner=self.owner1,
                dataspace=self.dataspace,
            )
        with self.assertMaxQueries(12):
            response = self.client.get(self.license_list_url)
        self.assertEqual(7, response.data["count"])

    def test_api_license_list_endpoint_multiple_char_filters(self):
        self.client.login(username="super_user", password="secret")
        license3 = License.objects.create(
            key="l3", name="L3", short_name="L3", owner=self.owner1, dataspace=self.dataspace
        )
        license3_detail_url = reverse("api_v2:license-detail", args=[license3.uuid])

        filters = "?key={}&key={}".format(self.license1.key, license3.key)
        response = self.client.get(self.license_list_url + filters)
        self.assertEqual(2, response.data["count"])
        self.assertContains(response, self.license1_detail_url)
        self.assertNotContains(response, self.license2_detail_url)
        self.assertContains(response, license3_detail_url)

    def test_api_license_detail_endpoint(self):
        self.client.login(username="super_user", password="secret")
        self.license1.spdx_license_key = "Apache-2.0"
        self.license1.save()

        # with self.assertNumQueries(8):
        response = self.client.get(self.license1_detail_url)
        self.assertContains(response, self.license1_detail_url)
        self.assertEqual(str(self.license1), response.data["display_name"])
        self.assertIn(self.license1_detail_url, response.data["api_url"])
        self.assertEqual(str(self.license1.uuid), response.data["uuid"])
        self.assertEqual(self.license1.name, response.data["name"])
        self.assertEqual(self.license1.key, response.data["key"])
        self.assertEqual(self.license1.short_name, response.data["short_name"])
        expected_tags = [
            dict([("label", "Tag 2"), ("value", False)]),
            dict([("label", "Tag 1"), ("value", True)]),
        ]
        self.assertEqual(expected_tags, expected_tags)
        self.assertEqual(3, len(response.data["external_references"]))
        self.assertEqual(self.license1.urn, response.data["urn"])
        self.assertEqual(self.license1.spdx_license_key, response.data["spdx_license_key"])
        self.assertEqual(self.license1.spdx_url, response.data["spdx_url"])

        self.assertEqual(self.owner1.name, response.data["owner_abcd"]["name"])
        self.assertEqual(str(self.owner1.uuid), response.data["owner_abcd"]["uuid"])

        self.license1.spdx_license_key = "LicenseRef-Apache-2.0"
        self.license1.save()
        response = self.client.get(self.license1_detail_url)
        self.assertEqual(self.license1.spdx_license_key, response.data["spdx_license_key"])
        self.assertIsNone(response.data["spdx_url"])

    def test_api_license_endpoint_create_minimal(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.post(self.license_list_url, {})
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {
            "owner": ["This field is required."],
            "short_name": ["This field is required."],
            "name": ["This field is required."],
            "key": ["This field is required."],
        }
        self.assertEqual(expected, response.data)

        data = {
            "owner": self.owner1,
            "short_name": "Short Name",
            "name": "Name",
            "key": "Wrong Slug",
        }
        response = self.client.post(self.license_list_url, data=data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {
            "key": [
                "Enter a valid 'slug' consisting of letters, numbers, underscores, dots or hyphens."
            ],
        }
        self.assertEqual(expected, response.data)

        data["key"] = "proper.key-2.0"
        response = self.client.post(self.license_list_url, data=data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

    def test_api_license_endpoint_create_full_text_is_stripped(self):
        self.client.login(username="super_user", password="secret")
        data = {
            "owner": self.owner1,
            "short_name": "Short Name",
            "name": "Name",
            "key": "key",
            "full_text": "   Full Text     ",
        }

        response = self.client.post(self.license_list_url, data=data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        license = License.objects.latest("id")
        self.assertEqual(data["full_text"].strip(), license.full_text)

    def test_api_license_endpoint_create_spdx_license_key(self):
        self.client.login(username="super_user", password="secret")

        data = {
            "owner": self.owner1,
            "short_name": "Short Name",
            "name": "Name",
            "key": "key",
            "spdx_license_key": "spdx_key_with_underscore",
        }

        response = self.client.post(self.license_list_url, data=data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {
            "spdx_license_key": [
                "Enter a valid value consisting of letters, numbers, dots or hyphens."
            ]
        }
        self.assertEqual(expected, response.data)

        data["spdx_license_key"] = "key"
        data["is_active"] = False
        response = self.client.post(self.license_list_url, data=data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"non_field_errors": ["A deprecated license must not have an SPDX license key."]}
        self.assertEqual(expected, response.data)

        data["is_active"] = True
        response = self.client.post(self.license_list_url, data=data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        response = self.client.post(self.license_list_url, data=data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        error_msg = "duplicate key value violates unique constraint"
        self.assertIn(error_msg, response.data[0])

    def test_api_license_endpoint_create_full(self):
        self.client.login(username="super_user", password="secret")
        policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            dataspace=self.dataspace,
        )
        data = {
            "key": "beerware",
            "name": "Beer-Ware License",
            "short_name": "Beer-Ware License",
            "reviewed": True,
            "owner": self.owner1.name,
            "keywords": "The Beer-Ware License (revision 42), The Beer-Ware License",
            "homepage_url": "http://people.freebsd.org/~phk/",
            "full_text": "/*\n * ---------------------------------------------------"
            '-------------------------\n * "THE BEER-WARE LICENSE" (Revision 42):\n'
            " * <phk@FreeBSD.ORG> wrote this file. As long as you retain this notice"
            " you\n * can do whatever you want with this stuff. If we meet some day,"
            " and you think\n * this stuff is worth it, you can buy me a beer in return"
            " Poul-Henning Kamp\n * ---------------------------------------------------"
            "-------------------------\n */",
            "standard_notice": "",
            "publication_year": "",
            "category": self.category1.label,
            "license_style": self.license_style1.name,
            "license_profile": "",
            "license_status": self.license_status1.code,
            "is_active": True,
            "usage_policy": policy.label,
            "is_component_license": False,
            "is_exception": False,
            "curation_level": 45,
            "guidance": "",
            "guidance_url": "",
            "reference_notes": "",
            "special_obligations": "",
            "admin_notes": "",
            "faq_url": "",
            "osi_url": "",
            "text_urls": "http://people.freebsd.org/~phk/\r\n"
            "https://fedoraproject.org/wiki/Licensing/Beerware",
            "other_urls": "",
            "spdx_license_key": "Beerware",
        }

        response = self.client.post(self.license_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        license = License.objects.latest("id")
        self.assertFalse(History.objects.get_for_object(license).exists())
        self.assertEqual(self.super_user, license.created_by)
        self.assertTrue(license.created_date)

        self.assertEqual(0, license.licenseassignedtag_set.count())

        for field_name, value in data.items():
            if field_name in ["last_modified_date", "license_profile"]:
                continue
            if field_name == "license_status":
                self.assertEqual(self.license_status1, getattr(license, field_name))
                continue
            self.assertEqual(str(value), str(getattr(license, field_name)), msg=field_name)

        expected = 'Added License: "Beer-Ware License (beerware)"'
        self.assertEqual(expected, mail.outbox[0].subject)
        body = mail.outbox[0].body
        self.assertIn(license.get_admin_url(), body)

    def test_api_license_endpoint_assigned_tags(self):
        self.client.login(username="super_user", password="secret")

        data = {
            "owner": self.owner1.name,
            "short_name": "Short Name",
            "name": "Name",
            "key": "proper.key-2.0",
            "tags": [
                {
                    "label": "Non existing",
                    "value": False,
                },
            ],
        }

        response = self.client.post(
            self.license_list_url, data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"tags": [{"label": ["Object with label=Non existing does not exist."]}]}
        self.assertEqual(expected, response.data)

        data["tags"][0]["label"] = self.license_tag1.label
        response = self.client.post(
            self.license_list_url, data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        created_license = License.objects.latest("id")
        self.assertEqual(1, created_license.licenseassignedtag_set.count())
        assigned_tag = created_license.licenseassignedtag_set.latest("id")
        self.assertEqual(False, assigned_tag.value)
        self.assertEqual(self.license_tag1, assigned_tag.license_tag)

        data["tags"][0]["value"] = True
        created_license_detail_url = reverse("api_v2:license-detail", args=[created_license.uuid])
        response = self.client.put(
            created_license_detail_url, data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        assigned_tag.refresh_from_db()
        self.assertTrue(assigned_tag.value)

        data["tags"][0]["value"] = None
        response = self.client.patch(
            created_license_detail_url, data=json.dumps(data), content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        assigned_tag.refresh_from_db()
        self.assertIsNone(assigned_tag.value)

    def test_api_license_endpoint_update_patch(self):
        self.client.login(username="super_user", password="secret")

        patch_data = json.dumps({"name": "Updated Name"})
        response = self.client.patch(
            self.license1_detail_url, data=patch_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        history = History.objects.get_for_object(self.license1, action_flag=History.CHANGE).latest(
            "id"
        )
        self.assertEqual("Changed name.", history.get_change_message())

        self.assertEqual('Updated License: "L1 (l1)"', mail.outbox[0].subject)
        body = mail.outbox[0].body
        self.assertIn('Changes details for License "L1 (l1)"', body)
        self.assertIn(self.license1.get_admin_url(), body)
        self.assertIn("Changed name.", body)
        self.assertIn("Old value: L1", body)
        self.assertIn("New value: Updated Name", body)

    def test_api_license_endpoint_attribution_required(self):
        self.client.login(username="super_user", password="secret")

        self.assertFalse(self.license1.attribution_required)
        response = self.client.get(self.license1_detail_url)
        self.assertFalse(response.data["attribution_required"])

        self.assigned_tag1.license_tag.attribution_required = True
        self.assigned_tag1.license_tag.save()
        self.assigned_tag1.value = False
        self.assigned_tag1.save()
        response = self.client.get(self.license1_detail_url)
        self.assertFalse(response.data["attribution_required"])

        self.assigned_tag1.value = True
        self.assigned_tag1.save()
        response = self.client.get(self.license1_detail_url)
        self.assertTrue(response.data["attribution_required"])
