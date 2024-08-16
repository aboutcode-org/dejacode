#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.test import TestCase

from dje.forms import CopyDefaultsForm
from dje.forms import CopyDefaultsFormSet
from dje.forms import TabPermissionsForm
from dje.forms import TabPermissionsFormSet
from dje.models import Dataspace
from dje.models import DataspaceConfiguration


class DJEFormsTestCase(TestCase):
    def setUp(self):
        self.dataspace1 = Dataspace.objects.create(name="Dataspace")

    def test_tabs_permission_form_get_choice_label(self):
        label = TabPermissionsForm.get_choice_label(
            tab_name="essentials",
            tab_fields=["key", "name", "short_name"],
        )
        expected = (
            '<span class="hint--bottom-right underline-dotted" '
            'aria-label="key, name, short_name">Essentials</span>'
        )
        self.assertEqual(expected, label)

        label = TabPermissionsForm.get_choice_label(
            tab_name="activity", tab_fields=None)
        expected = "Activity"
        self.assertEqual(expected, label)

    def test_tabs_permission_form(self):
        tab_form = TabPermissionsForm()
        expected = [
            "essentials",
            "licenses",
            "components",
            "hierarchy",
            "external_references",
            "history",
        ]
        tab_labels = list(tab_name for tab_name,
                          _ in tab_form.fields["owner"].choices)
        self.assertEqual(expected, tab_labels)

    def test_tabs_permission_formset_serialize_perms(self):
        self.assertEqual({}, TabPermissionsFormSet().serialize())

        data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "2",
            "form-0-package": ["license", "components"],
            "form-0-group_name": "Legal",
            "form-1-group_name": "Engineering",
        }

        formset = TabPermissionsFormSet(data)
        self.assertTrue(formset.is_valid())
        expected = {"Legal": {"package": ["license", "components"]}}
        self.assertEqual(expected, formset.serialize())

    def test_tabs_permission_formset_save_perms(self):
        self.assertEqual(0, DataspaceConfiguration.objects.count())
        TabPermissionsFormSet().save(self.dataspace1)

        configuration = DataspaceConfiguration.objects.get(
            dataspace=self.dataspace1)
        self.assertEqual({}, configuration.tab_permissions)

        data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "2",
            "form-0-package": ["license", "components"],
            "form-0-group_name": "Legal",
            "form-1-group_name": "Engineering",
        }

        formset = TabPermissionsFormSet(data)
        self.assertTrue(formset.is_valid())
        formset.save(self.dataspace1)
        configuration = DataspaceConfiguration.objects.get(
            dataspace=self.dataspace1)
        expected = {"Legal": {"package": ["license", "components"]}}
        self.assertEqual(expected, configuration.tab_permissions)

    def test_tabs_permission_formset_load_perms(self):
        self.assertIsNone(TabPermissionsFormSet().load(self.dataspace1))

        perms = {"Legal": {"package": ["license", "components"]}}
        DataspaceConfiguration.objects.create(
            dataspace=self.dataspace1,
            tab_permissions=perms,
        )
        self.assertIsNone(TabPermissionsFormSet().load(self.dataspace1))

        initial = [
            {"group_name": "Legal"},
            {"group_name": "Engineering"},
        ]
        formset = TabPermissionsFormSet(initial=initial)
        formset.load(self.dataspace1)
        expected = [
            {"group_name": "Legal", "package": ["license", "components"]},
            {"group_name": "Engineering"},
        ]
        self.assertEqual(expected, formset.initial)

    def test_copy_defaults_form_get_all_dataspaced_models(self):
        dataspaced_models = CopyDefaultsForm.get_all_dataspaced_models()
        self.assertEqual(9, len(dataspaced_models))
        self.assertEqual(7, len(dataspaced_models.get("Component Catalog")))
        self.assertIn("Subcomponent", str(
            dataspaced_models.get("Component Catalog")))

    def test_copy_defaults_formset_serialize_perms(self):
        self.assertEqual({}, CopyDefaultsFormSet().serialize())

        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-0-app_name": "DejaCode",
            "form-0-external source": ["homepage_url"],
        }

        formset = CopyDefaultsFormSet(data)
        self.assertTrue(formset.is_valid())
        expected = {"DejaCode": {"external source": ["homepage_url"]}}
        self.assertEqual(expected, formset.serialize())

    def test_copy_defaults_formset_save_perms(self):
        self.assertEqual(0, DataspaceConfiguration.objects.count())
        CopyDefaultsFormSet().save(self.dataspace1)

        configuration = DataspaceConfiguration.objects.get(
            dataspace=self.dataspace1)
        self.assertEqual({}, configuration.copy_defaults)

        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-0-app_name": "DejaCode",
            "form-0-external source": ["homepage_url"],
        }

        formset = CopyDefaultsFormSet(data)
        self.assertTrue(formset.is_valid())
        formset.save(self.dataspace1)
        configuration = DataspaceConfiguration.objects.get(
            dataspace=self.dataspace1)
        expected = {"DejaCode": {"external source": ["homepage_url"]}}
        self.assertEqual(expected, configuration.copy_defaults)

    def test_copy_defaults_formset_load_perms(self):
        self.assertIsNone(CopyDefaultsFormSet().load(self.dataspace1))

        copy_defaults = {"DejaCode": {"external source": ["homepage_url"]}}
        DataspaceConfiguration.objects.create(
            dataspace=self.dataspace1,
            copy_defaults=copy_defaults,
        )
        self.assertIsNone(CopyDefaultsFormSet().load(self.dataspace1))

        initial = [{"app_name": "DejaCode"}]
        formset = CopyDefaultsFormSet(initial=initial)
        formset.load(self.dataspace1)
        expected = [{"app_name": "DejaCode",
                     "external source": ["homepage_url"]}]
        self.assertEqual(expected, formset.initial)
