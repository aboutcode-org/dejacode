#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from collections import OrderedDict

from django.test import TestCase

from license_expression import LicenseSymbol

from dje.models import Dataspace
from dje.tests import create_superuser
from dje.tests import create_user
from license_library.models import License
from license_library.models import LicenseAnnotation
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseCategory
from license_library.models import LicenseChoice
from license_library.models import LicenseProfile
from license_library.models import LicenseProfileAssignedTag
from license_library.models import LicenseStatus
from license_library.models import LicenseStyle
from license_library.models import LicenseTag
from license_library.models import LicenseTagGroup
from license_library.models import LicenseTagGroupAssignedTag
from organization.models import Owner
from product_portfolio.models import Product


class LicenseModelsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="other")
        self.owner = Owner.objects.create(name="Owner", dataspace=self.dataspace)
        self.category = LicenseCategory.objects.create(
            label="1: Category 1", text="Some text", dataspace=self.dataspace
        )
        self.other_owner = Owner.objects.create(
            name="Other Organization", dataspace=self.other_dataspace
        )
        self.other_category = LicenseCategory.objects.create(
            label="1: Category 1", text="Some text", dataspace=self.other_dataspace
        )
        self.license_profile = LicenseProfile.objects.create(
            name="1: LicenseProfile 1", dataspace=self.dataspace
        )
        self.license_tag_group = LicenseTagGroup.objects.create(
            name="Group 1", dataspace=self.dataspace
        )
        self.license_status = LicenseStatus.objects.create(code="status", dataspace=self.dataspace)
        self.license1 = License.objects.create(
            key="license-1",
            name="License1",
            short_name="License1",
            dataspace=self.dataspace,
            owner=self.owner,
        )

        # Group1: Tag1 (True) and Tag3 (False)
        # Group2: Tag2 (NULL)
        # No Group: Tag 4 (True)
        self.tag1 = LicenseTag.objects.create(
            label="Tag1", text="Text for tag1", dataspace=self.dataspace
        )
        self.tag2 = LicenseTag.objects.create(
            label="Tag2", text="Text for tag2", dataspace=self.dataspace
        )
        self.tag3 = LicenseTag.objects.create(
            label="Tag3", text="Text for tag3", dataspace=self.dataspace
        )
        self.tag4 = LicenseTag.objects.create(
            label="Tag4", text="Text for tag4", dataspace=self.dataspace
        )
        self.assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1, license_tag=self.tag1, value=True, dataspace=self.dataspace
        )
        self.assigned_tag2 = LicenseAssignedTag.objects.create(
            license=self.license1, license_tag=self.tag2, dataspace=self.dataspace
        )
        self.assigned_tag3 = LicenseAssignedTag.objects.create(
            license=self.license1, license_tag=self.tag3, value=False, dataspace=self.dataspace
        )
        self.assigned_tag4 = LicenseAssignedTag.objects.create(
            license=self.license1, license_tag=self.tag4, value=True, dataspace=self.dataspace
        )
        self.group1 = LicenseTagGroup.objects.create(name="Group1", seq=2, dataspace=self.dataspace)
        self.group2 = LicenseTagGroup.objects.create(name="Group2", seq=1, dataspace=self.dataspace)
        LicenseTagGroupAssignedTag.objects.create(
            license_tag_group=self.group1, license_tag=self.tag1, seq=9, dataspace=self.dataspace
        )
        LicenseTagGroupAssignedTag.objects.create(
            license_tag_group=self.group1, license_tag=self.tag3, seq=1, dataspace=self.dataspace
        )
        LicenseTagGroupAssignedTag.objects.create(
            license_tag_group=self.group2, license_tag=self.tag2, seq=2, dataspace=self.dataspace
        )

    def test_save_fk_in_difference_dataspace(self):
        license1 = License(key="license1", name="License1", dataspace=self.dataspace)

        # Owner from other dataspace is not allowed
        license1.owner = self.other_owner
        with self.assertRaises(ValueError):
            license1.save()
        license1.owner = self.owner

        # Category from other dataspace is not allowed
        license1.category = self.other_category
        with self.assertRaises(ValueError):
            license1.save()

    def test_license_tag_slug_label(self):
        self.assertEqual("Tag1", str(self.tag1))
        self.assertEqual("tag__tag1", self.tag1.get_slug_label())
        self.tag1.label = "This Is A Label"
        self.tag1.save()
        self.assertEqual("tag__this_is_a_label", self.tag1.get_slug_label())

    def test_license_profile_get_assigned_tags(self):
        self.license_profile_assigned = LicenseProfileAssignedTag.objects.create(
            license_profile=self.license_profile,
            license_tag=self.tag1,
            value=True,
            dataspace=self.license_profile.dataspace,
        )

        self.assertEqual(
            '"Tag1" in "1: LicenseProfile 1": True', str(self.license_profile_assigned)
        )

        expected = """
        <div class="assigned_tags">
            <div class="media">
                <img alt="True" src="/static/img/icon-yes.png">
                <p>Tag1</p>
            </div>
        </div>"""
        html_result = self.license_profile.get_assigned_tags_html()

        self.assertHTMLEqual(expected, html_result)

    def test_license_unique_filters_for(self):
        selector = self.license1.unique_filters_for(self.other_dataspace)
        expected = {"key": self.license1.key, "dataspace": self.other_dataspace}
        self.assertEqual(expected, selector)

    def test_license_library_models_get_identifier_fields(self):
        inputs = [
            (License, ["key"]),
            (LicenseCategory, ["label"]),
            (LicenseTag, ["label"]),
            (LicenseProfile, ["name"]),
            (LicenseProfileAssignedTag, ["license_profile", "license_tag"]),
            (LicenseStyle, ["name"]),
            (LicenseStatus, ["code"]),
            (LicenseTagGroup, ["name"]),
            (LicenseTagGroupAssignedTag, ["license_tag_group", "license_tag"]),
            (LicenseAssignedTag, ["license", "license_tag"]),
            (LicenseAnnotation, ["uuid"]),
        ]
        for model_class, expected in inputs:
            self.assertEqual(expected, model_class.get_identifier_fields())

    def test_get_absolute_url(self):
        expected = "/licenses/nexB/license-1/"
        self.assertEqual(expected, self.license1.get_absolute_url())

    def test_license_get_tagset(self):
        result = self.license1.get_tagset()
        # We need to patch the result for the empty annotation list comparison
        expected = OrderedDict(
            [
                (
                    "Group1",
                    [["Tag3", False, "Text for tag3", []], ["Tag1", True, "Text for tag1", []]],
                )
            ]
        )
        result["Group1"][0][3] = []
        result["Group1"][1][3] = []
        self.assertEqual(expected, result)

        expected = OrderedDict(
            [
                (
                    "Group1",
                    [["Tag3", False, "Text for tag3", []], ["Tag1", True, "Text for tag1", []]],
                ),
                ("(No Group)", [["Tag4", True, "Text for tag4", []]]),
            ]
        )
        result = self.license1.get_tagset(include_no_group=True)
        result["Group1"][0][3] = []
        result["Group1"][1][3] = []
        result["(No Group)"][0][3] = []
        self.assertEqual(expected, result)

        expected = OrderedDict(
            [
                ("Group2", [["Tag2", None, "Text for tag2", []]]),
                (
                    "Group1",
                    [["Tag3", False, "Text for tag3", []], ["Tag1", True, "Text for tag1", []]],
                ),
            ]
        )
        result = self.license1.get_tagset(include_unknown=True)
        result["Group2"][0][3] = []
        result["Group1"][0][3] = []
        result["Group1"][1][3] = []
        self.assertEqual(expected, result)

    def test_license_tag_get_tag_value_from_label(self):
        label = self.assigned_tag1.license_tag.label

        self.assigned_tag1.value = True
        self.assigned_tag1.save()
        self.assertEqual("True", self.license1.get_tag_value_from_label(label))

        self.assigned_tag1.value = False
        self.assigned_tag1.save()
        self.assertEqual("False", self.license1.get_tag_value_from_label(label))

        self.assigned_tag1.value = None
        self.assigned_tag1.save()
        self.assertEqual("None", self.license1.get_tag_value_from_label(label))

        label = "NON EXISTING LABEL"
        self.assertEqual("", self.license1.get_tag_value_from_label(label))

    def test_license_model_get_license_tab_displayed_tags(self):
        self.assertTrue(self.assigned_tag4.value)
        self.assertFalse(self.assigned_tag4.license_tag.licensetaggroupassignedtag_set.exists())

        expected = [("Tag1", True, "Text for tag1")]
        self.assertEqual(expected, self.license1.get_license_tab_displayed_tags())

        LicenseTagGroupAssignedTag.objects.create(
            license_tag_group=self.group1, license_tag=self.tag4, seq=0, dataspace=self.dataspace
        )
        expected = [("Tag4", True, "Text for tag4"), ("Tag1", True, "Text for tag1")]
        self.assertEqual(expected, self.license1.get_license_tab_displayed_tags())

        self.assigned_tag4.value = False
        self.assigned_tag4.save()
        expected = [("Tag1", True, "Text for tag1")]
        self.assertEqual(expected, self.license1.get_license_tab_displayed_tags())

    def test_license_assigned_tag_model_prefetch_for_license_tab(self):
        # Checking the proper seq order inherited from the groups
        expected = [
            self.assigned_tag2,
            self.assigned_tag3,
            self.assigned_tag1,
            self.assigned_tag4,
        ]
        self.assertEqual(expected, list(LicenseAssignedTag.prefetch_for_license_tab().queryset))

    def test_license_model_attribution_required_property(self):
        self.assertFalse(self.license1.attribution_required)

        self.assigned_tag1.license_tag.attribution_required = True
        self.assigned_tag1.license_tag.save()
        self.assigned_tag1.value = False
        self.assigned_tag1.save()
        self.assertFalse(self.license1.attribution_required)

        self.assigned_tag1.value = True
        self.assigned_tag1.save()
        self.assertTrue(self.license1.attribution_required)

    def test_license_model_redistribution_required_property(self):
        self.assertFalse(self.license1.redistribution_required)

        self.assigned_tag1.license_tag.redistribution_required = True
        self.assigned_tag1.license_tag.save()
        self.assigned_tag1.value = False
        self.assigned_tag1.save()
        self.assertFalse(self.license1.redistribution_required)

        self.assigned_tag1.value = True
        self.assigned_tag1.save()
        self.assertTrue(self.license1.redistribution_required)

    def test_license_model_change_tracking_required_property(self):
        self.assertFalse(self.license1.change_tracking_required)

        self.assigned_tag1.license_tag.change_tracking_required = True
        self.assigned_tag1.license_tag.save()
        self.assigned_tag1.value = False
        self.assigned_tag1.save()
        self.assertFalse(self.license1.change_tracking_required)

        self.assigned_tag1.value = True
        self.assigned_tag1.save()
        self.assertTrue(self.license1.change_tracking_required)

    def test_license_model_data_for_expression_builder(self):
        expected = [("License1 (license-1)", "license-1")]
        data_for_expression_builder = License.objects.all().data_for_expression_builder()
        self.assertEqual(expected, data_for_expression_builder)

    def test_license_library_models_get_exclude_candidates_fields(self):
        input_data = (
            (
                License,
                [
                    "usage_policy",
                    "keywords",
                    "homepage_url",
                    "full_text",
                    "text_urls",
                    "faq_url",
                    "osi_url",
                    "other_urls",
                    "popularity",
                    "reference_notes",
                    "reviewed",
                    "publication_year",
                    "language",
                    "spdx_license_key",
                    "category",
                    "license_style",
                    "license_profile",
                    "license_status",
                    "is_active",
                    "curation_level",
                    "admin_notes",
                    "guidance",
                    "special_obligations",
                    "standard_notice",
                    "is_component_license",
                    "is_exception",
                    "guidance_url",
                ],
            ),
            (LicenseCategory, ["license_type"]),
            (
                LicenseTag,
                [
                    "attribution_required",
                    "change_tracking_required",
                    "default_value",
                    "guidance",
                    "redistribution_required",
                    "show_in_license_list_view",
                ],
            ),
            (LicenseStyle, ["notes"]),
            (LicenseStatus, []),
            (
                LicenseProfile,
                [
                    "examples",
                    "notes",
                ],
            ),
            (
                LicenseTagGroup,
                [
                    "notes",
                    "seq",
                ],
            ),
        )

        for model_class, expected in input_data:
            results = [f.name for f in model_class().get_exclude_candidates_fields()]
            self.assertEqual(sorted(expected), sorted(results))

    def test_license_model_where_used_property(self):
        Product.objects.create(
            name="P1", license_expression=f"{self.license1.key}", dataspace=self.dataspace
        )

        expected = (
            "Product 0\n"
            "Component 0\n"
            "Subcomponent 0\n"
            "Package 0\n"
            "ProductComponent 0\n"
            "ProductPackage 0"
        )
        basic_user = create_user("basic_user", self.dataspace)
        self.assertEqual(expected, self.license1.where_used(user=basic_user))

        expected = (
            "Product 1\n"
            "Component 0\n"
            "Subcomponent 0\n"
            "Package 0\n"
            "ProductComponent 0\n"
            "ProductPackage 0"
        )
        super_user = create_superuser("nexb_user", self.dataspace)
        self.assertEqual(expected, self.license1.where_used(user=super_user))

    def test_license_model_spdx_properties(self):
        self.license1.spdx_license_key = "Apache-2.0"
        self.license1.save()

        self.assertEqual("https://spdx.org/licenses/Apache-2.0.html", self.license1.spdx_url)
        expected = (
            '<a href="https://spdx.org/licenses/Apache-2.0.html" target="_blank">Apache-2.0</a>'
        )
        self.assertEqual(expected, self.license1.spdx_link)

        self.license1.spdx_license_key = "LicenseRef-Apache-2.0"
        self.license1.save()
        self.assertIsNone(self.license1.spdx_url)
        self.assertEqual(self.license1.spdx_license_key, self.license1.spdx_link)

    def test_license_model_spdx_id_property(self):
        self.assertEqual("", self.license1.spdx_license_key)
        self.assertEqual("LicenseRef-dejacode-license-1", self.license1.spdx_id)

        self.license1.spdx_license_key = "Apache-2.0"
        self.license1.save()
        self.assertEqual("Apache-2.0", self.license1.spdx_id)

    def test_license_model_as_spdx(self):
        self.license1.full_text = "License Text"
        self.license1.homepage_url = "https://homepage.url/"
        self.license1.osi_url = "https://homepage.url/osi"
        self.license1.text_urls = "https://homepage.url/text1\nhttps://homepage.url/text2"
        self.license1.other_urls = "https://homepage.url/"
        self.license1.save()

        expected = {
            "licenseId": "LicenseRef-dejacode-license-1",
            "extractedText": "License Text",
            "name": "License1",
            "seeAlsos": [
                "https://github.com/nexB/scancode-toolkit/tree/develop/src/"
                "licensedcode/data/licenses/license-1.LICENSE",
                "https://homepage.url/",
                "https://homepage.url/osi",
                "https://homepage.url/text1",
                "https://homepage.url/text2",
                "https://scancode-licensedb.aboutcode.org/license-1",
            ],
        }
        self.assertEqual(expected, self.license1.as_spdx().as_dict())

    def test_license_model_scancode_url_property(self):
        self.license1.key = "bsd-new"
        self.license1.save()
        expected = (
            "https://github.com/nexB/scancode-toolkit/tree/develop/src/licensedcode"
            "/data/licenses/bsd-new.LICENSE"
        )
        self.assertEqual(expected, self.license1.scancode_url)

    def test_license_model_licensedb_url_property(self):
        self.license1.key = "bsd-new"
        self.license1.save()
        expected = "https://scancode-licensedb.aboutcode.org/bsd-new"
        self.assertEqual(expected, self.license1.licensedb_url)

    def test_license_model_get_all_urls(self):
        self.license1.homepage_url = "https://homepage.url/"
        self.license1.osi_url = "https://homepage.url/osi"
        self.license1.faq_url = "https://homepage.url/faq"
        self.license1.text_urls = "https://homepage.url/text1\nhttps://homepage.url/text2"
        self.license1.other_urls = "https://homepage.url/\nhttps://homepage.url/other\n"
        self.license1.save()

        expected = [
            "https://github.com/nexB/scancode-toolkit/tree/develop/src/licensedcode/"
            "data/licenses/license-1.LICENSE",
            "https://homepage.url/",
            "https://homepage.url/faq",
            "https://homepage.url/osi",
            "https://homepage.url/other",
            "https://homepage.url/text1",
            "https://homepage.url/text2",
            "https://scancode-licensedb.aboutcode.org/license-1",
        ]
        self.assertEqual(expected, self.license1.get_all_urls())


class LicenseChoiceModelTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    def test_license_choice_model_str(self):
        license_choice = LicenseChoice(from_expression="mit OR bsd", to_expression="mit")
        self.assertEqual("mit OR bsd -> mit", str(license_choice))

    def test_license_choice_manager_get_substitutions(self):
        LicenseChoice.objects.create(
            from_expression="apache", to_expression="gpl", dataspace=self.dataspace
        )
        LicenseChoice.objects.create(
            from_expression="bsd", to_expression="mit", dataspace=self.dataspace
        )

        substitutions = LicenseChoice.objects.get_substitutions(self.dataspace)
        self.assertEqual(2, len(substitutions))
        expected1 = {
            LicenseSymbol("apache", is_exception=False): LicenseSymbol("gpl", is_exception=False)
        }
        self.assertIn(expected1, substitutions)
        expected2 = {
            LicenseSymbol("bsd", is_exception=False): LicenseSymbol("mit", is_exception=False)
        }
        self.assertIn(expected2, substitutions)

    def test_license_choice_manager_get_choices_expression(self):
        get_choices_expression = LicenseChoice.objects.get_choices_expression

        # Without choice substitutions
        self.assertEqual("", get_choices_expression(expression="", dataspace=self.dataspace))
        self.assertEqual("", get_choices_expression(expression=None, dataspace=self.dataspace))

        choices = get_choices_expression(expression="bsd OR gpl", dataspace=self.dataspace)
        self.assertEqual("bsd OR gpl", choices)

        LicenseChoice.objects.create(
            from_expression="bsd", to_expression="mit AND apache", dataspace=self.dataspace
        )
        choices = get_choices_expression(expression="bsd OR gps-2.0", dataspace=self.dataspace)
        self.assertEqual("(mit AND apache) OR gps-2.0", choices)

        # With choice substitutions
        self.assertEqual("", get_choices_expression(expression="", dataspace=self.dataspace))
        self.assertEqual("", get_choices_expression(expression=None, dataspace=self.dataspace))

        LicenseChoice.objects.create(
            from_expression="gps-2.0-plus",
            to_expression="gps-2.0 OR gps-2.0-plus OR gps-3.0 OR gps-3.0-plus",
            dataspace=self.dataspace,
        )
        choices = get_choices_expression(expression="gps-2.0-plus", dataspace=self.dataspace)
        self.assertEqual("gps-2.0 OR gps-2.0-plus OR gps-3.0 OR gps-3.0-plus", choices)

        choices = get_choices_expression(expression="gps-2.0-plus-ekiga", dataspace=self.dataspace)
        self.assertEqual("gps-2.0-plus-ekiga", choices)

    def test_license_choice_manager_get_choices_expression_and_sequence(self):
        get_choices_expression = LicenseChoice.objects.get_choices_expression

        choice1 = LicenseChoice.objects.create(
            from_expression="dual-bsd-gpl",
            to_expression="bsd-new OR gps-2.0",
            seq=0,
            dataspace=self.dataspace,
        )
        LicenseChoice.objects.create(
            from_expression="bsd-new OR gps-2.0",
            to_expression="bsd-new",
            seq=1,
            dataspace=self.dataspace,
        )

        choices = get_choices_expression(expression="dual-bsd-gpl", dataspace=self.dataspace)
        self.assertEqual("bsd-new", choices)

        choice1.seq = 2
        choice1.save()
        choices = get_choices_expression(expression="dual-bsd-gpl", dataspace=self.dataspace)
        self.assertEqual("bsd-new OR gps-2.0", choices)
