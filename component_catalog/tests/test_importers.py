#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import datetime
import os
from os.path import dirname
from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import NON_FIELD_ERRORS
from django.test import TestCase
from django.urls import reverse

from guardian.shortcuts import assign_perm

from component_catalog.importers import BaseImporter
from component_catalog.importers import ComponentImporter
from component_catalog.importers import PackageImporter
from component_catalog.importers import SubcomponentImporter
from component_catalog.models import AcceptableLinkage
from component_catalog.models import Component
from component_catalog.models import ComponentStatus
from component_catalog.models import ComponentType
from component_catalog.models import Subcomponent
from dje.models import Dataspace
from dje.models import History
from dje.tests import MaxQueryMixin
from dje.tests import add_perm
from dje.tests import create_admin
from dje.tests import create_superuser
from license_library.models import License
from organization.models import Owner
from policy.models import UsagePolicy
from product_portfolio.models import Product

TESTFILES_LOCATION = os.path.join(dirname(__file__), "testfiles", "import")


class ComponentImporterTestCase(MaxQueryMixin, TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="Alternate")

        self.super_user = create_superuser("super_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)
        self.alternate_super_user = create_superuser("alternate_user", self.alternate_dataspace)

        self.owner = Owner.objects.create(
            name="Apache Software Foundation", dataspace=self.dataspace
        )
        self.component_no_version = Component.objects.create(
            name="log4j", owner=self.owner, dataspace=self.dataspace
        )
        self.component_with_version = Component.objects.create(
            name="log4j", version="1.0", owner=self.owner, dataspace=self.dataspace
        )

        self.configuration_status = ComponentStatus.objects.create(
            label="Approved",
            text="Approved. Ready for Component Catalog.",
            dataspace=self.dataspace,
        )

        self.license = License.objects.create(
            key="license",
            short_name="License1",
            name='BSD 2-clause "FreeBSD" License',
            dataspace=self.dataspace,
            owner=self.owner,
        )

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

    def test_exclude_ManyToManyFields_from_model_form(self):
        for field_name in [x.name for x in Component._meta.local_many_to_many]:
            self.assertTrue(field_name in ComponentImporter.model_form._meta.exclude)

    def test_component_import_non_model_model(self):
        # Raise if the importer.model_form is None or not a ModelForm
        class Importer(BaseImporter):
            model_form = None

        with self.assertRaises(AttributeError):
            Importer(self.super_user)

    def test_component_import_empty_csv(self):
        # Input file is empty
        file = os.path.join(TESTFILES_LOCATION, "empty.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertEqual(["The input file is empty."], importer.fatal_errors)
        self.assertFalse(getattr(importer, "formset", None))

    def test_component_import_with_non_utf8_values(self):
        # non utf8 char in the header, the value is proper converted
        file = os.path.join(TESTFILES_LOCATION, "non_utf8_in_header.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertFalse(importer.fatal_errors)
        self.assertEqual(set(["\ufffd"]), importer.ignored_columns)
        self.assertEqual(["owner", "name", "version"], importer.headers)
        self.assertTrue(importer.formset.is_valid())

        # non utf8 char in a mandatory row
        file = os.path.join(TESTFILES_LOCATION, "non_utf8_decode_in_row.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertFalse(importer.fatal_errors)
        # The value is properly decoded but an error is raised on the name field
        # as the value does not comply with the field validation:
        # "periods, letters, numbers, or !#"\':,&()+_-.'"
        self.assertTrue("name" in importer.formset.errors[0].keys())
        self.assertTrue(importer.formset.errors)

        # Similar issue on the copyright field
        file = os.path.join(TESTFILES_LOCATION, "non_utf8_encode_in_row.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertFalse(importer.fatal_errors)
        # The copyright was properly decoded, the formset is valid.
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        expected = "\ufffd\ufffd_Copyright 2009, Mahmood Ali"
        self.assertEqual(expected, importer.results["added"][0].copyright)

    def test_component_import_unicode_encoding_issue(self):
        file = os.path.join(TESTFILES_LOCATION, "unicode_encoding_issue.csv")
        importer = ComponentImporter(self.super_user, file)
        # Make sure the errors are returned and no results
        self.assertTrue(importer.fatal_errors)
        self.assertFalse(getattr(importer, "formset", None))
        self.assertEqual(
            ["Encoding issue. The string that could not be encoded/decoded was: hlsch\ufffdtter "],
            importer.fatal_errors,
        )

    def test_component_import_cp1252_encoded_file_works(self):
        file = os.path.join(TESTFILES_LOCATION, "K-Components-INVT-UTF-bug.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertEqual([], importer.fatal_errors)

    def test_component_import_byte_order_mark(self):
        file = os.path.join(TESTFILES_LOCATION, "component_import_byte_order_mark.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertEqual([], importer.fatal_errors)

    def test_component_import_mandatory_columns(self):
        # The file is missing the mandatory columns
        file = os.path.join(TESTFILES_LOCATION, "missing_mandatory_columns.csv")
        importer = ComponentImporter(self.super_user, file)
        # Make sure the errors are returned and no results
        self.assertTrue(importer.fatal_errors)
        self.assertFalse(getattr(importer, "formset", None))

        # Now using a file containing the mandatory columns
        file = os.path.join(TESTFILES_LOCATION, "including_mandatory_columns.csv")
        importer = ComponentImporter(self.super_user, file)
        # Make sure no errors are returned and we got some results
        self.assertFalse(importer.fatal_errors)
        self.assertTrue(importer.formset)
        self.assertTrue(importer.formset.is_valid())

    def test_component_import_include_mandatory_columns_but_no_data(self):
        # The columns are correct, but no data row
        file = os.path.join(TESTFILES_LOCATION, "including_mandatory_columns_but_no_data.csv")
        importer = ComponentImporter(self.super_user, file)
        # Make sure the errors are returned and no results
        self.assertEqual(["No data row in input file."], importer.fatal_errors)
        self.assertFalse(getattr(importer, "formset", None))

    def test_component_import_mandatory_data(self):
        # The first line is missing the mandatory data
        file = os.path.join(TESTFILES_LOCATION, "missing_mandatory_data.csv")
        importer = ComponentImporter(self.super_user, file)
        expected = [{"name": ["This field is required."]}, {}]
        self.assertEqual(expected, importer.formset.errors)

    def test_component_import_empty_rows(self):
        file = os.path.join(TESTFILES_LOCATION, "including_empty_rows.csv")
        importer = ComponentImporter(self.super_user, file)

        # Make sure that there's no error ..
        self.assertFalse(importer.fatal_errors)
        # ...and that the empty rows are ignored
        self.assertEqual(2, len(importer.formset))

    def test_perform_form_validation(self):
        file = os.path.join(TESTFILES_LOCATION, "including_model_invalid_data.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertEqual(
            ["Ensure this value has at most 100 characters (it has 509)."],
            importer.formset[0].__getitem__("name").errors,
        )

    def test_component_import_quoted_values(self):
        file = os.path.join(TESTFILES_LOCATION, "quoted_values.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertFalse(importer.fatal_errors)
        self.assertTrue(importer.formset.is_valid())

    def test_component_import_windows_line_endings(self):
        file = os.path.join(TESTFILES_LOCATION, "windows_line_endings.csv")
        importer = ComponentImporter(self.super_user, file)
        # Some error at the formset level but none at the importer level
        self.assertFalse(importer.fatal_errors)
        self.assertTrue(importer.formset.errors)

    def test_component_import_line_breaks_support(self):
        file = os.path.join(TESTFILES_LOCATION, "copyright_with_linebreaks.csv")

        url = reverse("admin:component_catalog_component_import")
        self.client.login(username="super_user", password="secret")
        with open(file) as f:
            response = self.client.post(url, data={"file": f})
        # Line breaks are display in the HTML import preview as <br />
        expected = '<td class="">Copyright 1<br /><br />Copyright 2</td>'
        self.assertContains(response, expected, html=True)

        importer = ComponentImporter(self.super_user, file)
        importer.save_all()
        added_component = importer.results["added"][0]
        # Line break are kept and saved in the DB
        self.assertEqual("Copyright 1\n\nCopyright 2", added_component.copyright)

    def test_component_import_escaped_quote_characters(self):
        file = os.path.join(TESTFILES_LOCATION, "escaped_quote_characters.csv")
        importer = ComponentImporter(self.super_user, file)
        value = importer.formset[0].__getitem__("description").value()
        self.assertEqual('Some "quoted chars" description', value)

    def test_component_import_version_column(self):
        # Valid CSV:
        #  * without 'version' column
        #  * with 'version' column but empty data
        #  * with 'version' column and correct version data
        input = [
            ("valid_with_empty_version.csv", self.component_no_version),
            ("valid_without_version.csv", self.component_no_version),
            ("valid_with_version.csv", self.component_with_version),
        ]

        for file_name, component in input:
            file = os.path.join(TESTFILES_LOCATION, file_name)
            importer = ComponentImporter(self.super_user, file)
            self.assertFalse(importer.fatal_errors)
            # If id is a value, that means the Component has been matched
            self.assertEqual(component.id, importer.formset[0].instance.id)

    def test_component_import_duplicated_column_header(self):
        # There's 2 columns "name" in this file
        file = os.path.join(TESTFILES_LOCATION, "duplicated_column_header.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertTrue('Column "name" is listed more than once.' in importer.fatal_errors)

    def test_component_import_extra_cell_in_row_line_nb2(self):
        # There's a extra cell in line2
        file = os.path.join(TESTFILES_LOCATION, "extra_cell_in_row_line2.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertTrue("Row at line 2 is not valid." in importer.fatal_errors)

    def test_component_import_save_all(self):
        # Manually creating a formset with 1 new Component and 1 existing
        formset_data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-0-name": "Django",
            "form-0-version": "1.4",
            "form-0-owner": str(self.component_with_version.owner.id),
            "form-0-curation_level": 0,
            "form-1-name": self.component_with_version.name,
            "form-1-version": str(self.component_with_version.version),
            "form-1-owner": str(self.component_with_version.owner.id),
            "form-1-curation_level": 0,
        }
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertEqual([self.component_with_version], importer.results["unmodified"])
        added_component = importer.results["added"][0]
        self.assertTrue(added_component)

        self.assertFalse(History.objects.get_for_object(added_component).exists())
        self.assertEqual(self.super_user, added_component.created_by)
        self.assertTrue(added_component.created_date)

        self.assertEqual(self.super_user, added_component.created_by)
        self.assertEqual(self.super_user, added_component.last_modified_by)

    def test_component_import_clean_version_warnings(self):
        # There's a extra cell in line2
        file = os.path.join(TESTFILES_LOCATION, "cleaned_versions_warnings.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertTrue(importer.formset.is_valid())
        # No version cleaning applied on first row
        self.assertFalse(importer.formset.forms[0].warnings)
        self.assertEqual(
            {"version": ["Version will been cleaned to 1.1"]}, importer.formset.forms[1].warnings
        )
        self.assertEqual(
            {"version": ["Version will been cleaned to 1.6"]}, importer.formset.forms[2].warnings
        )

    def test_component_import_multiple_duplicate_rows(self):
        file = os.path.join(TESTFILES_LOCATION, "multiple_duplicate_rows.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertFalse(importer.formset.is_valid())
        self.assertTrue("One of the row is a duplicate." in importer.formset.non_form_errors())
        # List of errors, skipping the empty dicts
        errors = [error for error in importer.formset.errors if error]
        # We should have 3 error as we have 3 duplicates
        self.assertEqual(3, len(errors))
        expected = {"version": ["This row is a duplicate."], "name": ["This row is a duplicate."]}
        self.assertEqual(expected, errors[0])

    def test_component_import_url_stripping_extra_spaces(self):
        file = os.path.join(TESTFILES_LOCATION, "urls_stripped.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        added_component = importer.results["added"][0]
        self.assertFalse(" " in added_component.homepage_url)
        self.assertFalse(" " in added_component.code_view_url)
        self.assertFalse(" " in added_component.bug_tracking_url)
        self.assertFalse(" " in added_component.notice_url)
        # vcs_url is not an URLField but CharField
        self.assertFalse(" " in added_component.vcs_url)

    def test_component_import_url_without_scheme_validation(self):
        # In forms.URLField, if no URL scheme given, Django assumes and prepend http://
        # before saving the value in the DB.
        file = os.path.join(TESTFILES_LOCATION, "url_without_scheme_validation.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        added_component = importer.results["added"][0]
        self.assertEqual("http://www.a.com", added_component.homepage_url)

    def test_component_import_strip_input_values(self):
        file = os.path.join(TESTFILES_LOCATION, "valid_with_non_stripped_spaces.csv")
        importer = ComponentImporter(self.super_user, file)

        self.assertFalse(importer.fatal_errors)
        # If id is a value, that means the Component has been matched
        self.assertEqual(self.component_with_version.id, importer.formset[0].instance.id)

    def test_component_import_non_existing_organization(self):
        file = os.path.join(TESTFILES_LOCATION, "non_existing_organization.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertFalse(importer.formset.is_valid())
        expected = [{"owner": ["This Owner does not exists. No suggestion."]}]
        self.assertEqual(expected, importer.formset.errors)

    def test_component_import_organization_suggestions(self):
        Owner.objects.create(name="Apache 1", dataspace=self.dataspace)
        Owner.objects.create(name="Apache 2", alias="Alias1", dataspace=self.dataspace)
        Owner.objects.create(name="Apache 3", dataspace=self.dataspace)

        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-name": "c1",
            "form-0-curation_level": 0,
            "form-0-owner": "apache",
        }
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {
                "owner": [
                    "This Owner does not exists. Suggestion(s):"
                    " Apache 1, Apache 2, Apache 3, Apache Software Foundation."
                ]
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-owner"] = "alias1"
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [{"owner": ["This Owner does not exists. Suggestion(s): Apache 2."]}]
        self.assertEqual(expected, importer.formset.errors)

    def test_component_import_validate_case_insensitive_uniqueness(self):
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-name": self.component_no_version.name.upper(),
            "form-0-curation_level": 0,
        }
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {
                "name": [
                    'The application object that you are creating already exists as "log4j". '
                    "Note that a different case in the object name is not sufficient to "
                    "make it unique."
                ]
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-name"] = "other name"
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        file = os.path.join(TESTFILES_LOCATION, "component_names_suggestion.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertFalse(importer.formset.is_valid())
        self.assertEqual(expected, importer.formset.errors)

    def test_component_import_valid_configuration_status(self):
        file = os.path.join(TESTFILES_LOCATION, "valid_configuration_status.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertTrue(importer.formset.is_valid())
        status_field = importer.formset.forms[0].fields["configuration_status"]
        expected = self.configuration_status.get_admin_link(target="_blank")
        self.assertEqual(expected, status_field.value_for_display)

    def test_component_import_invalid_configuration_status(self):
        file = os.path.join(TESTFILES_LOCATION, "invalid_configuration_status.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {
                "configuration_status": [
                    'That choice is not one of the available choices: "Approved"'
                ]
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

    def test_component_import_curation_level_default_value(self):
        file = os.path.join(TESTFILES_LOCATION, "curation_level_default_value.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertTrue(importer.formset.is_valid())
        self.assertEqual(40, importer.formset.forms[0].instance.curation_level)
        self.assertEqual(0, importer.formset.forms[1].instance.curation_level)

    def test_component_import_fields_help_supported_values(self):
        url = reverse("admin:component_catalog_component_import")
        self.client.login(username="super_user", password="secret")

        # Let's add 2 ComponentType and 2 ComponentStatus and make sure they are
        # displayed as supported values in the help
        ComponentType.objects.create(label="TypeA", dataspace=self.dataspace)
        ComponentType.objects.create(label="TypeB", dataspace=self.dataspace)
        ComponentStatus.objects.create(label="S1", dataspace=self.dataspace)
        ComponentStatus.objects.create(label="S2", dataspace=self.dataspace)

        response = self.client.get(url)
        self.assertContains(response, "<li><strong>TypeA</strong></li>", html=True)
        self.assertContains(response, "<li><strong>TypeB</strong></li>", html=True)
        self.assertContains(response, "<li><strong>S1</strong></li>", html=True)
        self.assertContains(response, "<li><strong>S2</strong></li>", html=True)

    def test_component_import_usage_policy_help_supported_values(self):
        url = reverse("admin:component_catalog_component_import")
        self.client.login(username="super_user", password="secret")

        response = self.client.get(url)
        base_html = "<strong>{}</strong>"
        self.assertContains(response, base_html.format("usage_policy"))
        self.assertContains(response, base_html.format(self.component_policy))
        self.assertNotContains(response, base_html.format(self.license_policy))

        self.client.login(username="admin_user", password="secret")
        add_perm(self.admin_user, "add_component")
        response = self.client.get(url)
        self.assertContains(response, base_html.format("name"))
        self.assertNotContains(response, base_html.format("usage_policy"))

    def test_component_import_valid_usage_policy(self):
        file = os.path.join(TESTFILES_LOCATION, "valid_usage_policy.csv")
        # Using the same label to make sure the Policy is scoped by ContentType
        self.license_policy.label = self.component_policy.label
        self.license_policy.save()
        importer = ComponentImporter(self.super_user, file)
        self.assertTrue(importer.formset.is_valid())
        policy_field = importer.formset.forms[0].fields["usage_policy"]
        expected = self.component_policy.get_admin_link(target="_blank")
        self.assertEqual(expected, policy_field.value_for_display)
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))

    def test_component_import_invalid_usage_policy(self):
        file = os.path.join(TESTFILES_LOCATION, "invalid_usage_policy.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {"usage_policy": ['That choice is not one of the available choices: "ComponentPolicy"']}
        ]
        self.assertEqual(expected, importer.formset.errors)

    def test_component_import_nullboolean_field_values(self):
        file = os.path.join(TESTFILES_LOCATION, "nullboolean_field_values.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        added_component0 = importer.results["added"][0]
        added_component1 = importer.results["added"][1]
        added_component2 = importer.results["added"][2]

        self.assertEqual(False, importer.formset.forms[0].instance.is_license_notice)
        self.assertEqual(None, importer.formset.forms[0].instance.is_copyright_notice)
        self.assertEqual(True, importer.formset.forms[0].instance.is_notice_in_codebase)
        self.assertEqual(True, importer.formset.forms[0].instance.is_active)
        self.assertEqual(False, added_component0.is_license_notice)
        self.assertEqual(None, added_component0.is_copyright_notice)
        self.assertEqual(True, added_component0.is_notice_in_codebase)
        self.assertEqual(True, added_component0.is_active)

        self.assertEqual(False, importer.formset.forms[1].instance.is_license_notice)
        self.assertEqual(None, importer.formset.forms[1].instance.is_copyright_notice)
        self.assertEqual(True, importer.formset.forms[1].instance.is_notice_in_codebase)
        self.assertEqual(True, importer.formset.forms[1].instance.is_active)
        self.assertEqual(False, added_component1.is_license_notice)
        self.assertEqual(None, added_component1.is_copyright_notice)
        self.assertEqual(True, added_component1.is_notice_in_codebase)
        self.assertEqual(True, added_component1.is_active)

        self.assertEqual(True, importer.formset.forms[2].instance.is_license_notice)
        self.assertEqual(False, importer.formset.forms[2].instance.is_copyright_notice)
        self.assertEqual(None, importer.formset.forms[2].instance.is_notice_in_codebase)
        self.assertEqual(False, importer.formset.forms[2].instance.is_active)
        self.assertEqual(True, added_component2.is_license_notice)
        self.assertEqual(False, added_component2.is_copyright_notice)
        self.assertEqual(None, added_component2.is_notice_in_codebase)
        self.assertEqual(False, added_component2.is_active)

    def test_component_import_get_added_instance_ids(self):
        file = os.path.join(TESTFILES_LOCATION, "valid_multiple_rows.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertIsNone(importer.get_added_instance_ids())
        importer.save_all()
        self.assertEqual(2, len(importer.get_added_instance_ids()))

    def test_component_import_get_admin_changelist_url(self):
        file = os.path.join(TESTFILES_LOCATION, "valid_with_version.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertEqual(
            reverse("admin:component_catalog_component_changelist"),
            importer.get_admin_changelist_url(),
        )

    def test_component_import_download_template_from_view(self):
        url = reverse("admin:component_catalog_component_import")
        self.client.login(username="super_user", password="secret")
        response = self.client.get(url)
        expected = (
            '<a href="?get_template=1" target="_blank" class="btn btn-outline-dark">'
            "Download import template</a>"
        )
        self.assertContains(response, expected, html=True)

        response = self.client.get(url + "?get_template=1")
        self.assertEqual(
            'attachment; filename="component_import_template.csv"', response["Content-Disposition"]
        )
        self.assertEqual("application/csv", response["Content-Type"])

        importer = ComponentImporter(self.super_user)
        expected = ",".join(importer.required_fields + importer.supported_fields)
        self.assertContains(response, expected)

        protected_field = "usage_policy"
        self.assertIn(protected_field, str(response.content))

        self.client.login(username="admin_user", password="secret")
        add_perm(self.admin_user, "add_component")
        response = self.client.get(url + "?get_template=1")
        self.assertIn("name", str(response.content))
        self.assertNotIn(protected_field, str(response.content))

    def test_importers_view_num_queries_view(self):
        # Regrouping all importers here for simplicity
        self.client.login(username="super_user", password="secret")

        # WARNING: 3 tasks are inserted for some reason, using this
        # to avoid the impact of those insertions in following assertions
        self.client.get("/")

        with self.assertMaxQueries(6):
            self.client.get(reverse("admin:component_catalog_subcomponent_import"))

        with self.assertMaxQueries(9):
            self.client.get(reverse("admin:component_catalog_package_import"))

        with self.assertNumQueries(4):
            self.client.get(reverse("admin:organization_owner_import"))

        with self.assertMaxQueries(10):
            self.client.get(reverse("admin:component_catalog_component_import"))

    def test_component_import_keywords(self):
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-name": "Name",
            "form-0-curation_level": 10,
        }

        formset_data["form-0-keywords"] = None
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = ""
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = []
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = {}
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = ()
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = {"key": "value"}
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [{"keywords": ['Value must be valid JSON list: ["item1", "item2"].']}]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-keywords"] = "keyword1"
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = ", keyword1,keyword2  ,"
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        added_component = importer.results["added"][0]
        self.assertEqual(["keyword1", "keyword2"], added_component.keywords)

    def test_component_import_license_expression(self):
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-name": "Django",
            "form-0-version": "2.0",
            "form-0-curation_level": 0,
            "form-0-license_expression": "invalid",
        }
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [{"license_expression": ["Unknown license key(s): invalid"]}]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-license_expression"] = self.license.key
        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        added_component = importer.results["added"][0]
        self.assertEqual(1, added_component.licenses.count())
        self.assertEqual(self.license, added_component.licenses.all()[0])

    def test_component_import_license_expression_short_name(self):
        self.license.short_name = "Short Name with Space"
        self.license.save()

        license2 = License.objects.create(
            key="apache-1.1",
            short_name="Apache 1.1",
            name="Apache License 1.1",
            dataspace=self.dataspace,
            owner=self.owner,
        )

        mixed_expression = "{} AND {}".format(self.license.short_name, license2.key)
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-name": "Django",
            "form-0-version": "2.0",
            "form-0-curation_level": 0,
            "form-0-license_expression": mixed_expression,
        }

        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        added_component = importer.results["added"][0]
        self.assertEqual(2, added_component.licenses.count())
        self.assertIn(self.license, added_component.licenses.all())
        self.assertIn(license2, added_component.licenses.all())
        self.assertEqual("license AND apache-1.1", added_component.license_expression)

    def test_component_import_leading_space_in_formset_data(self):
        Component.objects.create(name="cURL", dataspace=self.dataspace)

        formset_data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-0-name": "ok",
            "form-0-curation_level": 0,
            # Leading space
            "form-1-name": " cURL",
            "form-1-curation_level": 0,
        }

        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        self.assertEqual(1, len(importer.results["unmodified"]))

    def test_component_import_protected_fields_ignored(self):
        file = os.path.join(TESTFILES_LOCATION, "valid_usage_policy.csv")
        perm = "component_catalog.change_usage_policy_on_component"
        self.assertFalse(self.admin_user.has_perm(perm))
        importer = ComponentImporter(self.admin_user, file_location=file)
        self.assertFalse(importer.fatal_errors)
        self.assertTrue(importer.formset.is_valid())
        self.assertEqual({"usage_policy"}, importer.ignored_columns)
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        self.assertIsNone(importer.results["added"][0].usage_policy)
        importer.results["added"][0].delete()

        self.admin_user = add_perm(self.admin_user, "change_usage_policy_on_component")
        self.assertTrue(self.admin_user.has_perm(perm))
        importer = ComponentImporter(self.admin_user, file_location=file)
        self.assertFalse(importer.fatal_errors)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        self.assertEqual(self.component_policy, importer.results["added"][0].usage_policy)

    def test_component_import_clean_validate_against_reference_data(self):
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-name": self.component_no_version.name,
            "form-0-curation_level": 0,
        }

        importer = ComponentImporter(self.alternate_super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())

        absolute_link = self.component_no_version.get_absolute_link(target="_blank")
        copy_link = self.component_no_version.get_html_link(
            self.component_no_version.get_copy_url(), value="Copy to my Dataspace", target="_blank"
        )
        error = (
            "The application object that you are creating already exists as "
            "{} in the reference dataspace. {}".format(absolute_link, copy_link)
        )

        expected = [
            {
                "version": [error],
                "name": [error],
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

    def test_component_import_clean_primary_language(self):
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-name": "Name",
            "form-0-curation_level": 0,
            "form-0-primary_language": "Python",
        }

        importer = ComponentImporter(self.alternate_super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        self.assertEqual({}, importer.formset.forms[0].warnings)

        formset_data["form-0-primary_language"] = "What"
        importer = ComponentImporter(self.alternate_super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        expected = {
            "primary_language": [
                '"What" is not in standard languages list.' "\nSuggestion(s): WebDNA, Whitespace."
            ]
        }
        self.assertEqual(expected, importer.formset.forms[0].warnings)

        formset_data["form-0-primary_language"] = "python"
        importer = ComponentImporter(self.alternate_super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        expected = {"primary_language": ['Language will be imported with proper case: "Python"']}
        self.assertEqual(expected, importer.formset.forms[0].warnings)
        importer.save_all()
        added_component = importer.results["added"][0]
        self.assertEqual("Python", added_component.primary_language)

    def test_component_import_add_to_product(self):
        self.client.login(username=self.admin_user.username, password="secret")
        url = reverse("admin:component_catalog_component_import")

        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-name": "a",
            "form-0-curation_level": 0,
        }

        expected1 = "<strong>1 Added Components:</strong>"
        expected2 = '<input name="checkbox-for-selection"'
        expected3 = '<i class="fas fa-plus-circle"></i> Add to Product'
        expected4 = (
            '<form autocomplete="off" method="post" action="/components/"'
            ' id="add-to-product-form" class="">'
        )

        add_perm(self.admin_user, "add_component")
        response = self.client.post(url, formset_data)
        self.assertContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, expected4)

        add_perm(self.admin_user, "add_productcomponent")
        formset_data["form-0-name"] = "b"
        response = self.client.post(url, formset_data)
        self.assertContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, expected4)

        product1 = Product.objects.create(name="Product1", dataspace=self.dataspace)
        assign_perm("change_product", self.admin_user, product1)
        assign_perm("view_product", self.admin_user, product1)
        formset_data["form-0-name"] = "c"
        response = self.client.post(url, formset_data)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertContains(response, expected4)

    def test_component_import_null_boolean_field(self):
        self.client.login(username=self.super_user.username, password="secret")
        url = reverse("admin:component_catalog_component_import")

        # Preview
        file = os.path.join(TESTFILES_LOCATION, "component_import_null_boolean_values.csv")
        with open(file) as f:
            response = self.client.post(url, {"file": f})

        expected1 = '<td class="">False</td>'
        self.assertContains(response, expected1, html=True, count=4)

        expected_template = """
        <select name="form-0-{field_name}"
                aria-describedby="id_form-0-{field_name}_helptext"
                id="id_form-0-{field_name}"
        >
          <option value="unknown">Unknown</option>
          <option value="true">Yes</option>
          <option value="false" selected>No</option>
        </select>
        """

        fields = [
            "sublicense_allowed",
            "express_patent_grant",
            "covenant_not_to_assert",
            "indemnification",
        ]
        for field_name in fields:
            expected = expected_template.format(field_name=field_name)
            self.assertContains(response, expected, html=True)

        # Results
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-name": "a",
            "form-0-curation_level": 0,
            "form-0-sublicense_allowed": "False",
            "form-0-express_patent_grant": "No",
            "form-0-covenant_not_to_assert": "F",
            "form-0-indemnification": "N",
        }

        self.client.post(url, formset_data)
        component = Component.objects.latest("id")
        self.assertEqual(formset_data["form-0-name"], component.name)
        self.assertFalse(component.sublicense_allowed)
        self.assertFalse(component.express_patent_grant)
        self.assertFalse(component.covenant_not_to_assert)
        self.assertFalse(component.indemnification)

    def test_component_import_acceptable_linkages(self):
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-name": "C1",
            "form-0-curation_level": 0,
            "form-0-acceptable_linkages": "linkage1",
        }

        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {
                "acceptable_linkages": [
                    "Select a valid choice. linkage1 is not one of the available choices."
                ]
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

        AcceptableLinkage.objects.create(label="linkage1", dataspace=self.dataspace)
        AcceptableLinkage.objects.create(label="linkage2", dataspace=self.dataspace)

        importer = ComponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        added_component = importer.results["added"][0]
        self.assertEqual(["linkage1"], added_component.acceptable_linkages)

        file = os.path.join(TESTFILES_LOCATION, "component_acceptable_linkages.csv")
        importer = ComponentImporter(self.super_user, file)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(2, len(importer.results["added"]))
        added_component1 = importer.results["added"][0]
        added_component2 = importer.results["added"][1]
        self.assertEqual(["linkage1"], added_component1.acceptable_linkages)
        self.assertEqual(["linkage2", "linkage1"], added_component2.acceptable_linkages)


class PackageImporterTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("super_user", self.dataspace)

        self.owner = Owner.objects.create(
            name="Apache Software Foundation", dataspace=self.dataspace
        )
        self.component_no_version = Component.objects.create(
            name="log4j", owner=self.owner, dataspace=self.dataspace
        )
        self.component_with_version = Component.objects.create(
            name="log4j", version="1.0", owner=self.owner, dataspace=self.dataspace
        )

        self.configuration_status = ComponentStatus.objects.create(
            label="Approved",
            text="Approved. Ready for Component Catalog.",
            dataspace=self.dataspace,
        )

        self.license = License.objects.create(
            key="license",
            short_name="License1",
            name='BSD 2-clause "FreeBSD" License',
            dataspace=self.dataspace,
            owner=self.owner,
        )

    def test_package_import_invalid_values(self):
        file = os.path.join(TESTFILES_LOCATION, "file_import_invalid_values.csv")
        importer = PackageImporter(self.super_user, file)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {
                "release_date": ["Enter a valid date."],
                "size": ["Enter a whole number."],
                "download_url": ["Enter a valid URI."],
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

    def test_package_import_with_invalid_component_value(self):
        file = os.path.join(TESTFILES_LOCATION, "package_import_with_invalid_component_value.csv")
        importer = PackageImporter(self.super_user, file)
        self.assertFalse(importer.formset.is_valid())
        expected = [{"component": ['Invalid format. Expected format: "<name>:<version>".']}]
        self.assertEqual(expected, importer.formset.errors)

    def test_package_import_with_non_existing_component(self):
        file = os.path.join(TESTFILES_LOCATION, "package_import_with_non_existing_component.csv")
        importer = PackageImporter(self.super_user, file)
        self.assertFalse(importer.formset.is_valid())
        expected = [{"component": ["Could not find the component."]}]
        self.assertEqual(expected, importer.formset.errors)

    def test_package_import_proper_with_component(self):
        file = os.path.join(TESTFILES_LOCATION, "file_import_proper_with_component.csv")
        importer = PackageImporter(self.super_user, file)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        added_package = importer.results["added"][0]
        self.assertEqual("Django-1.4.tar.gz", added_package.filename)
        self.assertEqual(
            "https://www.djangoproject.com/m/releases/1.4/Django-1.4.tar.gz",
            added_package.download_url,
        )
        self.assertEqual(datetime.date(2013, 1, 1), added_package.release_date)
        self.assertEqual("851d00905eb70e4aa6384b3b8b111fb7", added_package.md5)
        self.assertEqual("1bfaa4643c6775fbf394137f1533659be45441e7", added_package.sha1)
        self.assertEqual(411863, added_package.size)
        # A ComponentAssignedPackage relation was created
        self.assertEqual(self.component_with_version, added_package.component_set.all()[0])

    def test_package_import_clean_license_expression(self):
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-filename": "name.zip",
            "form-0-license_expression": "bsd-new, bsd-new",
        }

        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {
                "license_expression": [
                    "Invalid license key: the valid characters are: letters and numbers, "
                    "underscore, dot, colon or hyphen signs and spaces: 'bsd-new, bsd-new'"
                ]
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

    def test_package_import_unique_url_name_validation(self):
        formset_data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-0-filename": "a.zip",
            "form-1-filename": "a.zip",
        }

        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {},
            {
                "download_url": ["This row is a duplicate."],
                "filename": ["This row is a duplicate."],
                "name": ["This row is a duplicate."],
                "namespace": ["This row is a duplicate."],
                "qualifiers": ["This row is a duplicate."],
                "subpath": ["This row is a duplicate."],
                "type": ["This row is a duplicate."],
                "version": ["This row is a duplicate."],
            },
        ]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-download_url"] = "http://url.com/a.zip"
        formset_data["form-1-download_url"] = formset_data["form-0-download_url"]
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-1-download_url"] = "http://other_url.com/a.zip"
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-1-download_url"] = formset_data["form-0-download_url"]
        formset_data["form-1-name"] = "Name"
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

    def test_package_import_filename_validation(self):
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-filename": "a/b.zip",
        }

        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {"filename": ["Enter a valid filename: slash, backslash, or colon are not allowed."]}
        ]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-filename"] = "a\\b.zip"
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-filename"] = "a:b.zip"
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-filename"] = "filename1.zip"
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        added_package = importer.results["added"][0]
        self.assertEqual(formset_data["form-0-filename"], added_package.filename)

    def test_package_import_keywords(self):
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-filename": "name.zip",
        }

        formset_data["form-0-keywords"] = None
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = ""
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = []
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = {}
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = ()
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = {"key": "value"}
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.formset.is_valid())
        expected = [{"keywords": ['Value must be valid JSON list: ["item1", "item2"].']}]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-keywords"] = "keyword1"
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = "keyword1,keyword2"
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = " , keyword1,  ,"
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        formset_data["form-0-keywords"] = "keyword1, keyword2"
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())

        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        added_package = importer.results["added"][0]
        self.assertEqual(["keyword1", "keyword2"], added_package.keywords)

    def test_package_import_scancode_json_input_issues(self):
        file = os.path.join(TESTFILES_LOCATION, "package_empty.json")
        importer = PackageImporter(self.super_user, file)
        expected_errors = ["The content is not proper JSON."]
        self.assertEqual(expected_errors, importer.fatal_errors)

        file = os.path.join(TESTFILES_LOCATION, "package_empty_json.json")
        importer = PackageImporter(self.super_user, file)
        expected_errors = ["No package data to import in input file."]
        self.assertEqual(expected_errors, importer.fatal_errors)

        file = os.path.join(TESTFILES_LOCATION, "package_bad_json.json")
        importer = PackageImporter(self.super_user, file)
        expected_errors = ["The content is not proper JSON."]
        self.assertEqual(expected_errors, importer.fatal_errors)

        file = os.path.join(TESTFILES_LOCATION, "package_not_json.json")
        importer = PackageImporter(self.super_user, file)
        expected_errors = ["The content is not proper JSON."]
        self.assertEqual(expected_errors, importer.fatal_errors)

    def test_package_import_scancode_json_proper_input(self):
        file = os.path.join(TESTFILES_LOCATION, "package_from_scancode.json")
        importer = PackageImporter(self.super_user, file)
        self.assertEqual([], importer.fatal_errors)
        self.assertTrue(importer.is_from_scancode)
        importer.save_all()
        self.assertEqual([], importer.results["unmodified"])
        self.assertEqual(2, len(importer.results["added"]))
        added_package = importer.results["added"][0]
        self.assertEqual("gem", added_package.type)
        self.assertEqual("", added_package.namespace)
        self.assertEqual("i18n-js", added_package.name)
        self.assertEqual("3.0.11", added_package.version)
        self.assertEqual("Ruby", added_package.primary_language)
        self.assertEqual("", added_package.license_expression)
        self.assertEqual("pkg:gem/i18n-js@3.0.11", added_package.package_url)
        self.assertEqual("i18n-js-3.0.11.gem", added_package.filename)

    def test_package_import_scancode_json_proper_no_summary(self):
        file = os.path.join(TESTFILES_LOCATION, "package_from_scancode_no_summary.json")
        importer = PackageImporter(self.super_user, file)
        self.assertTrue(importer.is_valid())
        self.assertEqual([], importer.fatal_errors)
        self.assertTrue(importer.is_from_scancode)
        importer.save_all()
        self.assertEqual([], importer.results["unmodified"])
        self.assertEqual(3, len(importer.results["added"]))
        added_package = importer.results["added"][0]
        self.assertEqual("gem", added_package.type)
        self.assertEqual("", added_package.namespace)
        self.assertEqual("i18n-js", added_package.name)
        self.assertEqual("3.0.11", added_package.version)
        self.assertEqual("Ruby", added_package.primary_language)
        self.assertEqual("", added_package.license_expression)
        self.assertEqual("pkg:gem/i18n-js@3.0.11", added_package.package_url)
        self.assertEqual("i18n-js-3.0.11.gem", added_package.filename)

    def test_package_import_prepare_package(self):
        package_data = {
            "type": "maven",
            "namespace": "org.apache.activemq",
            "name": "activemq-camel",
            "version": "5.11.0",
            "qualifiers": None,
            "subpath": None,
            "primary_language": "Java",
            "description": "ActiveMQ :: Camel\nActiveMQ component for Camel",
            "release_date": None,
            "parties": [],
            "keywords": [],
            "homepage_url": None,
            "download_url": None,
            "size": None,
            "sha1": None,
            "md5": None,
            "sha256": None,
            "sha512": None,
            "bug_tracking_url": None,
            "code_view_url": None,
            "vcs_url": None,
            "copyright": None,
            "license_expression": None,
            "declared_license": None,
            "notice_text": None,
            "manifest_path": "META-INF/maven/org.apache.activemq/activemq-camel/pom.xml",
            "dependencies": [
                {
                    "purl": "pkg:maven/org.slf4j/slf4j-api",
                    "requirement": None,
                    "scope": "compile",
                    "is_runtime": True,
                    "is_optional": False,
                    "is_resolved": False,
                }
            ],
            "contains_source_code": None,
            "source_packages": [
                "pkg:maven/org.apache.activemq/activemq-camel@5.11.0?classifier=sources"
            ],
            "purl": "pkg:maven/org.apache.activemq/activemq-camel@5.11.0",
            "repository_homepage_url": "https://repo1.maven.org/maven2/org/apache/"
            "activemq/activemq-camel/5.11.0/",
            "repository_download_url": "https://repo1.maven.org/maven2/org/apache/"
            "activemq/activemq-camel/5.11.0/activemq-camel-5.11.0.jar",
            "api_data_url": "https://repo1.maven.org/maven2/org/apache/activemq/"
            "activemq-camel/5.11.0/activemq-camel-5.11.0.pom",
            "files": [
                {
                    "path": "activemq-camel-5.11.0.jar-extract",
                    "type": "directory",
                }
            ],
        }
        expected = {
            "type": "maven",
            "namespace": "org.apache.activemq",
            "name": "activemq-camel",
            "version": "5.11.0",
            "primary_language": "Java",
            "description": "ActiveMQ :: Camel\nActiveMQ component for Camel",
            "homepage_url": "https://repo1.maven.org/maven2/org/apache/activemq/"
            "activemq-camel/5.11.0/",
            "download_url": "https://repo1.maven.org/maven2/org/apache/activemq/"
            "activemq-camel/5.11.0/activemq-camel-5.11.0.jar",
            "dependencies": '[\n  {\n    "purl": "pkg:maven/org.slf4j/slf4j-api",'
            '\n    "requirement": null,\n    "scope": "compile",'
            '\n    "is_runtime": true,\n    "is_optional": false,'
            '\n    "is_resolved": false\n  }\n]',
            "repository_homepage_url": (
                "https://repo1.maven.org/maven2/org/apache/activemq/activemq-camel/5.11.0/"
            ),
            "repository_download_url": (
                "https://repo1.maven.org/maven2/org/apache/activemq/activemq-camel/"
                "5.11.0/activemq-camel-5.11.0.jar"
            ),
            "api_data_url": (
                "https://repo1.maven.org/maven2/org/apache/activemq/activemq-camel/"
                "5.11.0/activemq-camel-5.11.0.pom"
            ),
            "filename": "activemq-camel-5.11.0.jar",
        }
        prepared_package = PackageImporter.prepare_package(package_data)
        self.assertEqual(expected, prepared_package)

        package_data["files"] = []
        prepared_package = PackageImporter.prepare_package(package_data)
        self.assertEqual(expected, prepared_package)

        del package_data["files"]
        prepared_package = PackageImporter.prepare_package(package_data)
        self.assertEqual(expected, prepared_package)

    def test_package_import_update_existing(self):
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-filename": "filename.zip",
        }

        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))

        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(1, len(importer.results["unmodified"]))

        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-filename": "filename.zip",
            "form-0-notes": "Notes",
        }
        importer = PackageImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(1, len(importer.results["modified"]))
        modified_package = importer.results["modified"][0]
        self.assertEqual("Notes", modified_package.notes)

        history_entry = History.objects.get_for_object(modified_package).get()
        expected_messages = "Updated notes from import"
        self.assertEqual(expected_messages, history_entry.change_message)

    def test_package_import_add_to_product(self):
        admin_user = create_admin("admin_user", self.dataspace)
        self.client.login(username=admin_user.username, password="secret")
        url = reverse("admin:component_catalog_package_import")

        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-filename": "a.zip",
        }

        expected1 = "<strong>1 Added Packages:</strong>"
        expected2 = '<input name="checkbox-for-selection"'
        expected3 = '<i class="fas fa-plus-circle"></i> Add to Product'
        expected4 = (
            '<form autocomplete="off" method="post" action="/packages/"'
            ' id="add-to-product-form" class="">'
        )

        add_perm(admin_user, "add_package")
        response = self.client.post(url, formset_data)
        self.assertContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, expected4)

        add_perm(admin_user, "add_productpackage")
        formset_data["form-0-filename"] = "b.zip"
        response = self.client.post(url, formset_data)
        self.assertContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, expected4)

        product1 = Product.objects.create(name="Product1", dataspace=self.dataspace)
        assign_perm("change_product", admin_user, product1)
        assign_perm("view_product", admin_user, product1)
        formset_data["form-0-filename"] = "c.zip"
        response = self.client.post(url, formset_data)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertContains(response, expected4)

    @mock.patch("component_catalog.importers.fetch_for_queryset")
    def test_package_import_fetch_vulnerabilities(self, mock_fetch_for_queryset):
        mock_fetch_for_queryset.return_value = None
        self.dataspace.enable_vulnerablecodedb_access = True
        self.dataspace.save()

        file = os.path.join(TESTFILES_LOCATION, "package_from_scancode.json")
        importer = PackageImporter(self.super_user, file)
        importer.save_all()
        self.assertEqual(2, len(importer.results["added"]))
        mock_fetch_for_queryset.assert_called()


class SubcomponentImporterTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("super_user", self.dataspace)

        self.owner = Owner.objects.create(
            name="Apache Software Foundation", dataspace=self.dataspace
        )

        self.configuration_status = ComponentStatus.objects.create(
            label="Approved",
            text="Approved. Ready for Component Catalog.",
            dataspace=self.dataspace,
        )

        self.license1 = License.objects.create(
            key="apache-2.0",
            short_name="Apache 2.0",
            name="Apache License 2.0",
            dataspace=self.dataspace,
            owner=self.owner,
        )

        self.license2 = License.objects.create(
            key="apache-1.1",
            short_name="Apache 1.1",
            name="Apache License 1.1",
            dataspace=self.dataspace,
            owner=self.owner,
        )

        self.component_no_version = Component.objects.create(
            name="log4j",
            license_expression=self.license1.key,
            owner=self.owner,
            dataspace=self.dataspace,
        )
        self.component_with_version = Component.objects.create(
            name="log4j", version="1.0", owner=self.owner, dataspace=self.dataspace
        )

        self.license_ct = ContentType.objects.get_for_model(License)
        self.subcomponent_ct = ContentType.objects.get_for_model(Subcomponent)

        self.license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=self.license_ct,
            dataspace=self.dataspace,
        )

        self.subcomponent_policy = UsagePolicy.objects.create(
            label="SubcomponentPolicy",
            icon="icon",
            content_type=self.subcomponent_ct,
            dataspace=self.dataspace,
        )

    def test_subcomponent_import_mandatory_columns(self):
        # The first file is missing the mandatory columns
        file = os.path.join(TESTFILES_LOCATION, "missing_mandatory_columns.csv")
        importer = SubcomponentImporter(self.super_user, file)
        # Make sure the errors are returned and no results
        expected_errors = [
            'Required column missing: "parent".',
            'Required column missing: "child".',
        ]
        self.assertEqual(expected_errors, importer.fatal_errors)
        self.assertFalse(getattr(importer, "formset", None))

        # Now using a file containing the mandatory columns
        file = os.path.join(TESTFILES_LOCATION, "subcomponent_including_mandatory_columns.csv")
        importer = SubcomponentImporter(self.super_user, file)
        # Make sure no errors are returned and we got some results
        self.assertFalse(importer.fatal_errors)
        self.assertTrue(importer.formset)
        self.assertTrue(importer.formset.is_valid())

    def test_subcomponent_import_mandatory_data(self):
        # The first line is missing the mandatory columns
        file = os.path.join(TESTFILES_LOCATION, "subcomponent_missing_mandatory_data.csv")
        importer = SubcomponentImporter(self.super_user, file)
        expected = [{"child": ["This field is required."]}]
        self.assertEqual(expected, importer.formset.errors)

    def test_subcomponent_import_component_syntax_issues(self):
        file = os.path.join(TESTFILES_LOCATION, "subcomponent_component_syntax_issues.csv")
        importer = SubcomponentImporter(self.super_user, file)
        expected = [
            {
                "child": ["Could not find the component."],
                "parent": ['Invalid format. Expected format: "<name>:<version>".'],
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

    def test_subcomponent_import_parent_equal_child(self):
        file = os.path.join(TESTFILES_LOCATION, "subcomponent_parent_equal_child.csv")
        importer = SubcomponentImporter(self.super_user, file)
        expected = [{NON_FIELD_ERRORS: ["This Object cannot be his own child or parent."]}]
        self.assertEqual(expected, importer.formset.errors)

    def test_subcomponent_import_parent_is_descendant_of_child(self):
        Subcomponent.objects.create(
            parent=self.component_with_version,
            child=self.component_no_version,
            dataspace=self.dataspace,
        )

        file = os.path.join(TESTFILES_LOCATION, "subcomponent_parent_is_descendant_of_child.csv")
        importer = SubcomponentImporter(self.super_user, file)
        expected = [
            {
                NON_FIELD_ERRORS: [
                    "The current Object is a descendant of the selected child,"
                    " it cannot also be a parent for it."
                ]
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

    def test_subcomponent_import_save_all(self):
        component3 = Component.objects.create(name="log4j", version="3.0", dataspace=self.dataspace)

        subcomponent = Subcomponent.objects.create(
            parent=self.component_with_version,
            child=self.component_no_version,
            dataspace=self.dataspace,
        )

        # Manually creating a formset with 1 new Subcomponent and 1 existing
        formset_data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-0-parent": "{}:{}".format(
                self.component_with_version.name, self.component_with_version.version
            ),
            "form-0-child": "{}:{}".format(component3.name, component3.version),
            "form-0-notes": "Notes",
            "form-0-purpose": "Core",
            "form-0-package_paths": "/path/",
            "form-0-extra_attribution_text": "Extra Attrib",
            "form-1-parent": "{}:{}".format(
                self.component_with_version.name, self.component_with_version.version
            ),
            "form-1-child": "{}:{}".format(
                self.component_no_version.name, self.component_no_version.version
            ),
            "form-1-notes": "",
            "form-1-purpose": "",
            "form-1-package_paths": "",
            "form-1-extra_attribution": "",
        }
        importer = SubcomponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(importer.results["unmodified"], [subcomponent])
        self.assertEqual(1, len(importer.results["added"]))
        added_subcomponent = importer.results["added"][0]
        self.assertTrue(added_subcomponent)
        self.assertTrue(added_subcomponent.id)
        self.assertEqual("Notes", added_subcomponent.notes)
        self.assertEqual("Core", added_subcomponent.purpose)
        self.assertEqual("/path/", added_subcomponent.package_paths)
        self.assertEqual("Extra Attrib", added_subcomponent.extra_attribution_text)
        self.assertEqual(component3.pk, added_subcomponent.child.pk)
        self.assertEqual(self.component_with_version.pk, added_subcomponent.parent.pk)

    def test_subcomponent_import_license_expression(self):
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-parent": "{}:{}".format(
                self.component_with_version.name, self.component_with_version.version
            ),
            "form-0-child": "{}:{}".format(
                self.component_no_version.name, self.component_no_version.version
            ),
            "form-0-license_expression": "",  # license_expression is not mandatory
        }

        # license_expression is not provided, taken form the Component by default
        importer = SubcomponentImporter(self.super_user, formset_data=formset_data)
        self.assertFalse(importer.fatal_errors)
        self.assertTrue(importer.formset)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        added_subcomponent = importer.results["added"][0]
        self.assertEqual(1, added_subcomponent.licenses.count())
        self.assertEqual(self.license1, added_subcomponent.licenses.all()[0])
        self.assertEqual(
            added_subcomponent.child.license_expression, added_subcomponent.license_expression
        )
        added_subcomponent.delete()

        formset_data["form-0-license_expression"] = "{} AND {}".format(
            self.license1.key, self.license2.key
        )

        importer = SubcomponentImporter(self.super_user, formset_data=formset_data)
        expected = [
            {
                "license_expression": [
                    "Unknown license key(s): apache-1.1<br>Available licenses: apache-2.0"
                ]
            }
        ]
        self.assertEqual(expected, importer.formset.errors)

        formset_data["form-0-license_expression"] = self.license1.key
        importer = SubcomponentImporter(self.super_user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        added_subcomponent = importer.results["added"][0]
        self.assertEqual(1, added_subcomponent.licenses.count())
        self.assertEqual(self.license1, added_subcomponent.licenses.all()[0])

    def test_subcomponent_import_usage_policy_help_supported_values(self):
        url = reverse("admin:component_catalog_subcomponent_import")
        self.client.login(username="super_user", password="secret")

        response = self.client.get(url)
        self.assertContains(
            response, "<li><strong>{}</strong></li>".format(self.subcomponent_policy)
        )
        self.assertNotContains(response, "<li><strong>{}</strong></li>".format(self.license_policy))

    def test_subcomponent_import_valid_usage_policy(self):
        file = os.path.join(TESTFILES_LOCATION, "subcomponent_valid_usage_policy.csv")
        # Using the same label to make sure the Policy is scoped by ContentType
        self.license_policy.label = self.subcomponent_policy.label
        self.license_policy.save()
        importer = SubcomponentImporter(self.super_user, file)
        self.assertTrue(importer.formset.is_valid())
        policy_field = importer.formset.forms[0].fields["usage_policy"]
        expected = self.subcomponent_policy.get_admin_link(target="_blank")
        self.assertEqual(expected, policy_field.value_for_display)
        importer.save_all()
        self.assertEqual(1, len(importer.results["added"]))
        subcomponent = importer.results["added"][0]
        self.assertEqual(self.subcomponent_policy, subcomponent.usage_policy)
        self.assertTrue(subcomponent.is_deployed)
        self.assertTrue(subcomponent.is_modified)

    def test_subcomponent_import_invalid_usage_policy(self):
        file = os.path.join(TESTFILES_LOCATION, "subcomponent_invalid_usage_policy.csv")
        importer = SubcomponentImporter(self.super_user, file)
        self.assertFalse(importer.formset.is_valid())
        expected = [
            {
                "usage_policy": [
                    'That choice is not one of the available choices: "SubcomponentPolicy"'
                ]
            }
        ]
        self.assertEqual(expected, importer.formset.errors)
