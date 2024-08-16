#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.admin.options import IS_POPUP_VAR
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import NON_FIELD_ERRORS
from django.test import TestCase
from django.urls import reverse

from component_catalog.models import Component
from dje.models import Dataspace
from license_library.models import License
from organization.models import Owner
from reporting.models import ColumnTemplate
from reporting.models import ColumnTemplateAssignedField
from reporting.models import Filter
from reporting.models import OrderField
from reporting.models import Query
from reporting.models import Report


class ReportingAdminViewsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.owner = Owner.objects.create(
            name="Owner", dataspace=self.dataspace)
        self.user = get_user_model().objects.create_superuser(
            "test", "test@test.com", "t3st", self.dataspace
        )

        self.license_ct = ContentType.objects.get_for_model(License)
        self.component_ct = ContentType.objects.get_for_model(Component)
        self.query1 = Query.objects.create(
            dataspace=self.dataspace, name="Q1", content_type=self.component_ct, operator="and"
        )
        self.column_template1 = ColumnTemplate.objects.create(
            name="CT1", dataspace=self.dataspace, content_type=self.component_ct
        )
        self.report1 = Report.objects.create(
            name="Report1", query=self.query1, column_template=self.column_template1
        )

    def test_save_query(self):
        query = Query.objects.create(
            dataspace=self.dataspace,
            name="GPL2-related licenses",
            content_type=self.license_ct,
            operator="and",
        )
        filter1 = Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="licenseassignedtag__license_tag__label",
            lookup="exact",
            value="Network Redistribution",
        )
        filter2 = Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="licenseassignedtag__value",
            lookup="exact",
            value="True",
        )

        self.client.login(username="test", password="t3st")
        url = query.get_admin_url()
        data = {
            "name": query.name,
            "description": query.description,
            "content_type": self.license_ct.pk,
            "operator": query.operator,
            "filters-INITIAL_FORMS": 2,
            "filters-TOTAL_FORMS": 2,
            "filters-0-id": filter1.pk,
            "filters-0-field_name": "licenseassignedtag__license_tag__text",
            "filters-0-lookup": "exact",
            "filters-0-value": "Network Redistribution",
            "filters-1-id": filter2.pk,
            "filters-1-field_name": "licenseassignedtag__value",
            "filters-1-lookup": "exact",
            "filters-1-value": "True",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        filter1.refresh_from_db()
        self.assertEqual(
            "licenseassignedtag__license_tag__text", filter1.field_name)

    def test_save_new_query_get_filters_as_dicts(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")

        data = {
            "name": "",
            "description": "",
            "content_type": "",
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "",
            "filters-0-lookup": "",
            "filters-0-value": "",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = {
            "name": ["This field is required."],
            "content_type": ["This field is required."],
        }
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

    def test_save_new_query_validate_lookup_type_when_invalid_query_form(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")

        data = {
            "name": "",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "key",
            "filters-0-lookup": "contains",
            "filters-0-value": "1",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = {
            "name": ["This field is required."],
        }
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

    def test_save_new_query_get_order_fields_as_dicts(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")

        data = {
            "name": "aaaaa",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 0,
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 1,
            "order_fields-0-id": "",
            "order_fields-0-field_name": "",
            "order_fields-0-seq": "",
            "order_fields-0-sort": "ascending",
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_save_new_column_template_get_column_template_assigned_fields_as_dicts_issue(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_columntemplate_add")
        data = {
            "name": "",
            "description": "",
            "content_type": "",
            "fields-INITIAL_FORMS": "0",
            "fields-TOTAL_FORMS": "1",
            "fields-0-display_name": "",
            "fields-0-field_name": "",
            "fields-0-id": "",
            "fields-0-seq": "",
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = {
            "name": ["This field is required."],
            "content_type": ["This field is required."],
        }
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

    def test_save_new_column_template_invalid_field_name(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_columntemplate_add")
        data = {
            "name": "aaa",
            "description": "",
            "content_type": self.license_ct.pk,
            "fields-INITIAL_FORMS": "0",
            "fields-TOTAL_FORMS": "1",
            "fields-0-field_name": "INVALID",
            "fields-0-seq": "0",
            "fields-0-id": "",
            "fields-0-display_name": "",
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            True,
            response.context["client_data"]["column_template_assigned_field_formset_has_errors"],
        )

        data["fields-0-field_name"] = "INVALID__last"
        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            True,
            response.context["client_data"]["column_template_assigned_field_formset_has_errors"],
        )

        data["fields-0-field_name"] = "created_by__password"
        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            True,
            response.context["client_data"]["column_template_assigned_field_formset_has_errors"],
        )

        data["fields-0-field_name"] = "created_by__username"
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_save_report_with_non_matching_content_types_for_query_and_column_template(self):
        query = Query.objects.create(
            dataspace=self.dataspace,
            name="GPL2-related licenses",
            content_type=self.license_ct,
            operator="and",
        )

        component_ct = ContentType.objects.get_for_model(Component)
        column_template = ColumnTemplate.objects.create(
            name="CT2", dataspace=self.dataspace, content_type=component_ct
        )

        # The content types do not match
        self.assertNotEqual(query.content_type, column_template.content_type)

        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_report_add")
        data = {
            "name": "A really cool report",
            "query": query.pk,
            "column_template": column_template.pk,
            "user_available": True,
            "report_context": "",
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = {
            "column_template": ["The query and column template must have matching object types."],
            "query": ["The query and column template must have matching object types."],
            NON_FIELD_ERRORS: [
                "The query and column template must have matching object types. "
                "The query has an object type of license. "
                "The column template has an object type of component."
            ],
        }
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

    def test_save_report_missing_required_field_values(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_report_add")
        data = {
            "name": "",
            "query": "",
            "column_template": "",
            "report_context": "",
        }
        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = {
            "column_template": ["This field is required."],
            "query": ["This field is required."],
            "name": ["This field is required."],
        }
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

    def test_save_report_with_an_existing_name(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_report_add")
        data = {
            "name": self.report1.name,
            "query": self.query1.id,
            "column_template": self.column_template1.id,
        }
        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = {NON_FIELD_ERRORS: [
            "Report with this Dataspace and Name already exists."]}
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

    def test_raise_error_for_invalid_Filter_field(self):
        query = Query.objects.create(
            dataspace=self.dataspace,
            name="GPL2-related licenses",
            content_type=self.license_ct,
            operator="and",
        )
        filter1 = Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="licenseassignedtag__license_tag__label",
            lookup="exact",
            value="Network Redistribution",
        )

        self.client.login(username="test", password="t3st")
        url = query.get_admin_url()
        data = {
            "name": query.name,
            "description": query.description,
            "content_type": self.license_ct.pk,
            "operator": query.operator,
            "filters-INITIAL_FORMS": 1,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": filter1.pk,
            "filters-0-field_name": "dataspace__name",
            "filters-0-lookup": "exact",
            "filters-0-value": "nexB",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [{NON_FIELD_ERRORS: ["Invalid field value"]}]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][0].formset.errors)

    def test_raise_error_for_invalid_boolean_field_with_iexact_filter(self):
        # A boolean field fails with iexact on Postgres.
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")
        data = {
            "name": "aaaaa",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "is_active",
            "filters-0-lookup": "iexact",
            "filters-0-value": "True",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [
            {NON_FIELD_ERRORS: ['Lookup "iexact" on Boolean field is not supported']}]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][0].formset.errors)

    def test_raise_error_for_isnull_lookup_with_non_nullable_field(self):
        # A boolean field fails with iexact on Postgres.
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")
        data = {
            "name": "aaaaa",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "short_name",
            "filters-0-lookup": "isnull",
            "filters-0-value": "True",
            # GenericRelation are supported
            "filters-1-id": "",
            "filters-1-field_name": "external_references",
            "filters-1-lookup": "isnull",
            "filters-1-value": "True",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [
            {
                NON_FIELD_ERRORS: [
                    'Lookup "isnull" is only supported on nullable fields. '
                    'A "isempty" lookup is available for non-nullable fields'
                ]
            }
        ]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][0].formset.errors)

        data["filters-0-field_name"] = "category"
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_raise_error_for_isnull_lookup_with_non_valid_value(self):
        # A boolean field fails with iexact on Postgres.
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")
        data = {
            "name": "aaaaa",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "category",
            "filters-0-lookup": "isnull",
            "filters-0-value": "NONVALID",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [
            {
                NON_FIELD_ERRORS: [
                    '"NONVALID" is not a valid value for the isnull lookup. Use True or False'
                ]
            }
        ]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][0].formset.errors)

        data["filters-0-value"] = "True"
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_query_addition_isnull_lookup_allowed_on_m2o_and_m2m(self):
        # A boolean field fails with iexact on Postgres.
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")
        data = {
            "name": "aaaaa",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 2,
            "filters-0-id": "",
            "filters-0-field_name": "tags",  # m2m
            "filters-0-lookup": "isnull",
            "filters-0-value": "True",
            "filters-1-id": "",
            "filters-1-field_name": "licenseassignedtag",  # m2o
            "filters-1-lookup": "isnull",
            "filters-1-value": "True",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_raise_error_for_isempty_lookup_with_non_blank_or_related_field(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")
        data = {
            "name": "aaaaa",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "name",
            "filters-0-lookup": "isempty",
            "filters-0-value": "True",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [
            {NON_FIELD_ERRORS: [
                'Lookup "isempty" is only supported on blank-able fields.']}
        ]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][0].formset.errors)

        data["filters-0-field_name"] = "category"
        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [
            {NON_FIELD_ERRORS: ['Lookup "isempty" is not supported on related fields.']}]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][0].formset.errors)

        data["filters-0-field_name"] = "annotations"
        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [
            {NON_FIELD_ERRORS: ['Lookup "isempty" is not supported on related fields.']}]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][0].formset.errors)

        data["filters-0-field_name"] = "spdx_license_key"
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_raise_error_for_isempty_lookup_with_non_valid_value(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")
        data = {
            "name": "aaaaa",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "spdx_license_key",
            "filters-0-lookup": "isempty",
            "filters-0-value": "NONVALID",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [
            {
                NON_FIELD_ERRORS: [
                    '"NONVALID" is not a valid value for the isempty lookup. Use True or False'
                ]
            }
        ]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][0].formset.errors)

        data["filters-0-value"] = "True"
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_raise_error_for_invalid_ColumnTemplateAssignedField_field_name(self):
        column_template = ColumnTemplate.objects.create(
            name="ct1", dataspace=self.dataspace, content_type=self.license_ct
        )
        field = ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=column_template,
            field_name="owner__name",
            display_name="Owner Name",
            seq=0,
        )

        self.client.login(username="test", password="t3st")
        url = column_template.get_admin_url()
        data = {
            "name": column_template.name,
            "description": column_template.description,
            "content_type": self.license_ct.pk,
            "fields-INITIAL_FORMS": 1,
            "fields-TOTAL_FORMS": 1,
            "fields-0-id": field.pk,
            "fields-0-field_name": "dataspace__name",
            "fields-0-display_name": "Dataspace Name",
            "fields-0-seq": "0",
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [{"field_name": ["Invalid field value"]}]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][0].formset.errors)

    def test_raise_error_for_invalid_field_type_with_descendant_lookup(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")
        data = {
            "name": "aaaaa",
            "description": "",
            "content_type": self.component_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "name",
            "filters-0-lookup": "descendant",
            "filters-0-value": "",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [
            {NON_FIELD_ERRORS: ['Lookup "descendant" only supported on "id" field.']}]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][0].formset.errors)

        data["filters-0-field_name"] = "id"
        self.client.post(url, data)
        self.assertTrue(Query.objects.get(name="aaaaa"))

    def test_raise_error_for_invalid_model_with_descendant_lookup(self):
        # Not supported on License
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")
        data = {
            "name": "aaaaa",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "id",
            "filters-0-lookup": "descendant",
            "filters-0-value": "",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [
            {NON_FIELD_ERRORS: [
                'Lookup "descendant" only supported on models with hierarchy.']}
        ]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][0].formset.errors)

        data["content_type"] = ContentType.objects.get_for_model(Component).pk
        self.client.post(url, data)
        self.assertTrue(Query.objects.get(name="aaaaa"))

    def test_raise_error_for_invalid_model_with_product_descendant_lookup(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")
        data = {
            "name": "aaaaa",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "id",
            "filters-0-lookup": "product_descendant",
            "filters-0-value": "",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [
            {
                NON_FIELD_ERRORS: [
                    'Lookup "product_descendant" only supported on Component object type.'
                ]
            }
        ]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][0].formset.errors)

        data["content_type"] = ContentType.objects.get_for_model(Component).pk
        self.client.post(url, data)
        self.assertTrue(Query.objects.get(name="aaaaa"))

    def test_save_query_for_license_name_in_a_list(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")
        value = """
        ['Artistic License (Perl) 1.0', 'Artistic License 1.0','BSD-Original-UC',
        'BSD-Simplified','Dynamic Drive Terms of Use','FancyZoom License','GPL 1.0',
        'GPL 2.0','LGPL 2.0','OpenSSL/SSLeay License',
        'Original SSLeay License with Windows exception','Qpopper License',
        'RSA Data Security MD5','Sendmail License','Sun RPC License',
        'Technische Universitaet Berlin Attribution License',
        'TripTracker slideshow License','Unlicense','ZLIB License','MPL 1.1']
        """
        data = {
            "name": "The Name",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "name",
            "filters-0-lookup": "in",
            "filters-0-value": value,
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_save_column_template_with_zero_column_template_assigned_fields(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_columntemplate_add")
        data = {
            "name": "Foobar",
            "description": "",
            "content_type": self.license_ct.pk,
            "fields-INITIAL_FORMS": "0",
            "fields-TOTAL_FORMS": "1",
            "fields-0-display_name": "",
            "fields-0-field_name": "",
            "fields-0-id": "",
            "fields-0-seq": "",
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_invalid_add_query(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")
        data = {
            "name": "The Name",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            # Omit field
            "filters-0-field_name": "",
            "filters-0-lookup": "exact",
            "filters-0-value": "",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(
            True, response.context["client_data"]["filter_formset_has_errors"])

        data = {
            "name": "The Name",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "name",
            # Omit lookup
            "filters-0-lookup": "",
            "filters-0-value": "",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(
            True, response.context["client_data"]["filter_formset_has_errors"])

    def test_invalid_add_column_template(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_columntemplate_add")
        data = {
            "name": "Foobar",
            "description": "",
            "content_type": self.license_ct.pk,
            "fields-INITIAL_FORMS": "0",
            "fields-TOTAL_FORMS": "1",
            "fields-0-display_name": "",
            # Omit field_name
            "fields-0-field_name": "",
            "fields-0-id": "",
            "fields-0-seq": "0",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(
            True,
            response.context["client_data"]["column_template_assigned_field_formset_has_errors"],
        )

        data = {
            "name": "Foobar",
            "description": "",
            "content_type": self.license_ct.pk,
            "fields-INITIAL_FORMS": "0",
            "fields-TOTAL_FORMS": "1",
            "fields-0-display_name": "",
            "fields-0-field_name": "name",
            "fields-0-id": "",
            # Omit seq
            "fields-0-seq": "",
        }

        response = self.client.post(url, data)
        self.assertEqual(
            True,
            response.context["client_data"]["column_template_assigned_field_formset_has_errors"],
        )

    def test_invalid_OrderField_field_value(self):
        query = Query.objects.create(
            dataspace=self.dataspace,
            name="GPL2-related licenses",
            content_type=self.license_ct,
            operator="and",
        )
        filter_ = Filter.objects.create(
            dataspace=self.dataspace, query=query, field_name="key", lookup="exact", value="gps-2.0"
        )
        order_field = OrderField.objects.create(
            dataspace=self.dataspace, query=query, field_name="name", seq=0
        )

        self.client.login(username="test", password="t3st")
        url = query.get_admin_url()
        data = {
            "name": query.name,
            "description": query.description,
            "content_type": query.content_type_id,
            "operator": query.operator,
            "filters-INITIAL_FORMS": 1,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": filter_.pk,
            "filters-0-field_name": filter_.field_name,
            "filters-0-lookup": filter_.lookup,
            "filters-0-value": filter_.value,
            "order_fields-INITIAL_FORMS": 1,
            "order_fields-TOTAL_FORMS": 1,
            "order_fields-0-id": order_field.pk,
            "order_fields-0-field_name": "senseless value",
            "order_fields-0-seq": "0",
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)

        expected = [
            {
                NON_FIELD_ERRORS: ["senseless value is not a field of License"],
                "sort": ["This field is required."],
            }
        ]
        self.assertEqual(
            expected, response.context_data["inline_admin_formsets"][1].formset.errors)

    def test_save_query_with_order_fields(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")
        data = {
            "name": "The Name",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "name",
            "filters-0-lookup": "contains",
            "filters-0-value": "GPL",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 2,
            "order_fields-0-id": "",
            "order_fields-0-field_name": "name",
            "order_fields-0-seq": "0",
            "order_fields-0-sort": "ascending",
            "order_fields-1-id": "",
            "order_fields-1-field_name": "id",
            "order_fields-1-seq": "1",
            "order_fields-1-sort": "ascending",
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_query_add_popup(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add") + "?_popup=1"
        data = {
            IS_POPUP_VAR: "1",
            "name": "The Name",
            "description": "",
            "content_type": self.license_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 0,
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = [
            "admin/reporting/query/popup_response.html",
            "admin/reporting/popup_response.html",
            "admin/popup_response.html",
        ]
        self.assertEqual(expected, response.template_name)

    def test_order_of_changelist_link_in_preview_respects_order_fields_of_query(self):
        license_names = ["license_{}".format(x) for x in range(10)]
        for name in license_names:
            License.objects.create(
                key=name,
                name=name,
                short_name=name,
                dataspace=self.dataspace,
                owner=self.owner,
                is_active=True,
            )

        query = Query.objects.create(
            dataspace=self.dataspace, name="A query", content_type=self.license_ct, operator="and"
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="key",
            lookup="icontains",
            value="license",
        )
        OrderField.objects.create(
            dataspace=self.dataspace, query=query, field_name="name", seq=0)

        self.client.login(username="test", password="t3st")
        url = query.get_admin_url()
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        expected = '<a href="{}?reporting_query={}&amp;o=4" target="_blank">10 licenses</a>'.format(
            reverse("admin:license_library_license_changelist"), query.pk
        )
        self.assertContains(response, expected, html=True)

    def test_query_changeform_update_content_type_once_assigned_to_report(self):
        self.client.login(username="test", password="t3st")
        url = self.query1.get_admin_url()

        self.assertTrue(self.query1.report_set.exists())
        self.assertNotEqual(self.license_ct, self.query1.content_type)

        data = {
            "name": self.query1.name,
            "description": self.query1.description,
            "operator": self.query1.operator,
            "content_type": self.license_ct.pk,
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 0,
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = {
            "content_type": [
                "The content type cannot be modified since this object is assigned to "
                "a least one Report instance."
            ]
        }
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

        self.report1.delete()
        self.assertFalse(self.query1.report_set.exists())
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_columntemplate_changeform_update_content_type_once_assigned_to_report(self):
        self.client.login(username="test", password="t3st")
        url = self.column_template1.get_admin_url()

        self.assertTrue(self.column_template1.report_set.exists())
        self.assertNotEqual(
            self.license_ct, self.column_template1.content_type)

        data = {
            "name": self.column_template1.name,
            "description": self.column_template1.description,
            "content_type": self.license_ct.pk,
            "fields-INITIAL_FORMS": "0",
            "fields-TOTAL_FORMS": "0",
        }

        response = self.client.post(url, data)
        self.assertEqual(200, response.status_code)
        expected = {
            "content_type": [
                "The content type cannot be modified since this object is assigned to "
                "a least one Report instance."
            ]
        }
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

        self.report1.delete()
        self.assertFalse(self.column_template1.report_set.exists())
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_report_changelist_view_contains_query_and_column_template_links(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_report_changelist")
        response = self.client.get(url)
        self.assertContains(
            response, f'<a href="{self.query1.get_admin_url()}" target="_blank">Q1 (component)</a>'
        )
        admin_url = self.column_template1.get_admin_url()
        self.assertContains(
            response,
            f'<a href="{admin_url}" target="_blank">CT1 (component)</a>',
        )

    def test_get_query_options_dataspace_scoping(self):
        other_dataspace = Dataspace.objects.create(name="other")
        other_query = Query.objects.create(
            dataspace=other_dataspace, name="Other", content_type=self.license_ct, operator="and"
        )

        self.client.login(username="test", password="t3st")
        addition_url = reverse("admin:reporting_query_add")
        edition_url = self.query1.get_admin_url()

        for url in [addition_url, edition_url]:
            response = self.client.get(url)
            query_options = response.context["client_data"]["query_options"]
            ids = [query_option["id"] for query_option in query_options]
            self.assertIn(self.query1.id, ids)
            self.assertNotIn(other_query.id, ids)

        # Now edition but of a Query in another dataspace, make sure the scoping
        # is on the object dataspace.
        url = other_query.get_admin_url()
        response = self.client.get(url)
        query_options = response.context["client_data"]["query_options"]
        ids = [query_option["id"] for query_option in query_options]
        self.assertNotIn(self.query1.id, ids)
        self.assertIn(other_query.id, ids)

    def test_save_new_query_with_m2m_as_last_field(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")

        # Create a Component query using the license_query as value.
        data = {
            "name": "Query11",
            "description": "",
            "content_type": self.component_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "licenses",
            "filters-0-lookup": "exact",
            "filters-0-value": "",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

        # Similar with "M2M Relationship" field
        data["name"] = "rQuery122"
        data["filters-0-field_name"] = "keywords"
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_save_new_query_auto_strip_disabled_on_filter_value_field(self):
        self.client.login(username="test", password="t3st")
        url = reverse("admin:reporting_query_add")

        data = {
            "name": "LicenseExpressionQuery",
            "description": "",
            "content_type": self.component_ct.pk,
            "operator": "and",
            "filters-INITIAL_FORMS": 0,
            "filters-TOTAL_FORMS": 1,
            "filters-0-id": "",
            "filters-0-field_name": "license_expression",
            "filters-0-lookup": "icontains",
            "filters-0-value": " OR ",
            "order_fields-INITIAL_FORMS": 0,
            "order_fields-TOTAL_FORMS": 0,
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        filtr = Filter.objects.latest("id")
        self.assertEqual(" OR ", filtr.value)
