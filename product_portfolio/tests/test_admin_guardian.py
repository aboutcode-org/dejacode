#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json

from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from guardian.shortcuts import assign_perm
from guardian.shortcuts import get_perms

from component_catalog.models import Component
from component_catalog.models import ComponentKeyword
from dje.models import Dataspace
from dje.tests import add_perm
from dje.tests import create_admin
from dje.tests import create_superuser
from product_portfolio.admin import ProductAdmin
from product_portfolio.admin import ProductComponentAdmin
from product_portfolio.forms import ProductComponentMassUpdateForm
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductStatus
from reporting.models import Filter
from reporting.models import Query


def refresh_product(product):
    return Product.unsecured_objects.get(pk=product.pk)


class ProductGuardianAdminViewsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="alternate")
        self.super_user = create_superuser("super_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)
        self.alt_super_user = create_superuser(
            "alt_super_user", self.alternate_dataspace)

        self.p_changelist_url = reverse(
            "admin:product_portfolio_product_changelist")

        self.p1 = Product.objects.create(
            name="Product1", dataspace=self.dataspace)
        self.p2 = Product.objects.create(
            name="Product2", dataspace=self.dataspace)
        self.alt_p = Product.objects.create(
            name="Alternate", dataspace=self.alternate_dataspace)

        self.group1 = Group.objects.create(name="Group1")

    def test_product_guardian_admin_security_attributes(self):
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.p_changelist_url)

        # actions = []
        # actions_to_remove = ['copy_to', 'compare_with', 'delete_selected']
        expected = [("", "---------"), ("mass_update", "Mass update")]
        self.assertEqual(
            expected, response.context_data["action_form"].fields["action"].choices)

        # activity_log = False
        self.assertNotContains(response, "activity_log")

        # email_notification_on = []
        self.assertEqual([], ProductAdmin.email_notification_on)

    def test_product_guardian_admin_changelist_no_dataspace_lookup(self):
        self.client.login(username=self.super_user.username, password="secret")

        response = self.client.get(self.p_changelist_url)
        self.assertNotContains(response, "<label>Dataspace</label>")

        data = {"dataspace__id__exact": self.alternate_dataspace.id}
        response = self.client.get(self.p_changelist_url, data)
        self.assertEqual(400, response.status_code)

    def test_product_guardian_admin_changelist_secured_queryset(self):
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.p_changelist_url)
        self.assertEqual(2, response.context_data["cl"].result_count)
        self.assertIn(self.p1, response.context_data["cl"].queryset)
        self.assertIn(self.p2, response.context_data["cl"].queryset)
        self.assertNotIn(self.alt_p, response.context_data["cl"].queryset)

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.get(self.p_changelist_url)
        self.assertEqual(403, response.status_code)

        add_perm(self.admin_user, "change_product")
        response = self.client.get(self.p_changelist_url)
        self.assertEqual(0, response.context_data["cl"].result_count)
        self.assertEqual([], list(response.context_data["cl"].queryset))

        assign_perm("change_product", self.admin_user, self.p1)
        response = self.client.get(self.p_changelist_url)
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(self.p1, response.context_data["cl"].queryset)
        self.assertNotIn(self.p2, response.context_data["cl"].queryset)

    def test_product_guardian_admin_add_product_set_created_by_and_permission(self):
        self.client.login(username=self.admin_user.username, password="secret")
        self.admin_user = add_perm(self.admin_user, "add_product")

        url = reverse("admin:product_portfolio_product_add")
        data = {
            "name": "New Product",
        }
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "was added successfully")
        added_product = Product.unsecured_objects.latest("id")
        self.assertEqual(data["name"], added_product.name)
        self.assertEqual(self.admin_user, added_product.created_by)

        # Object permissions are added for the creator at save time
        expected = sorted(["change_product", "view_product", "delete_product"])
        self.assertEqual(expected, sorted(
            get_perms(self.admin_user, added_product)))

    def test_product_guardian_admin_delete_view_permission(self):
        self.client.login(username=self.super_user.username, password="secret")
        p1_delete_url = reverse(
            "admin:product_portfolio_product_delete", args=[self.p1.pk])
        response = self.client.get(p1_delete_url)
        self.assertTrue(self.super_user.has_perm("delete_product", self.p1))
        self.assertEqual(200, response.status_code)

        self.client.login(username=self.admin_user.username, password="secret")
        self.assertFalse(self.admin_user.has_perm(
            "product_portfolio.delete_product"))
        self.assertFalse(self.admin_user.has_perm("delete_product", self.p1))
        response = self.client.get(p1_delete_url)
        self.assertEqual(403, response.status_code)

        self.admin_user = add_perm(self.admin_user, "delete_product")
        self.assertTrue(self.admin_user.has_perm(
            "product_portfolio.delete_product"))
        response = self.client.get(p1_delete_url, follow=True)
        self.assertRedirects(response, reverse("admin:index"))
        self.assertContains(response, "Perhaps it was deleted?")

        # Object permission also needed
        assign_perm("delete_product", self.admin_user, self.p1)
        assign_perm("change_product", self.admin_user, self.p1)
        response = self.client.get(p1_delete_url)
        self.assertEqual(200, response.status_code)

    def test_product_guardian_admin_mass_update_view_permission(self):
        my_keyword = ComponentKeyword.objects.create(
            dataspace=self.dataspace, label="my_keyword")
        alt_keyword = ComponentKeyword.objects.create(
            dataspace=self.alternate_dataspace, label="alt_keyword"
        )

        my_status = ProductStatus.objects.create(
            label="my_status", dataspace=self.dataspace)
        alt_status = ProductStatus.objects.create(
            label="alt_status", dataspace=self.alternate_dataspace
        )

        data = {
            "_selected_action": "0",
            "action": "mass_update",
        }

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.post(self.p_changelist_url, data)
        self.assertEqual(302, response.status_code)

        data["_selected_action"] = self.alt_p.pk
        response = self.client.post(self.p_changelist_url, data)
        self.assertEqual(302, response.status_code)

        data["_selected_action"] = [self.p1.pk, self.p2.pk]
        response = self.client.post(self.p_changelist_url, data)
        self.assertContains(response, "<h1>Mass update Products</h1>")
        self.assertContains(response, self.p1.get_admin_link())
        self.assertContains(response, self.p2.get_admin_link())
        # Related fields scoping
        self.assertContains(response, my_keyword.label)
        self.assertNotContains(response, alt_keyword.label)
        self.assertContains(response, my_status.label)
        self.assertNotContains(response, alt_status.label)

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.post(self.p_changelist_url, data)
        self.assertEqual(403, response.status_code)

        add_perm(self.admin_user, "change_product")
        response = self.client.post(self.p_changelist_url, data)
        self.assertEqual(302, response.status_code)

        data.update(
            {
                "apply": "Update records",
                "chk_id_description": "on",
                "description": "description",
            }
        )

        response = self.client.post(self.p_changelist_url, data, follow=True)
        self.assertEqual(200, response.status_code)
        # Nothing was updated because no object permission
        self.assertNotContains(response, "Updated")
        self.p1 = refresh_product(self.p1)
        self.assertEqual("", self.p1.description)
        self.p2 = refresh_product(self.p2)
        self.assertEqual("", self.p2.description)

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.post(self.p_changelist_url, data, follow=True)
        self.assertContains(response, "Updated")
        self.p1 = refresh_product(self.p1)
        self.assertEqual("description", self.p1.description)
        self.p2 = refresh_product(self.p2)
        self.assertEqual("description", self.p2.description)

    def test_product_secured_grappelli_lookup_related(self):
        url = reverse("grp_related_lookup")
        params = f"?object_id={self.p1.pk}&app_label=product_portfolio&model_name=product"

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(url + params)
        expected = [
            {"value": str(self.p1.pk), "safe": False, "label": "Product1"}]
        self.assertEqual(expected, json.loads(response.content))

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.get(url + params)
        expected = [{"value": str(self.p1.pk), "safe": False, "label": "?"}]
        self.assertEqual(expected, json.loads(response.content))

        assign_perm("change_product", self.admin_user, self.p1)
        response = self.client.get(url + params)
        expected = [
            {"value": str(self.p1.pk), "safe": False, "label": "Product1"}]
        self.assertEqual(expected, json.loads(response.content))

    def test_product_secured_grappelli_lookup_autocomplete(self):
        url = reverse("grp_autocomplete_lookup")
        params = "?term=&app_label=product_portfolio&model_name=product"

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(url + params)
        expected = [
            {"value": self.p1.pk, "label": "Product1"},
            {"value": self.p2.pk, "label": "Product2"},
        ]
        self.assertEqual(expected, json.loads(response.content))

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.get(url + params)
        expected = [{"value": None, "label": "0 results"}]
        self.assertEqual(expected, json.loads(response.content))

        assign_perm("change_product", self.admin_user, self.p1)
        response = self.client.get(url + params)
        expected = [{"value": self.p1.pk, "label": "Product1"}]
        self.assertEqual(expected, json.loads(response.content))

    def test_product_guardian_admin_obj_perms_manage_views_access(self):
        # User must be a superuser or the instance creator to access guardian views.
        urls = [
            # /admin/products/<product_id>/permissions/
            reverse("admin:product_portfolio_product_permissions",
                    args=[self.p1.pk]),
            # /admin/products/<product_id>/permissions/user-manage/<user_id>/
            reverse(
                "admin:product_portfolio_product_permissions_manage_user",
                args=[self.p1.pk, self.super_user.pk],
            ),
            # /admin/producs/<product_id>/permissions/group-manage/<group_id>/
            reverse(
                "admin:product_portfolio_product_permissions_manage_group",
                args=[self.p1.pk, self.group1.pk],
            ),
        ]

        self.client.login(username=self.super_user.username, password="secret")
        for url in urls:
            self.assertEqual(200, self.client.get(url).status_code)

        self.client.login(username=self.admin_user.username, password="secret")
        for url in urls:
            self.assertEqual(404, self.client.get(url).status_code)

        assign_perm("change_product", self.admin_user, self.p1)
        add_perm(self.admin_user, "change_product")
        for url in urls:
            self.assertEqual(404, self.client.get(url).status_code)

        self.p1.created_by = self.admin_user
        self.p1.save()
        for url in urls:
            self.assertEqual(200, self.client.get(url).status_code)

    def test_product_guardian_admin_obj_perms_user_select_form_scoping(self):
        url = reverse(
            "admin:product_portfolio_product_permissions", args=[self.p1.pk])
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(url)
        user_form = response.context["user_form"]
        self.assertEqual("UserManageForm", user_form.__class__.__name__)
        user_qs = user_form.fields["user"].queryset
        self.assertIn(self.super_user, user_qs)
        self.assertIn(self.admin_user, user_qs)
        self.assertNotIn(self.alt_super_user, user_qs)

    def test_product_guardian_admin_reporting_query_list_filter(self):
        product_ct = ContentType.objects.get_for_model(Product)
        query1 = Query.objects.create(
            dataspace=self.dataspace, name="Q", content_type=product_ct, operator="and"
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query1,
            field_name="id",
            lookup="exact",
            value=self.p2.id,
        )

        self.client.login(username=self.admin_user.username, password="secret")
        add_perm(self.admin_user, "change_product")
        assign_perm("change_product", self.admin_user, self.p1)
        response = self.client.get(self.p_changelist_url)
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(self.p1, response.context_data["cl"].queryset)
        self.assertNotIn(self.p2, response.context_data["cl"].queryset)

        params = "?reporting_query={}".format(query1.id)
        response = self.client.get(self.p_changelist_url + params)
        self.assertEqual(0, response.context_data["cl"].result_count)

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.p_changelist_url + params)
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(self.p2, response.context_data["cl"].queryset)


class ProductComponentSecuredAdminViewsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="alternate")
        self.super_user = create_superuser("super_user", self.dataspace)
        self.admin_user = create_admin("admin_user", self.dataspace)
        self.alt_super_user = create_superuser(
            "alt_super_user", self.alternate_dataspace)

        self.pc_changelist_url = reverse(
            "admin:product_portfolio_productcomponent_changelist")

        self.p1 = Product.objects.create(
            name="Product1", dataspace=self.dataspace)
        self.p2 = Product.objects.create(
            name="Product2", dataspace=self.dataspace)
        self.alt_p = Product.objects.create(
            name="Alternate", dataspace=self.alternate_dataspace)

        self.c1 = Component.objects.create(dataspace=self.dataspace, name="c1")
        self.c2 = Component.objects.create(dataspace=self.dataspace, name="c2")

        self.p1_c1 = ProductComponent.objects.create(
            product=self.p1, component=self.c1, dataspace=self.dataspace
        )
        self.p2_c2 = ProductComponent.objects.create(
            product=self.p2, component=self.c2, dataspace=self.dataspace
        )

        self.group1 = Group.objects.create(name="Group1")

    def test_productcomponent_mass_update_no_product_field(self):
        # WARNING: Adding a secured field in the MassUpdate form would required
        # to adapt DejacodeMassUpdateForm scoping logic to secured querysets
        self.assertNotIn(
            "product", ProductComponentMassUpdateForm._meta.fields)

    def test_productcomponent_guardian_admin_changelist_secured_queryset(self):
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.pc_changelist_url)
        self.assertEqual(2, response.context_data["cl"].result_count)
        self.assertIn(self.p1_c1, response.context_data["cl"].queryset)
        self.assertIn(self.p2_c2, response.context_data["cl"].queryset)
        self.assertNotIn(self.alt_p, response.context_data["cl"].queryset)

        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.get(self.pc_changelist_url)
        self.assertEqual(403, response.status_code)

        add_perm(self.admin_user, "change_productcomponent")
        response = self.client.get(self.pc_changelist_url)
        self.assertEqual(0, response.context_data["cl"].result_count)
        self.assertEqual([], list(response.context_data["cl"].queryset))

        assign_perm("change_product", self.admin_user, self.p1)
        response = self.client.get(self.pc_changelist_url)
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(self.p1_c1, response.context_data["cl"].queryset)
        self.assertNotIn(self.p2_c2, response.context_data["cl"].queryset)

    def test_productcomponent_admin_reporting_query_list_filter(self):
        productcomponent_ct = ContentType.objects.get_for_model(
            ProductComponent)
        query1 = Query.objects.create(
            dataspace=self.dataspace, name="Q", content_type=productcomponent_ct, operator="and"
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query1,
            field_name="id",
            lookup="exact",
            value=self.p2_c2.id,
        )

        self.client.login(username=self.admin_user.username, password="secret")
        add_perm(self.admin_user, "change_productcomponent")
        assign_perm("change_product", self.admin_user, self.p1)
        response = self.client.get(self.pc_changelist_url)
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(self.p1_c1, response.context_data["cl"].queryset)
        self.assertNotIn(self.p2_c2, response.context_data["cl"].queryset)

        params = "?reporting_query={}".format(query1.id)
        response = self.client.get(self.pc_changelist_url + params)
        self.assertEqual(0, response.context_data["cl"].result_count)

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.pc_changelist_url + params)
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(self.p2_c2, response.context_data["cl"].queryset)

    def test_productcomponent_admin_changelist_product_related_lookup_list_filter(self):
        input_html = """
        <input id="id_product-autocomplete"
               type="text"
               class="ui-autocomplete-input"
               value="{}"
               autocomplete="off"
               readonly="readonly">
        """

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.pc_changelist_url)
        self.assertEqual(2, response.context_data["cl"].result_count)
        self.assertContains(response, input_html.format(""), html=True)

        data = {"product__id__exact": self.p1_c1.product.pk}
        response = self.client.get(self.pc_changelist_url, data)
        self.assertEqual(1, response.context_data["cl"].result_count)
        self.assertIn(self.p1_c1, response.context_data["cl"].queryset)
        self.assertNotIn(self.p2_c2, response.context_data["cl"].queryset)
        self.assertContains(response, input_html.format(
            self.p1_c1.product.name), html=True)

        add_perm(self.admin_user, "change_productcomponent")
        self.client.login(username=self.admin_user.username, password="secret")
        response = self.client.get(self.pc_changelist_url)
        self.assertEqual(0, response.context_data["cl"].result_count)

        response = self.client.get(self.pc_changelist_url, data)
        self.assertEqual(302, response.status_code)
        self.assertIn("?e=1", response["Location"])

    def test_productcomponent_admin_security_attributes(self):
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.pc_changelist_url)

        # actions = []
        # actions_to_remove = ['copy_to', 'compare_with']
        expected = [
            ("", "---------"),
            ("delete_selected", "Delete selected product component relationships"),
            ("mass_update", "Mass update"),
        ]
        self.assertEqual(
            expected, response.context_data["action_form"].fields["action"].choices)

        # activity_log = False
        self.assertNotContains(response, "activity_log")

        # email_notification_on = []
        self.assertEqual([], ProductComponentAdmin.email_notification_on)

    def test_productcomponent_admin_changelist_no_dataspace_lookup(self):
        self.client.login(username=self.super_user.username, password="secret")

        response = self.client.get(self.pc_changelist_url)
        self.assertNotContains(response, "<label>Dataspace</label>")

        data = {"dataspace__id__exact": self.alternate_dataspace.id}
        response = self.client.get(self.pc_changelist_url, data)
        self.assertEqual(400, response.status_code)
