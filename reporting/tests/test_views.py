#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.test import TestCase
from django.urls import NoReverseMatch
from django.urls import reverse

from component_catalog.models import Component
from dje.copier import copy_object
from dje.models import Dataspace
from license_library.models import License
from license_library.models import LicenseCategory
from organization.models import Owner
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductInventoryItem
from reporting.models import ColumnTemplate
from reporting.models import ColumnTemplateAssignedField
from reporting.models import Filter
from reporting.models import Query
from reporting.models import Report


class ReportDetailsViewTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.owner = Owner.objects.create(dataspace=self.dataspace, name="My Fancy Owner Name")

        for i in range(200):
            name = "license_{}".format(i)
            if i < 150:
                is_active = True
            else:
                is_active = False
            License.objects.create(
                key=name,
                name=name,
                short_name=name,
                dataspace=self.dataspace,
                owner=self.owner,
                is_active=is_active,
            )

        self.user = get_user_model().objects.create_superuser(
            "test", "test@test.com", "t3st", self.dataspace
        )

        license_ct = ContentType.objects.get_for_model(License)
        self.component_ct = ContentType.objects.get_for_model(Component)
        self.query = Query.objects.create(
            dataspace=self.dataspace,
            name="license list with ids",
            content_type=license_ct,
            operator="and",
        )
        self.filter1 = Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query,
            field_name="is_active",
            lookup="exact",
            value="True",
            runtime_parameter=True,
        )

        self.column_template = ColumnTemplate.objects.create(
            dataspace=self.dataspace, name="license keys and names", content_type=license_ct
        )
        ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=self.column_template,
            field_name="key",
            display_name="",
            seq=0,
        )
        ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=self.column_template,
            field_name="short_name",
            display_name="",
            seq=1,
        )
        ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=self.column_template,
            field_name="name",
            display_name="",
            seq=2,
        )

        self.report = Report.objects.create(
            name="License list for analysis",
            query=self.query,
            column_template=self.column_template,
            user_available=False,
        )

    def test_report_exports_all_records_not_just_the_first_page(self):
        self.client.login(username="test", password="t3st")

        url = self.report.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual(150, len(response.context_data["view"].object_list))
        self.assertEqual(
            100,
            response.context_data["view"].get_paginate_by(
                response.context_data["view"].object_list
            ),
        )
        self.assertEqual(100, len(response.context_data["output"]))

        url = self.report.get_absolute_url() + "?format=html"
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual(150, len(response.context_data["view"].object_list))
        self.assertEqual(
            None,
            response.context_data["view"].get_paginate_by(
                response.context_data["view"].object_list
            ),
        )
        self.assertEqual(150, len(response.context_data["output"]))

    def test_report_exports_do_not_include_outside_resources(self):
        self.client.login(username="test", password="t3st")
        css_link = "/static/fontawesome-free-6.5.1/css/all.min.css"

        url = self.report.get_absolute_url()
        response = self.client.get(url)
        self.assertContains(response, css_link)

        response = self.client.get(url + "?format=doc")
        self.assertNotContains(response, css_link)
        self.assertNotContains(response, 'rel="stylesheet"')

        response = self.client.get(url + "?format=html")
        self.assertNotContains(response, css_link)
        self.assertNotContains(response, 'rel="stylesheet"')

        response = self.client.get(url + "?format=json")
        self.assertNotContains(response, css_link)
        self.assertNotContains(response, 'rel="stylesheet"')

        response = self.client.get(url + "?format=xls")
        self.assertNotContains(response, css_link)
        self.assertNotContains(response, 'rel="stylesheet"')

        response = self.client.get(url + "?format=yaml")
        self.assertNotContains(response, css_link)
        self.assertNotContains(response, 'rel="stylesheet"')

        response = self.client.get(url + "?format=xlsx")
        self.assertEqual(200, response.status_code)

    def test_using_m2m_with_no_records_in_a_column_template(self):
        component = Component.objects.create(name="c1", owner=self.owner, dataspace=self.dataspace)
        self.assertEqual(0, component.children.count())

        query = Query.objects.create(
            dataspace=self.dataspace,
            name="a component query",
            content_type=self.component_ct,
            operator="and",
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="id",
            lookup="exact",
            value=str(component.pk),
        )

        column_template = ColumnTemplate.objects.create(
            dataspace=self.dataspace, name="a column template", content_type=self.component_ct
        )
        ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=column_template,
            field_name="children",
            display_name="",
            seq=0,
        )

        report = Report.objects.create(
            name="a report", query=query, column_template=column_template
        )

        self.client.login(username="test", password="t3st")

        url = report.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)

    def test_run_report_view_query_filter_syntax_error(self):
        self.client.login(username="test", password="t3st")
        url = self.report.get_absolute_url()

        self.filter1.field_name = "this_does_not_exist"
        self.filter1.runtime_parameter = False
        self.filter1.save()
        self.assertIn(self.filter1, self.report.query.filters.all())

        with self.assertRaises(FieldDoesNotExist):
            self.query.get_qs()

        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "<strong>Errors:</strong>")
        self.assertContains(response, "<li>License has no field named")

        self.filter1.runtime_parameter = True
        self.filter1.save()
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "<strong>Errors:</strong>")
        self.assertContains(response, "<li>License has no field named")

    def test_access_run_report_view_when_same_uuid_across_dataspace(self):
        self.client.login(username="test", password="t3st")
        # Let's copy the report in another dataspace, so we have 2 report with
        # the same uuid in the db.
        other_dataspace = Dataspace.objects.create(name="other")
        copied_report = copy_object(self.report, other_dataspace, self.user)
        self.assertEqual(self.report.uuid, copied_report.uuid)
        self.assertNotEqual(self.report.dataspace, copied_report.dataspace)

        # The QS is dataspace scoped to get the proper report.
        url = self.report.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)

        for obj in response.context_data["object_list"]:
            self.assertEqual(self.dataspace, obj.dataspace)

        with self.assertRaises(NoReverseMatch):
            reverse("reporting:report_details", args=[copied_report.pk])

    def test_only_staff_can_see_non_user_available_report(self):
        self.assertEqual(True, self.user.is_staff)
        self.assertEqual(False, self.report.user_available)

        self.client.login(username="test", password="t3st")
        url = self.report.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)

        self.user.is_staff = False
        self.user.save()
        self.assertEqual(False, self.user.is_staff)

        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_non_staff_can_see_user_available_report(self):
        self.user.is_staff = False
        self.user.save()
        self.assertEqual(False, self.user.is_staff)

        self.report.user_available = True
        self.report.save()
        self.assertEqual(True, self.report.user_available)

        self.client.login(username="test", password="t3st")
        url = self.report.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)

    def test_nobody_can_see_report_from_another_dataspace(self):
        dataspace2 = Dataspace.objects.create(name="Another Dataspace")
        user2 = get_user_model().objects.create_user("user2", "user2@user2.com", "pass", dataspace2)

        self.assertNotEqual(self.report.dataspace, user2.dataspace)
        self.client.login(username="user2", password="pass")
        url = self.report.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_runtime_parameter(self):
        self.client.login(username="test", password="t3st")

        url = (
            self.report.get_absolute_url()
            + "?runtime_filters-0-value=False&runtime_filters-TOTAL_FORMS=1&"
            "runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual(50, len(response.context_data["view"].object_list))

    def test_export_respects_runtime_parameters(self):
        self.client.login(username="test", password="t3st")

        url = (
            self.report.get_absolute_url()
            + "?runtime_filters-0-value=False&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)

        expected = """
        <input type="hidden" name="runtime_filters-0-value" value="False">
        <input type="hidden" name="runtime_filters-INITIAL_FORMS" value="1">
        <input type="hidden" name="runtime_filters-MAX_NUM_FORMS" value="1000">
        <input type="hidden" name="runtime_filters-TOTAL_FORMS" value="1">
        """
        self.assertContains(response, expected, html=True)

    def test_having_an_empty_override_value_does_not_cause_the_query_to_be_wrong(self):
        license_ct = ContentType.objects.get_for_model(License)
        query = Query.objects.create(
            dataspace=self.dataspace,
            name="List of Licenses",
            content_type=license_ct,
            operator="or",
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="name",
            lookup="in",
            value="",
            runtime_parameter=True,
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="short_name",
            lookup="in",
            value="",
            runtime_parameter=True,
        )

        report = Report.objects.create(
            name="All-Purpose License List",
            query=query,
            column_template=self.column_template,
            user_available=False,
        )

        self.client.login(username="test", password="t3st")

        url = (
            report.get_absolute_url() + "?runtime_filters-0-value=&runtime_filters-1-value=%5B%27"
            "license_1%27%2C%27license_2%27%2C%27license_3%27%5D"
            "&runtime_filters-TOTAL_FORMS=2&runtime_filters-INITIAL_FORMS=2"
            "&runtime_filters-MAX_NUM_FORMS=1000"
        )
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual([{}, {}], response.context_data["runtime_filter_formset"].errors)

    def test_run_report_view_lookup_displayed_value(self):
        self.client.login(username="test", password="t3st")
        filter1 = self.report.query.filters.first()
        filter1.lookup = "iexact"
        filter1.field_name = "short_name"
        filter1.save()
        response = self.client.get(self.report.get_absolute_url())
        self.assertContains(response, "Case-insensitive exact match.")

    def test_run_report_view_results_count(self):
        self.client.login(username="test", password="t3st")
        response = self.client.get(self.report.get_absolute_url())
        self.assertContains(response, "<p>Showing 100 results on 150 total.</p>")

        url = (
            self.report.get_absolute_url()
            + "?runtime_filters-0-value=False&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        response = self.client.get(url)
        self.assertContains(response, "<p>Showing 50 results on 50 total.</p>")

    def test_report_get_absolute_url(self):
        self.assertEqual("/reports/{}/".format(self.report.uuid), self.report.get_absolute_url())

    def test_report_view_get_json_response(self):
        self.client.login(username="test", password="t3st")
        url = self.report.get_absolute_url() + "?format=json"
        response = self.client.get(url)
        self.assertEqual(
            response["Content-Disposition"], 'attachment; filename="license-list-for-analysis.json"'
        )
        self.assertEqual(response["Content-Type"], "application/json")

        # Respecting the sequence ordering of the column_template.fields
        self.assertEqual(
            ["key", "short_name", "name"],
            list(self.column_template.fields.all().values_list("field_name", flat=True)),
        )
        self.assertEqual(
            [0, 1, 2], list(self.column_template.fields.all().values_list("seq", flat=True))
        )

        # In case of a change: print repr(response.content)
        expected = (
            "{\n    "
            '"key": "license_126",\n    '
            '"short_name": "license_126",\n    '
            '"name": "license_126"\n  '
            "}"
        )
        self.assertContains(response, expected)

    def test_report_view_get_yaml_response(self):
        self.client.login(username="test", password="t3st")
        url = self.report.get_absolute_url() + "?format=yaml"
        response = self.client.get(url)
        self.assertEqual(
            response["Content-Disposition"], 'attachment; filename="license-list-for-analysis.yaml"'
        )
        self.assertEqual(response["Content-Type"], "application/x-yaml")

        # In case of a change: >>> print repr(response.content)
        expected = "- key: license_138\n  short_name: license_138\n  name: license_138\n"
        self.assertContains(response, expected)

    def test_run_report_view_runtime_parameters_value_fields(self):
        self.client.login(username="test", password="t3st")

        default = {
            "query": self.query,
            "dataspace": self.dataspace,
            "runtime_parameter": True,
        }

        # Inserting all the different type of Fields.
        Filter.objects.create(field_name="full_text", lookup="contains", **default)
        Filter.objects.create(field_name="keywords", lookup="in", **default)
        Filter.objects.create(field_name="name", lookup="exact", **default)
        Filter.objects.create(field_name="key", lookup="contains", **default)
        Filter.objects.create(field_name="reviewed", lookup="exact", **default)

        expected1 = """
        <tr>
          <td>is_active</td>
          <td>Exact match. (e.g.: apache-2.0)</td>
          <td></td>
          <td><select name="runtime_filters-0-value"
               placeholder="Boolean (Either True or False)"
               class="form-control input-block-level" id="id_runtime_filters-0-value">
            <option value="0">All</option>
            <option value="1">Unknown</option>
            <option value="2" selected>Yes</option>
            <option value="3">No</option>
          </select></td>
        </tr>
        """

        expected2 = """
        <tr>
          <td>full_text</td>
          <td>Case-sensitive containment test. (e.g.: apache)</td>
          <td></td>
          <td><textarea name="runtime_filters-1-value" cols="40" rows="4"
               placeholder="Text" class="form-control input-block-level"
               id="id_runtime_filters-1-value">
          </textarea></td>
        </tr>
        """

        expected3 = """
        <tr>
          <td>keywords</td>
          <td>In a given list. (e.g.: [&quot;apache-1.1&quot;, &quot;apache-2.0&quot;])</td>
          <td></td>
          <td><textarea name="runtime_filters-2-value" cols="40" rows="4"
               placeholder="[&#39;name-1&#39;, &#39;name-2&#39;, ...]"
               class="form-control input-block-level" id="id_runtime_filters-2-value">
          </textarea></td>
        </tr>
        """

        expected4 = """
        <tr>
          <td>name</td>
          <td>Exact match. (e.g.: apache-2.0)</td>
          <td></td>
          <td><input type="text" name="runtime_filters-3-value"
               placeholder="String (up to 100)" class="form-control input-block-level"
               id="id_runtime_filters-3-value" /></td>
        </tr>
        """

        expected5 = """
        <tr>
          <td>key</td>
          <td>Case-sensitive containment test. (e.g.: apache)</td>
          <td></td>
          <td><input type="text" name="runtime_filters-4-value"
          placeholder="Letters, numbers, underscores or hyphens; e.g. &quot;apache-2.0&quot;"
          class="form-control input-block-level" id="id_runtime_filters-4-value" />
          </td>
        </tr>
        """

        expected6 = """
        <tr>
          <td>reviewed</td>
          <td>Exact match. (e.g.: apache-2.0)</td>
          <td></td>
          <td><select name="runtime_filters-5-value"
               placeholder="Boolean (Either True or False)"
               class="form-control input-block-level" id="id_runtime_filters-5-value">
          <option value="0" selected>All</option>
          <option value="2">Yes</option>
          <option value="3">No</option>
          </select></td>
        </tr>
        """

        response = self.client.get(self.report.get_absolute_url())
        self.assertContains(response, expected1, html=True)
        self.assertContains(response, expected2, html=True)
        self.assertContains(response, expected3, html=True)
        self.assertContains(response, expected4, html=True)
        self.assertContains(response, expected5, html=True)
        self.assertContains(response, expected6, html=True)

    def test_run_report_view_pagination_without_formset_management_params(self):
        self.client.login(username="test", password="t3st")

        base_report_url = self.report.get_absolute_url()
        response = self.client.get(base_report_url)
        expected = """
        <nav aria-label="Page navigation">
          <ul class="pagination pagination-sm">
              <li class="page-item disabled">
                <span class="page-link">&laquo;</span>
              </li>
            <li class="page-item disabled">
              <span class="page-link">Page 1 of 2</span>
            </li>
              <li class="page-item">
                <a class="page-link" href="?page=2" aria-label="Next">
                  <span aria-hidden="true">&raquo;</span>
                  <span class="sr-only">Next</span>
                </a>
              </li>
          </ul>
        </nav>
        """
        self.assertContains(response, expected, html=True)
        response = self.client.get(base_report_url + "?page=1")
        self.assertContains(response, expected, html=True)

        response = self.client.get(base_report_url + "?page=2")
        expected = """
        <nav aria-label="Page navigation">
          <ul class="pagination pagination-sm">
              <li class="page-item">
                <a class="page-link" href="?page=1" aria-label="Previous">
                  <span aria-hidden="true">&laquo;</span>
                  <span class="sr-only">Previous</span>
                </a>
              </li>
            <li class="page-item disabled">
              <span class="page-link">Page 2 of 2</span>
            </li>
              <li class="page-item disabled">
                <span class="page-link">&raquo;</span>
              </li>
          </ul>
        </nav>
        """
        self.assertContains(response, expected, html=True)

    def test_run_report_view_pagination_with_formset_management_params(self):
        self.client.login(username="test", password="t3st")

        base_report_url = self.report.get_absolute_url()
        params = (
            "?runtime_filters-0-value=True&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        response = self.client.get(base_report_url + params)
        query = (
            "?runtime_filters-0-value=True&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
            "&page=2"
        )
        expected = f"""
        <nav aria-label="Page navigation">
          <ul class="pagination pagination-sm">
              <li class="page-item disabled">
                <span class="page-link">&laquo;</span>
              </li>
            <li class="page-item disabled">
              <span class="page-link">Page 1 of 2</span>
            </li>
              <li class="page-item">
                <a class="page-link" href="{query}" aria-label="Next">
                  <span aria-hidden="true">&raquo;</span>
                  <span class="sr-only">Next</span>
                </a>
              </li>
          </ul>
        </nav>
        """
        self.assertContains(response, expected, html=True)

        response = self.client.get(base_report_url + params + "&page=1")
        # The params order is a little different when page=1 is explicitly given
        query = (
            "?runtime_filters-0-value=True&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
            "&page=2"
        )
        expected = f"""
        <nav aria-label="Page navigation">
          <ul class="pagination pagination-sm">
              <li class="page-item disabled">
                <span class="page-link">&laquo;</span>
              </li>
            <li class="page-item disabled">
              <span class="page-link">Page 1 of 2</span>
            </li>
              <li class="page-item">
                <a class="page-link" href="{query}" aria-label="Next">
                  <span aria-hidden="true">&raquo;</span>
                  <span class="sr-only">Next</span>
                </a>
              </li>
          </ul>
        </nav>
        """
        self.assertContains(response, expected, html=True)

        response = self.client.get(base_report_url + params + "&page=2")
        query = (
            "?runtime_filters-0-value=True&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
            "&page=1"
        )
        expected = f"""
        <nav aria-label="Page navigation">
          <ul class="pagination pagination-sm">
              <li class="page-item">
                <a class="page-link" href="{query}" aria-label="Previous">
                  <span aria-hidden="true">&laquo;</span>
                  <span class="sr-only">Previous</span>
                </a>
              </li>
            <li class="page-item disabled">
              <span class="page-link">Page 2 of 2</span>
            </li>
              <li class="page-item disabled">
                <span class="page-link">&raquo;</span>
              </li>
          </ul>
        </nav>
        """
        self.assertContains(response, expected, html=True)

    @patch("reporting.views.ReportDetailsView.get_paginate_by")
    def test_run_report_view_pagination_section(self, mock_get_paginate_by):
        # Required as the pagination is only noticeable for more than 10 pages
        mock_get_paginate_by.return_value = 5

        self.client.login(username="test", password="t3st")
        response = self.client.get(self.report.get_absolute_url())

        expected = """
        <nav aria-label="Page navigation">
          <ul class="pagination pagination-sm">
              <li class="page-item disabled">
                <span class="page-link">&laquo;</span>
              </li>
            <li class="page-item disabled">
              <span class="page-link">Page 1 of 30</span>
            </li>
              <li class="page-item">
                <a class="page-link" href="?page=2" aria-label="Next">
                  <span aria-hidden="true">&raquo;</span>
                  <span class="sr-only">Next</span>
                </a>
              </li>
          </ul>
        </nav>
        """
        self.assertContains(response, expected, html=True)

    def test_run_report_view_with_runtime_parameters_error(self):
        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query,
            field_name="key",
            lookup="exact",
            value="",
            runtime_parameter=True,
        )

        self.client.login(username="test", password="t3st")
        base_report_url = self.report.get_absolute_url()
        params = (
            "?runtime_filters-0-value=True&runtime_filters-1-value=a a"
            "&runtime_filters-TOTAL_FORMS=2&runtime_filters-INITIAL_FORMS=2"
            "&runtime_filters-MAX_NUM_FORMS=1000"
        )
        response = self.client.get(base_report_url + params)

        expected = """
        <ul class="mb-0">
            <li>
                Enter a valid &#39;slug&#39; consisting of letters, numbers,
                underscores, dots or hyphens.
            </li>
        </ul>
        """
        self.assertContains(response, expected, html=True)

    def test_run_report_view_runtime_parameters_choices_for_boolean(self):
        self.client.login(username="test", password="t3st")

        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query,
            field_name="is_component_license",
            lookup="exact",
            value="",
            runtime_parameter=True,
        )
        response = self.client.get(self.report.get_absolute_url())
        expected = """
        <select name="runtime_filters-1-value"
                placeholder="Boolean (Either True or False)"
                class="form-control input-block-level"
                id="id_runtime_filters-1-value">
          <option value="0" selected>All</option>
          <option value="2">Yes</option>
          <option value="3">No</option>
        </select>
        """
        self.assertContains(response, expected, html=True)

    def test_run_report_view_runtime_parameters_choices_for_boolean_with_default_value(self):
        self.client.login(username="test", password="t3st")

        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query,
            field_name="is_component_license",
            lookup="exact",
            value="True",
            runtime_parameter=True,
        )
        response = self.client.get(self.report.get_absolute_url())
        expected = """
        <select name="runtime_filters-0-value"
                placeholder="Boolean (Either True or False)"
                class="form-control input-block-level"
                id="id_runtime_filters-0-value">
          <option value="0">All</option>
          <option value="1">Unknown</option>
          <option value="2" selected>Yes</option>
          <option value="3">No</option>
        </select>
        """
        self.assertContains(response, expected, html=True)

    def test_run_report_view_with_given_runtime_parameters_for_boolean(self):
        self.client.login(username="test", password="t3st")
        base_report_url = self.report.get_absolute_url()

        self.filter1.delete()
        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query,
            field_name="is_component_license",
            lookup="exact",
            value="",
            runtime_parameter=True,
        )

        License.objects.scope(self.dataspace).filter(is_active=True).update(
            is_component_license=True
        )
        License.objects.scope(self.dataspace).filter(is_active=False).update(
            is_component_license=False
        )

        # All, no value provided
        response = self.client.get(base_report_url)
        self.assertContains(response, "Showing 0 results on 0 total.")

        # True
        response = self.client.get(
            base_report_url + "?runtime_filters-0-value=2&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        self.assertContains(
            response,
            "Showing 100 results on {} total.".format(
                License.objects.scope(self.dataspace).filter(is_component_license=True).count()
            ),
        )

        # False
        response = self.client.get(
            base_report_url + "?runtime_filters-0-value=3&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        self.assertContains(
            response,
            "Showing 50 results on {} total.".format(
                License.objects.scope(self.dataspace).filter(is_component_license=False).count()
            ),
        )

        # Not supported value, same as All.
        response = self.client.get(
            base_report_url + "?runtime_filters-0-value=WRONG&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        self.assertContains(response, "Showing 0 results on 0 total.")

    def test_run_report_view_runtime_parameters_choices_for_null_boolean(self):
        self.client.login(username="test", password="t3st")

        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query,
            field_name="is_active",
            lookup="exact",
            value="",
            runtime_parameter=True,
        )
        response = self.client.get(self.report.get_absolute_url())
        expected = """
        <select name="runtime_filters-1-value"
                placeholder="Boolean (Either True or False)"
                class="form-control input-block-level"
                id="id_runtime_filters-1-value">
          <option value="0" selected>All</option>
          <option value="1">Unknown</option>
          <option value="2">Yes</option>
          <option value="3">No</option>
        </select>
        """
        self.assertContains(response, expected, html=True)

    def test_run_report_view_runtime_parameters_choices_for_nullboolean_with_default_value(self):
        self.client.login(username="test", password="t3st")

        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query,
            field_name="is_active",
            lookup="exact",
            value="True",
            runtime_parameter=True,
        )
        response = self.client.get(self.report.get_absolute_url())
        expected = """
        <select name="runtime_filters-0-value"
                placeholder="Boolean (Either True or False)"
                class="form-control input-block-level"
                id="id_runtime_filters-0-value">
          <option value="0">All</option>
          <option value="1">Unknown</option>
          <option value="2" selected>Yes</option>
          <option value="3">No</option>
        </select>
        """
        self.assertContains(response, expected, html=True)

    def test_run_report_view_with_given_runtime_parameters_for_nullboolean(self):
        self.client.login(username="test", password="t3st")
        base_report_url = self.report.get_absolute_url()

        self.filter1.delete()
        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query,
            field_name="is_active",
            lookup="exact",
            value="",
            runtime_parameter=True,
        )

        license = License.objects.scope(self.dataspace)[:1][0]
        license.is_active = None
        license.save()

        # All, no value provided
        response = self.client.get(base_report_url)
        self.assertContains(response, "Showing 0 results on 0 total.")
        response = self.client.get(
            base_report_url + "?runtime_filters-0-value=0&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        self.assertContains(response, "Showing 0 results on 0 total.")

        # True
        response = self.client.get(
            base_report_url + "?runtime_filters-0-value=2&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        self.assertContains(
            response,
            "Showing 100 results on {} total.".format(
                License.objects.scope(self.dataspace).filter(is_active=True).count()
            ),
        )

        # False
        response = self.client.get(
            base_report_url + "?runtime_filters-0-value=3&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        self.assertContains(
            response,
            "Showing 50 results on {} total.".format(
                License.objects.scope(self.dataspace).filter(is_active=False).count()
            ),
        )

        # Unknown/None
        response = self.client.get(
            base_report_url + "?runtime_filters-0-value=1&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        self.assertContains(
            response,
            "Showing 1 result on {} total.".format(
                License.objects.scope(self.dataspace).filter(is_active=None).count()
            ),
        )

        # Not supported value, same as All.
        response = self.client.get(
            base_report_url + "?runtime_filters-0-value=WRONG&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        self.assertContains(response, "Showing 0 results on 0 total.")

    def test_run_report_view_runtime_parameters_choices_for_isnull_lookup(self):
        self.client.login(username="test", password="t3st")

        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query,
            field_name="category",
            lookup="isnull",
            value="",
            runtime_parameter=True,
        )
        response = self.client.get(self.report.get_absolute_url())
        expected = """
        <tr>
            <td>category</td>
            <td>IS NULL. Takes either True or False.</td>
            <td></td>
            <td><select name="runtime_filters-1-value"
                        placeholder="Foreign Key (type determined by related field)"
                        class="form-control input-block-level"
                        id="id_runtime_filters-1-value">
                <option value="0" selected>All</option>
                <option value="2">Yes</option>
                <option value="3">No</option>
            </select></td>
        </tr>
        """
        self.assertContains(response, expected, html=True)

    def test_run_report_view_with_given_runtime_parameters_for_isnull_lookup(self):
        self.client.login(username="test", password="t3st")
        base_report_url = self.report.get_absolute_url()

        self.filter1.delete()
        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query,
            field_name="category",
            lookup="isnull",
            value="",
            runtime_parameter=True,
        )

        category = LicenseCategory.objects.create(label="category1", dataspace=self.dataspace)

        License.objects.scope(self.dataspace).filter(is_active=True).update(category=category)
        License.objects.scope(self.dataspace).filter(is_active=False).update(category=None)

        # All, no value provided
        response = self.client.get(base_report_url)
        self.assertContains(response, "Showing 0 results on 0 total.")

        # True
        response = self.client.get(
            base_report_url + "?runtime_filters-0-value=2&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        self.assertContains(
            response,
            "Showing 50 results on {} total.".format(
                License.objects.scope(self.dataspace).filter(category__isnull=True).count()
            ),
        )

        # False
        response = self.client.get(
            base_report_url + "?runtime_filters-0-value=3&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        self.assertContains(
            response,
            "Showing 100 results on {} total.".format(
                License.objects.scope(self.dataspace).filter(category__isnull=False).count()
            ),
        )

        # Not supported value, same as All.
        response = self.client.get(
            base_report_url + "?runtime_filters-0-value=WRONG&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        self.assertContains(response, "Showing 0 results on 0 total.")

    def test_run_report_view_runtime_parameters_choices_for_isempty_lookup(self):
        self.client.login(username="test", password="t3st")

        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query,
            field_name="spdx_license_key",
            lookup="isempty",
            value="",
            runtime_parameter=True,
        )
        response = self.client.get(self.report.get_absolute_url())
        expected = """
        <tr>
              <td>spdx_license_key</td>
              <td>IS EMPTY. Takes either True or False.</td>
              <td></td>
              <td><select name="runtime_filters-1-value"
                          placeholder="String (up to 50)"
                          class="form-control input-block-level"
                          id="id_runtime_filters-1-value">
          <option value="0" selected>All</option>
          <option value="2">Yes</option>
          <option value="3">No</option>
        </select></td>
        </tr>
        """
        self.assertContains(response, expected, html=True)

    def test_run_report_view_runtime_parameters_default_all_value_for_choice_field(self):
        self.client.login(username="test", password="t3st")

        request_ct = ContentType.objects.get(app_label="workflow", model="request")
        query = Query.objects.create(
            dataspace=self.dataspace, name="query1", content_type=request_ct, operator="and"
        )

        Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="status",
            lookup="exact",
            value="",
            runtime_parameter=True,
        )

        column_template = ColumnTemplate.objects.create(
            dataspace=self.dataspace, name="ct1", content_type=request_ct
        )

        report = Report.objects.create(name="report1", query=query, column_template=column_template)

        response = self.client.get(report.get_absolute_url())
        expected = """
        <select name="runtime_filters-0-value"
                placeholder="String (up to 10)"
                class="form-control input-block-level"
                id="id_runtime_filters-0-value">
          <option value="" selected>All</option>
          <option value="open">Open</option>
          <option value="closed">Closed</option>
          <option value="draft">Draft</option>
        </select>
        """
        self.assertContains(response, expected, html=True)

    def test_run_report_view_with_runtime_parameters_in_list_lookup(self):
        self.client.login(username="test", password="t3st")

        filter_ = self.report.query.filters.last()
        filter_.lookup = "in"
        filter_.runtime_parameter = True
        filter_.save()

        base_report_url = self.report.get_absolute_url()
        params = (
            "?runtime_filters-0-value=string&runtime_filters-TOTAL_FORMS=1"
            "&runtime_filters-INITIAL_FORMS=1&runtime_filters-MAX_NUM_FORMS=1000"
        )
        response = self.client.get(base_report_url + params)

        expected = """
        <ul class="mb-0">
          <li>Invalid value for runtime parameter</li>
        </ul>
        """
        self.assertContains(response, expected, html=True)

    def test_report_list_view_num_queries(self):
        self.client.login(username="test", password="t3st")

        duplicate_report = self.report
        duplicate_report.id = None
        duplicate_report.uuid = uuid.uuid4()
        duplicate_report.name = "DupReport"
        duplicate_report.save()

        self.assertEqual(2, Report.objects.scope(self.report.dataspace).count())

        url = reverse("reporting:report_list")
        # Needed to clear the queries from the License batch creation in setUp
        self.client.get(url)

        with self.assertNumQueries(9):
            self.client.get(url)

    def test_run_report_view_query_using_related_fields(self):
        self.client.login(username="test", password="t3st")
        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query,
            field_name="annotations",
            lookup="isnull",
            value="True",
            runtime_parameter=True,
        )
        response = self.client.get(self.report.get_absolute_url())
        self.assertEqual(100, len(response.context_data["object_list"]))

    def test_run_report_product_inventory_item(self):
        self.client.login(username="test", password="t3st")
        inventory_item_ct = ContentType.objects.get_for_model(ProductInventoryItem)
        query = Query.objects.create(
            dataspace=self.dataspace,
            name="inventory",
            content_type=inventory_item_ct,
            operator="and",
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="item_type",
            lookup="exact",
            value="component",
        )

        column_template = ColumnTemplate.objects.create(
            dataspace=self.dataspace,
            name="inventory",
            content_type=inventory_item_ct,
        )
        ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=column_template,
            field_name="item",
            display_name="",
            seq=0,
        )

        report = Report.objects.create(
            name="inventory",
            query=query,
            column_template=column_template,
        )

        product = Product.objects.create(name="p1", dataspace=self.dataspace)
        component = Component.objects.create(name="c1", dataspace=self.dataspace)
        ProductComponent.objects.create(
            product=product, component=component, dataspace=self.dataspace
        )

        response = self.client.get(report.get_absolute_url())
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, len(response.context_data["view"].object_list))
        item = response.context_data["view"].object_list.get()
        self.assertEqual(component.id, item.component_id)
        self.assertEqual(f"{component.name} {component.version}", item.item)
        self.assertEqual("component", item.item_type)
        self.assertIsNone(item.package_id)
