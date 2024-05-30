#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from collections import OrderedDict

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIClient

from dje.api_custom import TabPermission
from dje.models import Dataspace
from dje.tests import create_superuser
from dje.tests import create_user
from reporting.api import ReportViewSet
from reporting.models import ColumnTemplate
from reporting.models import ColumnTemplateAssignedField
from reporting.models import Filter
from reporting.models import Query
from reporting.models import Report


class ReportAPITestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.base_user = create_user("base_user", self.dataspace)
        self.super_user = create_superuser("super_user", self.dataspace)

        self.report_list_url = reverse("api_v2:report-list")

        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.component1 = self.component_ct.model_class().objects.create(
            name="component1", version="1.0", dataspace=self.dataspace
        )
        self.license_ct = ContentType.objects.get(app_label="license_library", model="license")

        self.query1 = Query.objects.create(
            dataspace=self.dataspace, name="Q1", content_type=self.component_ct, operator="and"
        )
        self.column_template1 = ColumnTemplate.objects.create(
            name="CT1", dataspace=self.dataspace, content_type=self.component_ct
        )
        self.report1 = Report.objects.create(
            name="Report1",
            query=self.query1,
            column_template=self.column_template1,
            user_available=True,
        )
        self.report2 = Report.objects.create(
            name="Report2",
            query=self.query1,
            column_template=self.column_template1,
            user_available=True,
        )
        self.report3 = Report.objects.create(
            name="Report3", query=self.query1, column_template=self.column_template1
        )

        self.report1_detail_url = reverse("api_v2:report-detail", args=[self.report1.uuid])
        self.report2_detail_url = reverse("api_v2:report-detail", args=[self.report2.uuid])
        self.report3_detail_url = reverse("api_v2:report-detail", args=[self.report3.uuid])

    def test_api_report_list_endpoint_user_available_scope(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.report_list_url)

        self.assertContains(response, self.report1_detail_url)
        self.assertContains(response, self.report2_detail_url)
        self.assertNotContains(response, self.report3_detail_url)
        self.assertEqual(2, response.data["count"])
        self.assertEqual(self.report1.name, response.data["results"][0]["name"])
        self.assertEqual(self.report2.name, response.data["results"][1]["name"])

        # results field only available on details view
        self.assertNotIn("results", response.data["results"][0].keys())

    def test_api_report_list_endpoint_search(self):
        self.client.login(username="super_user", password="secret")
        data = {"search": self.report1.name}
        response = self.client.get(self.report_list_url, data)

        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.report1_detail_url)

    def test_api_report_list_endpoint_filters(self):
        self.client.login(username="super_user", password="secret")

        data = {"content_type": self.component_ct.model}
        response = self.client.get(self.report_list_url, data)
        self.assertEqual(2, response.data["count"])

        data = {"content_type": self.license_ct.model}
        response = self.client.get(self.report_list_url, data)
        self.assertEqual(0, response.data["count"])

    def test_api_report_list_endpoint_options(self):
        client = APIClient()
        client.login(username="super_user", password="secret")
        response = client.options(self.report_list_url, format="json")
        self.assertNotIn("actions", response.data.keys())  # read-only

    def test_api_report_detail_endpoint(self):
        self.client.login(username="super_user", password="secret")

        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query1,
            field_name="name",
            lookup="exact",
            value=self.component1.name,
        )
        ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=self.column_template1,
            field_name="name",
            display_name="Display Name",
            seq=0,
        )
        ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=self.column_template1,
            field_name="version",
            display_name="",
            seq=1,
        )

        response = self.client.get(self.report1_detail_url)

        self.assertContains(response, self.report1_detail_url)
        self.assertIn(self.report1_detail_url, response.data["api_url"])
        self.assertEqual(str(self.report1.uuid), response.data["uuid"])
        self.assertEqual(self.report1.column_template.name, response.data["column_template"])
        self.assertEqual(self.report1.description, response.data["description"])
        expected_url = f"http://testserver{self.report1.get_absolute_url()}"
        self.assertEqual(expected_url, response.data["absolute_url"])
        self.assertEqual(self.report1.name, response.data["name"])
        self.assertEqual(self.report1.query.content_type.model, response.data["content_type"])
        self.assertEqual(self.report1.query.name, response.data["query"])

        expected = [OrderedDict([("Display Name", "component1"), ("version", "1.0")])]
        self.assertEqual(expected, response.data["results"])

    def test_api_report_endpoint_tab_permission(self):
        self.assertEqual((TabPermission,), ReportViewSet.extra_permissions)
