#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import datetime
from unittest.util import safe_repr

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.db.models import Q
from django.db.models.query import EmptyQuerySet
from django.test import TestCase

from guardian.shortcuts import assign_perm
from guardian.shortcuts import remove_perm

from component_catalog.models import Component
from component_catalog.models import ComponentAssignedLicense
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import Package
from component_catalog.models import Subcomponent
from dje.copier import copy_object
from dje.models import Dataspace
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.tests import create_superuser
from dje.tests import create_user
from dje.validators import validate_url_segment
from dje.validators import validate_version
from license_library.models import License
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseProfile
from license_library.models import LicenseProfileAssignedTag
from license_library.models import LicenseTag
from license_library.models import validate_slug_plus
from organization.models import Owner
from policy.models import UsagePolicy
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductComponentAssignedLicense
from product_portfolio.models import ProductInventoryItem
from reporting.fields import BooleanSelect
from reporting.fields import DateFieldFilterSelect
from reporting.forms import get_model_data_for_column_template
from reporting.forms import get_model_data_for_order_field
from reporting.models import ERROR_STR
from reporting.models import LICENSE_TAG_PREFIX
from reporting.models import Card
from reporting.models import CardLayout
from reporting.models import ColumnTemplate
from reporting.models import ColumnTemplateAssignedField
from reporting.models import Filter
from reporting.models import LayoutAssignedCard
from reporting.models import OrderField
from reporting.models import Query
from reporting.models import Report
from reporting.models import get_by_reporting_key
from workflow.models import Request
from workflow.models import RequestTemplate


class QueryTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("super_user", self.dataspace)
        self.basic_user = create_user("basic_user", self.dataspace)

        self.owner = Owner.objects.create(name="Owner", dataspace=self.dataspace)
        license_tag = LicenseTag.objects.create(
            label="Network Redistribution", text="Text", dataspace=self.dataspace
        )
        license_ = License.objects.create(
            key="license",
            name="License1",
            short_name="License1",
            dataspace=self.dataspace,
            owner=self.owner,
        )
        LicenseAssignedTag.objects.create(
            license=license_, license_tag=license_tag, value=True, dataspace=self.dataspace
        )
        self.component = Component.objects.create(
            name="c1", owner=self.owner, dataspace=self.dataspace
        )
        self.assigned_license = ComponentAssignedLicense.objects.create(
            component=self.component, license=license_, dataspace=self.dataspace
        )

        license_names = ["license_{}".format(x) for x in range(200)]
        for name in license_names:
            License.objects.create(
                key=name, name=name, short_name=name, dataspace=self.dataspace, owner=self.owner
            )

    def test_query_get_qs(self):
        license_ct = ContentType.objects.get_for_model(License)
        query1 = Query.objects.create(
            dataspace=self.dataspace,
            name="GPL2-related licenses",
            content_type=license_ct,
            operator="and",
        )
        self.assertTrue(isinstance(query1.get_qs(), EmptyQuerySet))
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query1,
            field_name="key",
            lookup="exact",
            value="gps-2.0",
        )
        component_ct = ContentType.objects.get_for_model(Component)
        query2 = Query.objects.create(
            dataspace=self.dataspace,
            name="Components under GPL 2",
            content_type=component_ct,
            operator="and",
        )
        Filter.objects.create(
            dataspace=self.dataspace, query=query2, field_name="licenses", lookup="in", value="[]"
        )
        expected = (
            Component.objects.scope(self.dataspace)
            .filter(
                licenses__in=License.objects.scope(self.dataspace)
                .filter(key__exact="gps-2.0")
                .distinct()
            )
            .distinct()
        )
        self.assertEqual(list(expected), list(query2.get_qs()))

    def test_query_get_qs_for_isnull_lookup_with_m2o_and_m2m(self):
        license_ct = ContentType.objects.get_for_model(License)
        query = Query.objects.create(
            dataspace=self.dataspace, name="Q1", content_type=license_ct, operator="and"
        )
        filter1 = Filter.objects.create(
            dataspace=self.dataspace, query=query, field_name="tags", lookup="isnull", value="True"
        )
        self.assertEqual(200, query.get_qs().count())

        filter1.value = "False"
        filter1.save()
        self.assertEqual(1, query.get_qs().count())

        filter1.tags = "licenseassignedtag"
        filter1.save()
        self.assertEqual(1, query.get_qs().count())

        filter1.value = "True"
        filter1.save()
        self.assertEqual(200, query.get_qs().count())

    def test_query_get_qs_for_isempty_lookup_with_json_field(self):
        component_with_keywords = Component.objects.create(
            name="A", keywords=["Keyword1"], dataspace=self.dataspace
        )
        self.assertEqual(2, Component.objects.count())

        component_ct = ContentType.objects.get_for_model(Component)
        query1 = Query.objects.create(
            dataspace=self.dataspace, name="Q1", content_type=component_ct, operator="and"
        )
        filter1 = Filter.objects.create(
            dataspace=self.dataspace,
            query=query1,
            field_name="keywords",
            lookup="isempty",
            value=True,
        )

        self.assertEqual(1, query1.get_qs().count())
        self.assertIn(self.component, query1.get_qs())

        filter1.value = False
        filter1.save()
        self.assertEqual(1, query1.get_qs().count())
        self.assertIn(component_with_keywords, query1.get_qs())

        filter1.negate = True
        filter1.save()
        self.assertEqual(1, query1.get_qs().count())
        self.assertIn(self.component, query1.get_qs())

        filter1.value = True
        filter1.save()
        self.assertEqual(1, query1.get_qs().count())
        self.assertIn(component_with_keywords, query1.get_qs())

    def test_query_security_get_qs_with_related_model_manager_and_product_secured_method(self):
        request_ct = ContentType.objects.get_for_model(Request)
        product_ct = ContentType.objects.get_for_model(Product)
        component_ct = ContentType.objects.get_for_model(Component)

        p1 = Product.objects.create(
            name="p1", version="v1", owner=self.owner, dataspace=self.dataspace
        )
        request_template1 = RequestTemplate.objects.create(
            name="Template1",
            description="Header Desc1",
            dataspace=self.dataspace,
            content_type=product_ct,
        )
        request1 = Request.objects.create(
            title="Title",
            request_template=request_template1,
            requester=self.super_user,
            dataspace=self.dataspace,
            content_type=product_ct,
            object_id=p1.pk,
        )

        query1 = Query.objects.create(
            dataspace=self.dataspace, name="name", content_type=request_ct, operator="and"
        )
        self.assertTrue(isinstance(query1.get_qs(), EmptyQuerySet))

        Filter.objects.create(
            dataspace=self.dataspace, query=query1, field_name="id", lookup="gte", value="0"
        )
        self.assertEqual([request1], list(query1.get_qs(user=self.super_user)))
        self.assertEqual([], list(query1.get_qs(user=self.basic_user)))
        self.assertEqual([], list(query1.get_qs()))
        assign_perm("view_product", self.basic_user, p1)
        self.assertEqual([request1], list(query1.get_qs(user=self.basic_user)))

        remove_perm("view_product", self.basic_user, p1)
        request1.object_id = None
        request1.save()
        self.assertEqual([request1], list(query1.get_qs(user=self.super_user)))
        self.assertEqual([request1], list(query1.get_qs(user=self.basic_user)))
        self.assertEqual([], list(query1.get_qs()))
        assign_perm("view_product", self.basic_user, p1)
        self.assertEqual([request1], list(query1.get_qs(user=self.basic_user)))

        remove_perm("view_product", self.basic_user, p1)
        request1.product_context = p1
        request1.save()
        self.assertEqual([request1], list(query1.get_qs(user=self.super_user)))
        self.assertEqual([], list(query1.get_qs(user=self.basic_user)))
        self.assertEqual([], list(query1.get_qs()))
        assign_perm("view_product", self.basic_user, p1)
        self.assertEqual([request1], list(query1.get_qs(user=self.basic_user)))

        remove_perm("view_product", self.basic_user, p1)
        # No secured QuerySet on Component model
        request_template2 = RequestTemplate.objects.create(
            name="Template2",
            description="Header Desc2",
            dataspace=self.dataspace,
            content_type=component_ct,
        )
        request2 = Request.objects.create(
            title="Title2",
            request_template=request_template2,
            requester=self.super_user,
            dataspace=self.dataspace,
            content_type=component_ct,
            object_id=self.component.pk,
        )
        self.assertEqual(
            [request1, request2], list(query1.get_qs(user=self.super_user).order_by("id"))
        )
        self.assertEqual([request2], list(query1.get_qs(user=self.basic_user)))
        self.assertEqual([], list(query1.get_qs()))

    def test_query_get_qs_containment_filter_not_validated(self):
        Package.objects.create(
            filename="p1", download_url="http://nexb.com", notes="notes", dataspace=self.dataspace
        )
        package_ct = ContentType.objects.get_for_model(Package)
        q1 = Query.objects.create(
            dataspace=self.dataspace, name="Q1", content_type=package_ct, operator="and"
        )
        f1 = Filter.objects.create(
            dataspace=self.dataspace,
            query=q1,
            field_name="download_url",
            lookup="icontains",
            value="nexb",
        )
        self.assertEqual(1, q1.get_qs().count())
        f1.lookup = "contains"
        f1.save()
        self.assertEqual(1, q1.get_qs().count())

        component_ct = ContentType.objects.get_for_model(Component)
        self.component.homepage_url = "http://nexb.com"
        self.component.save()
        q2 = Query.objects.create(
            dataspace=self.dataspace, name="Q2", content_type=component_ct, operator="and"
        )
        f2 = Filter.objects.create(
            dataspace=self.dataspace,
            query=q2,
            field_name="homepage_url",
            lookup="icontains",
            value="nexb",
        )
        self.assertEqual(1, q2.get_qs().count())
        f2.lookup = "contains"
        f2.save()
        self.assertEqual(1, q1.get_qs().count())

    def test_reporting_models_query_get_qs_negate(self):
        license_ct = ContentType.objects.get_for_model(License)
        license_base_qs = License.objects.scope(self.dataspace).order_by("id")

        query1 = Query.objects.create(
            name="query1",
            content_type=license_ct,
            dataspace=self.dataspace,
        )
        filter1 = Filter.objects.create(
            query=query1,
            field_name="key",
            lookup="exact",
            value="gps-2.0",
            dataspace=self.dataspace,
        )

        expected = license_base_qs.filter(key__exact="gps-2.0")
        self.assertQuerySetEqual(expected, query1.get_qs())

        filter1.negate = True
        filter1.save()

        expected = license_base_qs.exclude(key__exact="gps-2.0")
        self.assertEqual(list(expected), list(query1.get_qs()))

        filter1.lookup = "contains"
        filter1.save()
        expected = license_base_qs.exclude(key__contains="gps-2.0")
        self.assertEqual(list(expected), list(query1.get_qs()))

        filter1.lookup = "regex"
        filter1.save()
        expected = license_base_qs.exclude(key__regex="gps-2.0")
        self.assertEqual(list(expected), list(query1.get_qs()))

        filter1.lookup = "gt"
        filter1.save()
        expected = license_base_qs.exclude(key__gt="gps-2.0")
        self.assertEqual(list(expected), list(query1.get_qs()))

        filter1.lookup = "in"
        filter1.value = '["gps-2.0"]'
        filter1.save()
        expected = license_base_qs.exclude(key__in=["gps-2.0"])
        self.assertEqual(list(expected), list(query1.get_qs()))

        filter1.lookup = "isnull"
        filter1.value = True
        filter1.save()
        expected = license_base_qs.exclude(key__isnull=True)
        self.assertEqual(list(expected), list(query1.get_qs()))
        expected = license_base_qs.filter(key__isnull=False)
        self.assertEqual(list(expected), list(query1.get_qs()))

    def test_get_components_whose_licenses_are_tagged_with_network_redistribution(self):
        license_ct = ContentType.objects.get_for_model(License)
        query1 = Query.objects.create(
            dataspace=self.dataspace,
            name="Network redistribution licenses",
            content_type=license_ct,
            operator="and",
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query1,
            field_name="licenseassignedtag__license_tag__label",
            lookup="exact",
            value="Network Redistribution",
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query1,
            field_name="licenseassignedtag__value",
            lookup="exact",
            value="True",
        )

        expected1 = (
            License.objects.scope(self.dataspace)
            .filter(
                Q(licenseassignedtag__license_tag__label__exact="Network Redistribution")
                & Q(licenseassignedtag__value__exact=True)
            )
            .distinct()
        )

        self.assertEqual(list(expected1), list(query1.get_qs()))

        component_ct = ContentType.objects.get_for_model(Component)
        query2 = Query.objects.create(
            dataspace=self.dataspace,
            name="Network  redistribution components",
            content_type=component_ct,
            operator="and",
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query2,
            field_name="licenses__licenseassignedtag__license_tag__label",
            lookup="exact",
            value="Network Redistribution",
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query2,
            field_name="licenses__licenseassignedtag__value",
            lookup="exact",
            value="True",
        )

        expected2 = (
            Component.objects.scope(self.dataspace).filter(licenses__in=expected1).distinct()
        )
        self.assertEqual(list(expected2), list(query2.get_qs()))

        expected3 = [self.component]
        self.assertEqual(expected3, list(query2.get_qs()))

    def test_query_with_category_id_as_filter(self):
        license_ct = ContentType.objects.get_for_model(License)
        query = Query.objects.create(
            dataspace=self.dataspace, name="A query", content_type=license_ct, operator="and"
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="category__id",
            lookup="exact",
            value="1",
        )

        expected = License.objects.filter(category__id__exact=1)
        self.assertEqual(list(expected), list(query.get_qs()))

    def test_query_with_filters_copy(self):
        license_ct = ContentType.objects.get_for_model(License)
        query1 = Query.objects.create(
            dataspace=self.dataspace,
            name="GPL2-related licenses",
            content_type=license_ct,
            operator="and",
        )
        filter1 = Filter.objects.create(
            dataspace=self.dataspace,
            query=query1,
            field_name="key",
            lookup="exact",
            value="gps-2.0",
        )
        order_field = OrderField.objects.create(
            dataspace=self.dataspace, query=query1, field_name="name", seq=0
        )
        other_dataspace = Dataspace.objects.create(name="other")

        copied_object = copy_object(query1, other_dataspace, self.super_user)
        self.assertEqual(query1.uuid, copied_object.uuid)
        self.assertEqual(1, copied_object.filters.count())
        self.assertEqual(filter1.uuid, copied_object.filters.get().uuid)
        self.assertEqual(order_field.uuid, copied_object.order_fields.get().uuid)

    def test_get_model_data_for_order_field_includes_fk_fields(self):
        all_value = get_model_data_for_order_field()
        fields = all_value["product_portfolio:productcomponent"]["fields"]
        expected = [
            "component",
            "copyright",
            "created_by",
            "created_date",
            "download_url",
            "extra_attribution_text",
            "feature",
            "homepage_url",
            "id",
            "is_deployed",
            "is_modified",
            "issue_ref",
            "last_modified_by",
            "last_modified_date",
            "license_expression",
            "name",
            "notes",
            "owner",
            "package_paths",
            "primary_language",
            "product",
            "purpose",
            "reference_notes",
            "review_status",
            "uuid",
            "version",
        ]
        self.assertEqual(expected, fields)

    def test_query_with_order_fields(self):
        license_ct = ContentType.objects.get_for_model(License)
        query = Query.objects.create(
            dataspace=self.dataspace,
            name="A really cool name",
            content_type=license_ct,
            operator="and",
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="key",
            lookup="contains",
            value="license",
        )
        order_field = OrderField.objects.create(
            query=query, field_name="key", seq=0, sort="ascending"
        )

        expected = [
            "license",
            "license_0",
            "license_1",
            "license_10",
            "license_100",
            "license_101",
            "license_102",
            "license_103",
            "license_104",
            "license_105",
        ]
        self.assertEqual(expected, [str(x.key) for x in query.get_qs()[:10]])

        order_field.sort = "descending"
        order_field.save()

        expected = [
            "license_99",
            "license_98",
            "license_97",
            "license_96",
            "license_95",
            "license_94",
            "license_93",
            "license_92",
            "license_91",
            "license_90",
        ]
        self.assertEqual(expected, [str(x.key) for x in query.get_qs()[:10]])

    def test_query_with_order_fields_foreign_key(self):
        productcomponent_ct = ContentType.objects.get_for_model(ProductComponent)
        p1 = Product.objects.create(dataspace=self.dataspace, name="product1")

        query = Query.objects.create(
            dataspace=self.dataspace, name="Q1", content_type=productcomponent_ct, operator="and"
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="product__id",
            lookup="exact",
            value=p1.id,
        )
        order_field = OrderField.objects.create(
            query=query, field_name="component", seq=0, sort="ascending"
        )

        c1 = Component.objects.create(dataspace=self.dataspace, name="ZZZ")
        c2 = Component.objects.create(dataspace=self.dataspace, name="AAA")
        c4 = Component.objects.create(dataspace=self.dataspace, name="1")
        c5 = Component.objects.create(dataspace=self.dataspace, name="zzz")
        c3 = Component.objects.create(dataspace=self.dataspace, name="BBB")
        c6 = Component.objects.create(dataspace=self.dataspace, name="aaa")

        # Creating in a random order
        pc6 = ProductComponent.objects.create(product=p1, component=c6, dataspace=self.dataspace)
        pc3 = ProductComponent.objects.create(product=p1, component=c3, dataspace=self.dataspace)
        pc1 = ProductComponent.objects.create(product=p1, component=c1, dataspace=self.dataspace)
        pc5 = ProductComponent.objects.create(product=p1, component=c5, dataspace=self.dataspace)
        pc_none = ProductComponent.objects.create(product=p1, dataspace=self.dataspace)
        pc2 = ProductComponent.objects.create(product=p1, component=c2, dataspace=self.dataspace)
        pc4 = ProductComponent.objects.create(product=p1, component=c4, dataspace=self.dataspace)

        expected = [
            pc4,  # 1
            pc6,  # aaa
            pc2,  # AAA
            pc3,  # BBB
            pc5,  # zzz
            pc1,  # ZZZ
            pc_none,
        ]
        self.assertEqual(expected, list(query.get_qs(user=self.super_user)))

        order_field.sort = "descending"
        order_field.save()
        expected.reverse()
        self.assertEqual(expected, list(query.get_qs(user=self.super_user)))

    def test_query_with_descendant_lookup(self):
        component_ct = ContentType.objects.get_for_model(Component)

        c2 = Component.objects.create(name="c2", owner=self.owner, dataspace=self.dataspace)
        c3 = Component.objects.create(name="c3", owner=self.owner, dataspace=self.dataspace)

        Subcomponent.objects.create(parent=self.component, child=c2, dataspace=self.dataspace)
        Subcomponent.objects.create(parent=c2, child=c3, dataspace=self.dataspace)

        query1 = Query.objects.create(
            dataspace=self.dataspace,
            name="All descendants",
            content_type=component_ct,
            operator="and",
        )
        filter1 = Filter.objects.create(
            dataspace=self.dataspace,
            query=query1,
            field_name="id",
            lookup="descendant",
            value=self.component.id,
        )

        # Making a copy to ensure Dataspace scoping
        alternate_dataspace = Dataspace.objects.create(name="Alternate")
        copy_object(self.component, alternate_dataspace, self.super_user)

        expected = sorted([c2.id, c3.id])
        self.assertEqual(expected, sorted([component.id for component in query1.get_qs()]))

        filter1.value = "{component.name}:{component.version}".format(component=self.component)
        filter1.save()
        self.assertEqual(expected, sorted([component.id for component in query1.get_qs()]))

        filter1.value = 99999  # non-existing id
        filter1.save()
        self.assertTrue(isinstance(query1.get_qs(), EmptyQuerySet))

    def test_query_with_product_descendant_lookup(self):
        component_ct = ContentType.objects.get_for_model(Component)

        c2 = Component.objects.create(name="c2", dataspace=self.dataspace)
        c3 = Component.objects.create(name="c3", dataspace=self.dataspace)
        c4 = Component.objects.create(name="c4", dataspace=self.dataspace)
        c5 = Component.objects.create(name="c5", dataspace=self.dataspace)

        p1 = Product.objects.create(dataspace=self.dataspace, name="p1")
        ProductComponent.objects.create(product=p1, component=c2, dataspace=self.dataspace)
        ProductComponent.objects.create(product=p1, component=c3, dataspace=self.dataspace)
        # Not part of the valids()
        ProductComponent.objects.create(product=p1, dataspace=self.dataspace)

        Subcomponent.objects.create(parent=c2, child=c4, dataspace=self.dataspace)
        Subcomponent.objects.create(parent=c4, child=c5, dataspace=self.dataspace)

        query1 = Query.objects.create(
            dataspace=self.dataspace,
            name="Product descendants",
            content_type=component_ct,
            operator="and",
        )
        filter1 = Filter.objects.create(
            dataspace=self.dataspace,
            query=query1,
            field_name="id",
            lookup="product_descendant",
            value=p1.id,
        )

        # Making a copy to ensure Dataspace scoping
        alternate_dataspace = Dataspace.objects.create(name="Alternate")
        Product.objects.create(dataspace=alternate_dataspace, name="p1", uuid=p1.uuid)

        expected = sorted([c2.id, c3.id, c4.id, c5.id])
        self.assertEqual(
            expected, sorted([component.id for component in query1.get_qs(user=self.super_user)])
        )
        self.assertFalse(query1.get_qs().exists())  # secured

        filter1.value = "{product.name}:{product.version}".format(product=p1)
        filter1.save()
        self.assertEqual(
            expected, sorted([component.id for component in query1.get_qs(user=self.super_user)])
        )
        self.assertFalse(query1.get_qs().exists())  # secured

        filter1.value = 99999  # non-existing id
        filter1.save()
        self.assertTrue(isinstance(query1.get_qs(user=self.super_user), EmptyQuerySet))
        self.assertTrue(isinstance(query1.get_qs(), EmptyQuerySet))  # secured

    def test_query_model_is_valid(self):
        license_ct = ContentType.objects.get_for_model(License)
        query = Query.objects.create(
            dataspace=self.dataspace, name="Name", content_type=license_ct, operator="and"
        )
        filtr = Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="key",
            lookup="contains",
            value="license",
        )
        self.assertTrue(query.is_valid())

        filtr.field_name = "INVALID"
        filtr.save()
        self.assertFalse(query.is_valid())

        filtr.field_name = "INVALID_last"
        filtr.save()
        self.assertFalse(query.is_valid())

        # Make sure OrderField are parts of the validation
        filtr.field_name = "key"
        filtr.save()
        self.assertTrue(query.is_valid())

        order_field = OrderField.objects.create(
            field_name="INVALID", seq=0, query=query, dataspace=self.dataspace
        )
        self.assertFalse(query.is_valid())

        order_field.field_name = "key"
        order_field.save()
        self.assertTrue(query.is_valid())

    def test_query_model_get_changelist_url(self):
        license_ct = ContentType.objects.get_for_model(License)
        query = Query.objects.create(name="Name", content_type=license_ct, dataspace=self.dataspace)
        expected = "/admin/license_library/license/"
        self.assertEqual(expected, query.get_changelist_url())
        expected += f"?reporting_query={query.id}"
        self.assertEqual(expected, query.get_changelist_url_with_filters())

        request_ct = ContentType.objects.get_for_model(Request)
        query.content_type = request_ct
        query.save()
        self.assertIsNone(query.get_changelist_url())
        self.assertIsNone(query.get_changelist_url_with_filters())

    def test_reporting_get_by_reporting_key(self):
        self.component.name = "Name : with :: colon"
        self.component.version = "1.0 and space"
        self.component.save()
        reporting_key = "{component.name}:{component.version}".format(component=self.component)
        self.assertEqual(
            self.component, get_by_reporting_key(Component, self.dataspace, reporting_key)
        )
        self.assertEqual(
            self.component, get_by_reporting_key(Component, self.dataspace, self.component.id)
        )

        p1 = Product.objects.create(dataspace=self.dataspace, name="p1 with space")
        reporting_key = "{product.name}:{product.version}".format(product=p1)
        queryset = Product.objects.get_queryset(self.super_user)
        self.assertEqual(p1, get_by_reporting_key(queryset, self.dataspace, reporting_key))
        self.assertEqual(p1, get_by_reporting_key(queryset, self.dataspace, p1.id))


class FilterTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.license_ct = ContentType.objects.get_for_model(License)
        self.component_ct = ContentType.objects.get_for_model(Component)

    def test_get_coerced_value(self):
        query = Query.objects.create(
            dataspace=self.dataspace,
            name="Network redistribution licenses",
            content_type=self.license_ct,
            operator="and",
        )
        f = Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="licenseassignedtag__value",
            lookup="exact",
            value="True",
        )

        expected = True
        self.assertEqual(expected, f.get_coerced_value(f.value))

    def test_get_coerced_value_validation_from_model_validators(self):
        query = Query.objects.create(
            dataspace=self.dataspace, operator="and", name="Q1", content_type=self.license_ct
        )
        f = Filter.objects.create(
            field_name="key", lookup="exact", query=query, dataspace=self.dataspace
        )

        # License model custom validators

        with self.assertRaises(ValidationError) as e:
            f.get_coerced_value("@#$%^&*")  # Not a valid key entry
        self.assertEqual([validate_slug_plus.message], list(e.exception))

        f.field_name = "curation_level"
        f.save()
        with self.assertRaises(ValidationError) as e:
            f.get_coerced_value("101")  # Max is 100 for the curation level
        self.assertEqual(["Ensure this value is less than or equal to 100."], list(e.exception))

        # Component model custom validators
        query.content_type = self.component_ct
        query.save()
        with self.assertRaises(ValidationError) as e:
            f.get_coerced_value("101")  # Max is 100 for the curation level
        self.assertEqual(["Ensure this value is less than or equal to 100."], list(e.exception))

        f.field_name = "name"
        f.save()
        with self.assertRaises(ValidationError) as e:
            f.get_coerced_value("$$$$$")  # Not a valid name entry
        self.assertEqual([validate_url_segment.message], list(e.exception))

        f.field_name = "version"
        f.save()
        with self.assertRaises(ValidationError) as e:
            f.get_coerced_value("1:0")  # Not a valid version entry
        self.assertEqual([validate_version.message], list(e.exception))

    def test_get_q(self):
        query = Query.objects.create(
            dataspace=self.dataspace,
            name="GPL2-related licenses",
            content_type=self.license_ct,
            operator="and",
        )
        f = Filter.objects.create(
            dataspace=self.dataspace, query=query, field_name="key", lookup="exact", value="gps-2.0"
        )

        expected = [("key__exact", "gps-2.0")]
        self.assertEqual(expected, f.get_q().children)
        self.assertFalse(f.get_q().negated)

    def test_get_q_for_null_boolean_field(self):
        query = Query.objects.create(
            dataspace=self.dataspace,
            name="GPL2-related licenses",
            content_type=self.license_ct,
            operator="and",
        )
        f = Filter.objects.create(
            dataspace=self.dataspace, query=query, field_name="is_active", lookup="exact", value=""
        )

        self.assertIsNone(f.get_q())  # "no value provided"
        self.assertEqual([("is_active__exact", True)], f.get_q("True").children)
        self.assertEqual([("is_active__exact", False)], f.get_q("False").children)
        # Looking for None is different from "no value provided".
        self.assertEqual([("is_active__exact", None)], f.get_q("None").children)

    def test_get_q_for_isnull_lookup_type(self):
        query = Query.objects.create(
            dataspace=self.dataspace, name="Q1", content_type=self.license_ct, operator="and"
        )
        f = Filter.objects.create(
            dataspace=self.dataspace, query=query, field_name="category", lookup="isnull", value=""
        )

        self.assertIsNone(f.get_q())  # "no value provided"
        self.assertEqual([("category__isnull", True)], f.get_q("True").children)
        self.assertEqual([("category__isnull", False)], f.get_q("False").children)
        self.assertIsNone(f.get_q("None"))
        self.assertIsNone(f.get_q("INVALID"))

    def test_get_q_for_isempty_lookup_type(self):
        query = Query.objects.create(
            dataspace=self.dataspace, name="Q1", content_type=self.license_ct, operator="and"
        )
        f = Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="spdx_license_key",
            lookup="isempty",
            value="",
        )

        self.assertIsNone(f.get_q())  # "no value provided"
        self.assertEqual([("spdx_license_key__in", ["", [], {}])], f.get_q("True").children)
        self.assertEqual([("spdx_license_key__gt", "")], f.get_q("False").children)
        # Everything else then False is considered as True but enforced in the
        # form to not happen anyway.
        self.assertEqual([("spdx_license_key__gt", "")], f.get_q("None").children)
        self.assertEqual([("spdx_license_key__gt", "")], f.get_q("INVALID").children)

    def test_get_q_for_date_field_filter(self):
        query = Query.objects.create(
            dataspace=self.dataspace, name="Q1", content_type=self.license_ct, operator="and"
        )
        f = Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name="last_modified_date",
            lookup="gte",
            value="past_7_days",
        )

        today = DateFieldFilterSelect._get_today()
        past_7_days = today - datetime.timedelta(days=7)
        self.assertEqual([("last_modified_date__gte", str(past_7_days))], f.get_q().children)

        self.assertEqual([("last_modified_date__gte", str(today))], f.get_q("today").children)

        with self.assertRaises(ValidationError):
            f.get_q("invalid").children

    def test_get_q_for_boolean_select_all_choice_value(self):
        query = Query.objects.create(
            dataspace=self.dataspace, name="Q1", content_type=self.license_ct, operator="and"
        )

        # No default value
        f = Filter.objects.create(
            dataspace=self.dataspace, query=query, field_name="reviewed", lookup="exact"
        )

        self.assertIsNone(f.get_q())
        self.assertEqual([("reviewed__exact", True)], f.get_q("True").children)
        self.assertEqual([("reviewed__exact", False)], f.get_q("False").children)
        self.assertIsNone(f.get_q(BooleanSelect.ALL_CHOICE_VALUE))

        # True as default value
        f.value = True
        f.save()

        self.assertEqual([("reviewed__exact", True)], f.get_q().children)
        self.assertEqual([("reviewed__exact", True)], f.get_q("True").children)
        self.assertEqual([("reviewed__exact", False)], f.get_q("False").children)
        self.assertIsNone(f.get_q(BooleanSelect.ALL_CHOICE_VALUE))

    def test_get_value_as_list(self):
        query = Query.objects.create(
            dataspace=self.dataspace,
            name="GPL2-related licenses",
            content_type=self.license_ct,
            operator="and",
        )
        f = Filter.objects.create(
            dataspace=self.dataspace, query=query, field_name="name", lookup="in", value=""
        )

        expected = ["AES-128 3.0 License", "AFL 2.1"]
        f.value = '["AES-128 3.0 License", "AFL 2.1"]'
        f.save()
        self.assertEqual(expected, f.get_value_as_list(f.value))

        expected = ['BSD 2-clause "FreeBSD" License', 'BSD 2-clause "NetBSD" License']
        f.value = """['BSD 2-clause "FreeBSD" License', 'BSD 2-clause "NetBSD" License']"""
        f.save()
        self.assertEqual(expected, f.get_value_as_list(f.value))

        expected = ["GPL, no version", "X11, Free Software Foundation variant"]
        f.value = '["GPL, no version", "X11, Free Software Foundation variant"]'
        f.save()
        self.assertEqual(expected, f.get_value_as_list(f.value))

        expected = []
        f.value = ""
        f.save()
        self.assertEqual(expected, f.get_value_as_list(f.value))


class ReportTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="Other")
        self.super_user = create_superuser("super_user", self.dataspace)

        self.component = Component.objects.create(dataspace=self.dataspace, name="c1")

        component_ct = ContentType.objects.get_for_model(Component)
        self.query1 = Query.objects.create(
            dataspace=self.dataspace, name="Q1", content_type=component_ct, operator="and"
        )
        self.filter1 = Filter.objects.create(
            dataspace=self.dataspace,
            query=self.query1,
            field_name="name",
            lookup="exact",
            value=self.component.name,
        )
        self.column_template1 = ColumnTemplate.objects.create(
            dataspace=self.dataspace, content_type=component_ct
        )
        self.field1 = ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=self.column_template1,
            field_name="name",
            display_name="Name",
            seq=0,
        )
        self.report1 = Report.objects.create(
            name="Report1", query=self.query1, column_template=self.column_template1
        )

    def test_report_copy(self):
        copied_object = copy_object(self.report1, self.other_dataspace, self.super_user)
        self.assertEqual(self.report1.uuid, copied_object.uuid)
        self.assertEqual(self.query1.uuid, copied_object.query.uuid)
        self.assertEqual(self.filter1.uuid, copied_object.query.filters.get().uuid)
        self.assertEqual(self.column_template1.uuid, copied_object.column_template.uuid)
        self.assertEqual(self.field1.uuid, copied_object.column_template.fields.get().uuid)

    def test_report_deletion(self):
        with self.assertRaises(ProtectedError):
            self.query1.delete()

        with self.assertRaises(ProtectedError):
            self.column_template1.delete()

        self.report1.delete()
        self.assertTrue(Query.objects.get(id=self.query1.id))
        self.assertTrue(ColumnTemplate.objects.get(id=self.column_template1.id))

    def test_report_model_get_output(self):
        self.assertEqual([[str(self.component)]], self.report1.get_output())

        component2 = Component.objects.create(dataspace=self.dataspace, name="c2")
        queryset = Component.objects.filter(pk=component2.pk)
        self.assertEqual([[str(component2)]], self.report1.get_output(queryset))


class ColumnTemplateTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("super_user", self.dataspace)
        self.owner = Owner.objects.create(dataspace=self.dataspace, name="My Fancy Owner Name")
        self.component = Component.objects.create(
            dataspace=self.dataspace, name="c1", owner=self.owner
        )

        self.license = License.objects.create(
            key="license-1",
            name="License1",
            short_name="License1",
            dataspace=self.dataspace,
            owner=self.owner,
        )
        self.license_tag = LicenseTag.objects.create(
            label="Network Redistribution", text="Text", dataspace=self.dataspace
        )
        self.assigned_license = ComponentAssignedLicense.objects.create(
            component=self.component, license=self.license, dataspace=self.dataspace
        )

        self.component_ct = ContentType.objects.get_for_model(Component)
        self.license_ct = ContentType.objects.get_for_model(License)
        self.column_template = ColumnTemplate.objects.create(
            dataspace=self.dataspace, content_type=self.component_ct
        )
        self.field1 = ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=self.column_template,
            field_name="owner__name",
            display_name="Owner Name",
            seq=0,
        )

    def test_get_value_for_instance_with_empty_field_name(self):
        self.field1.field_name = ""
        self.field1.save()
        expected = "Error"
        self.assertEqual(expected, self.field1.get_value_for_instance(self.component))

    def test_get_value_for_instance_with_wrong_value_for_field_name(self):
        self.field1.field_name = "this does not exists"
        self.field1.save()
        expected = "Error"
        self.assertEqual(expected, self.field1.get_value_for_instance(self.component))

    def test_get_value_for_instance_on_direct_field(self):
        self.field1.field_name = "name"
        self.field1.save()
        expected = "c1"
        self.assertEqual(expected, self.field1.get_value_for_instance(self.component))

    def test_get_value_for_instance_on_fk_field(self):
        self.field1.field_name = "owner__name"
        self.field1.save()
        expected = "My Fancy Owner Name"
        self.assertEqual(expected, self.field1.get_value_for_instance(self.component))

    def test_get_value_for_instance_on_m2m_base(self):
        self.field1.field_name = "licenses"
        self.field1.save()
        expected = str(self.license)
        self.assertEqual(expected, self.field1.get_value_for_instance(self.component))

        self.field1.field_name = "licenses__name"
        self.field1.save()
        expected = self.license.name
        self.assertEqual(expected, self.field1.get_value_for_instance(self.component))

    def test_get_value_for_instance_on_direct_property(self):
        self.field1.field_name = "urn"
        self.field1.save()
        expected = "urn:dje:component:c1:"
        self.assertEqual(expected, self.field1.get_value_for_instance(self.component))

    def test_get_value_for_instance_on_m2m_property(self):
        self.field1.field_name = "licenses__urn"
        self.field1.save()
        expected = "urn:dje:license:license-1"
        self.assertEqual(expected, self.field1.get_value_for_instance(self.component))

    def _base_get_value_for_instance(self, input_fields, filter_field, model_instance, user=None):
        # Common code goes here.
        for field_name, expected in input_fields:
            filter_field.field_name = field_name
            filter_field.save()
            value = filter_field.get_value_for_instance(model_instance, user=user)
            msg = 'Field "{}": {} != {}'.format(field_name, safe_repr(expected), safe_repr(value))
            self.assertEqual(expected, value, msg=msg)

    def test_get_value_for_instance_on_license_on_various_fields(self):
        self.column_template.content_type = self.license_ct
        self.column_template.content_type.save()

        policy_approved = UsagePolicy.objects.create(
            label="Approved",
            icon="icon-ok-circle",
            content_type=self.license_ct,
            dataspace=self.dataspace,
        )

        self.license.usage_policy = policy_approved
        self.license.save()

        license_tag2 = LicenseTag.objects.create(
            label="Tag2", text="Text", default_value="True", dataspace=self.dataspace
        )

        LicenseAssignedTag.objects.create(
            license=self.license, license_tag=self.license_tag, value=True, dataspace=self.dataspace
        )
        LicenseAssignedTag.objects.create(
            license=self.license, license_tag=license_tag2, value=False, dataspace=self.dataspace
        )

        ext_source1 = ExternalSource.objects.create(label="GitHub", dataspace=self.dataspace)
        ext_ref1 = ExternalReference.objects.create(
            content_type=ContentType.objects.get_for_model(self.license),
            object_id=self.license.pk,
            external_source=ext_source1,
            external_id="dejacode",
            dataspace=self.dataspace,
        )

        fields = [  # (field_name, expected_result)
            # DirectField
            ("admin_notes", ""),
            ("curation_level", "0"),
            ("created_date", str(self.license.created_date)),
            ("faq_url", ""),
            ("full_text", ""),
            ("guidance", ""),
            ("guidance_url", ""),
            ("homepage_url", ""),
            ("id", str(self.license.id)),
            ("is_active", ""),
            ("is_component_license", "False"),
            ("key", self.license.key),
            ("keywords", ""),
            ("last_modified_date", str(self.license.last_modified_date)),
            ("name", self.license.name),
            ("osi_url", ""),
            ("other_urls", ""),
            ("publication_year", ""),
            ("reviewed", "False"),
            ("short_name", self.license.short_name),
            ("uuid", str(self.license.uuid)),
            # ForeignKey
            ("owner", str(self.license.owner)),
            ("owner__id", str(self.license.owner.id)),
            ("owner__name", self.license.owner.name),
            ("owner__urn", self.license.owner.urn),
            ("owner__children", ""),
            ("usage_policy", str(self.license.usage_policy)),
            ("usage_policy__label", self.license.usage_policy.label),
            ("usage_policy__icon", self.license.usage_policy.icon),
            ("license_profile", ""),
            ("license_status", ""),
            ("license_style", ""),
            ("category", ""),
            ("request_count", ""),
            # We do not support traversing to a second Relational field for now.
            ("owner__children__alias", ""),
            ("owner__children__name", ""),
            ("owner__children__children", ""),
            ("owner__children__children__name", ""),
            # Many2Many
            ("tags", "{}\n{}".format(self.license_tag, license_tag2)),
            ("tags__id", "{}\n{}".format(self.license_tag.id, license_tag2.id)),
            ("tags__show_in_license_list_view", "False\nFalse"),
            ("tags__default_value", "None\nTrue"),
            ("tags__label", "Network Redistribution\nTag2"),
            ("tags__uuid", "{}\n{}".format(self.license_tag.uuid, license_tag2.uuid)),
            # Special tag property
            ("{}{}".format(LICENSE_TAG_PREFIX, self.license_tag.label), "True"),
            # Related
            ("external_references", str(ext_ref1)),
            ("external_references__id", str(ext_ref1.id)),
            ("external_references__external_id", ext_ref1.external_id),
            ("external_references__uuid", str(ext_ref1.uuid)),
            ("external_references__object_id", str(ext_ref1.object_id)),
            ("external_references__external_url", ext_ref1.external_url),
            ("external_references__external_source", str(ext_ref1.external_source)),
            ("external_references__external_source__id", str(ext_ref1.external_source.id)),
            ("external_references__external_source__label", ext_ref1.external_source.label),
            # Property
            ("urn", self.license.urn),
            ("details_url", self.license.details_url),
        ]

        self._base_get_value_for_instance(fields, self.field1, self.license)

    def test_get_value_for_instance_on_owner_on_various_fields(self):
        owner_ct = ContentType.objects.get_for_model(Owner)
        self.column_template.content_type = owner_ct
        self.column_template.content_type.save()

        owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)

        fields = [  # (field_name, expected_result)
            # Missing value
            ("", ERROR_STR),
            # DirectField
            ("alias", ""),
            ("contact_info", ""),
            ("homepage_url", ""),
            ("id", str(owner1.id)),
            ("name", owner1.name),
            ("notes", ""),
            ("type", owner1.type),
            ("uuid", str(owner1.uuid)),
            # Explicit Many2Many
            ("children", ""),
            ("children__alias", ""),
            ("children__contact_info", ""),
            ("children__homepage_url", ""),
            ("children__id", ""),
            ("children__name", ""),
            ("children__notes", ""),
            ("children__uuid", ""),
            ("children__children", ""),
            # Related
            ("external_references", ""),
            # Property
            ("urn", owner1.urn),
        ]

        self._base_get_value_for_instance(fields, self.field1, owner1)

    def test_get_value_for_instance_on_request_on_various_fields(self):
        request_ct = ContentType.objects.get_for_model(Request)
        self.column_template.content_type = request_ct
        self.column_template.content_type.save()

        LicenseAssignedTag.objects.create(
            license=self.license, license_tag=self.license_tag, value=True, dataspace=self.dataspace
        )

        request_template1 = RequestTemplate.objects.create(
            name="Template1",
            description="Header Desc1",
            dataspace=self.dataspace,
            content_type=self.license_ct,
        )

        p1 = Product.objects.create(
            name="p1", version="v1", owner=self.owner, dataspace=self.dataspace
        )

        request1 = Request.objects.create(
            title="Title",
            request_template=request_template1,
            requester=self.super_user,
            dataspace=self.dataspace,
            content_type=self.license_ct,
            object_id=self.license.id,
            product_context=p1,
        )

        fields = [  # (field_name, expected_result)
            # DirectField
            ("request_template", str(request_template1)),
            ("status", request1.get_status_display()),
            ("is_private", "False"),
            ("notes", ""),
            ("requester", str(self.super_user)),
            ("requester__username", str(self.super_user.username)),
            ("assignee", ""),
            ("created_date", str(request1.created_date)),
            ("last_modified_date", str(request1.last_modified_date)),
            ("product_context", ""),  # secured
            ("product_context__name", ""),  # secured
            ("product_context__version", ""),  # secured
            ("serialized_data", ""),
            # Property
            ("serialized_data_html", ""),
            ("details_url", request1.details_url),
            ("content_object", str(self.license)),
        ]

        self._base_get_value_for_instance(fields, self.field1, request1)

        fields = [
            ("product_context", str(p1)),
            ("product_context__name", str(p1.name)),
            ("product_context__version", str(p1.version)),
        ]

        self._base_get_value_for_instance(fields, self.field1, request1, user=self.super_user)

    def test_get_value_for_instance_on_component_on_various_fields(self):
        self.column_template.content_type = self.component_ct
        self.column_template.content_type.save()

        self.component.keywords = ["Keyword1", "Keyword2"]
        self.component.license_expression = self.license.key
        self.component.save()

        tag_property = "{}{}".format(LICENSE_TAG_PREFIX, self.license_tag.label)

        fields = [  # (field_name, expected_result)
            # DirectField
            ("name", self.component.name),
            ("version", self.component.version),
            ("release_date", ""),
            ("description", ""),
            ("copyright", ""),
            ("approval_reference", ""),
            ("homepage_url", ""),
            ("vcs_url", ""),
            ("code_view_url", ""),
            ("bug_tracking_url", ""),
            ("primary_language", ""),
            ("keywords", "Keyword1\nKeyword2"),
            ("guidance", ""),
            ("admin_notes", ""),
            ("is_active", "True"),
            ("curation_level", str(self.component.curation_level)),
            ("completion_level", str(self.component.completion_level)),
            ("notice_text", ""),
            ("is_license_notice", ""),
            ("is_copyright_notice", ""),
            ("is_notice_in_codebase", ""),
            ("notice_filename", ""),
            ("notice_url", ""),
            ("created_date", str(self.component.created_date)),
            ("last_modified_date", str(self.component.last_modified_date)),
            ("license_expression", str(self.license.key)),
            ("request_count", ""),
            # ForeignKey
            ("owner", str(self.component.owner)),
            ("owner__id", str(self.component.owner.id)),
            ("owner__urn", self.component.owner.urn),
            ("owner__children", ""),
            ("owner__children__id", ""),
            ("type", ""),
            ("type__label", ""),
            ("type__notes", ""),
            ("configuration_status", ""),
            ("configuration_status__label", ""),
            ("configuration_status__text", ""),
            ("configuration_status__default_on_addition", ""),
            # Many2Many
            ("licenses", str(self.license)),
            ("licenses__id", str(self.license.id)),
            ("licenses__owner", str(self.component.owner)),
            ("licenses__owner__id", str(self.component.owner.id)),
            ("licenses__owner__children", ""),
            ("licenses__owner__children__id", ""),
            ("licenses__tags", ""),
            ("licenses__tags__label", ""),
            ("licenses__urn", self.license.urn),
            # Special tag property
            ("licenses__{}".format(tag_property), ""),
            ("children", ""),
            ("children__id", ""),
            ("children__homepage_url", ""),
            ("children__type", ""),
            ("children__children", ""),
            # No need for more testing on file, only direct fields
            ("packages", ""),
            # Related
            ("external_references", ""),
            # Property
            ("urn", self.component.urn),
            ("details_url", self.component.details_url),
            ("primary_license", self.license.key),
        ]

        self._base_get_value_for_instance(fields, self.field1, self.component)

    def test_get_value_for_instance_on_licensetag_on_various_fields(self):
        licensetag_ct = ContentType.objects.get_for_model(LicenseTag)
        self.column_template.content_type = licensetag_ct
        self.column_template.content_type.save()
        license_profile = LicenseProfile.objects.create(
            name="LicenseProfile 1", dataspace=self.dataspace
        )
        assigned_tag = LicenseProfileAssignedTag.objects.create(
            license_profile=license_profile,
            license_tag=self.license_tag,
            value=True,
            dataspace=self.dataspace,
        )

        fields = [  # (field_name, expected_result)
            # DirectField
            ("id", str(self.license_tag.id)),
            ("default_value", ""),
            ("guidance", ""),
            ("label", self.license_tag.label),
            ("text", self.license_tag.text),
            ("show_in_license_list_view", str(self.license_tag.show_in_license_list_view)),
            ("uuid", str(self.license_tag.uuid)),
            # Related Many2Many
            ("licenseassignedtag", ""),
            ("licenseassignedtag__value", ""),
            ("licenseassignedtag__id", ""),
            ("licenseassignedtag__license", ""),
            ("licenseassignedtag__license__name", ""),
            ("licenseassignedtag__license_tag__label", ""),
            ("licenseprofileassignedtag__value", str(assigned_tag.value)),
            ("licenseprofileassignedtag__license_profile", str(license_profile)),
            ("licenseprofileassignedtag__license_profile__name", license_profile.name),
        ]

        self._base_get_value_for_instance(fields, self.field1, self.license_tag)

    def test_get_value_for_instance_on_subcomponent_on_various_fields(self):
        subcomponent_ct = ContentType.objects.get_for_model(Subcomponent)
        self.column_template.content_type = subcomponent_ct
        self.column_template.content_type.save()

        c2 = Component.objects.create(name="c2", owner=self.owner, dataspace=self.dataspace)
        sub1 = Subcomponent.objects.create(
            parent=self.component, child=c2, dataspace=self.dataspace
        )

        fields = [  # (field_name, expected_result)
            # DirectField
            ("id", str(sub1.id)),
            ("uuid", str(sub1.uuid)),
            # FKs
            ("parent", str(sub1.parent)),
            ("parent__name", str(sub1.parent.name)),
            ("child", str(sub1.child)),
            ("child__uuid", str(sub1.child.uuid)),
        ]

        self._base_get_value_for_instance(fields, self.field1, sub1)

    def test_get_value_for_instance_on_licenseprofile_on_various_fields(self):
        licenseprofile_ct = ContentType.objects.get_for_model(LicenseProfile)
        self.column_template.content_type = licenseprofile_ct
        self.column_template.content_type.save()
        license_profile = LicenseProfile.objects.create(
            name="LicenseProfile 1", dataspace=self.dataspace
        )
        assigned_tag = LicenseProfileAssignedTag.objects.create(
            license_profile=license_profile,
            license_tag=self.license_tag,
            value=True,
            dataspace=self.dataspace,
        )

        fields = [  # (field_name, expected_result)
            # DirectField
            ("id", str(license_profile.id)),
            ("name", license_profile.name),
            ("notes", license_profile.notes),
            ("uuid", str(license_profile.uuid)),
            # Many2Many
            ("tags", str(self.license_tag)),
            ("tags__label", self.license_tag.label),
            ("tags__default_value", ""),
            # Related Many2Many
            ("license", ""),
            ("license__name", ""),
            ("licenseprofileassignedtag__value", str(assigned_tag.value)),
            ("licenseprofileassignedtag__id", str(assigned_tag.id)),
            ("licenseprofileassignedtag__uuid", str(assigned_tag.uuid)),
            ("licenseprofileassignedtag__license_tag", str(assigned_tag.license_tag)),
            ("licenseprofileassignedtag__license_tag__label", self.license_tag.label),
        ]

        self._base_get_value_for_instance(fields, self.field1, license_profile)

    def test_get_value_for_instance_on_package_on_various_fields(self):
        package_ct = ContentType.objects.get_for_model(Package)
        self.column_template.content_type = package_ct
        self.column_template.content_type.save()

        package = Package.objects.create(
            filename="p1", download_url="http://nexb.com", notes="notes", dataspace=self.dataspace
        )
        assigned_package = ComponentAssignedPackage.objects.create(
            component=self.component, package=package, dataspace=self.dataspace
        )

        fields = [  # (field_name, expected_result)
            # DirectField
            ("id", str(package.id)),
            ("filename", package.filename),
            ("notes", package.notes),
            ("download_url", str(package.download_url)),
            ("uuid", str(package.uuid)),
            # Related
            ("external_references", ""),
            # Related Many2Many
            ("componentassignedpackage", str(assigned_package)),
            ("componentassignedpackage__id", str(assigned_package.id)),
            ("componentassignedpackage__uuid", str(assigned_package.uuid)),
            ("componentassignedpackage__component", str(assigned_package.component)),
            ("componentassignedpackage__component__id", str(assigned_package.component.id)),
            ("componentassignedpackage__component__name", str(assigned_package.component.name)),
            (
                "componentassignedpackage__component__version",
                str(assigned_package.component.version),
            ),
            ("componentassignedpackage__component__request_count", ""),
            # Property on Many2Many FK
            ("componentassignedpackage__component__urn", str(assigned_package.component.urn)),
            (
                "componentassignedpackage__component__details_url",
                str(assigned_package.component.details_url),
            ),
            (
                "componentassignedpackage__component__license_expression",
                str(assigned_package.component.license_expression),
            ),
        ]

        self._base_get_value_for_instance(fields, self.field1, package)

    def test_get_value_for_instance_on_product_on_various_fields(self):
        p1 = Product.objects.create(name="p1", owner=self.owner, dataspace=self.dataspace)
        pc1 = ProductComponent.objects.create(
            product=p1,
            component=self.component,
            dataspace=self.dataspace,
            name="temp name",
            version="temp version",
        )

        product_ct = ContentType.objects.get_for_model(Product)
        self.column_template.content_type = product_ct
        self.column_template.content_type.save()

        fields = [  # (field_name, expected_result)
            # DirectField
            ("id", str(p1.id)),
            ("uuid", str(p1.uuid)),
            ("name", str(p1.name)),
            # Many2Many
            ("components", str(self.component)),
            ("components__name", str(self.component.name)),
            # Related Many2Many
            ("productcomponents", str(pc1)),
            ("productcomponents__id", str(pc1.id)),
            ("productcomponents__component__name", str(pc1.component.name)),
            ("productcomponents__name", str(pc1.name)),
            ("productcomponents__version", str(pc1.version)),
            # Related Many2Many FK property
            ("productcomponents__component__urn", str(pc1.component.urn)),
            ("productcomponents__component__details_url", str(pc1.component.details_url)),
        ]

        self._base_get_value_for_instance(fields, self.field1, p1, user=self.super_user)

    def test_get_value_for_instance_on_productcomponent_on_various_fields(self):
        p1 = Product.objects.create(name="p1", owner=self.owner, dataspace=self.dataspace)
        pc1 = ProductComponent.objects.create(
            product=p1,
            component=self.component,
            dataspace=self.dataspace,
            name="temp name",
            version="temp version",
        )
        assigned_license1 = ProductComponentAssignedLicense.objects.create(
            productcomponent=pc1, license=self.license, dataspace=self.dataspace
        )

        productcomponent_ct = ContentType.objects.get_for_model(ProductComponent)
        self.column_template.content_type = productcomponent_ct
        self.column_template.content_type.save()

        fields = [  # (field_name, expected_result)
            # DirectField
            ("id", str(pc1.id)),
            ("uuid", str(pc1.uuid)),
            ("name", str(pc1.name)),
            # FK
            ("product", ""),  # secured
            ("product__id", ""),  # secured
            ("product__name", ""),  # secured
            ("component__productcomponents__product__name", ""),  # secured
            ("component", str(self.component)),
            ("component__name", str(self.component.name)),
            # Many2Many
            ("licenses", str(assigned_license1.license)),
            ("licenses__name", str(assigned_license1.license.name)),
        ]

        self._base_get_value_for_instance(fields, self.field1, pc1)

        fields = [
            ("product", str(p1)),
            ("product__id", str(p1.id)),
            ("product__name", str(p1.name)),
            ("component__productcomponents__product__name", str(p1.name)),
        ]

        self._base_get_value_for_instance(fields, self.field1, pc1, user=self.super_user)

    def test_get_value_for_instance_on_secured_related_model(self):
        p1 = Product.objects.create(name="p1", dataspace=self.dataspace)
        pc1 = ProductComponent.objects.create(
            product=p1, component=self.component, dataspace=self.dataspace
        )

        self.column_template.content_type = self.component_ct
        self.column_template.content_type.save()

        self.field1.field_name = "productcomponents__product__name"
        self.field1.save()
        self.assertEqual("", self.field1.get_value_for_instance(self.component))
        self.assertEqual(
            str(p1.name), self.field1.get_value_for_instance(self.component, user=self.super_user)
        )

        self.column_template.content_type = ContentType.objects.get_for_model(ProductComponent)
        self.column_template.content_type.save()
        self.field1.field_name = "component__productcomponents__product__name"
        self.field1.save()
        self.assertEqual("", self.field1.get_value_for_instance(pc1))
        self.assertEqual(
            str(p1.name), self.field1.get_value_for_instance(pc1, user=self.super_user)
        )

    def test_get_value_for_instance_on_license_for_a_tag(self):
        self.column_template.content_type = self.license_ct
        self.column_template.content_type.save()
        self.field1.field_name = "{}{}".format(LICENSE_TAG_PREFIX, self.license_tag.label)
        self.field1.save()
        expected = ""  # The Tag is not assigned to the license
        self.assertEqual(expected, self.field1.get_value_for_instance(self.license))

        LicenseAssignedTag.objects.create(
            license=self.license, license_tag=self.license_tag, value=True, dataspace=self.dataspace
        )

        expected = "True"
        self.assertEqual(expected, self.field1.get_value_for_instance(self.license))

    def test_get_value_for_instance_on_component_for_licenses_tags(self):
        self.field1.field_name = "licenses__{}{}".format(LICENSE_TAG_PREFIX, self.license_tag.label)
        self.field1.save()
        field2 = ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=self.column_template,
            field_name="licenses__name",
            seq=1,
        )

        expected = ""  # The Tag is not assigned to the license
        self.assertEqual(expected, self.field1.get_value_for_instance(self.component))

        LicenseAssignedTag.objects.create(
            license=self.license, license_tag=self.license_tag, value=True, dataspace=self.dataspace
        )

        license2 = License.objects.create(
            key="license-2",
            name="License2",
            short_name="License2",
            dataspace=self.dataspace,
            owner=self.owner,
        )
        LicenseAssignedTag.objects.create(
            license=license2, license_tag=self.license_tag, value=False, dataspace=self.dataspace
        )
        ComponentAssignedLicense.objects.create(
            component=self.component, license=license2, dataspace=self.dataspace
        )

        expected = "True\nFalse"
        self.assertEqual(expected, self.field1.get_value_for_instance(self.component))
        expected = "License1\nLicense2"
        self.assertEqual(expected, field2.get_value_for_instance(self.component))

    def test_get_value_for_instance_multi_value_ordering(self):
        self.assigned_license.delete()
        self.field1.field_name = "licenses__{}{}".format(LICENSE_TAG_PREFIX, self.license_tag.label)
        self.field1.save()
        field2 = ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=self.column_template,
            field_name="licenses__key",
            seq=1,
        )

        license_b = License.objects.create(
            key="b", name="b", short_name="b", dataspace=self.dataspace, owner=self.owner
        )
        license_a = License.objects.create(
            key="a", name="a", short_name="a", dataspace=self.dataspace, owner=self.owner
        )
        self.assertTrue(license_b.id < license_a.id)

        assigned_tag_b = LicenseAssignedTag.objects.create(
            license=license_b, license_tag=self.license_tag, value=True, dataspace=self.dataspace
        )
        assigned_tag_a = LicenseAssignedTag.objects.create(
            license=license_a, license_tag=self.license_tag, value=False, dataspace=self.dataspace
        )
        self.assertTrue(assigned_tag_b.id < assigned_tag_a.id)

        ComponentAssignedLicense.objects.create(
            component=self.component, license=license_b, dataspace=self.dataspace
        )
        ComponentAssignedLicense.objects.create(
            component=self.component, license=license_a, dataspace=self.dataspace
        )

        expected = [license_a.key, license_b.name]
        self.assertEqual(expected, list(self.component.licenses.values_list("key", flat=True)))
        expected = "\n".join([license_a.key, license_b.name])
        self.assertEqual(expected, field2.get_value_for_instance(self.component))
        expected = "\n".join([str(assigned_tag_a.value), str(assigned_tag_b.value)])
        self.assertEqual(expected, self.field1.get_value_for_instance(self.component))

    def test_column_template_with_fields_copy(self):
        other_dataspace = Dataspace.objects.create(name="other")

        copied_object = copy_object(self.column_template, other_dataspace, self.super_user)
        self.assertEqual(self.column_template.uuid, copied_object.uuid)
        self.assertEqual(1, copied_object.fields.count())
        self.assertEqual(self.field1.uuid, copied_object.fields.get().uuid)

    def test_column_template_assigned_field_model_is_valid(self):
        self.assertTrue(self.field1.is_valid())

        self.field1.field_name = "INVALID__last"
        self.field1.save()
        self.assertFalse(self.field1.is_valid())

        self.field1.field_name = "INVALID"
        self.field1.save()
        self.assertFalse(self.field1.is_valid())

    def test_column_template_model_is_valid(self):
        self.assertTrue(self.field1.is_valid())
        self.assertTrue(self.column_template.is_valid())

        field2 = ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=self.column_template,
            field_name="INVALID",
            display_name="",
            seq=1,
        )

        self.assertFalse(field2.is_valid())
        self.assertFalse(self.column_template.is_valid())

        field2.field_name = "owner"
        field2.save()
        self.assertTrue(field2.is_valid())
        self.assertTrue(self.column_template.is_valid())

    def test_get_model_data_for_license_column_template(self):
        self.maxDiff = None
        value = get_model_data_for_column_template()
        # Same order as the select input
        expected = [
            {"group": "Direct Fields", "value": "admin_notes", "label": "admin_notes"},
            {"group": "Direct Fields", "value": "category", "label": "category >>"},
            {"group": "Direct Fields", "value": "created_by", "label": "created_by >>"},
            {"group": "Direct Fields", "value": "created_date", "label": "created_date"},
            {"group": "Direct Fields", "value": "curation_level", "label": "curation_level"},
            {"group": "Direct Fields", "value": "faq_url", "label": "faq_url"},
            {"group": "Direct Fields", "value": "full_text", "label": "full_text"},
            {"group": "Direct Fields", "value": "guidance", "label": "guidance"},
            {"group": "Direct Fields", "value": "guidance_url", "label": "guidance_url"},
            {"group": "Direct Fields", "value": "homepage_url", "label": "homepage_url"},
            {"group": "Direct Fields", "value": "id", "label": "id"},
            {"group": "Direct Fields", "value": "is_active", "label": "is_active"},
            {
                "group": "Direct Fields",
                "value": "is_component_license",
                "label": "is_component_license",
            },
            {"group": "Direct Fields", "value": "is_exception", "label": "is_exception"},
            {"group": "Direct Fields", "value": "key", "label": "key"},
            {"group": "Direct Fields", "value": "keywords", "label": "keywords"},
            {"group": "Direct Fields", "label": "language", "value": "language"},
            {"group": "Direct Fields", "value": "last_modified_by", "label": "last_modified_by >>"},
            {
                "group": "Direct Fields",
                "value": "last_modified_date",
                "label": "last_modified_date",
            },
            {"group": "Direct Fields", "value": "license_profile", "label": "license_profile >>"},
            {"group": "Direct Fields", "value": "license_status", "label": "license_status >>"},
            {"group": "Direct Fields", "value": "license_style", "label": "license_style >>"},
            {"group": "Direct Fields", "value": "name", "label": "name"},
            {"group": "Direct Fields", "value": "osi_url", "label": "osi_url"},
            {"group": "Direct Fields", "value": "other_urls", "label": "other_urls"},
            {"group": "Direct Fields", "value": "owner", "label": "owner >>"},
            {"group": "Direct Fields", "label": "popularity", "value": "popularity"},
            {"group": "Direct Fields", "value": "publication_year", "label": "publication_year"},
            {"group": "Direct Fields", "value": "reference_notes", "label": "reference_notes"},
            {"group": "Direct Fields", "label": "request_count", "value": "request_count"},
            {"group": "Direct Fields", "value": "reviewed", "label": "reviewed"},
            {"group": "Direct Fields", "value": "short_name", "label": "short_name"},
            {"group": "Direct Fields", "value": "spdx_license_key", "label": "spdx_license_key"},
            {
                "group": "Direct Fields",
                "value": "special_obligations",
                "label": "special_obligations",
            },
            {"group": "Direct Fields", "value": "standard_notice", "label": "standard_notice"},
            {"group": "Direct Fields", "value": "text_urls", "label": "text_urls"},
            {"group": "Direct Fields", "value": "usage_policy", "label": "usage_policy >>"},
            {"group": "Direct Fields", "value": "uuid", "label": "uuid"},
            {"group": "Many to Many Fields", "value": "tags", "label": "tags"},
            {"group": "Related Fields", "label": "annotations", "value": "annotations"},
            {
                "group": "Related Fields",
                "label": "componentassignedlicense",
                "value": "componentassignedlicense",
            },
            {
                "group": "Related Fields",
                "label": "external_references",
                "value": "external_references",
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
            {"group": "Properties", "value": "urn", "label": "urn"},
            {"group": "Properties", "value": "details_url", "label": "details_url"},
            {"group": "Properties", "label": "spdx_url", "value": "spdx_url"},
            {
                "group": "Properties",
                "label": "attribution_required",
                "value": "attribution_required",
            },
            {
                "group": "Properties",
                "label": "redistribution_required",
                "value": "redistribution_required",
            },
            {
                "group": "Properties",
                "label": "change_tracking_required",
                "value": "change_tracking_required",
            },
            {"group": "Properties", "label": "where_used", "value": "where_used"},
            {"group": "Properties", "label": "language_code", "value": "language_code"},
        ]
        self.assertEqual(expected, value["license_library:license"]["grouped_fields"])

    def test_get_model_data_for_component_column_template(self):
        self.maxDiff = None
        value = get_model_data_for_column_template()
        # Same order as the select input
        expected = [
            {
                "group": "Direct Fields",
                "label": "acceptable_linkages",
                "value": "acceptable_linkages",
            },
            {"group": "Direct Fields", "label": "admin_notes", "value": "admin_notes"},
            {
                "group": "Direct Fields",
                "label": "affiliate_obligation_triggers",
                "value": "affiliate_obligation_triggers",
            },
            {
                "group": "Direct Fields",
                "label": "affiliate_obligations",
                "value": "affiliate_obligations",
            },
            {
                "group": "Direct Fields",
                "label": "approval_reference",
                "value": "approval_reference",
            },
            {
                "group": "Direct Fields",
                "label": "approved_community_interaction",
                "value": "approved_community_interaction",
            },
            {
                "group": "Direct Fields",
                "label": "approved_download_location",
                "value": "approved_download_location",
            },
            {"group": "Direct Fields", "label": "bug_tracking_url", "value": "bug_tracking_url"},
            {"group": "Direct Fields", "label": "code_view_url", "value": "code_view_url"},
            {
                "group": "Direct Fields",
                "label": "codescan_identifier",
                "value": "codescan_identifier",
            },
            {"group": "Direct Fields", "label": "completion_level", "value": "completion_level"},
            {
                "group": "Direct Fields",
                "label": "configuration_status >>",
                "value": "configuration_status",
            },
            {"group": "Direct Fields", "label": "copyright", "value": "copyright"},
            {
                "group": "Direct Fields",
                "label": "covenant_not_to_assert",
                "value": "covenant_not_to_assert",
            },
            {"group": "Direct Fields", "label": "cpe", "value": "cpe"},
            {"group": "Direct Fields", "value": "created_by", "label": "created_by >>"},
            {"group": "Direct Fields", "label": "created_date", "value": "created_date"},
            {"group": "Direct Fields", "label": "curation_level", "value": "curation_level"},
            {
                "group": "Direct Fields",
                "label": "declared_license_expression",
                "value": "declared_license_expression",
            },
            {"group": "Direct Fields", "label": "dependencies", "value": "dependencies"},
            {"group": "Direct Fields", "label": "description", "value": "description"},
            {
                "group": "Direct Fields",
                "label": "distribution_formats_allowed",
                "value": "distribution_formats_allowed",
            },
            {
                "group": "Direct Fields",
                "label": "export_restrictions",
                "value": "export_restrictions",
            },
            {
                "group": "Direct Fields",
                "label": "express_patent_grant",
                "value": "express_patent_grant",
            },
            {"group": "Direct Fields", "label": "guidance", "value": "guidance"},
            {"group": "Direct Fields", "label": "holder", "value": "holder"},
            {"group": "Direct Fields", "label": "homepage_url", "value": "homepage_url"},
            {"group": "Direct Fields", "label": "id", "value": "id"},
            {"group": "Direct Fields", "label": "indemnification", "value": "indemnification"},
            {
                "group": "Direct Fields",
                "label": "ip_sensitivity_approved",
                "value": "ip_sensitivity_approved",
            },
            {"group": "Direct Fields", "label": "is_active", "value": "is_active"},
            {
                "group": "Direct Fields",
                "label": "is_copyright_notice",
                "value": "is_copyright_notice",
            },
            {"group": "Direct Fields", "label": "is_license_notice", "value": "is_license_notice"},
            {
                "group": "Direct Fields",
                "label": "is_notice_in_codebase",
                "value": "is_notice_in_codebase",
            },
            {"group": "Direct Fields", "label": "keywords", "value": "keywords"},
            {"group": "Direct Fields", "value": "last_modified_by", "label": "last_modified_by >>"},
            {
                "group": "Direct Fields",
                "value": "last_modified_date",
                "label": "last_modified_date",
            },
            {"group": "Direct Fields", "label": "legal_comments", "value": "legal_comments"},
            {"group": "Direct Fields", "label": "legal_reviewed", "value": "legal_reviewed"},
            {
                "group": "Direct Fields",
                "label": "license_expression",
                "value": "license_expression",
            },
            {"group": "Direct Fields", "label": "name", "value": "name"},
            {"group": "Direct Fields", "label": "notice_filename", "value": "notice_filename"},
            {"group": "Direct Fields", "label": "notice_text", "value": "notice_text"},
            {"group": "Direct Fields", "label": "notice_url", "value": "notice_url"},
            {
                "group": "Direct Fields",
                "label": "other_license_expression",
                "value": "other_license_expression",
            },
            {"group": "Direct Fields", "label": "owner >>", "value": "owner"},
            {"group": "Direct Fields", "label": "primary_language", "value": "primary_language"},
            {"group": "Direct Fields", "label": "project", "value": "project"},
            {"group": "Direct Fields", "value": "reference_notes", "label": "reference_notes"},
            {"group": "Direct Fields", "label": "release_date", "value": "release_date"},
            {"group": "Direct Fields", "label": "request_count", "value": "request_count"},
            {
                "group": "Direct Fields",
                "label": "sublicense_allowed",
                "value": "sublicense_allowed",
            },
            {"group": "Direct Fields", "label": "type >>", "value": "type"},
            {"group": "Direct Fields", "label": "usage_policy >>", "value": "usage_policy"},
            {"group": "Direct Fields", "label": "uuid", "value": "uuid"},
            {"group": "Direct Fields", "label": "vcs_url", "value": "vcs_url"},
            {"group": "Direct Fields", "label": "version", "value": "version"},
            {
                "group": "Direct Fields",
                "label": "website_terms_of_use",
                "value": "website_terms_of_use",
            },
            {"group": "Many to Many Fields", "label": "children", "value": "children"},
            {"group": "Many to Many Fields", "label": "licenses", "value": "licenses"},
            {"group": "Many to Many Fields", "label": "packages", "value": "packages"},
            {
                "group": "Related Fields",
                "label": "componentassignedlicense",
                "value": "componentassignedlicense",
            },
            {
                "group": "Related Fields",
                "label": "componentassignedpackage",
                "value": "componentassignedpackage",
            },
            {
                "group": "Related Fields",
                "label": "external_references",
                "value": "external_references",
            },
            {"group": "Related Fields", "value": "productcomponents", "label": "productcomponents"},
            {
                "group": "Related Fields",
                "label": "productinventoryitem",
                "value": "productinventoryitem",
            },
            {"group": "Related Fields", "label": "related_children", "value": "related_children"},
            {"group": "Related Fields", "label": "related_parents", "value": "related_parents"},
            {"group": "Properties", "label": "urn", "value": "urn"},
            {"group": "Properties", "label": "details_url", "value": "details_url"},
            {"group": "Properties", "value": "primary_license", "label": "primary_license"},
            {
                "group": "Properties",
                "label": "attribution_required",
                "value": "attribution_required",
            },
            {
                "group": "Properties",
                "label": "redistribution_required",
                "value": "redistribution_required",
            },
            {
                "group": "Properties",
                "label": "change_tracking_required",
                "value": "change_tracking_required",
            },
            {"group": "Properties", "label": "where_used", "value": "where_used"},
        ]
        self.assertEqual(expected, value["component_catalog:component"]["grouped_fields"])

    def test_get_model_data_for_ColumnTemplate_includes_license_tag(self):
        value = get_model_data_for_column_template(self.dataspace)
        self.assertTrue("tag: Network Redistribution" in value["license_library:license"]["meta"])
        self.assertTrue("tag: Network Redistribution" in value["license_library:license"]["fields"])

    def test_column_template_model_as_headers(self):
        ColumnTemplateAssignedField.objects.create(
            dataspace=self.dataspace,
            column_template=self.column_template,
            field_name="version",
            seq=1,
        )
        self.assertEqual(["Owner Name", "version"], self.column_template.as_headers())

    def test_column_template_model_get_value_for_field_license_expression(self):
        inventory_item = ProductInventoryItem(license_expression="l1 AND l2 WITH e3")
        value = ColumnTemplateAssignedField.get_value_for_field(
            instance=inventory_item, field_name="license_expression", user=self.super_user
        )
        self.assertEqual("l1 AND (l2 WITH e3)", value)


class CardLayoutTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("super_user", self.dataspace)
        self.basic_user = create_user("basic_user", self.dataspace)

        self.owner = Owner.objects.create(name="Owner", dataspace=self.dataspace)
        license_names = ["license_{}".format(x) for x in range(10)]
        for name in license_names:
            License.objects.create(
                key=name, name=name, short_name=name, owner=self.owner, dataspace=self.dataspace
            )

        self.license_ct = ContentType.objects.get_for_model(License)
        self.query = Query.objects.create(
            dataspace=self.dataspace, name="Q1", content_type=self.license_ct, operator="and"
        )
        Filter.objects.create(
            dataspace=self.dataspace, query=self.query, field_name="id", lookup="gte", value=0
        )

    def test_reporting_card_model_get_object_list(self):
        card = Card.objects.create(dataspace=self.dataspace, query=self.query, number_of_results=3)
        object_list = card.get_object_list(user=None)
        self.assertEqual(3, len(object_list))
        self.assertIn('<a href="/licenses/nexB/license_0/">license_0 (license_0)</a>', object_list)
        self.assertIn('<a href="/licenses/nexB/license_1/">license_1 (license_1)</a>', object_list)
        self.assertIn('<a href="/licenses/nexB/license_2/">license_2 (license_2)</a>', object_list)

        card.number_of_results = 1000
        card.save()
        object_list = card.get_object_list(user=None)
        self.assertEqual(10, len(object_list))

    def test_reporting_card_layout_model_methods(self):
        card1 = Card.objects.create(
            title="1", dataspace=self.dataspace, query=self.query, number_of_results=1
        )
        card2 = Card.objects.create(
            title="2", dataspace=self.dataspace, query=self.query, number_of_results=2
        )
        card3 = Card.objects.create(
            title="3", dataspace=self.dataspace, query=self.query, number_of_results=3
        )

        layout = CardLayout.objects.create(name="Layout", dataspace=self.dataspace)
        LayoutAssignedCard.objects.create(
            layout=layout, card=card1, seq=3, dataspace=self.dataspace
        )
        LayoutAssignedCard.objects.create(
            layout=layout, card=card2, seq=1, dataspace=self.dataspace
        )
        LayoutAssignedCard.objects.create(
            layout=layout, card=card3, seq=2, dataspace=self.dataspace
        )

        expected = [card2, card3, card1]
        self.assertEqual(expected, list(layout.get_ordered_cards()))

        expected = ["2", "3", "1"]
        self.assertEqual(expected, layout.cards_title)

        cards_with_objects = layout.cards_with_objects(user=None)
        card2_object_list = cards_with_objects[0].object_list
        expected = [
            '<a href="/licenses/nexB/license_0/">license_0 (license_0)</a>',
            '<a href="/licenses/nexB/license_1/">license_1 (license_1)</a>',
        ]
        self.assertEqual(expected, card2_object_list)
        self.assertEqual(expected, card2.get_object_list(user=None))
