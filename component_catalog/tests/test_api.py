#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import datetime
import json
import uuid
from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from rest_framework import status
from rest_framework.exceptions import ErrorDetail
from rest_framework.test import APIClient

from component_catalog.api import PackageAPIFilterSet
from component_catalog.fuzzy import FuzzyPackageNameSearch
from component_catalog.models import Component
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import ComponentKeyword
from component_catalog.models import ComponentStatus
from component_catalog.models import ComponentType
from component_catalog.models import Package
from component_catalog.models import Subcomponent
from dje.models import Dataspace
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.models import History
from dje.tests import MaxQueryMixin
from dje.tests import add_perm
from dje.tests import add_perms
from dje.tests import create_admin
from dje.tests import create_superuser
from dje.tests import create_user
from license_library.models import License
from license_library.models import LicenseCategory
from license_library.models import LicenseChoice
from organization.models import Owner
from policy.models import UsagePolicy


@override_settings(
    EMAIL_HOST_USER="user",
    EMAIL_HOST_PASSWORD="password",
    EMAIL_HOST="localhost",
    EMAIL_PORT=25,
    DEFAULT_FROM_EMAIL="webmaster@localhost",
)
class ComponentAPITestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="Alternate")

        self.base_user = create_user("base_user", self.dataspace)
        self.super_user = create_superuser(
            "super_user", self.dataspace, data_email_notification=True
        )
        self.admin_user = create_admin("admin_user", self.dataspace)
        self.alternate_super_user = create_superuser("alternate_user", self.alternate_dataspace)

        self.type1 = ComponentType.objects.create(label="Type1", dataspace=self.dataspace)
        self.status1 = ComponentStatus.objects.create(
            label="Status1", default_on_addition=True, dataspace=self.dataspace
        )

        self.component_list_url = reverse("api_v2:component-list")

        self.component1 = Component.objects.create(
            name="c1", dataspace=self.dataspace, legal_reviewed=True
        )
        self.component1_detail_url = reverse("api_v2:component-detail", args=[self.component1.uuid])

        self.component2 = Component.objects.create(name="c2", dataspace=self.dataspace)
        self.component2_detail_url = reverse("api_v2:component-detail", args=[self.component2.uuid])

        self.component3 = Component.objects.create(name="c3", dataspace=self.dataspace)
        self.component3_detail_url = reverse("api_v2:component-detail", args=[self.component3.uuid])

        ext_source1 = ExternalSource.objects.create(label="GitHub", dataspace=self.dataspace)

        ExternalReference.objects.create_for_content_object(self.component1, ext_source1, "REF1")
        ExternalReference.objects.create_for_content_object(self.component1, ext_source1, "REF2")
        ExternalReference.objects.create_for_content_object(self.component1, ext_source1, "REF3")

    def test_api_component_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")
        # with self.assertNumQueries(10):
        response = self.client.get(self.component_list_url)

        self.assertContains(response, '"count":3,')
        self.assertContains(response, self.component1_detail_url)
        self.assertContains(response, self.component2_detail_url)
        self.assertEqual(3, response.data["count"])

    def test_api_component_list_endpoint_options(self):
        UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            dataspace=self.dataspace,
        )

        UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.dataspace,
        )

        client = APIClient()
        client.login(username="super_user", password="secret")
        response = client.options(self.component_list_url, format="json")
        actions_post = response.data["actions"]["POST"]

        self.assertFalse(bool(actions_post["owner"].get("choices")))
        self.assertEqual("field", actions_post["owner"].get("type"))

        self.assertFalse(bool(actions_post["type"].get("choices")))
        self.assertFalse(bool(actions_post["configuration_status"].get("choices")))
        self.assertFalse(bool(actions_post["usage_policy"].get("choices")))

    def test_api_component_list_endpoint_search(self):
        self.client.login(username="super_user", password="secret")
        data = {"search": self.component1.name}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)

        # Search is case in-sensitive
        data = {"search": self.component1.name.upper()}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)

    def test_api_component_list_endpoint_filters(self):
        self.client.login(username="super_user", password="secret")
        data = {"is_active": True}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(3, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertContains(response, self.component2_detail_url)
        self.assertContains(response, self.component3_detail_url)

        data = {"is_active": False}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(0, response.data["count"])
        self.assertNotContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)
        self.assertNotContains(response, self.component3_detail_url)

        data = {"legal_reviewed": True}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)

        self.component1.license_expression = "mit AND apache-2.0"
        self.component1.save()
        data = {"license_expression": "mit"}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)
        data = {"license_expression": "apache"}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)

        self.component1.keywords = ["Application", "Security"]
        self.component1.save()
        data = {"keywords": "application"}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)

    def test_api_component_list_endpoint_version_filters(self):
        self.client.login(username="super_user", password="secret")

        self.component1.version = "1.0"
        self.component1.save()
        self.component2.version = "2.0"
        self.component2.save()
        self.component3.version = "3.0"
        self.component3.save()

        data = {"version": "1.0"}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)
        self.assertNotContains(response, self.component3_detail_url)

        data = {"version__gt": "1.0"}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(2, response.data["count"])
        self.assertNotContains(response, self.component1_detail_url)
        self.assertContains(response, self.component2_detail_url)
        self.assertContains(response, self.component3_detail_url)

        data = {"version__lt": "2.0"}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)
        self.assertNotContains(response, self.component3_detail_url)

        data = {"version__gt": "1.0", "version__lt": "3.0"}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertNotContains(response, self.component1_detail_url)
        self.assertContains(response, self.component2_detail_url)
        self.assertNotContains(response, self.component3_detail_url)

    def test_api_component_list_endpoint_multiple_char_filters(self):
        self.client.login(username="super_user", password="secret")
        owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        self.component1.owner = owner1
        self.component1.save()
        owner2 = Owner.objects.create(name="Owner2", dataspace=self.dataspace)
        self.component2.owner = owner2
        self.component2.save()
        owner3 = Owner.objects.create(name="Own , er3", dataspace=self.dataspace)
        self.component3.owner = owner3
        self.component3.save()

        filters = "?owner={}&owner={}".format(owner1.name, owner3.name)
        response = self.client.get(self.component_list_url + filters)
        self.assertEqual(2, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)
        self.assertContains(response, self.component3_detail_url)

    def test_api_component_list_endpoint_name_version_filter(self):
        self.client.login(username="super_user", password="secret")

        filters = "?name_version={}:{}".format(self.component1.name, self.component1.version)
        response = self.client.get(self.component_list_url + filters)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)
        self.assertNotContains(response, self.component3_detail_url)

        # Supports multi-value
        filters += "&name_version={}:{}".format(self.component3.name, self.component3.version)
        response = self.client.get(self.component_list_url + filters)
        self.assertEqual(2, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)
        self.assertContains(response, self.component3_detail_url)

    def test_api_component_list_endpoint_uuid_filter(self):
        self.client.login(username="super_user", password="secret")
        data = {"uuid": ""}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(3, response.data["count"])
        response = self.client.get(self.component_list_url + "?uuid=")
        self.assertEqual(3, response.data["count"])

        data = {"uuid": "invalid"}
        expected = {
            "uuid": [
                ErrorDetail(
                    string="Select a valid choice. invalid is not one of " "the available choices.",
                    code="invalid_choice",
                )
            ]
        }
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(expected, response.data)
        response = self.client.get(self.component_list_url + "?uuid=invalid")
        self.assertEqual(expected, response.data)

        data = {"uuid": self.component1.uuid}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        response = self.client.get(self.component_list_url + f"?uuid={self.component1.uuid}")
        self.assertEqual(1, response.data["count"])

        data = {"uuid": [self.component1.uuid, self.component2.uuid]}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(2, response.data["count"])
        response = self.client.get(
            self.component_list_url + f"?uuid={self.component1.uuid}&uuid={self.component2.uuid}"
        )
        self.assertEqual(2, response.data["count"])

    def test_api_component_detail_endpoint(self):
        package1 = Package.objects.create(filename="file.zip", dataspace=self.dataspace)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.dataspace
        )
        package1_detail_url = reverse("api_v2:package-detail", args=[package1.uuid])
        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        self.component1.owner = owner
        self.component1.save()
        owner_detail_url = reverse("api_v2:owner-detail", args=[owner.uuid])
        self.client.login(username="super_user", password="secret")

        # with self.assertNumQueries(9):
        response = self.client.get(self.component1_detail_url)

        self.assertContains(response, self.component1_detail_url)
        self.assertEqual(str(self.component1), response.data["display_name"])
        self.assertIn(self.component1_detail_url, response.data["api_url"])
        expected_url = f"http://testserver{self.component1.get_absolute_url()}"
        self.assertEqual(expected_url, response.data["absolute_url"])
        self.assertEqual(str(self.component1.uuid), response.data["uuid"])
        self.assertEqual(self.component1.name, response.data["name"])
        self.assertEqual(self.component1.type, response.data["type"])
        self.assertEqual(0, response.data["curation_level"])
        self.assertIn(package1_detail_url, response.data["packages"][0])
        self.assertEqual(3, len(response.data["external_references"]))
        self.assertIn(owner_detail_url, response.data["owner"])
        self.assertEqual(owner.name, response.data["owner_name"])
        self.assertEqual(owner.name, response.data["owner_abcd"]["name"])
        self.assertEqual(str(owner.uuid), response.data["owner_abcd"]["uuid"])
        self.assertIn(owner_detail_url, response.data["owner_abcd"]["api_url"])
        self.assertEqual(self.component1.urn, response.data["urn"])

        package_abcd = response.data["packages_abcd"][0]
        self.assertEqual(package1.download_url, package_abcd["download_url"])
        self.assertEqual(package1.filename, package_abcd["filename"])
        self.assertEqual(str(package1.uuid), package_abcd["uuid"])
        self.assertIn(package1_detail_url, package_abcd["api_url"])

    def test_api_component_licenses_summary_field(self):
        self.client.login(username="super_user", password="secret")

        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="license1", name="License1", short_name="L1", owner=owner, dataspace=self.dataspace
        )
        license2 = License.objects.create(
            key="license2", name="License2", short_name="L2", owner=owner, dataspace=self.dataspace
        )

        self.component1.license_expression = license1.key
        self.component1.save()

        response = self.client.get(self.component1_detail_url)
        expected = {
            "category": None,
            "is_primary": True,
            "key": license1.key,
            "name": license1.name,
            "short_name": license1.short_name,
            "type": None,
        }
        self.assertEqual([expected], response.data["licenses_summary"])

        category1 = LicenseCategory.objects.create(label="C1", text="a", dataspace=self.dataspace)
        license1.category = category1
        license1.save()
        response = self.client.get(self.component1_detail_url)
        expected["category"] = category1.label
        self.assertEqual([expected], response.data["licenses_summary"])

        category1.license_type = "type1"
        category1.save()
        response = self.client.get(self.component1_detail_url)
        expected["type"] = category1.license_type
        self.assertEqual([expected], response.data["licenses_summary"])

        self.component1.license_expression = "({} OR {})".format(license2.key, license1.key)
        self.component1.save()
        response = self.client.get(self.component1_detail_url)
        licenses_summary = response.data["licenses_summary"]
        self.assertEqual(2, len(licenses_summary))
        self.assertEqual(license1.key, licenses_summary[0]["key"])
        self.assertFalse(licenses_summary[0]["is_primary"])
        self.assertEqual(license2.key, licenses_summary[1]["key"])
        self.assertTrue(licenses_summary[1]["is_primary"])

    def test_api_component_license_choices_fields(self):
        self.client.login(username="super_user", password="secret")

        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="license1", name="License1", short_name="L1", owner=owner, dataspace=self.dataspace
        )
        license2 = License.objects.create(
            key="license2", name="License2", short_name="L2", owner=owner, dataspace=self.dataspace
        )

        response = self.client.get(self.component1_detail_url)
        self.assertEqual([], response.data["license_choices"])
        self.assertIsNone(response.data["license_choices_expression"])

        self.component1.license_expression = license1.key
        self.component1.save()
        response = self.client.get(self.component1_detail_url)
        self.assertEqual([], response.data["license_choices"])
        self.assertIsNone(response.data["license_choices_expression"])

        LicenseChoice.objects.create(
            from_expression=license1.key, to_expression=license2.key, dataspace=self.dataspace
        )
        response = self.client.get(self.component1_detail_url)
        expected = [{"key": "license2", "short_name": "L2"}]
        self.assertEqual(expected, response.data["license_choices"])
        self.assertEqual(license2.key, response.data["license_choices_expression"])

    def test_api_component_list_endpoint_filter_by_last_modified_date(self):
        self.client.login(username="super_user", password="secret")
        now = datetime.datetime.now()
        one_hour = datetime.timedelta(hours=1)

        # No filters
        response = self.client.get(self.component_list_url)
        self.assertEqual(3, response.data["count"])

        # 1 hour in the past
        data = {"last_modified_date": self.component1.last_modified_date - one_hour}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(3, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertContains(response, self.component2_detail_url)

        # 1 hour in the future
        data = {"last_modified_date": self.component1.last_modified_date + one_hour}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(0, response.data["count"])

        # Modified after now
        data = {"last_modified_date": now}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(0, response.data["count"])

        self.component1.save()
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)

        # Same date as last_modified_date
        data = {"last_modified_date": self.component1.last_modified_date}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)

        # "YYYY-MM-DD" and "YYYY-MM-DD HH:MM" formats supported
        data = {"last_modified_date": "2000-01-01"}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(3, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertContains(response, self.component2_detail_url)
        data = {"last_modified_date": "9999-01-01"}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(0, response.data["count"])
        data = {"last_modified_date": "2000-01-01 10:10"}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(3, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertContains(response, self.component2_detail_url)

    def test_api_component_list_endpoint_filter_by_curation_level(self):
        self.client.login(username="super_user", password="secret")
        data = {"curation_level": 90}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(0, response.data["count"])

        self.component1.curation_level = 11
        self.component1.save()
        self.component2.curation_level = 9
        self.component2.save()
        data = {"curation_level": 10}
        response = self.client.get(self.component_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.component1_detail_url)
        self.assertNotContains(response, self.component2_detail_url)

    def test_api_component_list_endpoint_filter_by_is_active(self):
        self.client.login(username="super_user", password="secret")

        self.component3.is_active = False
        self.component3.save()

        self.assertEqual(2, Component.objects.filter(is_active=True).count())
        self.assertEqual(1, Component.objects.filter(is_active=False).count())

        for value in ["on", "2", True, "True", "true", "t", "T", "yes", "Yes", "y", "Y"]:
            response = self.client.get(self.component_list_url, {"is_active": value})
            self.assertEqual(2, response.data["count"])

        for value in ["3", "False", False, "false", "f", "F", "no", "No", "n", "N"]:
            response = self.client.get(self.component_list_url, {"is_active": value})
            self.assertEqual(1, response.data["count"])

    def test_api_component_endpoint_create_minimal(self):
        self.client.login(username="super_user", password="secret")
        data = {"name": "RapidJSON"}
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        component = Component.objects.get(name="RapidJSON")
        self.assertTrue(component.is_active)
        self.assertTrue(response.data["is_active"])

    def test_api_component_endpoint_create_update_keywords(self):
        keyword1 = ComponentKeyword.objects.create(label="Keyword1", dataspace=self.dataspace)
        keyword2 = ComponentKeyword.objects.create(label="Keyword2", dataspace=self.dataspace)
        # For scoping sanity check
        ComponentKeyword.objects.create(label=keyword1.label, dataspace=self.alternate_dataspace)

        self.client.login(username="super_user", password="secret")
        data = {
            "name": "Comp1",
            "keywords": [keyword1.label, keyword2.label],
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        c1 = Component.objects.get(name="Comp1")
        self.assertEqual(2, len(c1.keywords))
        self.assertEqual(7, c1.completion_level)

        data = {
            "name": "Comp3",
            "keywords": ["non-existing"],
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(201, response.status_code)
        new_keyword = ComponentKeyword.objects.get(label="non-existing")
        self.assertTrue(new_keyword)
        self.assertEqual([new_keyword.label], Component.objects.get(name="Comp3").keywords)

        # No keywords
        data = {
            "name": "Comp2",
            "keywords": [],
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        c2 = Component.objects.get(name="Comp2")
        self.assertEqual([], c2.keywords)

        data = {
            "name": "CompNoKeywords",
            "keywords": "",
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertEqual([], Component.objects.get(name=data["name"]).keywords)

        # Update
        data = json.dumps({"keywords": [keyword1.label]})
        c2_api_url = reverse("api_v2:component-detail", args=[c2.uuid])
        response = self.client.patch(c2_api_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        c2.refresh_from_db()
        self.assertEqual([keyword1.label], c2.keywords)

        data = json.dumps({"keywords": [keyword2.label]})
        response = self.client.patch(c2_api_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        c2.refresh_from_db()
        self.assertEqual([keyword2.label], c2.keywords)

        data = json.dumps({"keywords": [keyword1.label, keyword2.label]})
        response = self.client.patch(c2_api_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        c2.refresh_from_db()
        self.assertEqual([keyword1.label, keyword2.label], c2.keywords)

    def test_api_component_endpoint_create_update_m2m_packages(self):
        package1 = Package.objects.create(filename="package1.zip", dataspace=self.dataspace)
        package1_detail_url = reverse("api_v2:package-detail", args=[package1.uuid])
        package2 = Package.objects.create(filename="package2.zip", dataspace=self.dataspace)
        # For scoping sanity check
        Package.objects.create(filename="package1.zip", dataspace=self.alternate_dataspace)

        self.client.login(username="super_user", password="secret")
        data = {
            "name": "Comp1",
            # api url and uuid are supported
            "packages": [package1_detail_url, package2.uuid],
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        c1 = Component.objects.get(name="Comp1")
        self.assertEqual(2, c1.packages.count())
        self.assertEqual(7, c1.completion_level)

        data = {
            "name": "Comp2",
            "packages": ["non-existing"],
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(400, response.status_code)
        expected = {"packages": ["Invalid hyperlink - No URL match."]}
        self.assertEqual(expected, response.data)

        # No packages
        data = {
            "name": "Comp2",
            "packages": [],
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        c2 = Component.objects.get(name="Comp2")
        self.assertEqual(0, c2.packages.count())

        # Update
        data = json.dumps({"packages": [package1_detail_url]})
        c2_api_url = reverse("api_v2:component-detail", args=[c2.uuid])
        response = self.client.patch(c2_api_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, c2.packages.count())

        data = json.dumps({"packages": [str(package2.uuid)]})
        response = self.client.patch(c2_api_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(2, c2.packages.count())

    def test_api_component_endpoint_create_update_package1(self):
        package1 = Package.objects.create(filename="package1.zip", dataspace=self.dataspace)
        package1_detail_url = reverse("api_v2:package-detail", args=[package1.uuid])
        package2 = Package.objects.create(filename="package2.zip", dataspace=self.dataspace)

        self.client.login(username="super_user", password="secret")
        data = {
            "name": "Comp1",
            # api url and uuid are supported
            "packages": [package1_detail_url, package2.uuid],
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        c1 = Component.objects.get(name="Comp1")
        self.assertEqual(2, c1.packages.count())

    def test_api_component_endpoint_create(self):
        self.client.login(username="super_user", password="secret")
        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="license1", name="License1", short_name="L1", owner=owner, dataspace=self.dataspace
        )
        license2 = License.objects.create(
            key="license2", name="License2", short_name="L2", owner=owner, dataspace=self.dataspace
        )
        policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.dataspace,
        )
        data = {
            "name": "RapidJSON",
            "version": "1.0.2",
            "owner": owner.name,
            "copyright": "Copyright (C) 2015 THL A29 Limited, a Tencent company, and Milo Yip.",
            "license_expression": "{} AND {}".format(license1.key, license2.key),
            "reference_notes": "",
            "release_date": "2015-05-14",
            "description": "RapidJSON is a JSON parser and generator for C++."
            " It was inspired by RapidXml.",
            "homepage_url": "http://rapidjson.org/",
            "vcs_url": "https://github.com/miloyip/rapidjson.git",
            "code_view_url": "https://github.com/miloyip/rapidjson",
            "bug_tracking_url": "https://github.com/miloyip/rapidjson/issues",
            "primary_language": "C++",
            "type": "",
            "notice_text": "Tencent is pleased to support the open source community by"
            " making RapidJSON available.",
            "is_license_notice": True,
            "is_copyright_notice": True,
            "is_notice_in_codebase": True,
            "notice_filename": "license.txt",
            "notice_url": "https://github.com/miloyip/rapidjson/blob/master/license.txt",
            "dependencies": [],
            "configuration_status": "",
            "is_active": False,
            "usage_policy": policy.label,
            "curation_level": 45,
            "guidance": "There are two files licensed under BSD-Modified",
            "admin_notes": "",
            "approval_reference": "",
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        component = Component.objects.latest("id")
        self.assertEqual(83, component.completion_level)
        self.assertEqual(2, component.licenses.count())

        self.assertFalse(History.objects.get_for_object(component).exists())
        self.assertEqual(self.super_user, component.created_by)
        self.assertTrue(component.created_date)

        for field_name, value in data.items():
            if field_name in ["last_modified_date", "type"]:
                continue
            if field_name == "configuration_status":  # default_on_addition
                self.assertEqual(self.status1, getattr(component, field_name))
                continue
            self.assertEqual(str(value), str(getattr(component, field_name)), msg=field_name)

        expected = 'Added Component: "RapidJSON 1.0.2"'
        self.assertEqual(expected, mail.outbox[0].subject)
        body = mail.outbox[0].body
        self.assertIn(component.get_admin_url(), body)

    def test_api_component_endpoint_create_acceptable_linkages(self):
        self.client.login(username="super_user", password="secret")

        data = {
            "name": "comp1",
            "acceptable_linkages": "Dynamic Linkage",
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        component = Component.objects.latest("id")
        self.assertEqual(["Dynamic Linkage"], component.acceptable_linkages)

        data = {
            "name": "comp2",
            "acceptable_linkages": ["Dynamic Linkage"],
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        component = Component.objects.latest("id")
        self.assertEqual(["Dynamic Linkage"], component.acceptable_linkages)

        data = {
            "name": "comp3",
            "acceptable_linkages": ["Dynamic Linkage", "Any Linkage Allowed"],
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        component = Component.objects.latest("id")
        self.assertEqual(["Dynamic Linkage", "Any Linkage Allowed"], component.acceptable_linkages)

        data = {
            "name": "comp4",
            "acceptable_linkages": [],
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        component = Component.objects.latest("id")
        self.assertIsNone(component.acceptable_linkages)

    def test_api_component_endpoint_create_dependencies(self):
        self.client.login(username="super_user", password="secret")

        data = {
            "name": "comp1",
            "dependencies": "simple string",
        }
        response = self.client.post(self.component_list_url, data)
        expected_error = b'{"dependencies":["Value must be valid JSON."]}'
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected_error, response.content)

        data = {
            "name": "comp2",
            "dependencies": "{'json': 'yes'}",
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected_error, response.content)

        data = {
            "name": "comp3",
            "dependencies": json.dumps([{"json": "yes"}]),
        }
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        component = Component.objects.latest("id")
        self.assertEqual([{"json": "yes"}], component.dependencies)

        data = json.dumps(
            {
                "name": "comp4",
                "dependencies": {"json": "yes"},
            }
        )
        response = self.client.post(
            self.component_list_url, data=data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        component = Component.objects.latest("id")
        self.assertEqual({"json": "yes"}, component.dependencies)

    def test_api_component_endpoint_create_clean_validate_against_reference_data(self):
        self.client.login(username=self.alternate_super_user, password="secret")
        data = {"name": self.component1.name}
        response = self.client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        copy_to_my_dataspace_url = self.component1.get_api_copy_to_my_dataspace_url()
        expected = {
            "error": [
                ErrorDetail(
                    string=f"The application object that you are creating already "
                    f"exists as c1 in the reference dataspace. Use the "
                    f"following URL to copy the reference object to your local "
                    f"Dataspace: {copy_to_my_dataspace_url}",
                    code="invalid",
                )
            ],
            "copy_url": [ErrorDetail(string=copy_to_my_dataspace_url, code="invalid")],
        }
        self.assertEqual(expected, response.data)

    def test_api_component_endpoint_copy_to_my_dataspace_action(self):
        self.client.login(username=self.alternate_super_user, password="secret")
        copy_to_my_dataspace_url = self.component1.get_api_copy_to_my_dataspace_url()
        self.assertTrue(self.component1.dataspace.is_reference)

        response = self.client.post(copy_to_my_dataspace_url)
        self.assertEqual("Alternate", response.data["dataspace"])
        self.assertEqual("c1", response.data["display_name"])

        response = self.client.post(copy_to_my_dataspace_url)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"error": "The object already exists in your local Dataspace."}
        self.assertEqual(expected, response.data)

        not_found_url = reverse("api_v2:component-copy-to-my-dataspace", args=[uuid.uuid4()])
        response = self.client.post(not_found_url)
        self.assertEqual(status.HTTP_404_NOT_FOUND, response.status_code)

        self.client.login(username=self.super_user, password="secret")
        response = self.client.post(copy_to_my_dataspace_url)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"error": "Target dataspace cannot be the reference one."}
        self.assertEqual(expected, response.data)

        with override_settings(REFERENCE_DATASPACE="non_existing"):
            response = self.client.post(copy_to_my_dataspace_url)
            self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
            expected = {"error": "You do not have rights to execute this action."}
            self.assertEqual(expected, response.data)

    def test_api_component_endpoint_update_put(self):
        self.client.login(username="super_user", password="secret")

        put_data = json.dumps({"name": "Updated Name"})
        response = self.client.put(
            self.component1_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        history = History.objects.get_for_object(
            self.component1, action_flag=History.CHANGE
        ).latest("id")
        self.assertEqual("Changed name.", history.get_change_message())

        self.assertEqual('Updated Component: "Updated Name"', mail.outbox[0].subject)
        body = mail.outbox[0].body
        self.assertIn('Changes details for Component "Updated Name"', body)
        self.assertIn(self.component1.get_admin_url(), body)
        self.assertIn("Changed name.", body)
        self.assertIn("Old value: c1", body)
        self.assertIn("New value: Updated Name", body)

    def test_api_component_protected_fields_as_read_only(self):
        component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.dataspace,
        )

        client = APIClient()
        client.login(username="admin_user", password="secret")

        response = client.get(self.component_list_url, format="json")
        c1 = response.data["results"][0]
        self.assertIn("usage_policy", c1.keys())
        self.assertIsNone(c1["usage_policy"])

        self.component1.usage_policy = component_policy
        self.component1.save()
        response = client.get(self.component1_detail_url, format="json")
        self.assertEqual(component_policy.label, response.data["usage_policy"])

        self.admin_user = add_perms(self.admin_user, ["add_component", "change_component"])
        data = {
            "name": "comp1",
            "usage_policy": component_policy.label,
        }
        response = client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        component = Component.objects.latest("id")
        self.assertIsNone(component.usage_policy)

        detail_url = reverse("api_v2:component-detail", args=[component.uuid])
        response = client.put(detail_url, data)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        component = Component.objects.latest("id")
        self.assertIsNone(component.usage_policy)

        response = client.patch(detail_url, data)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        component = Component.objects.latest("id")
        self.assertIsNone(component.usage_policy)

        self.admin_user = add_perm(self.admin_user, "change_usage_policy_on_component")
        response = client.put(detail_url, data)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        component = Component.objects.latest("id")
        self.assertEqual(component_policy, component.usage_policy)

        data["name"] = "comp2"
        response = client.post(self.component_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        component = Component.objects.latest("id")
        self.assertEqual(component_policy, component.usage_policy)


@override_settings(
    EMAIL_HOST_USER="user",
    EMAIL_HOST_PASSWORD="password",
    EMAIL_HOST="localhost",
    EMAIL_PORT=25,
    DEFAULT_FROM_EMAIL="webmaster@localhost",
)
class PackageAPITestCase(MaxQueryMixin, TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="Other")

        self.base_user = create_user("base_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)
        self.super_user = create_superuser(
            "super_user", self.dataspace, data_email_notification=True
        )

        self.package_list_url = reverse("api_v2:package-list")

        self.package1 = Package.objects.create(
            filename="package1.zip",
            dataspace=self.dataspace,
            size=1024,
            md5="6eed96478ad6ff01b97b7edf005b58ea",
            sha1="96b63269c5c5762b005a59a4e8ae57f453df3865",
        )
        self.package1_detail_url = reverse("api_v2:package-detail", args=[self.package1.uuid])

        self.package2 = Package.objects.create(
            filename="package2.zip",
            dataspace=self.dataspace,
            md5="e555c0900d1debb26ea463c747de169d",
            sha1="d7b3679279b3d1bb1044a63232e1b309790a99ac",
        )
        self.package2_detail_url = reverse("api_v2:package-detail", args=[self.package2.uuid])

        self.package3 = Package.objects.create(
            filename="package3.zip",
            dataspace=self.dataspace,
            md5="92d15ca3cf229be08c2cf5da1b4ab74b",
            sha1="f379606577b3a6f05b19a0162b53e0e1228c4e16",
        )
        self.package3_detail_url = reverse("api_v2:package-detail", args=[self.package3.uuid])

    def test_api_package_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")
        # with self.assertNumQueries(9):
        response = self.client.get(self.package_list_url)

        self.assertContains(response, '"count":3,')
        self.assertContains(response, self.package1_detail_url)
        self.assertContains(response, self.package2_detail_url)
        self.assertEqual(3, response.data["count"])

    def test_api_package_list_endpoint_search(self):
        self.client.login(username="super_user", password="secret")
        data = {"search": self.package1.filename}
        response = self.client.get(self.package_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.package1_detail_url)
        self.assertNotContains(response, self.package2_detail_url)

        # Search is case in-sensitive
        data = {"search": self.package1.filename.upper()}
        response = self.client.get(self.package_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.package1_detail_url)
        self.assertNotContains(response, self.package2_detail_url)

    def test_api_package_list_endpoint_autocomplete_search(self):
        self.client.login(username="super_user", password="secret")

        django = Package.objects.create(
            type="pypi",
            namespace="djangoproject",
            name="django",
            version="3.1",
            dataspace=self.dataspace,
        )
        django_detail_url = reverse("api_v2:package-detail", args=[django.uuid])

        search_queries = [
            "pkg:pypi/djangoproject/django@3.1",
            "pypi/djangoproject/django@3.1",
            "pypi/django@3.1",
            "django@3.1",
            "django 3.1",
            "pypi django 3.1",
        ]

        for query in search_queries:
            data = {"search": query, "autocomplete": 1}
            response = self.client.get(self.package_list_url, data)
            self.assertEqual(1, response.data["count"])
            self.assertContains(response, django_detail_url)

    def test_api_package_list_endpoint_filters(self):
        self.client.login(username="super_user", password="secret")
        data = {
            "filename": self.package1.filename,
            "size": self.package1.size,
        }
        response = self.client.get(self.package_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.package1_detail_url)
        self.assertNotContains(response, self.package2_detail_url)

        self.package1.keywords = ["Application", "Security"]
        self.package1.save()
        data = {"keywords": "application"}
        response = self.client.get(self.package_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.package1_detail_url)
        self.assertNotContains(response, self.package2_detail_url)

    def test_api_package_list_endpoint_multiple_char_filters(self):
        self.client.login(username="super_user", password="secret")
        filters = "?md5={}&md5={}".format(self.package1.md5, self.package2.md5)
        response = self.client.get(self.package_list_url + filters)
        self.assertEqual(2, response.data["count"])
        self.assertContains(response, self.package1_detail_url)
        self.assertContains(response, self.package2_detail_url)
        self.assertNotContains(response, self.package3_detail_url)

        filters = "?sha1={}&sha1={}".format(self.package2.sha1, self.package3.sha1)
        response = self.client.get(self.package_list_url + filters)
        self.assertEqual(2, response.data["count"])
        self.assertNotContains(response, self.package1_detail_url)
        self.assertContains(response, self.package2_detail_url)
        self.assertContains(response, self.package3_detail_url)

    def test_api_package_detail_endpoint(self):
        component1 = Component.objects.create(name="c1", dataspace=self.dataspace)
        ComponentAssignedPackage.objects.create(
            component=component1, package=self.package1, dataspace=self.dataspace
        )
        component1_detail_url = reverse("api_v2:component-detail", args=[component1.uuid])

        # Make sure the protected_fields does not break when a protected field is
        # not available on the serializer, here `usage_policy` on `ComponentEmbeddedSerializer`
        self.client.login(username=self.base_user, password="secret")
        response = self.client.get(self.package_list_url)
        self.assertEqual(200, response.status_code)

        self.client.login(username="super_user", password="secret")
        with self.assertMaxQueries(10):
            response = self.client.get(self.package1_detail_url)

        self.assertContains(response, self.package1_detail_url)
        self.assertIn(self.package1_detail_url, response.data["api_url"])
        expected_url = f"http://testserver{self.package1.get_absolute_url()}"
        self.assertEqual(expected_url, response.data["absolute_url"])
        self.assertEqual(str(self.package1.uuid), response.data["uuid"])
        self.assertEqual(self.package1.filename, response.data["filename"])
        self.assertEqual(self.package1.size, response.data["size"])
        self.assertEqual(
            list(self.package1.external_references.all()), response.data["external_references"]
        )

        component_data = response.data["components"][0]
        self.assertEqual(str(component1), component_data["display_name"])
        self.assertEqual(component1.name, component_data["name"])
        self.assertEqual(component1.version, component_data["version"])
        self.assertEqual(str(component1.uuid), component_data["uuid"])
        self.assertIn(component1_detail_url, component_data["api_url"])

    def test_api_package_endpoint_create_minimal(self):
        self.client.login(username="super_user", password="secret")
        data = {"filename": "package.tar.gz"}
        response = self.client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

    def test_api_package_endpoint_create_identifier_validation(self):
        self.client.login(username="super_user", password="secret")

        data = {"download_url": "https://download.url"}
        response = self.client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = [ErrorDetail(string="['package_url or filename required']", code="invalid")]
        self.assertEqual(expected, response.data)

        data = {
            "type": "type",
            "name": "name",
        }
        response = self.client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

    def test_api_package_endpoint_create_filename_validation(self):
        self.client.login(username="super_user", password="secret")
        data = {"filename": "pack/age.tar.gz"}
        response = self.client.post(self.package_list_url, data)
        expected = {
            "filename": [
                ErrorDetail(
                    string="Enter a valid filename: slash, backslash, or colon are not allowed.",
                    code="invalid",
                )
            ]
        }
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected, response.data)

        data = {"filename": "pack\\age.tar.gz"}
        response = self.client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected, response.data)

        data = {"filename": "pack:age.tar.gz"}
        response = self.client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected, response.data)

    def test_api_package_endpoint_create_with_license_expression(self):
        self.client.login(username="super_user", password="secret")
        data = {
            "filename": "package.tar.gz",
            "license_expression": "",
        }
        response = self.client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        data["license_expression"] = "non-existing-license"
        response = self.client.post(self.package_list_url, data)
        expected = {"license_expression": ["Unknown license key(s): non-existing-license"]}
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected, response.data)

        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="l1", name="L1", short_name="L1", owner=owner, dataspace=self.dataspace
        )
        data = {
            "filename": "package2.tar.gz",
            "license_expression": license1.key,
        }
        response = self.client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

    def test_api_package_endpoint_create(self):
        self.client.login(username="super_user", password="secret")

        policy = UsagePolicy.objects.create(
            label="PackagePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Package),
            dataspace=self.dataspace,
        )

        data = {
            "download_url": "https://github.com/django/django/archive/1.9.6.tar.gz",
            "filename": "django-1.9.6.tar.gz",
            "sha1": "60f00300d0171ba4ac63f14121d2b6d60dfc5fd0",
            "md5": "1cb693d3f3872b1056766e4a973b750d",
            "size": 7443963,
            "release_date": "1984-10-10",
            "notes": "Notes",
            "type": "deb",
            "namespace": "debian",
            "name": "curl",
            "version": "7.50.3-1",
            "qualifiers": "arch=i386",
            "subpath": "googleapis/api/annotations",
            "usage_policy": policy.label,
        }

        response = self.client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        package = Package.objects.get(download_url=data["download_url"])
        self.assertFalse(History.objects.get_for_object(package).exists())
        self.assertEqual(self.super_user, package.created_by)
        self.assertTrue(package.created_date)

        for field_name, value in data.items():
            self.assertEqual(str(value), str(getattr(package, field_name)))

        expected = 'Added Package: "deb/debian/curl@7.50.3-1"'
        self.assertEqual(expected, mail.outbox[0].subject)
        body = mail.outbox[0].body
        self.assertIn(package.get_admin_url(), body)

        expected = "pkg:deb/debian/curl@7.50.3-1?arch=i386#googleapis/api/annotations"
        self.assertEqual(expected, package.package_url)

    def test_api_package_endpoint_create_unicity_validation(self):
        self.client.login(username="super_user", password="secret")

        self.package1.download_url = "http://url.com/a.zip"
        self.package1.save()

        # Same download_url, different filename
        data = {"filename": self.package1.filename}
        response = self.client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        # Same download_url, same filename
        data["download_url"] = self.package1.download_url
        response = self.client.post(self.package_list_url, data)
        expected1 = "duplicate key value violates unique constraint"
        expected2 = (
            "Key (dataspace_id, type, namespace, name, version, qualifiers, subpath,"
            " download_url, filename)"
        )
        self.assertContains(response, expected1, status_code=400)
        self.assertContains(response, expected2, status_code=400)

        # Same download_url, same filename, name
        data["name"] = "Name"
        response = self.client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        # Same download_url, same filename, same name
        response = self.client.post(self.package_list_url, data)
        self.assertContains(response, expected1, status_code=400)
        self.assertContains(response, expected2, status_code=400)

    def test_api_package_endpoint_create_update_keywords(self):
        keyword1 = ComponentKeyword.objects.create(label="Keyword1", dataspace=self.dataspace)
        keyword2 = ComponentKeyword.objects.create(label="Keyword2", dataspace=self.dataspace)
        # For scoping sanity check
        ComponentKeyword.objects.create(label=keyword1.label, dataspace=self.other_dataspace)

        self.client.login(username="super_user", password="secret")
        data = {
            "filename": "filename.ext",
            "keywords": [keyword1.label, keyword2.label],
        }
        response = self.client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        p1 = Package.objects.get(filename="filename.ext")
        self.assertEqual([keyword1.label, keyword2.label], p1.keywords)

        data = {
            "filename": "filename2.ext",
            "keywords": ["non-existing"],
        }
        response = self.client.post(self.package_list_url, data)
        self.assertEqual(201, response.status_code)
        new_keyword = ComponentKeyword.objects.get(label="non-existing")
        self.assertTrue(new_keyword)
        p2 = Package.objects.get(filename="filename2.ext")
        self.assertEqual([new_keyword.label], p2.keywords)
        history = History.objects.get_for_object(new_keyword).latest("id")
        self.assertEqual("Added.", history.get_change_message())

        data = {
            "filename": "filename3.ext",
            "keywords": "",
        }
        response = self.client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertEqual([], Package.objects.get(filename=data["filename"]).keywords)

        # Update
        data = json.dumps({"keywords": [keyword1.label]})
        p2_api_url = reverse("api_v2:package-detail", args=[p2.uuid])
        response = self.client.patch(p2_api_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        p2.refresh_from_db()
        self.assertEqual([keyword1.label], p2.keywords)

        data = json.dumps({"keywords": [keyword2.label]})
        p2_api_url = reverse("api_v2:package-detail", args=[p2.uuid])
        response = self.client.patch(p2_api_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        p2.refresh_from_db()
        self.assertEqual([keyword2.label], p2.keywords)

        data = json.dumps({"keywords": [keyword1.label, keyword2.label]})
        p2_api_url = reverse("api_v2:package-detail", args=[p2.uuid])
        response = self.client.patch(p2_api_url, data=data, content_type="application/json")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        p2.refresh_from_db()
        self.assertEqual([keyword1.label, keyword2.label], p2.keywords)

    def test_api_package_endpoint_update_put(self):
        self.package1.created_by = self.base_user
        self.package1.save()

        self.client.login(username="super_user", password="secret")

        put_data = json.dumps({"filename": "Updated Name"})
        response = self.client.put(
            self.package1_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        history = History.objects.get_for_object(self.package1, action_flag=History.CHANGE).latest(
            "id"
        )
        self.assertEqual("Changed filename.", history.get_change_message())
        self.assertIn("package1.zip", history.serialized_data)

        self.assertEqual('Updated Package: "Updated Name"', mail.outbox[0].subject)
        body = mail.outbox[0].body
        self.assertIn('Changes details for Package "Updated Name"', body)
        self.assertIn(self.package1.get_admin_url(), body)
        self.assertIn("Changed filename.", body)
        self.assertIn("Old value: package1.zip", body)
        self.assertIn("New value: Updated Name", body)

        self.package1.refresh_from_db()
        self.assertEqual(self.base_user, self.package1.created_by)
        self.assertEqual(self.super_user, self.package1.last_modified_by)

    def test_api_package_license_choices_fields(self):
        self.client.login(username="super_user", password="secret")

        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="license1", name="License1", short_name="L1", owner=owner, dataspace=self.dataspace
        )
        license2 = License.objects.create(
            key="license2", name="License2", short_name="L2", owner=owner, dataspace=self.dataspace
        )

        response = self.client.get(self.package1_detail_url)
        self.assertEqual([], response.data["license_choices"])
        self.assertIsNone(response.data["license_choices_expression"])

        self.package1.license_expression = license1.key
        self.package1.save()
        response = self.client.get(self.package1_detail_url)
        self.assertEqual([], response.data["license_choices"])
        self.assertIsNone(response.data["license_choices_expression"])

        LicenseChoice.objects.create(
            from_expression=license1.key, to_expression=license2.key, dataspace=self.dataspace
        )
        response = self.client.get(self.package1_detail_url)
        expected = [{"key": "license2", "short_name": "L2"}]
        self.assertEqual(expected, response.data["license_choices"])
        self.assertEqual(license2.key, response.data["license_choices_expression"])

    def test_api_package_viewset_add_action(self):
        add_url = reverse("api_v2:package-add")

        response = self.client.get(add_url)
        self.assertEqual(403, response.status_code)
        response = self.client.post(add_url)
        self.assertEqual(403, response.status_code)

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.get(add_url)
        self.assertEqual(405, response.status_code)
        response = self.client.post(add_url)
        # DjangoModelPermissions: POST requires add_{model_name}
        self.assertEqual(403, response.status_code)

        add_perm(self.base_user, "add_package")
        response = self.client.get(add_url)
        self.assertEqual(405, response.status_code)

        data = {}
        response = self.client.post(add_url, data)
        expected = {"download_url": "This field is required."}
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected, response.json())

        data = {"download_url": "http://bad_url"}
        response = self.client.post(add_url, data)
        self.assertEqual(200, response.status_code)
        expected = {"failed": ["http://bad_url"]}
        self.assertEqual(expected, response.json())

        data = {"download_url": ["http://bad_url", "http://bad_url2"]}
        response = self.client.post(add_url, data)
        self.assertEqual(200, response.status_code)
        expected = {"failed": ["http://bad_url", "http://bad_url2"]}
        self.assertEqual(expected, response.json())

        with mock.patch("component_catalog.api.collect_create_scan") as collect:
            collect.return_value = True
            data = {"download_url": "http://url.com/package.zip"}
            response = self.client.post(add_url, data)
        self.assertEqual(200, response.status_code)
        expected = {"added": ["http://url.com/package.zip"]}
        self.assertEqual(expected, response.json())

    def test_api_package_viewset_about_action(self):
        about_url = reverse("api_v2:package-about", args=[self.package1.uuid])

        response = self.client.get(about_url)
        self.assertEqual(403, response.status_code)
        response = self.client.post(about_url)
        self.assertEqual(403, response.status_code)

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.get(about_url)
        self.assertEqual(200, response.status_code)
        expected = {
            "about_data": (
                "about_resource: package1.zip\n"
                "checksum_md5: 6eed96478ad6ff01b97b7edf005b58ea\n"
                "checksum_sha1: 96b63269c5c5762b005a59a4e8ae57f453df3865\n"
            )
        }
        self.assertEqual(expected, response.json())

    def test_api_package_viewset_about_files_action(self):
        about_url = reverse("api_v2:package-about-files", args=[self.package1.uuid])

        response = self.client.get(about_url)
        self.assertEqual(403, response.status_code)
        response = self.client.post(about_url)
        self.assertEqual(403, response.status_code)

        self.client.login(username=self.base_user.username, password="secret")
        response = self.client.get(about_url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("application/zip", response["content-type"])
        self.assertEqual(
            'attachment; filename="package1.zip_about.zip"', response["content-disposition"]
        )

    def test_api_package_protected_fields_as_read_only(self):
        policy = UsagePolicy.objects.create(
            label="PackagePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Package),
            dataspace=self.dataspace,
        )

        client = APIClient()
        client.login(username=self.admin_user.username, password="secret")

        response = client.get(self.package_list_url, format="json")
        p1 = response.data["results"][0]
        self.assertIn("usage_policy", p1.keys())
        self.assertIsNone(p1["usage_policy"])

        self.package1.usage_policy = policy
        self.package1.save()
        response = client.get(self.package1_detail_url, format="json")
        self.assertEqual(policy.label, response.data["usage_policy"])

        self.admin_user = add_perms(self.admin_user, ["add_package", "change_package"])
        data = {
            "filename": "pack1",
            "usage_policy": policy.label,
        }
        response = client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        package = Package.objects.latest("id")
        self.assertIsNone(package.usage_policy)

        detail_url = reverse("api_v2:package-detail", args=[package.uuid])
        response = client.put(detail_url, data)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        package = Package.objects.latest("id")
        self.assertIsNone(package.usage_policy)

        response = client.patch(detail_url, data)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        package = Package.objects.latest("id")
        self.assertIsNone(package.usage_policy)

        self.admin_user = add_perm(self.admin_user, "change_usage_policy_on_package")
        response = client.put(detail_url, data)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        package = Package.objects.latest("id")
        self.assertEqual(policy, package.usage_policy)

        data["filename"] = "pack2"
        response = client.post(self.package_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        package = Package.objects.latest("id")
        self.assertEqual(policy, package.usage_policy)


class PackageAPIFilterSetTest(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

        def create_package(**kwargs):
            return Package.objects.create(dataspace=self.dataspace, **kwargs)

        self.package1 = create_package(
            filename="apache-log4j.zip",
            type="maven",
            namespace="org.apache.commons",
            name="io",
            version="1.3.4",
            download_url="http://example1.com",
        )
        self.package2 = create_package(
            filename="jna-4.0.zip",
            type="maven",
            namespace="org.apache.commons",
            name="io",
            version="2.3.4",
            download_url="http://example2.com",
        )
        self.package3 = create_package(
            filename="jna-src-3.3.0.tar.xz",
            type="github",
        )
        self.package4 = create_package(
            filename="logjnative-4.3.2.tar.gz",
            namespace="namespace",
        )

    def test_package_api_filterset_fuzzy_filter(self):
        data = {"fuzzy": "jna.jar"}
        package_filterset = PackageAPIFilterSet(data)
        expected = [
            "jna-4.0.zip",
            "jna-src-3.3.0.tar.xz",
        ]
        self.assertEqual(expected, [package.filename for package in package_filterset.qs])

    def test_package_api_filterset_fuzzy_filter_create_search_names_no_version(self):
        filename = "jna.jar"
        expected = (
            filename,
            "jna",
        )
        self.assertEqual(expected, FuzzyPackageNameSearch.create_search_names(filename))

    def test_package_api_filterset_fuzzy_filter_create_search_names_version(self):
        create_search_names = FuzzyPackageNameSearch.create_search_names

        filename_version = "jna-1.6.3.jar"
        expected = (
            filename_version,
            "jna 1.6.3",
            "jna",
        )
        self.assertEqual(expected, create_search_names(filename_version))

        filename_version_alphanumeric = "jna-1.6.3-RELEASE.jar"
        expected = (
            filename_version_alphanumeric,
            "jna 1.6.3-RELEASE",
            "jna",
        )
        self.assertEqual(expected, create_search_names(filename_version_alphanumeric))

    def test_package_api_filterset_purl_filter_invalid_purl(self):
        data = {"purl": "jna.jar"}
        expected = 0
        self.assertEqual(expected, PackageAPIFilterSet(data).qs.count())

    def test_package_api_filterset_purl_filter_no_value(self):
        data = {"purl": ""}
        expected = Package.objects.scope(self.dataspace).count()
        self.assertEqual(expected, PackageAPIFilterSet(data).qs.count())

    def test_package_api_filterset_purl_filter_non_existant_purl(self):
        data = {"purl": "pkg:PYPI/Django_package@1.11.1.dev1"}
        expected = 0
        self.assertEqual(expected, PackageAPIFilterSet(data).qs.count())

    def test_package_api_filterset_purl_filter_no_version(self):
        data = {"purl": "pkg:maven/org.apache.commons/io"}
        expected = 2
        self.assertEqual(expected, PackageAPIFilterSet(data).qs.count())

    def test_package_api_filterset_purl_filter_single_match(self):
        data = {"purl": self.package1.package_url}
        expected = 1
        filterset_qs = PackageAPIFilterSet(data).qs
        self.assertEqual(expected, filterset_qs.count())
        self.assertEqual(filterset_qs.get(), self.package1)

    def test_package_api_filterset_purl_empty(self):
        data = {"purl": "EMPTY"}
        qs = PackageAPIFilterSet(data).qs
        self.assertEqual(2, PackageAPIFilterSet(data).qs.count())
        self.assertTrue(self.package1.package_url)
        self.assertNotIn(self.package1, qs)
        self.assertTrue(self.package2.package_url)
        self.assertNotIn(self.package2, qs)
        self.assertFalse(self.package3.package_url)
        self.assertIn(self.package3, qs)
        self.assertFalse(self.package4.package_url)
        self.assertIn(self.package4, qs)

    def test_package_api_filterset_type_namespace_filters(self):
        data = {"type": self.package3.type.upper()}
        filterset_qs = PackageAPIFilterSet(data).qs
        self.assertEqual(1, filterset_qs.count())
        self.assertEqual(filterset_qs.get(), self.package3)

        data = {"namespace": self.package4.namespace.upper()}
        filterset_qs = PackageAPIFilterSet(data).qs
        self.assertEqual(1, filterset_qs.count())
        self.assertEqual(filterset_qs.get(), self.package4)


class SubcomponentAPITestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

        self.base_user = create_user("base_user", self.dataspace)
        self.super_user = create_superuser(
            "super_user", self.dataspace, data_email_notification=True
        )

        self.component1 = Component.objects.create(
            name="c1", dataspace=self.dataspace, legal_reviewed=True
        )
        self.component1_detail_url = reverse("api_v2:component-detail", args=[self.component1.uuid])

        self.component2 = Component.objects.create(name="c2", dataspace=self.dataspace)
        self.component2_detail_url = reverse("api_v2:component-detail", args=[self.component2.uuid])

        self.subcomponent_list_url = reverse("api_v2:subcomponent-list")
        self.subcomponent1 = Subcomponent.objects.create(
            parent=self.component1, child=self.component2, dataspace=self.dataspace
        )
        self.subcomponent1_detail_url = reverse(
            "api_v2:subcomponent-detail", args=[self.subcomponent1.uuid]
        )

    def test_api_subcomponent_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.subcomponent_list_url)

        self.assertContains(response, '"count":1,')
        self.assertContains(response, self.subcomponent1_detail_url)
        self.assertEqual(1, response.data["count"])

    def test_api_subcomponent_detail_endpoint(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.subcomponent1_detail_url)
        self.assertContains(response, self.subcomponent1_detail_url)
        self.assertIn(self.subcomponent1_detail_url, response.data["api_url"])
        self.assertEqual(str(self.subcomponent1.uuid), response.data["uuid"])
        self.assertIn(str(self.subcomponent1.parent.uuid), response.data["parent"])
        self.assertIn(str(self.subcomponent1.child.uuid), response.data["child"])
        self.assertEqual(self.subcomponent1.is_deployed, response.data["is_deployed"])
        self.assertEqual(self.subcomponent1.is_modified, response.data["is_modified"])

    def test_api_subcomponent_endpoint_create_minimal(self):
        self.client.login(username="super_user", password="secret")
        self.subcomponent1.delete()
        data = {
            "parent": self.component1_detail_url,
            "child": f"{self.component2.name}:{self.component2.version}",
        }
        response = self.client.post(self.subcomponent_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        subcomponent = Subcomponent.objects.latest("created_date")
        self.assertTrue(subcomponent.is_deployed)
        self.assertTrue(response.data["is_deployed"])
        self.assertFalse(subcomponent.is_modified)
        self.assertFalse(response.data["is_modified"])

    def test_api_subcomponent_endpoint_create_required_fields(self):
        self.client.login(username="super_user", password="secret")
        data = {}
        response = self.client.post(self.subcomponent_list_url, data)
        expected = {
            "parent": [ErrorDetail(string="This field is required.", code="required")],
            "child": [ErrorDetail(string="This field is required.", code="required")],
        }
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected, response.data)

    def test_api_subcomponent_endpoint_create_with_license_expression(self):
        self.client.login(username="super_user", password="secret")
        self.subcomponent1.delete()
        data = {
            "parent": self.component1_detail_url,
            "child": self.component2_detail_url,
            "license_expression": "non-existing-license",
        }
        response = self.client.post(self.subcomponent_list_url, data)
        expected = {"license_expression": ["Unknown license key(s): non-existing-license"]}
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected, response.data)

        owner = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="l1", name="L1", short_name="L1", owner=owner, dataspace=self.dataspace
        )
        data["license_expression"] = license1.key
        response = self.client.post(self.subcomponent_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

    def test_api_subcomponent_endpoint_create_unique_parent_child_validation(self):
        self.client.login(username="super_user", password="secret")
        data = {
            "parent": self.component1_detail_url,
            "child": self.component2_detail_url,
        }
        response = self.client.post(self.subcomponent_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {
            "non_field_errors": [
                ErrorDetail(
                    string="The fields parent, child must make a unique set.", code="unique"
                )
            ]
        }
        self.assertEqual(expected, response.data)
