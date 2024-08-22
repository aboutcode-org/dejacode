#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import NON_FIELD_ERRORS
from django.test import RequestFactory
from django.test import TestCase

from guardian.shortcuts import assign_perm
from license_expression import Licensing

from component_catalog.models import Component
from component_catalog.models import Package
from component_catalog.models import Subcomponent
from dje.models import Dataspace
from dje.tests import create_admin
from license_library.models import License
from organization.models import Owner
from product_portfolio.forms import AttributionConfigurationForm
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductPackage
from product_portfolio.templatetags.attribution import get_html_id
from product_portfolio.views import AttributionNode
from product_portfolio.views import AttributionView
from reporting.models import Filter
from reporting.models import Query


class AttributionGenerationTest(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.nexb_user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.dataspace
        )
        self.admin_user = create_admin("admin_user", self.dataspace)

        self.owner1 = Owner.objects.create(name="Test Organization", dataspace=self.dataspace)

        self.license1 = License.objects.create(
            key="license1",
            name="License1",
            short_name="License1",
            full_text="FULLTEXT_FOR_LICENSE1",
            owner=self.owner1,
            dataspace=self.dataspace,
        )
        self.license2 = License.objects.create(
            key="license2",
            name="License2",
            short_name="License2",
            full_text="FULLTEXT_FOR_LICENSE2",
            owner=self.owner1,
            dataspace=self.dataspace,
        )
        self.license3 = License.objects.create(
            key="license3",
            name="License3",
            short_name="License3",
            full_text="FULLTEXT_FOR_LICENSE3",
            owner=self.owner1,
            dataspace=self.dataspace,
        )

        self.c1 = Component.objects.create(
            name="Component1",
            version="0.1",
            license_expression=self.license1.key,
            dataspace=self.dataspace,
        )
        self.c2 = Component.objects.create(
            name="Component2",
            version="0.2",
            license_expression=self.license2.key,
            dataspace=self.dataspace,
        )
        self.c3 = Component.objects.create(
            name="Component3", version="0.3", dataspace=self.dataspace
        )

        license_expression = "{} AND {}".format(self.license1.key, self.license2.key)
        self.product1 = Product.objects.create(
            name="Product1", dataspace=self.dataspace, license_expression=license_expression
        )

        self.pc1 = ProductComponent.objects.create(
            product=self.product1, component=self.c1, dataspace=self.dataspace, feature="Feature3"
        )
        self.pc2 = ProductComponent.objects.create(
            product=self.product1, component=self.c2, dataspace=self.dataspace, feature="Feature3"
        )
        self.pc3 = ProductComponent.objects.create(
            product=self.product1, component=self.c3, dataspace=self.dataspace, feature="Feature1"
        )

        self.sub3_license = License.objects.create(
            key="sub3_license",
            name="Sub3",
            short_name="Sub3",
            full_text="FULLTEXT_FOR_Sub3",
            owner=self.owner1,
            dataspace=self.dataspace,
        )

        self.child1 = Component.objects.create(
            name="Child1", version="1.1", dataspace=self.dataspace
        )
        self.child2 = Component.objects.create(
            name="Child2", version="2.1", dataspace=self.dataspace
        )
        self.child3 = Component.objects.create(
            name="Child3",
            version="3.1",
            copyright="Child3 Copyright",
            notice_text="C3 notice text",
            dataspace=self.dataspace,
        )
        self.sub1 = Subcomponent.objects.create(
            parent=self.c1, child=self.child1, dataspace=self.dataspace
        )
        self.sub2 = Subcomponent.objects.create(
            parent=self.child1, child=self.child2, dataspace=self.dataspace
        )
        self.sub3 = Subcomponent.objects.create(
            extra_attribution_text="Child3 extra text",
            license_expression=str(self.sub3_license.key),
            parent=self.child2,
            child=self.child3,
            dataspace=self.dataspace,
        )

        license_ct = ContentType.objects.get_for_model(License)
        self.license_query = Query.objects.create(
            dataspace=self.dataspace, name="License", content_type=license_ct
        )

        productcomponent_ct = ContentType.objects.get_for_model(ProductComponent)
        self.pc_query = Query.objects.create(
            dataspace=self.dataspace, name="ProductComponent", content_type=productcomponent_ct
        )

        component_ct = ContentType.objects.get_for_model(Component)
        self.component_query = Query.objects.create(
            dataspace=self.dataspace, name="Component", content_type=component_ct
        )

        self.package1 = Package.objects.create(filename="package1", dataspace=self.dataspace)
        self.pp1 = ProductPackage.objects.create(
            product=self.product1, package=self.package1, dataspace=self.dataspace
        )

    def test_attribution_generation_configuration_view_proper(self):
        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(self.product1.get_attribution_url())
        self.assertEqual(200, response.status_code)

    def test_attribution_generation_configuration_view_breadcrumbs_contains_product_link(self):
        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(self.product1.get_attribution_url())
        expected = """
        <div class="header-pretitle">
            <a href="/products/">Products</a>
            / <a href="/products/nexB/Product1/">Product1</a>
        </div>
        """
        self.assertContains(response, expected, html=True)

    def test_attribution_generation_configuration_form_query_is_valid(self):
        request = RequestFactory()
        request.user = self.nexb_user

        query_input = [
            ("component_query", self.component_query),
            ("pc_query", self.pc_query),
        ]

        for param, query in query_input:
            form = AttributionConfigurationForm(request)
            query_qs = form.fields[param].queryset
            self.assertNotIn(self.license_query, query_qs)
            self.assertIn(query, query_qs)

            form = AttributionConfigurationForm(request, data={param: self.license_query.id})
            self.assertFalse(form.is_valid())
            expected = {
                param: ["Select a valid choice. That choice is not one of the available choices."]
            }
            self.assertEqual(expected, form.errors)

            form = AttributionConfigurationForm(request, data={param: query.id})
            self.assertTrue(form.is_valid())

    def test_attribution_generation_configuration_queries_validation(self):
        request = RequestFactory()
        request.user = self.nexb_user
        query_input = [
            ("component_query", self.component_query),
            ("pc_query", self.pc_query),
        ]

        for param, query in query_input:
            filtr = Filter.objects.create(
                dataspace=self.dataspace,
                query=query,
                field_name="INVALID",
                lookup="exact",
                value=True,
            )

            self.assertFalse(query.is_valid())
            form = AttributionConfigurationForm(request, data={param: query.id})
            self.assertFalse(form.is_valid())
            expected = {NON_FIELD_ERRORS: ["Query not valid."]}
            self.assertEqual(expected, form.errors)

            filtr.delete()
            self.assertTrue(query.is_valid())
            form = AttributionConfigurationForm(request, data={param: query.id})
            self.assertTrue(form.is_valid())

    def test_attribution_generation_configuration_single_query_validation(self):
        request = RequestFactory()
        request.user = self.nexb_user
        data = {
            "component_query": self.component_query.id,
            "pc_query": self.pc_query.id,
        }

        form = AttributionConfigurationForm(request, data=data)
        self.assertFalse(form.is_valid())
        expected = {NON_FIELD_ERRORS: ["Only one Query type allowed at once."]}
        self.assertEqual(expected, form.errors)

    def test_attribution_apply_reporting_pc_query_secured_queryset(self):
        apply_query = AttributionView.apply_productcomponent_query
        productcomponents = [self.pc1, self.pc2, self.pc3]

        self.c1.is_active = False
        self.c1.save()
        self.c2.is_active = False
        self.c2.save()
        self.c3.is_active = True
        self.c3.save()

        # No filter in query, nothing is returned
        results_list = apply_query(productcomponents, self.pc_query, self.nexb_user)
        self.assertEqual([], results_list)

        Filter.objects.create(
            dataspace=self.dataspace,
            query=self.pc_query,
            field_name="component__is_active",
            lookup="exact",
            value=True,
        )

        results_list = apply_query(productcomponents, self.pc_query, self.nexb_user)
        self.assertNotIn(self.pc1, results_list)
        self.assertNotIn(self.pc2, results_list)
        self.assertTrue(self.pc3.component.is_active)
        self.assertIn(self.pc3, results_list)

        # Admin user with no Product object permission
        results_list = apply_query(productcomponents, self.pc_query, self.admin_user)
        self.assertEqual([], results_list)

        assign_perm("change_product", self.admin_user, self.pc3.product)
        results_list = apply_query(productcomponents, self.pc_query, self.nexb_user)
        self.assertNotIn(self.pc1, results_list)
        self.assertNotIn(self.pc2, results_list)
        self.assertIn(self.pc3, results_list)

    def test_attribution_generation_configuration_owner_in_product_section(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()

        self.assertIsNone(self.product1.owner)
        response = self.client.get(url, data={"submit": 1})
        self.assertContains(response, "<h1>Attribution for {}</h1>".format(self.product1))

        self.product1.owner = self.owner1
        self.product1.save()
        response = self.client.get(url, data={"submit": 1})
        self.assertContains(
            response, "<h1>Attribution for {} by {}</h1>".format(self.product1, self.owner1)
        )

    def test_attribution_generation_configuration_licensing_in_product_section(self):
        self.client.login(username="nexb_user", password="t3st")
        self.product1.productcomponents.all().delete()
        self.product1.copyright = "COPYRIGHT"
        self.product1.notice_text = "NOTICE_TEXT"
        self.product1.save()
        self.assertEqual(2, self.product1.licenses.count())
        self.assertEqual("license1 AND license2", self.product1.license_expression)

        url = self.product1.get_attribution_url()
        response = self.client.get(url, data={"submit": 1})
        expected = """
        <p>
            {} is licensed under
            <a href="#license_license1">License1</a> AND <a href="#license_license2">License2</a>
             and the third-party licenses listed below.
        </p>
        """.format(self.product1)
        self.assertContains(response, expected, html=True)
        self.assertContains(response, '<h2 id="license_texts">Licenses that apply to Product1</h2>')
        self.assertContains(response, '<a href="#license_license1">License1</a>')
        self.assertContains(response, '<a href="#license_license2">License2</a>')
        self.assertContains(response, "<pre>FULLTEXT_FOR_LICENSE1</pre>")
        self.assertContains(response, "<pre>FULLTEXT_FOR_LICENSE2</pre>")

    def test_attribution_generation_configuration_product_component_table_of_contents(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()
        self.assertEqual(3, self.product1.productcomponents.count())

        response = self.client.get(url, data={"submit": 1})
        expected_header = "<h2>Product1 contains the following software components:</h2>"
        self.assertContains(response, expected_header)

        hierarchy = response.context["hierarchy"]
        node1 = hierarchy["Feature3"][0][0]
        node2 = hierarchy["Feature3"][1][0]
        node3 = hierarchy["Feature1"][0][0]

        expected = """
        <ul class="oss-table-of-contents list-unstyled">
            <li><a href="#{}">{}</a></li>
            <li><a href="#{}">{}</a></li>
            <li><a href="#{}">{}</a></li>
        </ul>""".format(
            get_html_id(node1), self.c1, get_html_id(node2), self.c2, get_html_id(node3), self.c3
        )

        self.assertContains(response, expected, html=True)

        product2 = Product.objects.create(name="Product2", dataspace=self.dataspace)
        self.assertEqual(0, product2.productcomponents.count())
        url = product2.get_attribution_url()
        response = self.client.get(url, data={"submit": 1})
        self.assertNotContains(response, expected_header)

    def test_attribution_generation_relation_has_same_license_expression_as_component(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()

        # Special case: 'oracle-bcl-javaee' contains 'or'
        self.license1.key = "oracle-bcl-javaee"
        self.license1.save()

        # We need at least 2 licenses in the expression to expose the potential equivalence issue
        self.pc1.license_expression = f"{self.license1.key} AND {self.license3.key}"
        self.pc1.save()
        self.pc1.component.license_expression = self.pc1.license_expression
        self.pc1.component.save()
        self.pc2.component.license_expression = ""
        self.pc2.component.save()

        self.assertEqual(list(self.pc1.licenses.all()), list(self.pc1.component.licenses.all()))
        self.assertTrue(
            Licensing().is_equivalent(
                self.pc1.license_expression, self.pc1.component.license_expression
            )
        )

        response = self.client.get(url, data={"submit": 1, "all_license_texts": "on"})
        self.assertContains(
            response, "<h2>The following licenses are used in {}:</h2>".format(self.product1)
        )
        self.assertContains(
            response,
            '<p><a href="#license_{}">{}</a></p>'.format(
                self.license1.key, self.license1.short_name
            ),
        )
        self.assertContains(
            response,
            '<a href="#license_{}">{}</a>'.format(self.license1.key, self.license1.short_name),
        )

        self.assertNotContains(response, "The original component is licensed under")

        self.pc1.component.license_expression = f"{self.license1.key}"
        self.pc1.component.save()
        response = self.client.get(url, data={"submit": 1, "all_license_texts": "on"})
        self.assertContains(response, "The original component is licensed under")

    def test_attribution_generation_configuration_include_all_license_texts(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()

        self.product1.license_expression = ""
        self.product1.save()
        self.assertEqual(0, self.product1.licenses.count())

        self.pc1.license_expression = self.license1.key
        self.pc1.save()
        self.assertEqual(1, self.pc1.licenses.count())

        self.c1.license_expression = "{} AND {}".format(self.license1.key, self.license3.key)
        self.c1.save()

        expected = """
        <p>The original component is licensed under
            <a href="#license_{}">{}</a> AND <a href="#license_{}">{}</a></p>
        """.format(
            self.license1.key, self.license1.short_name, self.license3.key, self.license3.short_name
        )

        response = self.client.get(url, data={"submit": 1})
        self.assertContains(response, "FULLTEXT_FOR_LICENSE1")
        self.assertNotContains(response, "FULLTEXT_FOR_LICENSE2")
        self.assertNotContains(response, "FULLTEXT_FOR_LICENSE3")
        self.assertNotContains(response, expected, html=True)

        response = self.client.get(url, data={"submit": 1, "all_license_texts": "on"})
        self.assertContains(response, "FULLTEXT_FOR_LICENSE1")
        self.assertContains(response, "FULLTEXT_FOR_LICENSE2")
        self.assertContains(response, "FULLTEXT_FOR_LICENSE3")
        self.assertContains(response, expected, html=True)

    def test_attribution_generation_configuration_not_include_all_license_texts(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()

        special_license = License.objects.create(
            key="special_license",
            name="Special",
            short_name="Special",
            full_text="Special_Text",
            owner=self.owner1,
            dataspace=self.dataspace,
        )

        self.child1.license_expression = special_license.key
        self.child1.save()
        self.sub1.license_expression = special_license.key
        self.sub1.save()

        expected = '<a href="#license_{}">{}</a>'.format(
            special_license.key, special_license.short_name
        )
        self.assertEqual(expected, self.sub1.get_license_expression_attribution())
        response = self.client.get(
            url, data={"submit": 1, "all_license_texts": False, "subcomponent_hierarchy": "on"}
        )

        self.assertContains(response, expected, html=True)
        self.assertContains(
            response,
            '<h3 id="license_{}">{}</h3>'.format(special_license.key, special_license.short_name),
            html=True,
        )

    def test_attribution_generation_configuration_include_complete_subcomponent_hierarchy(self):
        self.client.login(username="nexb_user", password="t3st")

        url = self.product1.get_attribution_url()
        response = self.client.get(url, data={"submit": 1, "subcomponent_hierarchy": False})

        node1 = AttributionNode(
            model_name="component",
            display_name="Component1 0.1",
            owner="",
            copyright="",
            extra_attribution_text="",
            relationship_expression=None,
            component_expression=None,
            notice_text="",
            is_displayed=True,
            homepage_url="",
            standard_notice="",
        )
        node2 = AttributionNode(
            model_name="component",
            display_name="Component2 0.2",
            owner="",
            copyright="",
            extra_attribution_text="",
            relationship_expression=None,
            component_expression=None,
            notice_text="",
            is_displayed=True,
            homepage_url="",
            standard_notice="",
        )
        node3 = AttributionNode(
            model_name="component",
            display_name="Component3 0.3",
            owner="",
            copyright="",
            extra_attribution_text="",
            relationship_expression=None,
            component_expression=None,
            notice_text="",
            is_displayed=True,
            homepage_url="",
            standard_notice="",
        )
        expected = {
            "Feature3": [
                (node1, []),
                (node2, []),
            ],
            "Feature1": [
                (node3, []),
            ],
        }
        self.assertEqual(expected, response.context["hierarchy"])

        data = {
            "submit": 1,
            "subcomponent_hierarchy": True,
            "all_license_texts": True,
        }
        response = self.client.get(url, data)

        node1 = AttributionNode(
            model_name="component",
            display_name="Component1 0.1",
            owner="",
            copyright="",
            extra_attribution_text="",
            relationship_expression=None,
            component_expression='<a href="#license_license1">License1</a>',
            notice_text="",
            is_displayed=True,
            homepage_url="",
            standard_notice="",
        )
        node2 = AttributionNode(
            model_name="component",
            display_name="Component2 0.2",
            owner="",
            copyright="",
            extra_attribution_text="",
            relationship_expression=None,
            component_expression='<a href="#license_license2">License2</a>',
            notice_text="",
            is_displayed=True,
            homepage_url="",
            standard_notice="",
        )
        node3 = AttributionNode(
            model_name="component",
            display_name="Component3 0.3",
            owner="",
            copyright="",
            extra_attribution_text="",
            relationship_expression=None,
            component_expression=None,
            notice_text="",
            is_displayed=True,
            homepage_url="",
            standard_notice="",
        )
        node4 = AttributionNode(
            model_name="component",
            display_name="Child1 1.1",
            owner="",
            copyright="",
            extra_attribution_text="",
            relationship_expression=None,
            component_expression=None,
            notice_text="",
            is_displayed=True,
            homepage_url="",
            standard_notice="",
        )
        node5 = AttributionNode(
            model_name="component",
            display_name="Child2 2.1",
            owner="",
            copyright="",
            extra_attribution_text="",
            relationship_expression=None,
            component_expression=None,
            notice_text="",
            is_displayed=True,
            homepage_url="",
            standard_notice="",
        )
        node6 = AttributionNode(
            model_name="component",
            display_name="Child3 3.1",
            owner="",
            copyright="Child3 Copyright",
            extra_attribution_text="Child3 extra text",
            relationship_expression='<a href="#license_sub3_license">Sub3</a>',
            component_expression=None,
            notice_text="C3 notice text",
            is_displayed=True,
            homepage_url="",
            standard_notice="",
        )
        expected = {
            "Feature3": [
                (node1, {"": [(node4, {"": [(node5, {"": [(node6, {})]})]})]}),
                (node2, {}),
            ],
            "Feature1": [
                (node3, {}),
            ],
        }

        self.assertEqual(expected, response.context["hierarchy"])
        expected = '<li><a href="#{}">{}</a></li>'.format(get_html_id(node6), self.sub3.child)
        self.assertContains(response, expected, html=True)

        expected = """
        <div class="oss-component" id="{}">
            <h3 class="component-name">{}</h3>
            <pre>{}</pre>
            <pre>{}</pre>
            <p>
                This component is licensed under <a href="#license_{}">{}</a>
            </p>
            <pre>{}</pre>
        </div>""".format(
            get_html_id(node6),
            self.sub3.child,
            self.sub3.child.copyright,
            self.sub3.extra_attribution_text,
            self.sub3_license.key,
            self.sub3_license.short_name,
            self.sub3.child.notice_text,
        )

        self.assertContains(response, expected, html=True)

        expected = '<p><a href="#license_{}">{}</a></p>'.format(
            self.sub3_license.key, self.sub3_license.short_name
        )
        self.assertContains(response, expected, html=True)
        expected = '<h3 id="license_{}">{}</h3>'.format(
            self.sub3_license.key, self.sub3_license.short_name
        )
        self.assertContains(response, expected, html=True)
        expected = "<pre>{}</pre>".format(self.sub3_license.full_text)
        self.assertContains(response, expected, html=True)

    def test_attribution_generation_configuration_toc_as_nested_list(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()
        response = self.client.get(
            url, data={"submit": 1, "subcomponent_hierarchy": True, "toc_as_nested_list": False}
        )
        self.assertFalse(response.context["toc_as_nested_list"])

        unique_component_nodes = response.context["unique_component_nodes"]
        expected = """
            <ul class="oss-table-of-contents list-unstyled">
                <li><a href="#{}">Child1 1.1</a></li>
                <li><a href="#{}">Child2 2.1</a></li>
                <li><a href="#{}">Child3 3.1</a></li>
                <li><a href="#{}">Component1 0.1</a></li>
                <li><a href="#{}">Component2 0.2</a></li>
                <li><a href="#{}">Component3 0.3</a></li>
            </ul>
            """.format(*[get_html_id(node) for node in unique_component_nodes])
        self.assertContains(response, expected, html=True)

        response = self.client.get(
            url, data={"submit": 1, "subcomponent_hierarchy": True, "toc_as_nested_list": True}
        )
        self.assertTrue(response.context["toc_as_nested_list"])

        hierarchy = response.context["hierarchy"]
        expected = """
        <ul class="oss-table-of-contents list-unstyled">
            <li>
                <a href="#{}">Component1 0.1</a>
                <ul>
                    <li>
                        <a href="#{}">Child1 1.1</a>
                        <ul>
                            <li>
                                <a href="#{}">Child2 2.1</a>
                                <ul>
                                    <li>
                                        <a href="#{}">Child3 3.1</a>
                                    </li>
                                </ul>
                            </li>
                        </ul>
                    </li>
                </ul>
            </li>
            <li>
                <a href="#{}">Component2 0.2</a>
            </li>
            <li>
                <a href="#{}">Component3 0.3</a>
            </li>
        </ul>
        """.format(
            get_html_id(hierarchy["Feature3"][0][0]),
            get_html_id(hierarchy["Feature3"][0][1][""][0][0]),
            get_html_id(hierarchy["Feature3"][0][1][""][0][1][""][0][0]),
            get_html_id(hierarchy["Feature3"][0][1][""][0][1][""][0][1][""][0][0]),
            get_html_id(hierarchy["Feature3"][1][0]),
            get_html_id(hierarchy["Feature1"][0][0]),
        )
        self.assertContains(response, expected, html=True)

    def test_attribution_generation_configuration_group_by_feature(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()

        response = self.client.get(
            url, data={"submit": 1, "group_by_feature": True, "toc_as_nested_list": False}
        )

        expected = (
            "<li>Grouping components by feature requires &quot;"
            "Display components as hierarchy&quot;.</li>"
        )
        self.assertContains(response, expected, html=True)

        response = self.client.get(
            url,
            data={
                "submit": 1,
                "group_by_feature": True,
                "toc_as_nested_list": True,
                "subcomponent_hierarchy": True,
            },
        )

        self.assertContains(
            response, '<li class="feature"><strong>Feature1</strong></li>', html=True
        )
        self.assertContains(
            response, '<li class="feature"><strong>Feature3</strong></li>', html=True
        )

        self.assertEqual(["Feature1", "Feature3"], list(response.context["hierarchy"].keys()))

    def test_attribution_generation_configuration_component_query(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()
        data = {"submit": 1, "subcomponent_hierarchy": True, "include_packages": True}

        response = self.client.get(url, data=data)
        displayed_nodes = [
            node for node in response.context["unique_component_nodes"] if node.is_displayed
        ]
        self.assertEqual(6, len(displayed_nodes))

        # ProductComponent
        component = self.pc1.component
        query_filter = Filter.objects.create(
            dataspace=self.dataspace,
            query=self.component_query,
            field_name="id",
            lookup="exact",
            value=component.id,
        )
        data["component_query"] = self.component_query.id
        response = self.client.get(url, data=data)
        displayed_nodes = [
            node for node in response.context["unique_component_nodes"] if node.is_displayed
        ]
        self.assertEqual(1, len(displayed_nodes))
        self.assertEqual(str(component), displayed_nodes[0].display_name)

        # Subcomponent
        component = self.sub1.child
        query_filter.value = component.id
        query_filter.save()
        response = self.client.get(url, data=data)
        displayed_nodes = [
            node for node in response.context["unique_component_nodes"] if node.is_displayed
        ]
        self.assertEqual(1, len(displayed_nodes))
        self.assertEqual(str(component), displayed_nodes[0].display_name)

        # Package
        self.assertContains(response, self.package1.filename)

    def test_attribution_generation_configuration_requires_submit(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()

        response = self.client.get(url, data={})
        self.assertTemplateUsed(response, "product_portfolio/attribution_configuration.html")

        response = self.client.get(url, data={"_list_filters": "leftover"})
        self.assertTemplateUsed(response, "product_portfolio/attribution_configuration.html")

        response = self.client.get(url, data={"submit": 1})
        self.assertTemplateUsed(response, "product_portfolio/attribution/base.html")

    def test_attribution_generation_component_duplication(self):
        self.client.login(username="nexb_user", password="t3st")
        data = {"submit": 1, "subcomponent_hierarchy": True}
        url = self.product1.get_attribution_url()

        # True duplicate
        duplicate = Subcomponent.objects.create(
            parent=self.c2, child=self.sub1.child, dataspace=self.dataspace
        )

        response = self.client.get(url, data=data)
        res = [
            node
            for node in response.context["unique_component_nodes"]
            if str(duplicate.child) == node.display_name
        ]
        self.assertEqual(1, len(res))

        # False duplicate, included since 1 value on the AttributionNode is different
        duplicate.extra_attribution_text = "a"
        duplicate.save()

        response = self.client.get(url, data=data)
        res = [
            node
            for node in response.context["unique_component_nodes"]
            if str(duplicate.child) == node.display_name
        ]
        self.assertEqual(2, len(res))

    def test_attribution_templatetags_get_html_id(self):
        node = AttributionNode(
            model_name="component",
            display_name="Component1 0.1",
            owner="",
            copyright="",
            extra_attribution_text="",
            relationship_expression=None,
            component_expression=None,
            notice_text="",
            is_displayed=True,
            homepage_url="",
            standard_notice="",
        )

        id1 = get_html_id(node)
        self.assertEqual(get_html_id(node), get_html_id(node))

        node = node._replace(extra_attribution_text="a")
        self.assertNotEqual(id1, get_html_id(node))

    def test_attribution_generation_views_secured(self):
        url = self.product1.get_attribution_url()
        self.client.login(username=self.admin_user.username, password="secret")
        self.assertEqual(404, self.client.get(url).status_code)
        self.assertEqual(404, self.client.get(url, data={"submit": 1}).status_code)

        assign_perm("view_product", self.admin_user, self.pc3.product)
        self.assertEqual(200, self.client.get(url).status_code)
        self.assertEqual(200, self.client.get(url, data={"submit": 1}).status_code)

    def test_attribution_generation_configuration_include_homepage_url(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()

        response = self.client.get(url, data={"submit": 1, "include_homepage_url": True})
        self.assertNotContains(response, "Homepage")

        self.c1.homepage_url = "http://component1.com"
        self.c1.save()
        response = self.client.get(url, data={"submit": 1, "include_homepage_url": True})
        expected = 'Homepage: <a href="{0}" rel="nofollow">{0}</a>'.format(self.c1.homepage_url)
        self.assertContains(response, expected)

        response = self.client.get(url, data={"submit": 1})
        self.assertNotContains(response, "Homepage")

    def test_attribution_generation_configuration_include_standard_notice(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()
        self.pc1.license_expression = self.license1.key
        self.pc1.save()
        standard_notice = "Standard notice for License 1"

        response = self.client.get(url, data={"submit": 1, "include_standard_notice": True})
        self.assertNotContains(response, standard_notice)

        self.license1.standard_notice = standard_notice
        self.license1.save()
        response = self.client.get(url, data={"submit": 1, "include_standard_notice": True})
        self.assertContains(response, standard_notice)

        response = self.client.get(url, data={"submit": 1})
        self.assertNotContains(response, standard_notice)

    def test_attribution_generation_productpackage(self):
        self.pp1.license_expression = self.license3.key
        self.pp1.save()

        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()

        expected1 = "<h2>Product1 contains the following software packages:</h2>"
        expected2 = '<h3 class="component-name">package1</h3>'
        expected3 = "<h2>List of package details:</h2>"
        expected4 = self.license3.key

        response = self.client.get(url, data={"submit": 1})
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, expected4)

        response = self.client.get(url, data={"submit": 1, "include_packages": True})
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertContains(response, expected4)

    def test_attribution_generation_include_packages(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()

        expected = (
            '<input type="checkbox" name="include_packages" '
            'class="checkboxinput form-check-input" '
            'aria-describedby="id_include_packages_helptext" id="id_include_packages" '
            "checked>"
        )
        response = self.client.get(url)
        self.assertContains(response, expected)

        self.pp1.delete()
        expected = (
            '<input type="checkbox" name="include_packages" '
            'class="checkboxinput form-check-input" '
            'aria-describedby="id_include_packages_helptext" id="id_include_packages">'
        )
        response = self.client.get(url)
        self.assertContains(response, expected)

    def test_attribution_generation_include_custom_component(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.product1.get_attribution_url()

        custom_license = License.objects.create(
            key="custom",
            name="Custom",
            short_name="Custom",
            full_text="FULLTEXT_FOR_CUSTOM",
            owner=self.owner1,
            dataspace=self.dataspace,
        )
        custom_component = ProductComponent.objects.create(
            product=self.product1,
            name="custom",
            version="8.9",
            license_expression=f"{custom_license.key}",
            dataspace=self.dataspace,
        )

        response = self.client.get(url, data={"submit": 1})
        self.assertContains(response, f'<h3 class="component-name">{custom_component}</h3>')
        self.assertContains(
            response, '<p>This component is licensed under <a href="#license_custom">Custom</a></p>'
        )
        self.assertContains(response, '<a href="#license_custom">Custom</a>')
        self.assertContains(response, '<h3 id="license_custom">Custom</h3>')
        self.assertContains(response, "<pre>FULLTEXT_FOR_CUSTOM</pre>")
