#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import uuid
from operator import attrgetter
from pathlib import Path
from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction
from django.db.models import ProtectedError
from django.db.utils import DataError
from django.test import TestCase
from django.urls import reverse

import license_expression
import requests
from license_expression import Licensing

from component_catalog.importers import ComponentImporter
from component_catalog.importers import PackageImporter
from component_catalog.models import PACKAGE_URL_FIELDS
from component_catalog.models import Component
from component_catalog.models import ComponentAssignedLicense
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import ComponentKeyword
from component_catalog.models import ComponentStatus
from component_catalog.models import ComponentType
from component_catalog.models import LicenseExpressionMixin
from component_catalog.models import Package
from component_catalog.models import PackageAlreadyExistsWarning
from component_catalog.models import Subcomponent
from component_catalog.tests import make_package
from dejacode_toolkit import download
from dejacode_toolkit.download import DataCollectionException
from dejacode_toolkit.download import collect_package_data
from dje.copier import copy_object
from dje.models import Dataspace
from dje.models import History
from dje.tests import add_perm
from dje.tests import create_admin
from dje.tests import create_superuser
from dje.tests import create_user
from license_library.models import License
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseChoice
from license_library.models import LicenseTag
from organization.models import Owner
from product_portfolio.tests import make_product


class ComponentCatalogModelsTestCase(TestCase):
    data = Path(__file__).parent / "testfiles"

    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="other")
        self.user = create_superuser("nexb_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)

        self.owner = Owner.objects.create(name="Owner", dataspace=self.dataspace)
        self.other_owner = Owner.objects.create(name="Other_Org", dataspace=self.other_dataspace)
        self.license1 = License.objects.create(
            key="license1",
            name="License1",
            short_name="L1",
            is_active=True,
            spdx_license_key="SPDX-1",
            owner=self.owner,
            dataspace=self.dataspace,
        )
        self.license2 = License.objects.create(
            key="license2",
            name="License2",
            short_name="L2",
            is_active=True,
            owner=self.owner,
            dataspace=self.dataspace,
        )
        self.component_type = ComponentType.objects.create(label="type1", dataspace=self.dataspace)
        self.configuration_status = ComponentStatus.objects.create(
            label="Status1", dataspace=self.dataspace
        )
        self.status1 = ComponentStatus.objects.create(
            label="Label1", text="Status1", default_on_addition=True, dataspace=self.dataspace
        )
        self.status2 = ComponentStatus.objects.create(
            label="Label2", text="Status2", default_on_addition=True, dataspace=self.dataspace
        )
        self.component1 = Component.objects.create(
            owner=self.owner,
            name="a",
            version="1.0",
            type=self.component_type,
            dataspace=self.dataspace,
        )
        self.c1 = Component.objects.create(
            name="c1", owner=self.owner, type=self.component_type, dataspace=self.dataspace
        )
        self.c2 = Component.objects.create(
            name="c2", owner=self.owner, type=self.component_type, dataspace=self.dataspace
        )
        self.c3 = Component.objects.create(
            name="c3", owner=self.owner, type=self.component_type, dataspace=self.dataspace
        )
        self.c4 = Component.objects.create(
            name="c4", owner=self.owner, type=self.component_type, dataspace=self.dataspace
        )
        self.sub_1_2 = Subcomponent.objects.create(
            parent=self.c1, child=self.c2, dataspace=self.c1.dataspace
        )
        self.sub_1_3 = Subcomponent.objects.create(
            parent=self.c1, child=self.c3, dataspace=self.c1.dataspace
        )
        self.sub_2_4 = Subcomponent.objects.create(
            parent=self.c2, child=self.c4, dataspace=self.c2.dataspace
        )
        self.sub_3_4 = Subcomponent.objects.create(
            parent=self.c3, child=self.c4, dataspace=self.c3.dataspace
        )

    def test_component_unique_together(self):
        # A unique component is defined by:
        # Dataspace + Component Name + Component Version
        # It's ok to have a blank "" (empty string) value for the Version

        # First, we try to create a duplication entry of component1
        dup_component = Component(
            name=self.component1.name, version=self.component1.version, dataspace=self.dataspace
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            dup_component.save()

        # Changing the version
        dup_component.version = ""
        dup_component.save()

        dup_component.id = None  # Force insert
        dup_component.uuid = uuid.uuid4()

        with self.assertRaises(IntegrityError), transaction.atomic():
            dup_component.save()

        dup_component.name = "New Name"
        dup_component.save()

    def test_component_model_clean_validate_against_reference_data(self):
        c = Component(
            name=self.c1.name,
            version=self.c1.version,
            dataspace=self.other_dataspace,
        )

        with self.assertRaises(ValidationError) as cm:
            c.clean()

        self.assertEqual(2, len(cm.exception.error_dict.keys()))
        self.assertIn("name", cm.exception.error_dict.keys())
        self.assertIn("version", cm.exception.error_dict.keys())

        absolute_link = self.c1.get_absolute_link(target="_blank")
        copy_link = self.c1.get_html_link(
            self.c1.get_copy_url(), value="Copy to my Dataspace", target="_blank"
        )

        error = (
            "The application object that you are creating already exists as "
            "{} in the reference dataspace. {}".format(absolute_link, copy_link)
        )

        self.assertEqual(error, cm.exception.error_dict["version"][0].message)
        self.assertEqual(error, cm.exception.error_dict["name"][0].message)

        copy_object(self.c1, self.other_dataspace, self.user)
        c.clean()  # Skipped to not raised along _perform_unique_checks()

    def test_component_ordering(self):
        # All the Component will be create with this type to query only on this set
        type_ordering = ComponentType.objects.create(label="ordering", dataspace=self.dataspace)
        # Creating the component in out of order on purpose
        Component.objects.create(name="b", version="", type=type_ordering, dataspace=self.dataspace)
        Component.objects.create(
            name="b", version="1", type=type_ordering, dataspace=self.dataspace
        )
        Component.objects.create(
            name="a", version="2.0", type=type_ordering, dataspace=self.dataspace
        )
        Component.objects.create(
            name="a", version="4.0", type=type_ordering, dataspace=self.dataspace
        )
        Component.objects.create(
            name="a", version="3.0", type=type_ordering, dataspace=self.dataspace
        )
        Component.objects.create(
            name="a", version="1", type=type_ordering, dataspace=self.dataspace
        )
        Component.objects.create(
            name="c", version="1.0", type=type_ordering, dataspace=self.dataspace
        )

        # Expected values in order
        expected = [
            ("a", "1"),
            ("a", "2.0"),
            ("a", "3.0"),
            ("a", "4.0"),
            ("b", ""),
            ("b", "1"),
            ("c", "1.0"),
        ]

        # Testing the default ordering of the queryset
        queryset = Component.objects.filter(type=type_ordering)
        self.assertEqual(7, queryset.count())
        qs_values = queryset.values_list("name", "version")
        self.assertEqual(list(expected), list(qs_values))

    def test_component_get_children(self):
        self.assertEqual([self.c2, self.c3], list(self.c1.get_children()))
        self.assertEqual([self.c4], list(self.c2.get_children()))
        self.assertEqual([self.c4], list(self.c3.get_children()))
        self.assertEqual([], list(self.c4.get_children()))

    def test_component_get_parents(self):
        self.assertEqual([], list(self.c1.get_parents()))
        self.assertEqual([self.c1], list(self.c2.get_parents()))
        self.assertEqual([self.c1], list(self.c3.get_parents()))
        self.assertEqual([self.c2, self.c3], list(self.c4.get_parents()))

    def test_component_is_child_of(self):
        self.assertFalse(self.c1.is_child_of(self.c1))
        self.assertFalse(self.c1.is_child_of(self.c2))
        self.assertFalse(self.c1.is_child_of(self.c3))
        self.assertFalse(self.c1.is_child_of(self.c4))

        self.assertTrue(self.c2.is_child_of(self.c1))
        self.assertFalse(self.c2.is_child_of(self.c2))
        self.assertFalse(self.c2.is_child_of(self.c3))
        self.assertFalse(self.c2.is_child_of(self.c4))

        self.assertFalse(self.c4.is_child_of(self.c1))
        self.assertTrue(self.c4.is_child_of(self.c2))
        self.assertTrue(self.c4.is_child_of(self.c3))
        self.assertFalse(self.c4.is_child_of(self.c4))

    def test_component_is_parent_of(self):
        self.assertFalse(self.c1.is_parent_of(self.c1))
        self.assertTrue(self.c1.is_parent_of(self.c2))
        self.assertTrue(self.c1.is_parent_of(self.c3))
        self.assertFalse(self.c1.is_parent_of(self.c4))

        self.assertFalse(self.c2.is_parent_of(self.c1))
        self.assertFalse(self.c2.is_parent_of(self.c2))
        self.assertFalse(self.c2.is_parent_of(self.c3))
        self.assertTrue(self.c2.is_parent_of(self.c4))

        self.assertFalse(self.c4.is_parent_of(self.c1))
        self.assertFalse(self.c4.is_parent_of(self.c2))
        self.assertFalse(self.c4.is_parent_of(self.c3))
        self.assertFalse(self.c4.is_parent_of(self.c4))

    def test_component_get_ancestors(self):
        self.assertEqual([], list(self.c1.get_ancestors()))
        self.assertEqual([self.c1], list(self.c2.get_ancestors()))
        self.assertEqual([self.c1], list(self.c3.get_ancestors()))
        self.assertEqual(
            sorted([self.c1, self.c2, self.c3], key=attrgetter("name")),
            sorted(self.c4.get_ancestors(), key=attrgetter("name")),
        )

    def test_component_get_ancestor_ids(self):
        self.assertEqual([], self.c1.get_ancestor_ids())
        self.assertEqual([self.c1.id], self.c2.get_ancestor_ids())
        self.assertEqual([self.c1.id], self.c3.get_ancestor_ids())
        self.assertEqual(
            sorted([self.c1.id, self.c2.id, self.c3.id]), sorted(self.c4.get_ancestor_ids())
        )

    def test_component_get_descendants(self):
        self.assertEqual(
            sorted([self.c2, self.c3, self.c4], key=attrgetter("name")),
            sorted(self.c1.get_descendants(), key=attrgetter("name")),
        )
        self.assertEqual([self.c4], list(self.c2.get_descendants()))
        self.assertEqual([self.c4], list(self.c3.get_descendants()))
        self.assertEqual([], list(self.c4.get_descendants()))

        descendants = self.c2.get_descendants(set_direct_parent=True)
        self.assertEqual([self.c4], list(descendants))
        self.assertEqual(self.c2, list(descendants)[0].direct_parent)

    def test_component_get_descendant_ids(self):
        self.assertEqual(
            sorted([self.c2.id, self.c3.id, self.c4.id]), sorted(self.c1.get_descendant_ids())
        )
        self.assertEqual([self.c4.id], self.c2.get_descendant_ids())
        self.assertEqual([self.c4.id], self.c3.get_descendant_ids())
        self.assertEqual([], self.c4.get_descendant_ids())

    def test_component_get_related_ancestors(self):
        self.assertEqual([], list(self.c1.get_related_ancestors()))
        self.assertEqual([self.sub_1_2], list(self.c2.get_related_ancestors()))
        self.assertEqual([self.sub_1_3], list(self.c3.get_related_ancestors()))
        self.assertEqual(
            sorted([self.sub_1_3, self.sub_1_2, self.sub_2_4, self.sub_3_4], key=attrgetter("id")),
            sorted(self.c4.get_related_ancestors(), key=attrgetter("id")),
        )

    def test_component_get_related_descendants(self):
        self.assertEqual(
            sorted([self.sub_1_3, self.sub_1_2, self.sub_2_4, self.sub_3_4], key=attrgetter("id")),
            sorted(self.c1.get_related_descendants(), key=attrgetter("id")),
        )
        self.assertEqual([self.sub_2_4], list(self.c2.get_related_descendants()))
        self.assertEqual([self.sub_3_4], list(self.c3.get_related_descendants()))
        self.assertEqual([], list(self.c4.get_related_descendants()))

    def test_component_is_ancestor_of(self):
        self.assertFalse(self.c1.is_ancestor_of(self.c1))
        self.assertTrue(self.c1.is_ancestor_of(self.c2))
        self.assertTrue(self.c1.is_ancestor_of(self.c3))
        self.assertTrue(self.c1.is_ancestor_of(self.c4))

        self.assertFalse(self.c2.is_ancestor_of(self.c1))
        self.assertFalse(self.c2.is_ancestor_of(self.c2))
        self.assertFalse(self.c2.is_ancestor_of(self.c3))
        self.assertTrue(self.c2.is_ancestor_of(self.c4))

        self.assertFalse(self.c4.is_ancestor_of(self.c1))
        self.assertFalse(self.c4.is_ancestor_of(self.c2))
        self.assertFalse(self.c4.is_ancestor_of(self.c3))
        self.assertFalse(self.c4.is_ancestor_of(self.c4))

    def test_component_is_descendant_of(self):
        self.assertFalse(self.c1.is_descendant_of(self.c1))
        self.assertFalse(self.c1.is_descendant_of(self.c2))
        self.assertFalse(self.c1.is_descendant_of(self.c3))
        self.assertFalse(self.c1.is_descendant_of(self.c4))

        self.assertTrue(self.c2.is_descendant_of(self.c1))
        self.assertFalse(self.c2.is_descendant_of(self.c2))
        self.assertFalse(self.c2.is_descendant_of(self.c3))
        self.assertFalse(self.c2.is_descendant_of(self.c4))

        self.assertTrue(self.c4.is_descendant_of(self.c1))
        self.assertTrue(self.c4.is_descendant_of(self.c2))
        self.assertTrue(self.c4.is_descendant_of(self.c3))
        self.assertFalse(self.c4.is_descendant_of(self.c4))

    def test_component_type_unique_filters_for(self):
        filters = self.component_type.unique_filters_for(self.other_dataspace)
        expected = {"label": self.component_type.label, "dataspace": self.other_dataspace}
        self.assertEqual(expected, filters)

    def test_component_catalog_models_get_identifier_fields(self):
        inputs = [
            (ComponentType, ["label"]),
            (ComponentStatus, ["label"]),
            (Component, ["name", "version"]),
            (Subcomponent, ["parent", "child"]),
            (ComponentAssignedLicense, ["component", "license"]),
            (ComponentKeyword, ["label"]),
        ]
        for model_class, expected in inputs:
            self.assertEqual(expected, model_class.get_identifier_fields())

        self.assertEqual(PACKAGE_URL_FIELDS, Package.get_identifier_fields(purl_fields_only=True))

    def test_component_model_get_absolute_url(self):
        c = Component(name="c1", version="1.0", dataspace=self.dataspace)
        self.assertEqual("/components/nexB/c1/1.0/", c.get_absolute_url())

    def test_component_model_get_absolute_url_with_space(self):
        c = Component(name="c1 c1", dataspace=self.dataspace, version="1.0")
        self.assertEqual("/components/nexB/c1+c1/1.0/", c.get_absolute_url())

    def test_component_model_get_absolute_url_with_slash_in_name(self):
        c = Component(name="c1/c1", dataspace=self.dataspace, version="1.0")
        self.assertEqual("/components/nexB/c1%252Fc1/1.0/", c.get_absolute_url())

    def test_component_model_get_absolute_url_with_multiline_name_ticket(self):
        multilines_name = (
            "* zstream.h - C++ interface to the 'zlib' general purpose"
            " compression library\r\n * $Id: zstream.h"
        )
        c = Component(name=multilines_name, dataspace=self.dataspace, version="1.0")
        expected = (
            "/components/nexB/%252A+zstream.h+-+C%252B%252B+"
            "interface+to+the+%2527zlib%2527+general+purpose+compression"
            "+library%250D%250A+%252A+%2524Id%253A+zstream.h/1.0/"
        )
        self.assertEqual(expected, c.get_absolute_url())

    def test_component_model_get_absolute_url_with_long_component_name_version(self):
        c = Component(
            name="*" * 600,
            owner=self.owner,
            dataspace=self.dataspace,
            version="1" * 400,
        )
        self.assertGreater(len(c.get_absolute_url()), 3000)

    def test_component_license_expression_linked(self):
        expression = "{} AND {}".format(self.license1.key, self.license2.key)

        self.component1.license_expression = expression
        self.component1.save()
        expected = (
            '<a href="{}" title="L1">license1</a> AND <a href="{}" title="L2">license2</a>'.format(
                self.license1.get_absolute_url(), self.license2.get_absolute_url()
            )
        )
        self.assertEqual(expected, self.component1.get_license_expression_linked())

    def test_component_concluded_license_expression_spdx(self):
        self.license1.spdx_license_key = "SPDX-1"
        self.license1.save()

        expression = "{} AND {}".format(self.license1.key, self.license2.key)
        self.component1.license_expression = expression
        self.component1.save()
        expected = "SPDX-1 AND LicenseRef-dejacode-license2"
        self.assertEqual(expected, self.component1.concluded_license_expression_spdx)

        expression = "{} WITH {}".format(self.license1.key, self.license2.key)
        self.component1.license_expression = expression
        self.component1.save()
        # WITH is replaced by AND for "LicenseRef-" exceptions
        expected = "SPDX-1 AND LicenseRef-dejacode-license2"
        self.assertEqual(expected, self.component1.concluded_license_expression_spdx)

        self.license2.spdx_license_key = "SPDX-2"
        self.license2.save()
        self.component1 = Component.objects.get(pk=self.component1.pk)
        # WITH is kept for exceptions in SPDX list
        expected = "SPDX-1 WITH SPDX-2"
        self.assertEqual(expected, self.component1.concluded_license_expression_spdx)

    def test_component_model_license_expression_spdx_properties(self):
        self.license1.spdx_license_key = "SPDX-1"
        self.license1.save()

        expression = "{} AND {}".format(self.license1.key, self.license2.key)
        self.component1.license_expression = expression
        self.component1.declared_license_expression = expression
        self.component1.other_license_expression = expression
        self.component1.save()

        expected = "SPDX-1 AND LicenseRef-dejacode-license2"
        self.assertEqual(expected, self.component1.concluded_license_expression_spdx)
        self.assertEqual(expected, self.component1.declared_license_expression_spdx)
        self.assertEqual(expected, self.component1.other_license_expression_spdx)

        self.component1.license_expression = "unknown"
        self.component1.declared_license_expression = "unknown"
        self.component1.other_license_expression = "unknown"
        self.component1.save()
        expected = "Unknown license key(s): unknown"
        self.assertEqual(expected, self.component1.concluded_license_expression_spdx)
        self.assertEqual(expected, self.component1.declared_license_expression_spdx)
        self.assertEqual(expected, self.component1.other_license_expression_spdx)

    def test_component_model_get_expression_as_spdx(self):
        self.license1.spdx_license_key = "SPDX-1"
        self.license1.save()

        expression_as_spdx = self.component1.get_expression_as_spdx(str(self.license1.key))
        self.assertEqual("SPDX-1", expression_as_spdx)

        expression_as_spdx = self.component1.get_expression_as_spdx("unknown")
        self.assertEqual("Unknown license key(s): unknown", expression_as_spdx)

    def test_get_license_expression_key_as_link_conflict(self):
        # self.license1.key is contained in self.license2.key
        self.license1.key = "w3c"
        self.license2.key = "w3c-documentation"
        self.license1.save()
        self.license2.save()

        self.component1.license_expression = "{} AND {}".format(
            self.license1.key, self.license2.key
        )
        self.component1.save()

        expected = (
            f'<a href="{self.license1.get_absolute_url()}" title="L1">w3c</a> AND'
            f' <a href="{self.license2.get_absolute_url()}" title="L2">w3c-documentation</a>'
        )
        self.assertEqual(expected, self.component1.get_license_expression_linked())

    def test_component_model_save_license_expression_handle_assigned_licenses(self):
        expression = "{} AND {}".format(self.license1.key, self.license2.key)

        c1 = Component.objects.create(
            name="c 1",
            dataspace=self.dataspace,
            license_expression=expression,
        )

        self.assertEqual(2, c1.licenses.count())
        self.assertIn(self.license1, c1.licenses.all())
        self.assertIn(self.license2, c1.licenses.all())

        c1.license_expression = self.license1.key
        c1.save()

        self.assertEqual(1, c1.licenses.count())
        self.assertIn(self.license1, c1.licenses.all())
        self.assertNotIn(self.license2, c1.licenses.all())

        c1.license_expression = ""
        c1.save()
        self.assertEqual(0, c1.licenses.count())

    def test_subcomponent_model_license_expression_handle_assigned_licenses(self):
        self.assertFalse(self.sub_1_2.license_expression)
        self.assertFalse(self.sub_1_2.licenses.exists())

        self.sub_1_2.license_expression = self.license1.key
        self.sub_1_2.save()

        # license1 is assigned from the expression, and license is deleted as not in expression
        self.assertEqual(1, self.sub_1_2.licenses.count())
        self.assertIn(self.license1, self.sub_1_2.licenses.all())

        self.sub_1_2.license_expression = ""
        self.sub_1_2.save()
        self.assertFalse(self.sub_1_2.licenses.exists())

    def test_component_status_model_set_default_on_addition(self):
        # The default_on_addition can only be True on 1 ComponentStatus per Dataspace
        self.assertFalse(ComponentStatus.objects.get(pk=self.status1.pk).default_on_addition)
        self.assertTrue(ComponentStatus.objects.get(pk=self.status2.pk).default_on_addition)

        self.status1.default_on_addition = True
        self.status1.save()
        self.assertTrue(ComponentStatus.objects.get(pk=self.status1.pk).default_on_addition)
        self.assertFalse(ComponentStatus.objects.get(pk=self.status2.pk).default_on_addition)

    def test_component_model_default_status_on_component_addition(self):
        self.status1.default_on_addition = True
        self.status1.save()

        # No status given at creation time, the default is set
        c1 = Component.objects.create(owner=self.owner, name="C1", dataspace=self.dataspace)
        self.assertEqual(self.status1, c1.configuration_status)

        # A status is given at creation time, no default is set
        c2 = Component.objects.create(
            configuration_status=self.status2, name="C2", dataspace=self.dataspace
        )
        self.assertEqual(self.status2, c2.configuration_status)

    def test_component_model_attribution_required_property(self):
        self.component1.license_expression = self.license1.key
        self.component1.save()

        self.assertFalse(self.component1.attribution_required)

        tag1 = LicenseTag.objects.create(
            label="Tag1", text="Text for tag1", dataspace=self.dataspace
        )
        assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1, license_tag=tag1, value=True, dataspace=self.dataspace
        )

        assigned_tag1.license_tag.attribution_required = True
        assigned_tag1.license_tag.save()
        assigned_tag1.value = False
        assigned_tag1.save()
        self.assertFalse(self.component1.attribution_required)

        assigned_tag1.value = True
        assigned_tag1.save()
        self.assertTrue(self.component1.attribution_required)

    def test_component_model_redistribution_required_property(self):
        self.component1.license_expression = self.license1.key
        self.component1.save()

        self.assertFalse(self.component1.redistribution_required)

        tag1 = LicenseTag.objects.create(
            label="Tag1", text="Text for tag1", dataspace=self.dataspace
        )
        assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1, license_tag=tag1, value=True, dataspace=self.dataspace
        )

        assigned_tag1.license_tag.redistribution_required = True
        assigned_tag1.license_tag.save()
        assigned_tag1.value = False
        assigned_tag1.save()
        self.assertFalse(self.component1.redistribution_required)

        assigned_tag1.value = True
        assigned_tag1.save()
        self.assertTrue(self.component1.redistribution_required)

    def test_component_model_change_tracking_required_property(self):
        self.component1.license_expression = self.license1.key
        self.component1.save()

        self.assertFalse(self.component1.change_tracking_required)

        tag1 = LicenseTag.objects.create(
            label="Tag1", text="Text for tag1", dataspace=self.dataspace
        )
        assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1, license_tag=tag1, value=True, dataspace=self.dataspace
        )

        assigned_tag1.license_tag.change_tracking_required = True
        assigned_tag1.license_tag.save()
        assigned_tag1.value = False
        assigned_tag1.save()
        self.assertFalse(self.component1.change_tracking_required)

        assigned_tag1.value = True
        assigned_tag1.save()
        self.assertTrue(self.component1.change_tracking_required)

    def test_get_parents(self):
        self.assertEqual([self.c2, self.c3], list(self.c4.get_parents()))

    def test_get_children(self):
        self.assertEqual([self.c2, self.c3], list(self.c1.get_children()))

    def test_component_deletion(self):
        # We have a Subcomponent relation between c1 and c2
        self.assertTrue(Subcomponent.objects.filter(parent=self.c1, child=self.c2))
        # Deleting c1 should delete the c1 object and the Subcomponent, but c2
        # is not impacted
        self.c1.delete()
        self.assertFalse(Subcomponent.objects.filter(parent__id=self.c1.id, child=self.c2))
        self.assertFalse(Component.objects.filter(id=self.c1.id))
        self.assertTrue(Component.objects.filter(id=self.c2.id))

        # Assigning a License on c2
        self.c2.license_expression = self.license1.key
        self.c2.save()
        self.assertTrue(self.c2.licenses.exists())
        # Deleting the license is not possible, the field is protected.
        with self.assertRaises(ProtectedError):
            self.license1.delete()

        # Although deleting the Component is ok, it will delete the relation in
        # cascade but the license is not impacted
        self.c2.delete()
        self.assertFalse(Component.objects.filter(id=self.c2.id))
        self.assertTrue(License.objects.filter(id=self.license1.id))

    def test_component_compute_completion_level(self):
        component = Component.objects.create(name="Component", dataspace=self.dataspace)

        # Minimum possible for a Component
        self.assertEqual(0, component.compute_completion_level())

        component.notice_text = "a"
        component.copyright = "a"
        component.description = "a"
        component.homepage_url = "a"
        component.notice_filename = "a"
        component.notice_url = "a"
        component.bug_tracking_url = "a"
        component.code_view_url = "a"
        component.primary_language = "a"
        component.release_date = "2013-01-01"
        component.vcs_url = "a"
        component.owner = self.owner
        component.type = self.component_type
        component.version = "a"
        component.keywords = ["Keyword"]
        component.save()

        # Maximum with no m2m
        self.assertEqual(85, component.compute_completion_level())

        component.license_expression = self.license1.key

        component.save()
        package = Package.objects.create(filename="package", dataspace=self.dataspace)
        ComponentAssignedPackage.objects.create(
            component=component, package=package, dataspace=self.dataspace
        )

        # Including m2m
        self.assertEqual(100, component.compute_completion_level())

    def test_component_update_completion_level_method(self):
        self.assertFalse(self.component1.completion_level)
        self.component1.update_completion_level()
        self.component1.refresh_from_db()
        self.assertTrue(self.component1.completion_level)

    def test_component_update_completion_level_after_copy(self):
        # Making sure the weight of m2m is included
        self.component1.license_expression = self.license1.key
        self.component1.save()
        copied_component = copy_object(self.component1, self.other_dataspace, self.user)
        self.assertEqual(15, copied_component.completion_level)

    def test_component_update_completion_level_after_update(self):
        copied_component = copy_object(self.component1, self.other_dataspace, self.user)
        self.assertEqual(8, copied_component.completion_level)

        self.component1.description = "desc"
        self.component1.notice_url = "http://url.com"
        self.component1.license_expression = self.license1.key
        self.component1.save()
        # Let's copy again with update
        copied_component = copy_object(
            self.component1, self.other_dataspace, self.user, update=True
        )
        self.assertEqual(29, copied_component.completion_level)

    def test_component_update_completion_level_after_save_in_ui(self):
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:component_catalog_component_add")
        data = {
            "name": "New Component",
            "version": "1.0",
            "curation_level": 0,
            "copyright": "copyright",
            "related_children-INITIAL_FORMS": 0,
            "related_children-TOTAL_FORMS": 0,
            "componentassignedpackage_set-TOTAL_FORMS": 0,
            "componentassignedpackage_set-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        self.client.post(url, data)
        added_component = Component.objects.get(
            name="New Component", version="1.0", dataspace=self.user.dataspace
        )
        self.assertEqual(9, added_component.completion_level)

    def test_component_update_completion_level_after_import(self):
        # A license is given to ensure that the m2m weight is included.
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-name": "Django",
            "form-0-version": "1.4",
            "form-0-curation_level": 0,
            "form-0-type": self.component_type.id,
            "form-0-license_expression": self.license1.key,
        }
        importer = ComponentImporter(self.user, formset_data=formset_data)
        importer.save_all()
        component = Component.objects.get(
            name="Django", version="1.4", dataspace=self.user.dataspace
        )
        self.assertEqual(12, component.completion_level)

    def test_component_update_completion_level_after_package_import(self):
        self.assertEqual(0, self.component1.componentassignedpackage_set.count())
        self.assertEqual(0, self.component1.completion_level)

        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-filename": "Django-2.0.zip",
            "form-0-component": "{}:{}".format(self.component1.name, self.component1.version),
        }

        importer = PackageImporter(self.user, formset_data=formset_data)
        importer.save_all()

        package1 = Package.objects.get(filename="Django-2.0.zip")
        self.assertEqual(1, self.component1.componentassignedpackage_set.count())
        self.assertEqual(1, package1.componentassignedpackage_set.count())
        self.component1.refresh_from_db()
        self.assertEqual(15, self.component1.completion_level)

    def test_component_update_completion_level_after_mass_update(self):
        self.client.login(username="nexb_user", password="secret")
        self.assertEqual(0, self.component1.completion_level)
        url = reverse("admin:component_catalog_component_changelist")
        data = {
            "_selected_action": [self.component1.id],
            "copyright": "Copyright",
            "chk_id_copyright": "on",
            "description": "Description",
            "chk_id_description": "on",
            "select_across": "False",
            "action": "mass_update",
            "apply": "Update records",
        }
        self.client.post(url, data)
        self.component1.refresh_from_db()
        self.assertEqual(22, self.component1.completion_level)

    def test_component_model_has_license_choices_when_no_license_expression(self):
        self.component1.license_expression = ""
        self.component1.save()
        self.assertFalse(self.component1.has_license_choices)

    def test_component_model_license_choices_expression_and_has_license_choices(self):
        self.component1.license_expression = self.license1.key
        self.component1.save()
        self.assertEqual(
            self.component1.license_expression, self.component1.license_choices_expression
        )
        self.assertFalse(self.component1.has_license_choices)

        LicenseChoice.objects.create(
            from_expression=self.license1.key,
            to_expression=self.license2.key,
            dataspace=self.dataspace,
        )
        # Since it's a cached_property
        self.assertEqual(
            self.component1.license_expression, self.component1.license_choices_expression
        )
        # Force a refresh of the instance
        self.component1 = Component.objects.get(pk=self.component1.pk)
        self.assertEqual(self.license2.key, self.component1.license_choices_expression)
        self.assertTrue(self.component1.has_license_choices)

    def test_mass_update_m2m_fields_scope_to_dataspace(self):
        # The limitation of the m2ms is done in dje.forms.DejacodeMassUpdateForm
        self.client.login(username="nexb_user", password="secret")

        keyword1 = ComponentKeyword.objects.create(label="Keyword1", dataspace=self.dataspace)

        other_keyword = ComponentKeyword.objects.create(
            label="OtherKeyword", dataspace=self.other_dataspace
        )

        data = {
            "_selected_action": [self.component1.pk],
            "action": "mass_update",
            "select_across": 0,
        }

        url = reverse("admin:component_catalog_component_changelist")
        response = self.client.post(url, data)

        self.assertContains(response, keyword1.label)
        self.assertNotContains(response, other_keyword.label)

    def test_mass_update_component_keywords(self):
        self.client.login(username="nexb_user", password="secret")

        keyword1 = ComponentKeyword.objects.create(label="Keyword1", dataspace=self.dataspace)
        keyword2 = ComponentKeyword.objects.create(label="Keyword2", dataspace=self.dataspace)

        data = {
            "_selected_action": [self.c1.pk, self.c2.pk],
            "action": "mass_update",
            "select_across": 0,
            "apply": "Update records",
            "chk_id_keywords": "on",
            "keywords": f"{keyword1.label}, {keyword2.label}",
        }

        url = reverse("admin:component_catalog_component_changelist")
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Updated 2 records")

        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.assertEqual([keyword1.label, keyword2.label], self.c1.keywords)
        self.assertEqual([keyword1.label, keyword2.label], self.c2.keywords)

    def test_mass_update_component_owner(self):
        self.client.login(username="nexb_user", password="secret")

        new_owner = Owner.objects.create(name="new owner", dataspace=self.dataspace)

        data = {
            "_selected_action": [self.component1.pk, self.c2.pk],
            "action": "mass_update",
            "select_across": 0,
            "apply": "Update records",
            "chk_id_owner": "on",
            "owner": new_owner.id,
        }

        url = reverse("admin:component_catalog_component_changelist")
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Updated 2 records")
        self.component1.refresh_from_db()
        self.c2.refresh_from_db()
        self.assertEqual(self.component1.owner, new_owner)
        self.assertEqual(self.c2.owner, new_owner)

        # Check the scoping
        data["owner"] = self.other_owner.id
        response = self.client.post(url, data)
        expected = {
            "owner": ["Select a valid choice. That choice is not one of the available choices."]
        }
        self.assertEqual(expected, response.context["adminform"].form.errors)

    def test_mass_update_component_license_expression(self):
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:component_catalog_component_changelist")
        self.assertFalse(self.component1.licenses.exists())

        data = {
            "_selected_action": [self.component1.pk, self.c2.pk],
            "action": "mass_update",
            "select_across": 0,
        }
        response = self.client.post(url, data)
        self.assertContains(response, "awesomplete-1.1.5.css")
        self.assertContains(response, "awesomplete-1.1.5.min.js")
        self.assertContains(response, "license_expression_builder.js")
        expected = [("L1 (license1)", "license1"), ("L2 (license2)", "license2")]
        self.assertEqual(expected, response.context["client_data"]["license_data"])

        data.update(
            {
                "apply": "Update records",
                "chk_id_license_expression": "on",
                "license_expression": "wrong",
            }
        )

        response = self.client.post(url, data)
        expected = {"license_expression": ["Unknown license key(s): wrong"]}
        self.assertEqual(expected, response.context["adminform"].form.errors)
        expected = '<p class="errornote">Please correct the error below.</p>'
        self.assertContains(response, expected)
        self.assertContains(response, "<li>Unknown license key(s): wrong</li>", html=True)
        # Make sure the enabler checkbox is checked
        expected = (
            '<input type="checkbox" name="chk_id_license_expression"'
            ' class="enabler" checked="checked">'
        )
        self.assertContains(response, expected, html=True)

        data["license_expression"] = "{} OR {}".format(self.license1.key, self.license2.key)
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Updated 2 records")
        self.assertEqual(2, self.component1.licenses.count())
        self.assertIn(self.license1, self.component1.licenses.all())
        self.assertIn(self.license2, self.component1.licenses.all())
        self.assertEqual(2, self.c2.licenses.count())
        self.assertIn(self.license1, self.c2.licenses.all())
        self.assertIn(self.license2, self.c2.licenses.all())

    def test_mass_update_component_protected_fields(self):
        self.client.login(username="admin_user", password="secret")
        url = reverse("admin:component_catalog_component_changelist")
        self.admin_user = add_perm(self.admin_user, "change_component")

        data = {
            "_selected_action": [self.component1.pk],
            "action": "mass_update",
            "select_across": 0,
        }
        response = self.client.post(url, data)
        self.assertNotContains(response, "usage_policy")

        self.admin_user = add_perm(self.admin_user, "change_usage_policy_on_component")
        response = self.client.post(url, data)
        self.assertContains(response, "usage_policy")

    def test_mass_update_packages(self):
        self.client.login(username="nexb_user", password="secret")

        package1 = Package.objects.create(filename="a", dataspace=self.dataspace)
        package2 = Package.objects.create(filename="b", dataspace=self.dataspace)

        data = {
            "_selected_action": [package1.pk, package2.pk],
            "action": "mass_update",
            "select_across": 0,
            "apply": "Update records",
            "chk_id_notes": "on",
            "notes": "Notes",
        }

        url = reverse("admin:component_catalog_package_changelist")
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Updated 2 records")

        package1.refresh_from_db()
        package2.refresh_from_db()
        self.assertEqual("Notes", package1.notes)
        self.assertEqual("Notes", package2.notes)

        # Break the purl on a Package without a filename
        package3 = Package.objects.create(type="type", name="name", dataspace=self.dataspace)
        data["_selected_action"] = [package3.pk]
        data["chk_id_name"] = "on"
        data["name"] = ""
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "1 error(s): package_url or filename required")

    def test_mass_update_package_keywords(self):
        self.client.login(username="nexb_user", password="secret")

        package1 = Package.objects.create(filename="a", dataspace=self.dataspace)
        package2 = Package.objects.create(filename="b", dataspace=self.dataspace)
        keyword1 = ComponentKeyword.objects.create(label="Keyword1", dataspace=self.dataspace)
        keyword2 = ComponentKeyword.objects.create(label="Keyword2", dataspace=self.dataspace)

        data = {
            "_selected_action": [package1.pk, package2.pk],
            "action": "mass_update",
            "select_across": 0,
            "apply": "Update records",
            "chk_id_keywords": "on",
            "keywords": f"{keyword1.label}, {keyword2.label}",
        }

        url = reverse("admin:component_catalog_package_changelist")
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Updated 2 records")

        package1.refresh_from_db()
        package2.refresh_from_db()
        self.assertEqual([keyword1.label, keyword2.label], package1.keywords)
        self.assertEqual([keyword1.label, keyword2.label], package2.keywords)

    def test_subcomponent_str_method(self):
        self.sub_1_2.purpose = "Core"
        self.sub_1_2.save()
        self.assertEqual("Core: c2", str(self.sub_1_2))

    def test_subcomponent_has_same_license_expression_as_component(self):
        self.client.login(username="nexb_user", password="secret")

        self.sub_1_2.license_expression = self.license1.key
        self.sub_1_2.save()
        self.sub_1_2.child.license_expression = self.license1.key
        self.sub_1_2.child.save()

        self.assertEqual(list(self.sub_1_2.licenses.all()), list(self.sub_1_2.child.licenses.all()))
        self.assertTrue(
            Licensing().is_equivalent(
                self.sub_1_2.license_expression, self.sub_1_2.child.license_expression
            )
        )

        self.sub_1_2.license_expression = ""
        self.sub_1_2.save()
        self.assertFalse(
            Licensing().is_equivalent(
                self.sub_1_2.license_expression, self.sub_1_2.child.license_expression
            )
        )

        # Special case: 'oracle-bcl-javaee' contains 'or'
        self.sub_1_2.license_expression = "oracle-bcl-javaee"
        self.sub_1_2.save()
        self.assertFalse(
            Licensing().is_equivalent(
                self.sub_1_2.license_expression, self.sub_1_2.child.license_expression
            )
        )

    def test_component_model_primary_license_property(self):
        c = Component(license_expression="")
        self.assertIsNone(self.component1.primary_license)

        c = Component(license_expression="{} AND {}".format(self.license2.key, self.license1.key))
        self.assertEqual(self.license2.key, c.primary_license)

        c = Component(license_expression="({} OR {})".format(self.license1.key, self.license2.key))
        self.assertEqual(self.license1.key, c.primary_license)

        c = Component(license_expression=self.license2.key)
        self.assertEqual(self.license2.key, c.primary_license)

    def test_component_get_policy_from_primary_license(self):
        from policy.models import AssociatedPolicy
        from policy.models import UsagePolicy

        # Invalid expression, non-existing license
        self.component1.license_expression = "invalid"
        self.component1.save()
        self.assertEqual("invalid", self.component1.primary_license)
        self.assertIsNone(self.component1.get_policy_from_primary_license())

        self.component1.license_expression = ""
        self.component1.save()
        self.assertFalse(self.component1.licenses.exists())
        self.assertIsNone(self.component1.get_policy_from_primary_license())

        self.component1.license_expression = "{} AND {}".format(
            self.license1.key, self.license2.key
        )
        self.component1.save()
        self.component1 = Component.objects.get(id=self.component1.id)
        self.assertEqual(self.license1.key, self.component1.primary_license)
        self.assertIsNone(self.component1.get_policy_from_primary_license())

        license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            dataspace=self.dataspace,
        )
        self.license1.usage_policy = license_policy
        self.license1.save()

        component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.dataspace,
        )

        # No association yet
        self.assertIsNone(self.component1.get_policy_from_primary_license())

        AssociatedPolicy.objects.create(
            from_policy=license_policy,
            to_policy=component_policy,
            dataspace=self.dataspace,
        )
        self.assertEqual(component_policy, self.component1.get_policy_from_primary_license())
        self.assertEqual(component_policy, self.component1.policy_from_primary_license)
        self.assertIsNone(self.component1.usage_policy)

    def test_component_create_save_set_usage_policy_from_license(self):
        from policy.models import AssociatedPolicy
        from policy.models import UsagePolicy

        self.client.login(username="nexb_user", password="secret")

        license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            dataspace=self.dataspace,
        )
        self.license1.usage_policy = license_policy
        self.license1.save()

        component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.dataspace,
        )
        AssociatedPolicy.objects.create(
            from_policy=license_policy,
            to_policy=component_policy,
            dataspace=self.dataspace,
        )

        component1 = Component.objects.create(
            name="component1",
            dataspace=self.dataspace,
            license_expression=self.license1.key,
        )
        self.assertIsNone(component1.usage_policy)

        self.dataspace.set_usage_policy_on_new_component_from_licenses = True
        self.dataspace.save()
        component2 = Component.objects.create(
            name="component2",
            dataspace=self.dataspace,
            license_expression=self.license1.key,
        )
        self.assertEqual(component_policy, component2.usage_policy)

        # Edition
        component1.save()
        self.assertEqual(component_policy, component1.usage_policy)

        # API
        data = {
            "name": "component3",
            "license_expression": self.license1.key,
        }
        response = self.client.post(reverse("api_v2:component-list"), data)
        self.assertEqual(201, response.status_code)
        component3 = Component.objects.latest("id")
        self.assertEqual(component_policy, component3.usage_policy)

        # API Edit
        component4 = Component.objects.create(
            name="component4",
            dataspace=self.dataspace,
        )
        component4_api_url = reverse("api_v2:component-detail", args=[component4.uuid])
        put_data = json.dumps(
            {
                "name": component4.name,
                "license_expression": self.license1.key,
            }
        )
        response = self.client.put(
            component4_api_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(200, response.status_code)
        component4 = Component.objects.get(id=component4.id)
        self.assertEqual(component_policy, component4.usage_policy)

        # Import
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-name": "component5",
            "form-0-curation_level": 0,
            "form-0-license_expression": self.license1.key,
        }
        importer = ComponentImporter(self.user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        component5 = importer.results["added"][0]
        self.assertEqual(component_policy, component5.usage_policy)

    def test_subcomponent_get_policy_from_child_component(self):
        from policy.models import AssociatedPolicy
        from policy.models import UsagePolicy

        self.assertIsNone(self.sub_1_2.get_policy_from_child_component())

        component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.dataspace,
        )
        subcomponent_policy = UsagePolicy.objects.create(
            label="SubcomponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Subcomponent),
            dataspace=self.dataspace,
        )

        self.sub_1_2.child.usage_policy = component_policy
        self.sub_1_2.child.save()

        # No association yet
        self.assertIsNone(self.sub_1_2.get_policy_from_child_component())

        AssociatedPolicy.objects.create(
            from_policy=component_policy,
            to_policy=subcomponent_policy,
            dataspace=self.dataspace,
        )
        self.assertEqual(subcomponent_policy, self.sub_1_2.get_policy_from_child_component())
        self.assertIsNone(self.sub_1_2.usage_policy)

    def test_component_catalog_models_get_exclude_candidates_fields(self):
        input_data = (
            (
                Component,
                [
                    "reference_notes",
                    "usage_policy",
                    "version",
                    "other_license_expression",
                    "owner",
                    "release_date",
                    "description",
                    "copyright",
                    "holder",
                    "homepage_url",
                    "vcs_url",
                    "code_view_url",
                    "bug_tracking_url",
                    "primary_language",
                    "admin_notes",
                    "notice_text",
                    "license_expression",
                    "configuration_status",
                    "type",
                    "approval_reference",
                    "guidance",
                    "is_active",
                    "curation_level",
                    "project",
                    "completion_level",
                    "is_license_notice",
                    "is_copyright_notice",
                    "is_notice_in_codebase",
                    "notice_filename",
                    "notice_url",
                    "declared_license_expression",
                    "dependencies",
                    "codescan_identifier",
                    "website_terms_of_use",
                    "ip_sensitivity_approved",
                    "affiliate_obligations",
                    "affiliate_obligation_triggers",
                    "keywords",
                    "legal_comments",
                    "sublicense_allowed",
                    "express_patent_grant",
                    "covenant_not_to_assert",
                    "indemnification",
                    "legal_reviewed",
                    "distribution_formats_allowed",
                    "acceptable_linkages",
                    "export_restrictions",
                    "approved_download_location",
                    "approved_community_interaction",
                    "cpe",
                ],
            ),
            (ComponentType, ["notes"]),
            (ComponentStatus, ["default_on_addition"]),
            (
                Subcomponent,
                [
                    "extra_attribution_text",
                    "is_deployed",
                    "is_modified",
                    "license_expression",
                    "notes",
                    "purpose",
                    "package_paths",
                    "reference_notes",
                    "usage_policy",
                ],
            ),
            (
                Package,
                [
                    "reference_notes",
                    "usage_policy",
                    "type",
                    "namespace",
                    "name",
                    "version",
                    "qualifiers",
                    "subpath",
                    "holder",
                    "keywords",
                    "cpe",
                    "homepage_url",
                    "vcs_url",
                    "code_view_url",
                    "bug_tracking_url",
                    "sha256",
                    "sha512",
                    "filename",
                    "download_url",
                    "sha1",
                    "md5",
                    "size",
                    "release_date",
                    "primary_language",
                    "description",
                    "project",
                    "notes",
                    "license_expression",
                    "copyright",
                    "notice_text",
                    "author",
                    "declared_license_expression",
                    "dependencies",
                    "repository_homepage_url",
                    "repository_download_url",
                    "api_data_url",
                    "datasource_id",
                    "file_references",
                    "other_license_expression",
                    "parties",
                ],
            ),
        )

        for model_class, expected in input_data:
            results = [f.name for f in model_class().get_exclude_candidates_fields()]
            self.assertEqual(sorted(expected), sorted(results))

    def test_component_create_with_or_and_and_in_license_name_and_key(self):
        or_license = License.objects.create(
            key="orrible",
            name="Orrible license",
            short_name="orL3",
            owner=self.owner,
            dataspace=self.dataspace,
        )
        and_license = License.objects.create(
            key="anddistrophic",
            name="Anddistrophic license",
            short_name="andL4",
            owner=self.owner,
            dataspace=self.dataspace,
        )

        expression = "{} AND {} or {} with {}".format(
            or_license.key, and_license.key, self.license1.key, self.license2.key
        )

        Component.objects.create(
            name="c 1",
            dataspace=self.dataspace,
            license_expression=expression,
        )

    def test_component_save_license_expression_handles_assigned_licenses_with(self):
        c1 = Component.objects.create(
            name="c 1",
            dataspace=self.dataspace,
            license_expression=self.license1.key,
        )
        self.assertEqual(1, c1.licenses.count())
        self.assertIn(self.license1, c1.licenses.all())

        or_license = License.objects.create(
            key="orrible",
            name="Orrible license",
            short_name="orL3",
            owner=self.owner,
            dataspace=self.dataspace,
        )

        c1.license_expression = or_license.key
        c1.save()

    def test_license_expression_mixin_normalized_expression(self):
        lem = LicenseExpressionMixin()
        lem.license_expression = None
        self.assertEqual(None, lem.normalized_expression)

        self.component1.license_expression = f"{self.license1.key} AND {self.license2.key}"
        self.component1.save()

        normalized_expression = self.component1.normalized_expression
        self.assertEqual("license1 AND license2", str(normalized_expression))
        self.assertEqual(license_expression.AND, type(normalized_expression))

    def test_license_expression_mixin_get_license_expression_without_expression(self):
        lem = LicenseExpressionMixin()
        lem.license_expression = None
        self.assertEqual(None, lem.get_license_expression())

    def test_license_expression_mixin_get_license_expression_with_exception(self):
        or_license = License.objects.create(
            key="orrible",
            name="Orrible license",
            short_name="orL3",
            owner=self.owner,
            dataspace=self.dataspace,
        )
        and_license = License.objects.create(
            key="anddistrophic",
            name="Anddistrophic license",
            short_name="andL4",
            owner=self.owner,
            dataspace=self.dataspace,
        )

        expression = "{} AND {} or {} with {}".format(
            or_license.key, and_license.key, self.license1.key, self.license2.key
        )

        comp = Component.objects.create(
            name="c 1",
            dataspace=self.dataspace,
            license_expression=expression,
        )

        expected = "(orrible AND anddistrophic) OR (license1 WITH license2)"
        self.assertEqual(expected, comp.get_license_expression())

        expected = (
            "(<foo Orrible license bar orrible> AND "
            "<foo Anddistrophic license bar anddistrophic>) OR "
            "(<foo License1 bar license1> WITH <foo License2 bar license2>)"
        )
        self.assertEqual(
            expected, comp.get_license_expression(template="<foo {symbol.name} bar {symbol.key}>")
        )

        expected = (
            '(<a href="/licenses/nexB/orrible/" title="orL3">orrible</a> AND '
            '<a href="/licenses/nexB/anddistrophic/" title="andL4">anddistrophic</a>) OR '
            '(<a href="/licenses/nexB/license1/" title="L1">license1</a> WITH '
            '<a href="/licenses/nexB/license2/" title="L2">license2</a>)'
        )
        self.assertEqual(expected, comp.get_license_expression(as_link=True))
        self.assertEqual(
            comp.get_license_expression_linked(), comp.get_license_expression(as_link=True)
        )

        expected = (
            '(<a href="#license_orrible">orL3</a> AND '
            '<a href="#license_anddistrophic">andL4</a>) OR '
            '(<a href="#license_license1">L1</a> WITH <a href="#license_license2">L2</a>)'
        )
        self.assertEqual(expected, comp.get_license_expression_attribution())

    def test_license_expression_mixin_get_primary_license(self):
        or_license = License.objects.create(
            key="orrible",
            name="Orrible license",
            short_name="orL3",
            owner=self.owner,
            dataspace=self.dataspace,
        )
        and_license = License.objects.create(
            key="anddistrophic",
            name="Anddistrophic license",
            short_name="andL4",
            owner=self.owner,
            dataspace=self.dataspace,
        )
        expression = f"{or_license.key} AND {and_license.key} with {self.license2.key}"
        comp = Component.objects.create(
            name="c 1",
            dataspace=self.dataspace,
            license_expression=expression,
        )

        self.assertEqual("orrible AND anddistrophic with license2", str(expression))
        self.assertEqual(or_license.key, comp._get_primary_license())

        # With exception first
        expression = f"{self.license1.key} WITH {self.license2.key} AND {and_license.key}"
        self.assertEqual("license1 WITH license2 AND anddistrophic", str(expression))
        comp.license_expression = expression
        comp.save()
        # Primary license with exceptions are not supported
        self.assertEqual(self.license1.key, comp._get_primary_license())

    def test_component_model_package_property(self):
        self.assertIsNone(self.component1.package)

        package = Package.objects.create(filename="package.zip", dataspace=self.dataspace)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package, dataspace=self.dataspace
        )
        self.component1 = Component.objects.get(pk=self.component1.pk)
        self.assertEqual(package, self.component1.package)

        package2 = Package.objects.create(filename="package2.zip", dataspace=self.dataspace)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package2, dataspace=self.dataspace
        )
        self.component1 = Component.objects.get(pk=self.component1.pk)
        self.assertIsNone(self.component1.package)

    def test_package_model_unique_constraint(self):
        def create_package(dataspace=None, **kwargs):
            return Package.objects.create(**kwargs, dataspace=dataspace or self.dataspace)

        def assert_unique(**kwargs):
            """
            1. Create a Package with provided values
            2. Assert it cannot be created twice with same values
            3. Make sure ti can be create with same values in another Dataspace
            """
            create_package(**kwargs)

            with self.assertRaises(IntegrityError), transaction.atomic():
                create_package(**kwargs)

            create_package(**kwargs, dataspace=self.other_dataspace)

        filename = {
            "filename": "setup.exe",
        }
        download_url = {"download_url": "https://domain.com/setup.exe"}
        simple_purl = {
            "type": "deb",
            "name": "curl",
        }
        simple_purl2 = {
            **simple_purl,
            "type": "git",
        }
        complete_purl = {
            "type": "deb",
            "namespace": "debian",
            "name": "curl",
            "version": "7.50.3-1",
            "qualifiers": "arch=i386",
            "subpath": "googleapis/api/annotations",
        }

        # 1a. filename, no download_url, no purl
        assert_unique(**filename)
        # 1b. same filename, purl
        assert_unique(**filename, **simple_purl)
        # 1c. same filename, another purl
        assert_unique(**filename, **complete_purl)
        # 2g. same filename, optional purl fields
        assert_unique(**filename, version="1.0")
        assert_unique(**filename, version="1.0", namespace="namespace")

        # 2a. download_url, no filename, no purl
        with self.assertRaises(ValidationError), transaction.atomic():
            create_package(**download_url)

        # 2b. download_url, no filename, purl
        assert_unique(**download_url, **simple_purl)
        # 2c. same download_url, filename, same purl
        assert_unique(**download_url, **filename, **simple_purl)
        # 2d. same download_url, no filename, different purl
        assert_unique(**download_url, **simple_purl2)
        # 2e. download_url, filename, no purl
        assert_unique(**download_url, **filename)
        # 2f. download_url, filename, optional purl fields
        assert_unique(**download_url, **filename, version="1.0")
        assert_unique(**download_url, **filename, version="1.0", namespace="namespace")

        # 3a. simple purl, no download_url
        assert_unique(**simple_purl)
        # 3b. complete purl, no download_url
        assert_unique(**complete_purl)
        # 3b. complete purl, download_url
        assert_unique(**complete_purl, **download_url)

    def test_package_model_create_from_data(self):
        with self.assertRaises(ValidationError) as cm:
            Package.create_from_data(user=self.user, data={})
        self.assertEqual("package_url or filename required", cm.exception.message)

        package_data = {
            "not_available": True,
            "filename": "filename.zip",
        }
        package = Package.create_from_data(user=self.user, data=package_data)
        self.assertTrue(package.pk)
        self.assertEqual(package_data["filename"], package.filename)

        package_data = {
            "type": "pypi",
            "name": "name",
            "version": "1.0",
        }
        package = Package.create_from_data(user=self.user, data=package_data)
        self.assertTrue(package.pk)
        self.assertEqual("pkg:pypi/name@1.0", package.package_url)

    def test_package_model_create_from_data_validation(self):
        package_data = {
            "filename": "filename.zip",
            "primary_language": "Python" * 100,
        }

        with self.assertRaises(ValidationError) as cm:
            Package.create_from_data(user=self.user, data=package_data, validate=True)

        expected = {
            "primary_language": ["Ensure this value has at most 50 characters (it has 600)."]
        }
        self.assertEqual(expected, cm.exception.message_dict)

        with self.assertRaises(DataError) as cm:
            Package.create_from_data(user=self.user, data=package_data)
        expected = "value too long for type character varying(50)"
        self.assertEqual(expected, str(cm.exception).strip())

    def test_package_model_update_from_data(self):
        package = Package.objects.create(
            filename="package.zip",
            name="name",
            dataspace=self.dataspace,
        )

        updated_fields = package.update_from_data(self.user, data={})
        self.assertEqual([], updated_fields)

        new_data = {
            "filename": "new_filename",
            "notes": "Some notes",
            "unknown_field": "value",
        }
        updated_fields = package.update_from_data(self.user, data=new_data)
        self.assertEqual(["notes"], updated_fields)
        package.refresh_from_db()
        # Already has a value, not updated
        self.assertEqual("package.zip", package.filename)
        # Empty field, updated
        self.assertEqual(new_data["notes"], package.notes)

        updated_fields = package.update_from_data(self.user, data=new_data, override=True)
        self.assertEqual(["filename"], updated_fields)
        package.refresh_from_db()
        self.assertEqual(new_data["filename"], package.filename)

        new_data = {"filename": "new_filename2"}
        updated_fields = package.update_from_data(user=None, data=new_data, override=True)
        self.assertEqual(["filename"], updated_fields)

        package.update(declared_license_expression="unknown")
        new_data = {"declared_license_expression": "apache-2.0"}
        updated_fields = package.update_from_data(
            user=None, data=new_data, override=False, override_unknown=False
        )
        self.assertEqual([], updated_fields)

        updated_fields = package.update_from_data(
            user=None, data=new_data, override=False, override_unknown=True
        )
        self.assertEqual(["declared_license_expression"], updated_fields)
        package.refresh_from_db()
        self.assertEqual("apache-2.0", package.declared_license_expression)

    @mock.patch("dejacode_toolkit.download.collect_package_data")
    def test_package_model_create_from_url(self, mock_collect):
        self.assertIsNone(Package.create_from_url(url=" ", user=self.user))

        download_url = "https://dejacode.com/archive.zip"
        mock_collect.return_value = {
            "download_url": download_url,
            "filename": "archive.zip",
        }
        package = Package.create_from_url(url=download_url, user=self.user)
        self.assertTrue(package.uuid)
        self.assertEqual(self.user, package.created_by)
        expected = "pkg:generic/archive.zip?download_url=https://dejacode.com/archive.zip"
        self.assertEqual(expected, package.package_url)
        self.assertEqual(download_url, package.download_url)

        with self.assertRaises(PackageAlreadyExistsWarning) as cm:
            Package.create_from_url(url=download_url, user=self.user)
        self.assertIn("already exists in your Dataspace", cm.exception.message)

        purl = "pkg:npm/is-npm@1.0.0"
        mock_collect.return_value = {}
        package = Package.create_from_url(url=purl, user=self.user)
        self.assertTrue(package.uuid)
        self.assertEqual(self.user, package.created_by)
        self.assertEqual(purl, package.package_url)
        mock_collect.assert_called_with("https://registry.npmjs.org/is-npm/-/is-npm-1.0.0.tgz")

        purl = "pkg:pypi/django@5.2"
        download_url = "https://files.pythonhosted.org/packages/Django-5.2.tar.gz"
        mock_collect.return_value = {}
        with mock.patch("dejacode_toolkit.download.PyPIFetcher.get_download_url") as mock_pypi_get:
            mock_pypi_get.return_value = download_url
            package = Package.create_from_url(url=purl, user=self.user)
        self.assertEqual(purl, package.package_url)
        mock_collect.assert_called_with(download_url)

    @mock.patch("component_catalog.models.Package.get_purldb_entries")
    @mock.patch("dejacode_toolkit.purldb.PurlDB.is_configured")
    def test_package_model_create_from_url_enable_purldb_access(
        self, mock_is_configured, mock_get_purldb_entries
    ):
        self.dataspace.enable_purldb_access = True
        self.dataspace.save()
        mock_is_configured.return_value = True
        purldb_entry = {
            "uuid": "7b947095-ab4c-45e3-8af3-6a73bd88e31d",
            "filename": "abbot-1.4.0.jar",
            "release_date": "2023-02-01T00:27:00Z",
            "type": "maven",
            "namespace": "abbot",
            "name": "abbot",
            "version": "1.4.0",
            "primary_language": "Java",
            "description": "Abbot Java GUI Test Library",
            "keywords": ["keyword1", "keyword2"],
            "homepage_url": "http://abbot.sf.net/",
            "download_url": "http://repo1.maven.org/maven2/abbot/abbot/1.4.0/abbot-1.4.0.jar",
            "size": 687192,
            "sha1": "a2363646a9dd05955633b450010b59a21af8a423",
            "declared_license_expression": "bsd-new OR epl-1.0 OR apache-2.0",
            "package_url": "pkg:maven/abbot/abbot@1.4.0",
        }
        mock_get_purldb_entries.return_value = [purldb_entry]

        purl = "pkg:maven/abbot/abbot@1.4.0"
        package = Package.create_from_url(url=purl, user=self.user)
        mock_get_purldb_entries.assert_called_once()

        self.assertEqual(self.user, package.created_by)
        self.assertEqual(purldb_entry["declared_license_expression"], package.license_expression)

        for field_name, value in purldb_entry.items():
            self.assertEqual(value, getattr(package, field_name))

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.is_configured")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.update_from_scan")
    def test_package_model_update_from_scan(self, mock_scio_update_from_scan, mock_is_configured):
        mock_is_configured.return_value = True
        package1 = make_package(self.dataspace, declared_license_expression="mit")
        product1 = make_product(self.dataspace, inventory=[package1])

        pp1 = product1.productpackages.get()
        self.assertEqual("", pp1.license_expression)
        pp1.update(license_expression="unknown")

        results = package1.update_from_scan(user=self.user)
        mock_scio_update_from_scan.assert_not_called()
        self.assertIsNone(results)

        self.dataspace.enable_package_scanning = True
        self.dataspace.update_packages_from_scan = True
        self.dataspace.save()

        mock_scio_update_from_scan.return_value = ["declared_license_expression"]
        results = package1.update_from_scan(user=self.user, update_products=False)
        mock_scio_update_from_scan.assert_called()
        self.assertEqual(["declared_license_expression"], results)
        pp1.refresh_from_db()
        self.assertEqual("unknown", pp1.license_expression)

        results = package1.update_from_scan(user=self.user, update_products=True)
        pp1.refresh_from_db()
        self.assertEqual("mit", pp1.license_expression)

    def test_package_model_get_url_methods(self):
        package = Package(
            filename="filename.zip",
            uuid="dd0afd00-89bd-46d6-b1f0-57b553c44d32",
            dataspace=self.dataspace,
        )
        self.assertEqual(
            "/packages/nexB/filename.zip/dd0afd00-89bd-46d6-b1f0-57b553c44d32/",
            package.get_absolute_url(),
        )
        self.assertEqual(
            "/packages/nexB/filename.zip/dd0afd00-89bd-46d6-b1f0-57b553c44d32/change/",
            package.get_change_url(),
        )
        self.assertEqual(
            "/packages/nexB/dd0afd00-89bd-46d6-b1f0-57b553c44d32/delete/",
            package.get_delete_url(),
        )

        package = Package(
            filename="",
            type="pypi",
            name="django",
            version="1.0",
            subpath="sub/path/",
            uuid="dd0afd00-89bd-46d6-b1f0-57b553c44d32",
            dataspace=self.dataspace,
        )
        self.assertEqual(
            "/packages/nexB/pkg:pypi/django@1.0/dd0afd00-89bd-46d6-b1f0-57b553c44d32/",
            package.get_absolute_url(),
        )
        self.assertEqual(
            "/packages/nexB/pkg:pypi/django@1.0/dd0afd00-89bd-46d6-b1f0-57b553c44d32/change/",
            package.get_change_url(),
        )

    def test_package_model_component_property(self):
        package = Package.objects.create(filename="package.zip", dataspace=self.dataspace)
        self.assertIsNone(package.component)

        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package, dataspace=self.dataspace
        )
        package = Package.objects.get(pk=package.pk)
        self.assertEqual(self.component1, package.component)

        ComponentAssignedPackage.objects.create(
            component=self.c2, package=package, dataspace=self.dataspace
        )
        package = Package.objects.get(pk=package.pk)
        self.assertIsNone(package.component)

    def test_package_model_package_str_repr(self):
        package = Package.objects.create(
            filename="package.zip",
            type="deb",
            namespace="debian",
            name="curl",
            version="7.50.3-1",
            qualifiers="arch=i386",
            subpath="googleapis/api/annotations",
            dataspace=self.dataspace,
        )

        # 1. Full Package URL
        expected = "pkg:deb/debian/curl@7.50.3-1?arch=i386#googleapis/api/annotations"
        self.assertEqual(expected, str(package))
        self.assertEqual(expected, str(package.package_url))

        # 2. Filename
        package.type = ""
        package.save()
        self.assertFalse(package.package_url)
        self.assertEqual("package.zip", str(package))

    def test_package_model_package_save(self):
        with self.assertRaises(ValidationError):
            Package.objects.create(dataspace=self.dataspace)

        self.assertTrue(Package.objects.create(filename="a", dataspace=self.dataspace))
        self.assertTrue(Package.objects.create(type="a", name="a", dataspace=self.dataspace))

    def test_package_model_package_url_properties(self):
        package = Package.objects.create(
            filename="package.zip",
            type="deb",
            namespace="debian",
            name="curl",
            version="7.50.3-1",
            qualifiers="arch=i386",
            subpath="googleapis/api/annotations",
            dataspace=self.dataspace,
        )

        expected = "pkg:deb/debian/curl@7.50.3-1?arch=i386#googleapis/api/annotations"
        self.assertEqual(expected, package.package_url)

        expected = "pkg:deb/debian/curl@7.50.3-1"
        self.assertEqual(expected, package.plain_package_url)

        expected = "deb/debian/curl@7.50.3-1"
        self.assertEqual(expected, package.short_package_url)

        expected = "pkg_deb_debian_curl_7.50.3-1"
        self.assertEqual(expected, package.package_url_filename)

    def test_package_model_set_package_url(self):
        package = Package(dataspace=self.dataspace, filename="p1.zip")

        package_url = "pkg:deb/debian/curl@7.50.3-1?arch=i386#googleapis/api/annotations"
        package.set_package_url(package_url)
        self.assertEqual("deb", package.type)
        self.assertEqual("debian", package.namespace)
        self.assertEqual("curl", package.name)
        self.assertEqual("7.50.3-1", package.version)
        self.assertEqual("arch=i386", package.qualifiers)
        self.assertEqual("googleapis/api/annotations", package.subpath)
        package.save()

        package_url = "pkg:deb/curl"
        package.set_package_url(package_url)
        self.assertEqual("deb", package.type)
        self.assertEqual("", package.namespace)
        self.assertEqual("curl", package.name)
        self.assertEqual("", package.version)
        self.assertEqual("", package.qualifiers)
        self.assertEqual("", package.subpath)
        package.save()

        package_url = f"pkg:maven/mysql/mysql-connector-java@%40MYSQL_CJ_.{'version' * 100}"
        with self.assertRaises(ValidationError) as e:
            package.set_package_url(package_url)
        self.assertEqual('Value too long for field "version".', e.exception.message)

    def test_package_model_update_package_url(self):
        package = Package.objects.create(dataspace=self.dataspace, filename="p1.zip")
        self.assertEqual("", package.download_url)

        package_url = package.update_package_url(self.user)
        self.assertIsNone(package_url)
        self.assertEqual("", package.package_url)

        package.download_url = "http://repo1.maven.org/maven2/jdbm/jdbm/0.20-dev/"
        package.save()
        self.assertTrue(package.last_modified_date)
        initial_modified_date = package.last_modified_date

        package_url = package.update_package_url(self.user, save=True)
        purl = "pkg:maven/jdbm/jdbm@0.20-dev"
        self.assertEqual(purl, str(package_url))
        package.refresh_from_db()
        self.assertEqual(purl, package.package_url)
        self.assertNotEqual(initial_modified_date, package.last_modified_date)
        self.assertFalse(History.objects.get_for_object(package).exists())

        package_url = package.update_package_url(self.user, save=True)
        self.assertIsNone(package_url)

        package_url = package.update_package_url(self.user, save=True, overwrite=True)
        self.assertIsNone(package_url)

        package.download_url = "http://repo1.maven.org/maven2/jdbm/jdbm/1.0/"
        package.save()
        package_url = package.update_package_url(self.user, save=True, overwrite=True, history=True)
        purl = "pkg:maven/jdbm/jdbm@1.0"
        self.assertEqual(purl, str(package_url))
        package.refresh_from_db()
        self.assertEqual(purl, package.package_url)

        history_entry = History.objects.get_for_object(package).get()
        expected_messages = "Set Package URL from Download URL"
        self.assertEqual(expected_messages, history_entry.change_message)

    def test_package_model_as_about(self):
        package_purl_only = Package.objects.create(
            type="type", name="name", dataspace=self.dataspace
        )

        expected = {"about_resource": ".", "name": "name", "package_url": "pkg:type/name"}
        self.assertEqual(expected, package_purl_only.as_about())
        expected = "about_resource: .\nname: name\npackage_url: pkg:type/name\n"
        self.assertEqual(expected, package_purl_only.as_about_yaml())
        self.assertEqual("pkg_type_name.ABOUT", package_purl_only.about_file_name)

        package = Package.objects.create(
            filename="package.zip",
            download_url="http://domain.com/package.zip",
            copyright="copyright on package",
            dataspace=self.dataspace,
        )

        # No Components assigned
        expected = {
            "about_resource": "package.zip",
            "copyright": "copyright on package",
            "download_url": "http://domain.com/package.zip",
            "notice_file": "package.zip.NOTICE",
        }

        extra = {"notice_file": "package.zip.NOTICE"}
        self.assertEqual(expected, package.as_about(extra))
        self.assertEqual("package.zip.ABOUT", package.about_file_name)

        # Assigning 1 Component
        self.component1.copyright = "copyright on component"
        self.component1.save()
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package, dataspace=self.dataspace
        )
        package = Package.objects.get(pk=package.pk)

        expected = {
            "about_resource": "package.zip",
            "copyright": "copyright on package",
            "name": "a",
            "version": "1.0",
            "download_url": "http://domain.com/package.zip",
            "owner": "Owner",
        }

        self.assertEqual(expected, package.as_about())

        expected_yaml = (
            "about_resource: package.zip\n"
            "name: a\n"
            "version: '1.0'\n"
            "download_url: http://domain.com/package.zip\n"
            "copyright: copyright on package\n"
            "owner: Owner\n"
        )
        self.assertEqual(expected_yaml, package.as_about_yaml())

        # No copyright on Package, taken from Component
        package.copyright = ""
        package.save()
        expected["copyright"] = "copyright on component"
        self.assertEqual(expected, package.as_about())

        # More than 1 Component associated
        ComponentAssignedPackage.objects.create(
            component=self.c2, package=package, dataspace=self.dataspace
        )
        package = Package.objects.get(pk=package.pk)

        expected = {
            "about_resource": "package.zip",
            "download_url": "http://domain.com/package.zip",
        }
        self.assertEqual(expected, package.as_about())

        package_with_purl = Package.objects.create(
            filename="package.zip",
            type="deb",
            namespace="debian",
            name="curl",
            version="7.50.3-1",
            qualifiers="arch=i386",
            subpath="googleapis/api/annotations",
            dataspace=self.dataspace,
        )
        expected = {
            "about_resource": "package.zip",
            "name": "curl",
            "package_url": "pkg:deb/debian/curl@7.50.3-1?arch=i386#googleapis/api/annotations",
            "version": "7.50.3-1",
        }
        self.assertEqual(expected, package_with_purl.as_about())

    def test_package_model_about_file_and_notice_file_filename(self):
        p1 = Package.objects.create(
            filename="package.zip",
            dataspace=self.dataspace,
        )
        self.assertEqual("package.zip.ABOUT", p1.about_file_name)
        self.assertEqual("package.zip.NOTICE", p1.notice_file_name)

        p2 = Package.objects.create(
            type="deb",
            name="name",
            version="1.0 beta",
            dataspace=self.dataspace,
        )
        self.assertEqual("pkg_deb_name_1.020beta.ABOUT", p2.about_file_name)
        self.assertEqual("pkg_deb_name_1.020beta.NOTICE", p2.notice_file_name)

    def test_package_model_get_about_files(self):
        # Using a CRLF (windows) line endings to ensure it's converted to LF (unix) in the output
        self.license1.full_text = "line1\r\nline2"
        self.license1.save()

        package = Package.objects.create(
            filename="package.zip",
            download_url="htp://domain.com/package.zip",
            copyright="copyright on package",
            notice_text="Notice\r\nText",
            license_expression=f"{self.license1.key} AND {self.license2.key}",
            dataspace=self.dataspace,
        )

        expected_yaml = (
            "about_resource: package.zip\n"
            "download_url: htp://domain.com/package.zip\n"
            "license_expression: license1 AND license2\n"
            "copyright: copyright on package\n"
            "notice_file: package.zip.NOTICE\n"
            "licenses:\n"
            "  - key: license1\n"
            "    name: License1\n"
            "    file: license1.LICENSE\n"
            "  - key: license2\n"
            "    name: License2\n"
            "    file: license2.LICENSE\n"
        )

        expected = [
            ("package.zip.NOTICE", "Notice\nText"),
            ("license1.LICENSE", "line1\nline2"),
            ("license2.LICENSE", ""),
            ("package.zip.ABOUT", expected_yaml),
        ]

        self.assertEqual(expected, package.get_about_files())

    def test_component_model_get_about_files(self):
        package1 = Package.objects.create(
            filename="package1.zip",
            download_url="htp://domain.com/package.zip",
            copyright="copyright on package",
            notice_text="Notice\r\nText",
            license_expression=f"{self.license1.key} AND {self.license2.key}",
            dataspace=self.dataspace,
        )
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.dataspace
        )

        package2 = Package.objects.create(
            filename="package2.zip",
            notice_text="Notice",
            license_expression=f"{self.license1.key}",
            dataspace=self.dataspace,
        )
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package2, dataspace=self.dataspace
        )

        expected_yaml1 = (
            "about_resource: package1.zip\n"
            "name: a\n"
            "version: '1.0'\n"
            "download_url: htp://domain.com/package.zip\n"
            "license_expression: license1 AND license2\n"
            "copyright: copyright on package\n"
            "notice_file: package1.zip.NOTICE\n"
            "owner: Owner\n"
            "licenses:\n"
            "  - key: license1\n"
            "    name: License1\n"
            "    file: license1.LICENSE\n"
            "  - key: license2\n"
            "    name: License2\n"
            "    file: license2.LICENSE\n"
        )

        expected_yaml2 = (
            "about_resource: package2.zip\n"
            "name: a\n"
            "version: '1.0'\n"
            "license_expression: license1\n"
            "notice_file: package2.zip.NOTICE\n"
            "owner: Owner\n"
            "licenses:\n"
            "  - key: license1\n"
            "    name: License1\n"
            "    file: license1.LICENSE\n"
        )

        expected = [
            ("package1.zip.NOTICE", "Notice\nText"),
            ("license1.LICENSE", ""),
            ("license2.LICENSE", ""),
            ("package1.zip.ABOUT", expected_yaml1),
            ("package2.zip.NOTICE", "Notice"),
            ("license1.LICENSE", ""),
            ("package2.zip.ABOUT", expected_yaml2),
        ]

        self.assertEqual(expected, self.component1.get_about_files())

    def test_component_model_as_spdx(self):
        self.component1.license_expression = f"{self.license1.key} AND {self.license2.key}"
        self.component1.declared_license_expression = self.license1.key
        self.component1.copyright = "copyright on component"
        self.component1.homepage_url = "https://homepage.url"
        self.component1.description = "Description"
        self.component1.release_date = "2020-10-10"
        self.component1.notice_text = ("Notice\r\nText",)
        self.component1.save()

        expected = {
            "name": "a",
            "SPDXID": f"SPDXRef-dejacode-component-{self.component1.uuid}",
            "attributionTexts": [("Notice\r\nText",)],
            "downloadLocation": "NOASSERTION",
            "licenseConcluded": "SPDX-1 AND LicenseRef-dejacode-license2",
            "licenseDeclared": "SPDX-1",
            "copyrightText": "copyright on component",
            "filesAnalyzed": False,
            "supplier": "Organization: Owner",
            "versionInfo": "1.0",
            "homepage": "https://homepage.url",
            "description": "Description",
            "releaseDate": "2020-10-10T00:00:00Z",
        }
        self.assertEqual(expected, self.component1.as_spdx().as_dict())

    def test_component_model_get_spdx_packages(self):
        self.assertEqual([self.component1], self.component1.get_spdx_packages())

    def test_package_model_as_spdx(self):
        package1 = Package.objects.create(
            filename="package1.zip",
            download_url="htp://domain.com/package.zip",
            copyright="copyright on package",
            notice_text="Notice\r\nText",
            license_expression=f"{self.license1.key} AND {self.license2.key}",
            declared_license_expression=self.license1.key,
            sha1="5ba93c9db0cff93f52b521d7420e43f6eda2784f",
            md5="93b885adfe0da089cdf634904fd59f71",
            cpe="cpe:2.3:a:djangoproject:django:0.95:*:*:*:*:*:*:*",
            release_date="2020-10-10",
            homepage_url="https://homepage.url",
            description="Description",
            notes="Notes",
            dataspace=self.dataspace,
        )
        package_url = "pkg:deb/debian/curl@7.50.3-1?arch=i386#subpath"
        package1.set_package_url(package_url)
        package1.save()

        expected = {
            "name": "curl",
            "SPDXID": f"SPDXRef-dejacode-package-{package1.uuid}",
            "downloadLocation": "htp://domain.com/package.zip",
            "licenseConcluded": "SPDX-1 AND LicenseRef-dejacode-license2",
            "licenseDeclared": "SPDX-1",
            "copyrightText": "copyright on package",
            "filesAnalyzed": False,
            "versionInfo": "7.50.3-1",
            "homepage": "https://homepage.url",
            "packageFileName": "package1.zip",
            "description": "Description",
            "releaseDate": "2020-10-10T00:00:00Z",
            "comment": "Notes",
            "checksums": [
                {"algorithm": "SHA1", "checksumValue": "5ba93c9db0cff93f52b521d7420e43f6eda2784f"},
                {"algorithm": "MD5", "checksumValue": "93b885adfe0da089cdf634904fd59f71"},
            ],
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": "pkg:deb/debian/curl@7.50.3-1?arch=i386#subpath",
                },
                {
                    "referenceCategory": "SECURITY",
                    "referenceType": "cpe23Type",
                    "referenceLocator": "cpe:2.3:a:djangoproject:django:0.95:*:*:*:*:*:*:*",
                },
            ],
            "attributionTexts": ["Notice\r\nText"],
        }
        self.assertEqual(expected, package1.as_spdx().as_dict())

    def test_package_model_get_spdx_packages(self):
        package1 = Package.objects.create(
            filename="package1.zip",
            dataspace=self.dataspace,
        )
        self.assertEqual([package1], package1.get_spdx_packages())

    def test_component_model_as_cyclonedx(self):
        self.component1.primary_language = "Python"
        self.component1.homepage_url = "https://homepage.url"
        self.component1.notice_text = "Notice"
        cyclonedx_data = self.component1.as_cyclonedx()
        self.assertEqual("library", cyclonedx_data.type)
        self.assertEqual(self.component1.name, cyclonedx_data.name)
        self.assertEqual(self.component1.version, cyclonedx_data.version)
        self.assertEqual(str(self.component1.uuid), str(cyclonedx_data.bom_ref))

        expected = {
            "aboutcode:homepage_url": "https://homepage.url",
            "aboutcode:notice_text": "Notice",
            "aboutcode:primary_language": "Python",
        }
        properties = {property.name: property.value for property in cyclonedx_data.properties}
        self.assertEqual(expected, properties)

    def test_package_model_as_cyclonedx(self):
        package = Package.objects.create(
            filename="package.zip",
            type="deb",
            namespace="debian",
            name="curl",
            version="7.50.3-1",
            primary_language="Python",
            homepage_url="https://homepage.url",
            download_url="https://download.url",
            notice_text="Notice",
            dataspace=self.dataspace,
        )
        cyclonedx_data = package.as_cyclonedx()

        self.assertEqual("library", cyclonedx_data.type)
        self.assertEqual(package.name, cyclonedx_data.name)
        self.assertEqual(package.version, cyclonedx_data.version)
        self.assertEqual("pkg:deb/debian/curl@7.50.3-1", str(cyclonedx_data.bom_ref))
        package_url = package.get_package_url()
        self.assertEqual(package_url, cyclonedx_data.purl)

        expected = {
            "aboutcode:download_url": "https://download.url",
            "aboutcode:filename": "package.zip",
            "aboutcode:homepage_url": "https://homepage.url",
            "aboutcode:notice_text": "Notice",
            "aboutcode:primary_language": "Python",
        }
        properties = {property.name: property.value for property in cyclonedx_data.properties}
        self.assertEqual(expected, properties)

    def test_package_model_github_repo_url(self):
        urls = [
            ("", None),
            ("http://someurl.com/archive.zip", None),
            (
                "https://github.com/adobe/brackets/releases/download/release-1.14/"
                "Brackets.Release.1.14.32-bit.deb",
                "https://github.com/adobe/brackets/tree/release-1.14",
            ),
            (
                "https://github.com/adobe/brackets/releases/download/release-1.14/"
                "Brackets.Release.1.14.64-bit.deb",
                "https://github.com/adobe/brackets/tree/release-1.14",
            ),
            (
                "https://github.com/adobe/brackets/releases/download/release-1.14/"
                "Brackets.Release.1.14.dmg",
                "https://github.com/adobe/brackets/tree/release-1.14",
            ),
            (
                "https://github.com/adobe/brackets/releases/download/release-1.14/"
                "Brackets.Release.1.14.msi",
                "https://github.com/adobe/brackets/tree/release-1.14",
            ),
            (
                "https://github.com/adobe/brackets/archive/release-1.14.zip",
                "https://github.com/adobe/brackets/tree/release-1.14",
            ),
            (
                "https://github.com/adobe/brackets/archive/release-1.14.tar.gz",
                "https://github.com/adobe/brackets/tree/release-1.14",
            ),
            (
                "https://github.com/adobe/brackets/archive/master.zip",
                "https://github.com/adobe/brackets/tree/master",
            ),
        ]

        for url, expected in urls:
            p = Package()
            p.download_url = url
            self.assertEqual(expected, p.github_repo_url)

    @mock.patch("requests.get")
    def test_collect_package_data(self, mock_get):
        expected_message = (
            "Could not download content: ftp://ftp.denx.de/pub/u-boot/u-boot-2017.11.tar.bz2"
        )
        with self.assertRaisesMessage(DataCollectionException, expected_message):
            collect_package_data("ftp://ftp.denx.de/pub/u-boot/u-boot-2017.11.tar.bz2")

        download_url = "http://domain.com/a%20b.zip;<params>?<query>#<fragment>"

        default_max_length = download.CONTENT_MAX_LENGTH
        download.CONTENT_MAX_LENGTH = 0

        expected_message = "Downloaded content too large (Max: 0\xa0bytes)."
        mock_get.return_value = mock.Mock(
            content=b"\x00", headers={"content-length": 300000000}, status_code=200
        )
        with self.assertRaisesMessage(DataCollectionException, expected_message):
            collect_package_data(download_url)

        download.CONTENT_MAX_LENGTH = default_max_length
        mock_get.return_value = mock.Mock(
            content=b"\x00",
            headers={"content-length": 1},
            status_code=200,
            url=download_url,
        )
        expected_data = {
            "download_url": download_url,
            "filename": "a b.zip",
            "size": 1,
            "sha1": "5ba93c9db0cff93f52b521d7420e43f6eda2784f",
            "md5": "93b885adfe0da089cdf634904fd59f71",
            "sha256": ("6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"),
            "sha512": (
                "b8244d028981d693af7b456af8efa4cad63d282e19ff14942c246e50d9351d2270"
                "4a802a71c3580b6370de4ceb293c324a8423342557d4e5c38438f0e36910ee"
            ),
        }
        self.assertEqual(expected_data, collect_package_data(download_url))

        expected_message = (
            "Exception Value: HTTPConnectionPool"
            "(host='mirror.centos.org', port=80): Read timed out."
        )
        response = mock.MagicMock(headers={}, status_code=200)
        type(response).content = mock.PropertyMock(
            side_effect=requests.ConnectionError(expected_message)
        )
        mock_get.return_value = response
        with self.assertRaisesMessage(DataCollectionException, expected_message):
            collect_package_data(download_url)

        headers = {
            "content-length": 1,
            "content-disposition": 'attachment; filename="another_name.zip"',
        }
        mock_get.return_value = mock.Mock(content=b"\x00", headers=headers, status_code=200)
        expected_data = {
            "download_url": download_url,
            "filename": "another_name.zip",
            "size": 1,
            "sha1": "5ba93c9db0cff93f52b521d7420e43f6eda2784f",
            "md5": "93b885adfe0da089cdf634904fd59f71",
            "sha256": ("6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"),
            "sha512": (
                "b8244d028981d693af7b456af8efa4cad63d282e19ff14942c246e50d9351d2270"
                "4a802a71c3580b6370de4ceb293c324a8423342557d4e5c38438f0e36910ee"
            ),
        }
        self.assertEqual(expected_data, collect_package_data(download_url))

    def test_package_create_save_set_usage_policy_from_license(self):
        from policy.models import AssociatedPolicy
        from policy.models import UsagePolicy

        self.client.login(username="nexb_user", password="secret")

        license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(License),
            dataspace=self.dataspace,
        )
        self.license1.usage_policy = license_policy
        self.license1.save()

        package_policy = UsagePolicy.objects.create(
            label="PackagePolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Package),
            dataspace=self.dataspace,
        )
        AssociatedPolicy.objects.create(
            from_policy=license_policy,
            to_policy=package_policy,
            dataspace=self.dataspace,
        )

        package1 = Package.objects.create(
            filename="package1",
            dataspace=self.dataspace,
            license_expression=self.license1.key,
        )
        self.assertIsNone(package1.usage_policy)

        self.dataspace.set_usage_policy_on_new_component_from_licenses = True
        self.dataspace.save()
        package2 = Package.objects.create(
            filename="package2",
            dataspace=self.dataspace,
            license_expression=self.license1.key,
        )
        self.assertEqual(package_policy, package2.usage_policy)

        # Edition
        package1.save()
        self.assertEqual(package_policy, package1.usage_policy)

        # API Create
        data = {
            "filename": "package3",
            "license_expression": self.license1.key,
        }
        response = self.client.post(reverse("api_v2:package-list"), data)
        self.assertEqual(201, response.status_code)
        package3 = Package.objects.latest("id")
        self.assertEqual(package_policy, package3.usage_policy)

        # API Edit
        package4 = Package.objects.create(
            filename="package4",
            dataspace=self.dataspace,
        )
        package4_api_url = reverse("api_v2:package-detail", args=[package4.uuid])
        put_data = json.dumps(
            {
                "filename": package4.filename,
                "license_expression": self.license1.key,
            }
        )
        response = self.client.put(package4_api_url, data=put_data, content_type="application/json")
        self.assertEqual(200, response.status_code)
        package4 = Package.objects.get(id=package4.id)
        self.assertEqual(package_policy, package4.usage_policy)

        # Import
        formset_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-0-filename": "package5",
            "form-0-license_expression": self.license1.key,
        }
        importer = PackageImporter(self.user, formset_data=formset_data)
        self.assertTrue(importer.formset.is_valid())
        importer.save_all()
        package5 = importer.results["added"][0]
        self.assertEqual(package_policy, package5.usage_policy)

    def test_component_model_where_used_property(self):
        make_product(self.dataspace, inventory=[self.component1])
        basic_user = create_user("basic_user", self.dataspace)
        self.assertEqual("Product 0\n", self.component1.where_used(user=basic_user))

        self.assertTrue(self.user.is_superuser)
        self.assertEqual("Product 1\n", self.component1.where_used(user=self.user))

    def test_package_model_where_used_property(self):
        package1 = Package.objects.create(filename="package", dataspace=self.dataspace)
        make_product(self.dataspace, inventory=[package1])

        basic_user = create_user("basic_user", self.dataspace)
        self.assertEqual("Product 0\nComponent 0\n", package1.where_used(user=basic_user))

        self.assertTrue(self.user.is_superuser)
        self.assertEqual("Product 1\nComponent 0\n", package1.where_used(user=self.user))

        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.dataspace
        )
        self.assertEqual("Product 0\nComponent 1\n", package1.where_used(user=basic_user))

    def test_package_model_inferred_url_property(self):
        package1 = Package.objects.create(filename="package", dataspace=self.dataspace)
        self.assertIsNone(package1.inferred_url)

        package1.set_package_url("pkg:pypi/toml@0.10.2")
        package1.save()
        self.assertEqual("https://pypi.org/project/toml/0.10.2/", package1.inferred_url)

        package1.set_package_url("pkg:github/package-url/packageurl-python@0.10.4?version_prefix=v")
        package1.save()
        expected = "https://github.com/package-url/packageurl-python/tree/v0.10.4"
        self.assertEqual(expected, package1.inferred_url)

    @mock.patch("dejacode_toolkit.purldb.PurlDB.find_packages")
    def test_package_model_get_purldb_entries(self, mock_find_packages):
        purl1 = "pkg:pypi/django@3.0"
        purl2 = "pkg:pypi/django@3.0?file_name=Django-3.0.tar.gz"
        purl3 = "pkg:pypi/django"
        package1 = make_package(self.dataspace, package_url=purl1)
        purldb_entry1 = {
            "purl": purl1,
            "type": "pypi",
            "name": "django",
            "version": "3.0",
        }
        purldb_entry2 = {
            "purl": purl2,
            "type": "pypi",
            "name": "django",
            "version": "3.0",
        }
        purldb_entry3 = {
            "purl": purl3,
            "type": "pypi",
            "name": "django",
        }

        mock_find_packages.return_value = None
        purldb_entries = package1.get_purldb_entries(user=self.user)

        mock_find_packages.return_value = [purldb_entry1, purldb_entry2, purldb_entry3]
        purldb_entries = package1.get_purldb_entries(user=self.user)
        # The purldb_entry2 is excluded as the PURL differs
        self.assertEqual([purldb_entry1, purldb_entry2], purldb_entries)

    @mock.patch("component_catalog.models.Package.get_purldb_entries")
    def test_package_model_update_from_purldb(self, mock_get_purldb_entries):
        purldb_entry = {
            "uuid": "326aa7a8-4f28-406d-89f9-c1404916925b",
            "purl": "pkg:pypi/django@3.0",
            "type": "pypi",
            "name": "django",
            "version": "3.0",
            "primary_language": "Python",
            "description": "Description",
            "release_date": "2019-11-18T00:00:00Z",
            "parties": [],
            "keywords": ["Keyword1", "Keyword2"],
            "download_url": "https://files.pythonhosted.org/packages/38/Django-3.0.tar.gz",
            "sha1": "96ae8d8dd673d4fc92ce2cb2df9cdab6f6fd7d9f",
            "sha256": "0a1efde1b685a6c30999ba00902f23613cf5db864c5a1532d2edf3eda7896a37",
            "copyright": "(c) Copyright",
            "declared_license_expression": "(bsd-simplified AND bsd-new)",
        }

        mock_get_purldb_entries.return_value = [purldb_entry]
        package1 = make_package(
            self.dataspace,
            filename="package",
            # "unknown" values are overrided
            declared_license_expression="unknown",
        )
        updated_fields = package1.update_from_purldb(self.user)
        # Note: PURL fields are never updated.
        expected = [
            "primary_language",
            "description",
            "release_date",
            "keywords",
            "download_url",
            "sha1",
            "sha256",
            "copyright",
            "declared_license_expression",
            "license_expression",
        ]
        self.assertEqual(expected, updated_fields)

        package1.refresh_from_db()
        # Handle release_date separatly
        updated_fields.remove("release_date")
        self.assertEqual(purldb_entry["release_date"], str(package1.release_date))

        for field_name in updated_fields:
            self.assertEqual(purldb_entry[field_name], getattr(package1, field_name))

    @mock.patch("component_catalog.models.Package.get_purldb_entries")
    def test_package_model_update_from_purldb_multiple_entries(self, mock_get_purldb_entries):
        purldb_entry1 = {
            "uuid": "326aa7a8-4f28-406d-89f9-c1404916925b",
            "purl": "pkg:pypi/django@3.0",
            "type": "pypi",
            "name": "django",
            "version": "3.0",
            "keywords": ["Keyword1", "Keyword2"],
            "filename": "Django-3.0.tar.gz",
            "download_url": "https://files.pythonhosted.org/packages/38/Django-3.0.tar.gz",
        }
        purldb_entry2 = {
            "uuid": "e133e70b-8dd3-4cf1-9711-72b1f57523a0",
            "purl": "pkg:pypi/django@3.0",
            "type": "pypi",
            "name": "django",
            "version": "3.0",
            "primary_language": "Python",
            "keywords": ["Keyword1", "Keyword2"],
            "download_url": "https://another.url/Django-3.0.tar.gz",
        }

        mock_get_purldb_entries.return_value = [purldb_entry1, purldb_entry2]
        package1 = make_package(self.dataspace, package_url="pkg:pypi/django@3.0")
        updated_fields = package1.update_from_purldb(self.user)
        expected = ["filename", "keywords", "primary_language"]
        self.assertEqual(expected, sorted(updated_fields))
        self.assertEqual("Django-3.0.tar.gz", package1.filename)
        self.assertEqual(["Keyword1", "Keyword2"], package1.keywords)
        self.assertEqual("Python", package1.primary_language)

    @mock.patch("component_catalog.models.Package.get_purldb_entries")
    def test_package_model_update_from_purldb_duplicate_exception(self, mock_get_purldb_entries):
        package_url = "pkg:pypi/django@3.0"
        download_url = "https://files.pythonhosted.org/packages/38/Django-3.0.tar.gz"
        purldb_entry = {
            "purl": package_url,
            "type": "pypi",
            "name": "django",
            "version": "3.0",
            "download_url": download_url,
            "description": "This value will be updated",
            "md5": "This value is skipped",
            "sha1": "This value is skipped",
        }
        mock_get_purldb_entries.return_value = [purldb_entry]

        # 2 packages with the same "pkg:pypi/django@3.0" PURL:
        # - 1 with a `download_url` value
        # - 1 without a `download_url` value
        make_package(self.dataspace, package_url=package_url, download_url=download_url)
        package_no_download_url = make_package(self.dataspace, package_url=package_url)

        # Updating the package with the `download_url` from the purldb_entry data
        # would violates the unique constraint.
        # This is handle properly by update_from_purldb.
        updated_fields = package_no_download_url.update_from_purldb(self.user)
        self.assertEqual(["description"], updated_fields)
        package_no_download_url.refresh_from_db()
        self.assertEqual(purldb_entry["description"], package_no_download_url.description)

    def test_package_model_get_related_packages_qs(self):
        package_url = "pkg:pypi/django@5.0"
        package1 = make_package(self.dataspace, package_url=package_url)
        related_packages_qs = package1.get_related_packages_qs()
        self.assertQuerySetEqual(related_packages_qs, [package1])

        package2 = make_package(
            self.dataspace,
            package_url=package_url,
            filename="Django-5.0.tar.gz",
        )
        related_packages_qs = package1.get_related_packages_qs()
        self.assertQuerySetEqual(related_packages_qs, [package1, package2])

    def test_package_model_vulnerability_queryset_mixin(self):
        package1 = make_package(self.dataspace, is_vulnerable=True)
        package2 = make_package(self.dataspace)

        qs = Package.objects.with_vulnerability_count()
        self.assertEqual(1, qs.get(pk=package1.pk).vulnerability_count)
        self.assertEqual(0, qs.get(pk=package2.pk).vulnerability_count)

        qs = Package.objects.vulnerable()
        self.assertQuerySetEqual(qs, [package1])

    def test_vulnerability_mixin_is_vulnerable_property(self):
        package1 = make_package(self.dataspace, is_vulnerable=True)
        package2 = make_package(self.dataspace)
        self.assertTrue(package1.is_vulnerable)
        self.assertFalse(package2.is_vulnerable)

    def test_package_queryset_has_package_url(self):
        package1 = make_package(self.dataspace, package_url="pkg:pypi/django@5.0")
        make_package(self.dataspace)
        qs = Package.objects.has_package_url()
        self.assertQuerySetEqual(qs, [package1])

    def test_package_queryset_annotate_sortable_identifier(self):
        package1 = make_package(self.dataspace, package_url="pkg:pypi/django@5.0")
        package2 = make_package(self.dataspace)
        qs = Package.objects.annotate_sortable_identifier()
        self.assertEqual("pypidjango5.0", qs.get(pk=package1.pk).sortable_identifier)
        self.assertEqual(package2.filename, qs.get(pk=package2.pk).sortable_identifier)

    def test_package_queryset_annotate_package_url(self):
        package_url = "pkg:pypi/django@5.0?qualifier=true#path"
        package1 = make_package(self.dataspace, package_url=package_url)
        package2 = make_package(self.dataspace)
        qs = Package.objects.annotate_package_url()
        self.assertEqual(package_url, qs.get(pk=package1.pk).purl)
        self.assertEqual("", qs.get(pk=package2.pk).purl)

    def test_package_queryset_annotate_plain_package_url(self):
        package_url = "pkg:pypi/django@5.0?qualifier=true#path"
        package1 = make_package(self.dataspace, package_url=package_url)
        package2 = make_package(self.dataspace)
        qs = Package.objects.annotate_plain_package_url()
        self.assertEqual("pkg:pypi/django@5.0", qs.get(pk=package1.pk).plain_purl)
        self.assertEqual("", qs.get(pk=package2.pk).plain_purl)
