#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.test import TestCase

from component_catalog.models import Component
from component_catalog.models import ComponentAssignedLicense
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import Package
from component_catalog.models import PackageAssignedLicense
from component_catalog.models import Subcomponent
from component_catalog.models import SubcomponentAssignedLicense
from dje.models import Dataspace
from dje.models import DejacodeUser
from license_library.models import License
from license_library.models import LicenseAnnotation
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseCategory
from license_library.models import LicenseProfile
from license_library.models import LicenseStatus
from license_library.models import LicenseStyle
from license_library.models import LicenseTag
from organization.models import Owner
from policy.models import UsagePolicy
from product_portfolio.models import Product
from product_portfolio.models import ProductAssignedLicense
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductComponentAssignedLicense
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductPackageAssignedLicense
from reporting.forms import MODEL_WHITELIST
from reporting.forms import get_model_data_for_column_template
from reporting.forms import get_model_data_for_order_field
from reporting.forms import get_model_data_for_query
from reporting.introspection import introspector
from reporting.models import get_reportable_models


class ModelIntrospectorTestCase(TestCase):
    maxDiff = None

    def test_reporting_get_reportable_models(self):
        expected = (
            "["
            "<class 'license_library.models.License'>, "
            "<class 'component_catalog.models.Component'>, "
            "<class 'component_catalog.models.Subcomponent'>, "
            "<class 'component_catalog.models.Package'>, "
            "<class 'organization.models.Owner'>, "
            "<class 'workflow.models.Request'>, "
            "<class 'license_library.models.LicenseTag'>, "
            "<class 'license_library.models.LicenseProfile'>, "
            "<class 'license_library.models.LicenseChoice'>, "
            "<class 'product_portfolio.models.Product'>, "
            "<class 'product_portfolio.models.ProductComponent'>, "
            "<class 'product_portfolio.models.ProductPackage'>, "
            "<class 'product_portfolio.models.ProductInventoryItem'>, "
            "<class 'product_portfolio.models.ProductDependency'>, "
            "<class 'product_portfolio.models.CodebaseResource'>"
            "]"
        )
        self.assertEqual(expected, str(get_reportable_models()))

    def test_reporting_get_query_name_map(self):
        expected = {
            "admin_notes": None,
            "annotations": LicenseAnnotation,
            "category": LicenseCategory,
            "created_by": DejacodeUser,
            "created_date": None,
            "curation_level": None,
            "dataspace": Dataspace,
            "faq_url": None,
            "full_text": None,
            "guidance": None,
            "guidance_url": None,
            "homepage_url": None,
            "id": None,
            "is_active": None,
            "is_component_license": None,
            "key": None,
            "keywords": None,
            "last_modified_by": DejacodeUser,
            "last_modified_date": None,
            "license_profile": LicenseProfile,
            "license_status": LicenseStatus,
            "license_style": LicenseStyle,
            "licenseassignedtag": LicenseAssignedTag,
            "name": None,
            "osi_url": None,
            "other_urls": None,
            "owner": Owner,
            "publication_year": None,
            "language": None,
            "reference_notes": None,
            "request_count": None,
            "reviewed": None,
            "short_name": None,
            "spdx_license_key": None,
            "special_obligations": None,
            "tags": LicenseTag,
            "text_urls": None,
            "usage_policy": UsagePolicy,
            "uuid": None,
            "component": Component,
            "componentassignedlicense": ComponentAssignedLicense,
            "subcomponentassignedlicense": SubcomponentAssignedLicense,
            "subcomponent": Subcomponent,
            "productassignedlicense": ProductAssignedLicense,
            "productcomponent": ProductComponent,
            "productcomponentassignedlicense": ProductComponentAssignedLicense,
            "productpackage": ProductPackage,
            "productpackageassignedlicense": ProductPackageAssignedLicense,
            "popularity": None,
            "product": Product,
            "package": Package,
            "packageassignedlicense": PackageAssignedLicense,
            "is_exception": None,
            "standard_notice": None,
        }

        test = introspector.get_query_name_map(
            License, get_fields=True, get_m2m=True, get_related_m2m=True, get_related=True
        )

        # Enable the following to figure out what is missing
        # print set(test.keys()).difference(set(expected.keys()))
        self.assertEqual(expected, test)

    def test_reporting_get_query_name_map_exclude_product_is_active(self):
        query_name_map = introspector.get_query_name_map(
            Product, get_fields=True, get_m2m=True, get_related_m2m=True, get_related=True
        )
        self.assertNotIn("is_active", query_name_map)

    def test_reporting_grouped_fields_feature_respects_whitelist(self):
        expected = [
            {"group": "Direct Fields", "label": "admin_notes", "value": "admin_notes"},
            {"group": "Direct Fields", "label": "category >>", "value": "category"},
            {"group": "Direct Fields", "value": "created_by", "label": "created_by >>"},
            {"group": "Direct Fields", "value": "created_date", "label": "created_date"},
            {"group": "Direct Fields", "label": "curation_level", "value": "curation_level"},
            {"group": "Direct Fields", "label": "faq_url", "value": "faq_url"},
            {"group": "Direct Fields", "label": "full_text", "value": "full_text"},
            {"group": "Direct Fields", "label": "guidance", "value": "guidance"},
            {"group": "Direct Fields", "label": "guidance_url", "value": "guidance_url"},
            {"group": "Direct Fields", "label": "homepage_url", "value": "homepage_url"},
            {"group": "Direct Fields", "label": "id", "value": "id"},
            {"group": "Direct Fields", "label": "is_active", "value": "is_active"},
            {
                "group": "Direct Fields",
                "label": "is_component_license",
                "value": "is_component_license",
            },
            {"group": "Direct Fields", "label": "is_exception", "value": "is_exception"},
            {"group": "Direct Fields", "label": "key", "value": "key"},
            {"group": "Direct Fields", "label": "keywords", "value": "keywords"},
            {"group": "Direct Fields", "label": "language", "value": "language"},
            {"group": "Direct Fields", "value": "last_modified_by", "label": "last_modified_by >>"},
            {
                "group": "Direct Fields",
                "value": "last_modified_date",
                "label": "last_modified_date",
            },
            {"group": "Direct Fields", "label": "license_profile >>", "value": "license_profile"},
            {"group": "Direct Fields", "label": "license_status >>", "value": "license_status"},
            {"group": "Direct Fields", "label": "license_style >>", "value": "license_style"},
            {"group": "Direct Fields", "label": "name", "value": "name"},
            {"group": "Direct Fields", "label": "osi_url", "value": "osi_url"},
            {"group": "Direct Fields", "label": "other_urls", "value": "other_urls"},
            {"group": "Direct Fields", "label": "owner >>", "value": "owner"},
            {"group": "Direct Fields", "label": "popularity", "value": "popularity"},
            {"group": "Direct Fields", "label": "publication_year", "value": "publication_year"},
            {"group": "Direct Fields", "value": "reference_notes", "label": "reference_notes"},
            {"group": "Direct Fields", "label": "request_count", "value": "request_count"},
            {"group": "Direct Fields", "label": "reviewed", "value": "reviewed"},
            {"group": "Direct Fields", "label": "short_name", "value": "short_name"},
            {"group": "Direct Fields", "label": "spdx_license_key", "value": "spdx_license_key"},
            {
                "group": "Direct Fields",
                "label": "special_obligations",
                "value": "special_obligations",
            },
            {"group": "Direct Fields", "label": "standard_notice", "value": "standard_notice"},
            {"group": "Direct Fields", "label": "text_urls", "value": "text_urls"},
            {"group": "Direct Fields", "label": "usage_policy >>", "value": "usage_policy"},
            {"group": "Direct Fields", "label": "uuid", "value": "uuid"},
            {"group": "Many to Many Fields", "label": "tags", "value": "tags"},
            {"group": "Related Many to Many Fields", "label": "component", "value": "component"},
            {"group": "Related Many to Many Fields", "value": "package", "label": "package"},
            {"group": "Related Many to Many Fields", "value": "product", "label": "product"},
            {
                "group": "Related Many to Many Fields",
                "value": "productcomponent",
                "label": "productcomponent",
            },
            {
                "group": "Related Many to Many Fields",
                "label": "productpackage",
                "value": "productpackage",
            },
            {
                "group": "Related Many to Many Fields",
                "label": "subcomponent",
                "value": "subcomponent",
            },
            {"group": "Related Fields", "label": "annotations", "value": "annotations"},
            {
                "group": "Related Fields",
                "label": "componentassignedlicense",
                "value": "componentassignedlicense",
            },
            {
                "group": "Related Fields",
                "label": "licenseassignedtag",
                "value": "licenseassignedtag",
            },
            {
                "group": "Related Fields",
                "value": "packageassignedlicense",
                "label": "packageassignedlicense",
            },
            {
                "group": "Related Fields",
                "value": "subcomponentassignedlicense",
                "label": "subcomponentassignedlicense",
            },
        ]

        model_data = introspector.get_model_data(
            model_classes=[License],
            model_whitelist=MODEL_WHITELIST,
        )

        self.assertEqual(expected, model_data["license_library:license"]["grouped_fields"])

    def test_reporting_inspector_grouped_fields_base(self):
        expected = [
            {"group": "Direct Fields", "label": "admin_notes", "value": "admin_notes"},
            {"group": "Direct Fields", "label": "category >>", "value": "category"},
            {"group": "Direct Fields", "value": "created_by", "label": "created_by >>"},
            {"group": "Direct Fields", "value": "created_date", "label": "created_date"},
            {"group": "Direct Fields", "label": "curation_level", "value": "curation_level"},
            {"group": "Direct Fields", "label": "dataspace >>", "value": "dataspace"},
            {"group": "Direct Fields", "label": "faq_url", "value": "faq_url"},
            {"group": "Direct Fields", "label": "full_text", "value": "full_text"},
            {"group": "Direct Fields", "label": "guidance", "value": "guidance"},
            {"group": "Direct Fields", "label": "guidance_url", "value": "guidance_url"},
            {"group": "Direct Fields", "label": "homepage_url", "value": "homepage_url"},
            {"group": "Direct Fields", "label": "id", "value": "id"},
            {"group": "Direct Fields", "label": "is_active", "value": "is_active"},
            {
                "group": "Direct Fields",
                "label": "is_component_license",
                "value": "is_component_license",
            },
            {"group": "Direct Fields", "label": "is_exception", "value": "is_exception"},
            {"group": "Direct Fields", "label": "key", "value": "key"},
            {"group": "Direct Fields", "label": "keywords", "value": "keywords"},
            {"group": "Direct Fields", "label": "language", "value": "language"},
            {"group": "Direct Fields", "value": "last_modified_by", "label": "last_modified_by >>"},
            {
                "group": "Direct Fields",
                "value": "last_modified_date",
                "label": "last_modified_date",
            },
            {"group": "Direct Fields", "label": "license_profile >>", "value": "license_profile"},
            {"group": "Direct Fields", "label": "license_status >>", "value": "license_status"},
            {"group": "Direct Fields", "label": "license_style >>", "value": "license_style"},
            {"group": "Direct Fields", "label": "name", "value": "name"},
            {"group": "Direct Fields", "label": "osi_url", "value": "osi_url"},
            {"group": "Direct Fields", "label": "other_urls", "value": "other_urls"},
            {"group": "Direct Fields", "label": "owner >>", "value": "owner"},
            {"group": "Direct Fields", "label": "popularity", "value": "popularity"},
            {"group": "Direct Fields", "label": "publication_year", "value": "publication_year"},
            {"group": "Direct Fields", "value": "reference_notes", "label": "reference_notes"},
            {"group": "Direct Fields", "label": "request_count", "value": "request_count"},
            {"group": "Direct Fields", "label": "reviewed", "value": "reviewed"},
            {"group": "Direct Fields", "label": "short_name", "value": "short_name"},
            {"group": "Direct Fields", "label": "spdx_license_key", "value": "spdx_license_key"},
            {
                "group": "Direct Fields",
                "label": "special_obligations",
                "value": "special_obligations",
            },
            {"group": "Direct Fields", "label": "standard_notice", "value": "standard_notice"},
            {"group": "Direct Fields", "label": "text_urls", "value": "text_urls"},
            {"group": "Direct Fields", "label": "usage_policy >>", "value": "usage_policy"},
            {"group": "Direct Fields", "label": "uuid", "value": "uuid"},
            {"group": "Many to Many Fields", "label": "tags", "value": "tags"},
            {"group": "Related Many to Many Fields", "label": "component", "value": "component"},
            {"group": "Related Many to Many Fields", "value": "package", "label": "package"},
            {"group": "Related Many to Many Fields", "value": "product", "label": "product"},
            {
                "group": "Related Many to Many Fields",
                "value": "productcomponent",
                "label": "productcomponent",
            },
            {
                "group": "Related Many to Many Fields",
                "label": "productpackage",
                "value": "productpackage",
            },
            {
                "group": "Related Many to Many Fields",
                "label": "subcomponent",
                "value": "subcomponent",
            },
            {"group": "Related Fields", "label": "annotations", "value": "annotations"},
            {
                "group": "Related Fields",
                "label": "componentassignedlicense",
                "value": "componentassignedlicense",
            },
            {
                "group": "Related Fields",
                "value": "external_references",
                "label": "external_references",
            },
            {
                "group": "Related Fields",
                "label": "licenseassignedtag",
                "value": "licenseassignedtag",
            },
            {
                "group": "Related Fields",
                "value": "packageassignedlicense",
                "label": "packageassignedlicense",
            },
            {
                "group": "Related Fields",
                "value": "productassignedlicense",
                "label": "productassignedlicense",
            },
            {
                "group": "Related Fields",
                "value": "productcomponentassignedlicense",
                "label": "productcomponentassignedlicense",
            },
            {
                "group": "Related Fields",
                "label": "productpackageassignedlicense",
                "value": "productpackageassignedlicense",
            },
            {
                "group": "Related Fields",
                "value": "subcomponentassignedlicense",
                "label": "subcomponentassignedlicense",
            },
        ]
        value = introspector.get_grouped_fields(
            License,
            get_fields=True,
            get_m2m=True,
            get_related_m2m=True,
            get_related=True,
            get_generic_relation=True,
            limit_to=None,
        )

        self.assertEqual(expected, value)

    def test_reporting_omit_foreign_keys(self):
        fields = introspector.get_fields(
            model_class=License,
            get_fields=True,
            omit_foreign_key_fields=False,
            get_m2m=False,
            get_related_m2m=False,
            get_related=False,
            get_generic_relation=False,
            limit_to=None,
        )

        expected = [
            "admin_notes",
            "category",
            "created_by",
            "created_date",
            "curation_level",
            "dataspace",
            "faq_url",
            "full_text",
            "guidance",
            "guidance_url",
            "homepage_url",
            "id",
            "is_active",
            "is_component_license",
            "is_exception",
            "key",
            "keywords",
            "language",
            "last_modified_by",
            "last_modified_date",
            "license_profile",
            "license_status",
            "license_style",
            "name",
            "osi_url",
            "other_urls",
            "owner",
            "popularity",
            "publication_year",
            "reference_notes",
            "request_count",
            "reviewed",
            "short_name",
            "spdx_license_key",
            "special_obligations",
            "standard_notice",
            "text_urls",
            "usage_policy",
            "uuid",
        ]
        self.assertEqual(expected, fields)

        fields = introspector.get_fields(
            model_class=License,
            get_fields=True,
            omit_foreign_key_fields=True,
            get_m2m=False,
            get_related_m2m=False,
            get_related=False,
            get_generic_relation=False,
            limit_to=None,
        )

        expected = [
            "admin_notes",
            "created_date",
            "curation_level",
            "faq_url",
            "full_text",
            "guidance",
            "guidance_url",
            "homepage_url",
            "id",
            "is_active",
            "is_component_license",
            "is_exception",
            "key",
            "keywords",
            "language",
            "last_modified_date",
            "name",
            "osi_url",
            "other_urls",
            "popularity",
            "publication_year",
            "reference_notes",
            "request_count",
            "reviewed",
            "short_name",
            "spdx_license_key",
            "special_obligations",
            "standard_notice",
            "text_urls",
            "uuid",
        ]
        self.assertEqual(expected, fields)

    def test_reporting_get_model_class_via_field_traversal(self):
        input = [  # (starting_model, field, output_model),
            # Direct
            (License, "name", License),
            # Property
            (License, "urn", License),
            # FK
            (License, "owner", License),
            # FK -> Direct
            (License, "owner__id", Owner),
            # FK -> Property
            (License, "owner__urn", Owner),
            # FK -> Many2Many
            (License, "owner__children", Owner),
            # FK -> Many2Many -> Direct
            (License, "owner__children__name", Owner),
            # FK -> Many2Many -> Many2Many
            (License, "owner__children__children", Owner),
            # FK -> Many2Many -> Many2Many -> Direct
            (License, "owner__children__children__name", Owner),
            # Many2Many
            (License, "tags", License),
            # Many2Many -> Direct
            (License, "tags__label", LicenseTag),
            # RelatedM2M
            (License, "licenseassignedtag", License),
            # RelatedM2M -> Direct
            (License, "licenseassignedtag__label", LicenseAssignedTag),
        ]

        model_data = get_model_data_for_query()
        for starting_model, fields, expected in input:
            result = introspector.get_model_class_via_field_traversal(
                fields=fields.split("__"),
                starting_model=starting_model,
                model_data=model_data,
            )
            self.assertEqual(expected, result)

    def test_reporting_get_model_field_via_field_traversal(self):
        model_class = Component
        model_data = get_model_data_for_query()

        input = [
            # FKs
            ("owner", Component._meta.get_field("owner")),
            ("owner__id", Owner._meta.get_field("id")),
            # Many2Many
            ("licenses", Component._meta.get_field("licenses")),
            ("licenses__id", License._meta.get_field("id")),
            # M2M Relationship
            ("componentassignedpackage", Component._meta.get_field("componentassignedpackage")),
            ("componentassignedpackage__id", ComponentAssignedPackage._meta.get_field("id")),
            (
                "componentassignedpackage__component",
                ComponentAssignedPackage._meta.get_field("component"),
            ),
            ("componentassignedpackage__component__id", Component._meta.get_field("id")),
            (
                "componentassignedpackage__package",
                ComponentAssignedPackage._meta.get_field("package"),
            ),
            ("componentassignedpackage__package__id", Package._meta.get_field("id")),
        ]

        for fields, expect in input:
            field_instance = introspector.get_model_field_via_field_traversal(
                fields=fields.split("__"),
                starting_model=model_class,
                model_data=model_data,
            )
            self.assertEqual(expect, field_instance)

    def test_reporting_model_data_fields_whitelist(self):
        expected = {
            "fields": ["username"],
            "meta": {"username": {}},
            "grouped_fields": [
                {"group": "Direct Fields", "value": "username", "label": "username"},
            ],
        }

        query_model_data = get_model_data_for_query()
        self.assertEqual(expected, query_model_data["dje:dejacodeuser"])

        order_field_model_data = get_model_data_for_order_field()
        self.assertNotIn("dje:dejacodeuser", order_field_model_data.keys())

        column_template_model_data = get_model_data_for_column_template()
        self.assertEqual(expected, column_template_model_data["dje:dejacodeuser"])
