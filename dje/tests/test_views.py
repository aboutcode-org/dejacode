#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import apps
from django.conf import settings
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.paginator import Paginator
from django.shortcuts import resolve_url
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from guardian.shortcuts import assign_perm

from dje.models import Dataspace
from dje.models import DataspaceConfiguration
from dje.models import History
from dje.templatetags.dje_tags import smart_page_range
from dje.tests import add_perm
from dje.tests import create
from dje.tests import create_superuser
from dje.tests import create_user

Owner = apps.get_model("organization", "Owner")
Component = apps.get_model("component_catalog", "Component")
Product = apps.get_model("product_portfolio", "Product")


class DJEViewsTestCase(TestCase):
    def setUp(self):
        self.dataspace1 = Dataspace.objects.create(name="Dataspace")
        self.dataspace2 = Dataspace.objects.create(name="Alternate")
        self.user = create_user("user", self.dataspace1)
        self.super_user = create_superuser("test", self.dataspace1)
        self.alternate_user = create_user("alternate", self.dataspace2)
        self.owner1 = Owner.objects.create(name="Organization", dataspace=self.dataspace1)

    def test_admin_login_template(self):
        response = self.client.get(reverse("admin:index"), follow=True)
        self.assertTemplateUsed(response, "registration/login.html")

    def test_login_view_redirect_authenticated_user(self):
        self.client.login(username="test", password="secret")
        response = self.client.get(reverse("login"))
        self.assertRedirects(response, reverse(settings.LOGIN_REDIRECT_URL))

    def test_home_view(self):
        home_url = reverse("home")
        response = self.client.get(home_url)
        self.assertRedirects(response, "{}?next={}".format(reverse("login"), home_url))

        self.client.login(username="test", password="secret")
        response = self.client.get(home_url)
        self.assertFalse(self.dataspace1.home_page_announcements)
        self.assertFalse(self.super_user.request_as_assignee.exists())
        self.assertFalse(self.super_user.request_as_requester.exists())
        self.assertContains(response, "Welcome to DejaCode!")
        self.assertContains(response, "Documentation:")

        self.dataspace1.home_page_announcements = "Custom announcements"
        self.dataspace1.save()
        response = self.client.get(home_url)
        self.assertNotContains(response, "Welcome to DejaCode")
        self.assertContains(response, "Custom announcements")

        Request = apps.get_model("workflow", "Request")
        RequestTemplate = apps.get_model("workflow", "RequestTemplate")
        component_ct = ContentType.objects.get(app_label="component_catalog", model="component")

        request_template1 = RequestTemplate.objects.create(
            name="T1", dataspace=self.dataspace1, content_type=component_ct
        )
        Request.objects.create(
            title="Title1",
            request_template=request_template1,
            requester=self.super_user,
            dataspace=self.dataspace1,
            content_type=component_ct,
        )
        self.assertTrue(self.super_user.request_as_requester.exists())

        response = self.client.get(home_url)
        self.assertContains(response, "Requests assigned to me")
        self.assertContains(response, "Requests I am following")
        request_list_url = reverse("workflow:request_list")
        expected = f'<a href="{request_list_url}?following=yes">View all 1 requests</a>'
        self.assertContains(response, expected, html=True)

    def test_home_view_card_layout(self):
        self.client.login(username=self.user.username, password="secret")
        home_url = reverse("home")

        owner_ct = ContentType.objects.get_for_model(Owner)
        query = create("Query", self.dataspace1, content_type=owner_ct)
        create("Filter", self.dataspace1, query=query, field_name="id", lookup="gte", value=0)

        card1 = create(
            "Card", dataspace=self.dataspace1, title="Card1", query=query, number_of_results=1
        )
        layout = create("CardLayout", self.dataspace1)
        create("LayoutAssignedCard", self.dataspace1, layout=layout, card=card1)

        self.user.homepage_layout = layout
        self.user.save()

        response = self.client.get(home_url)
        self.assertContains(
            response, '<div class="h6 card-header fw-bold px-2">Card1</div>', html=True
        )
        self.assertContains(
            response,
            '<li><a href="/owners/Dataspace/Organization/">Organization</a></li>',
            html=True,
        )
        changelist_link = (
            f'<a href="/admin/organization/owner/?reporting_query={query.id}"'
            f' class="card-link smaller">'
            f"  View all the objects in changelist"
            f"</a>"
        )
        self.assertNotContains(response, changelist_link, html=True)

        card1.display_changelist_link = True
        card1.save()
        self.assertFalse(self.user.is_staff)
        response = self.client.get(home_url)
        self.assertNotContains(response, changelist_link, html=True)

        self.user.is_staff = True
        self.user.save()
        response = self.client.get(home_url)
        self.assertContains(response, changelist_link, html=True)

    def test_logout_view(self):
        logout_url = reverse("logout")
        login_url = resolve_url("login")

        # Call the view as non logged in
        response = self.client.post(logout_url, follow=True)
        self.assertRedirects(response, login_url)

        self.assertTrue(self.client.login(username="test", password="secret"))
        response = self.client.post(logout_url, follow=True)
        self.assertRedirects(response, login_url)

    def test_admin_index_dashboard_shortcuts_links(self):
        self.client.login(username="test", password="secret")
        url = reverse("admin:index")

        response = self.client.get(url)
        self.assertContains(response, "Owner import")
        self.assertContains(response, "Component import")
        self.assertContains(response, "Package import")
        self.assertContains(response, "Subcomponent import")

    def _base_test_urn_resolve_view_errors(self, url, error_message):
        # Base test for the URN view
        self.client.login(username="test", password="secret")
        response = self.client.get(url)
        self.assertTemplateUsed(response, "urn_resolve.html")
        self.assertContains(response, error_message)

    def test_urn_resolve_view_wrong_urn_format(self):
        # Wrong format, URN is 4 parts + segments
        url = "/urn/urn:dje:aaa/"
        error_message = "Invalid URN format"
        self._base_test_urn_resolve_view_errors(url, error_message)

    def test_urn_resolve_view_wrong_urn_segments(self):
        # Wrong format, there are only 1 segment for a License, the key
        url = "/urn/urn:dje:license:license1:extra_segment/"
        error_message = "Invalid number of segments in URN"
        self._base_test_urn_resolve_view_errors(url, error_message)

    def test_urn_resolve_view_wrong_urn_prefix(self):
        # Wrong prefix, should always be urn:dje:
        url = "/urn/urn:not_dje:license:license1/"
        error_message = "Invalid URN prefix or namespace"
        self._base_test_urn_resolve_view_errors(url, error_message)

    def test_urn_resolve_view_model_not_supported_by_urn(self):
        # Everything is correct except the Dataspace.name
        url = "/urn/urn:dje:not_supported_model:license1/"
        error_message = "Unsupported URN object"
        self._base_test_urn_resolve_view_errors(url, error_message)

    def test_urn_resolve_view_model_proper_redirect(self):
        url = "/urn/urn:dje:owner:{}/".format(self.owner1.name)
        self.client.login(username="test", password="secret")
        response = self.client.get(url)
        self.assertRedirects(response, self.owner1.details_url)

    def test_urn_resolve_view_object_does_not_exists(self):
        # Everything is correct except the license.key
        url = "/urn/urn:dje:license:license_do_not_exist/"
        error_message = "The requested Object does not exist."
        self._base_test_urn_resolve_view_errors(url, error_message)

    def test_smart_page_range_templatetag(self):
        # Create a paginator on a 150 items list with 10 object per page
        paginator = Paginator(range(1, 150), 10)

        test_input = {
            1: [1, 2, 3, None, 14, 15],
            2: [1, 2, 3, 4, None, 14, 15],
            3: [1, 2, 3, 4, 5, None, 14, 15],
            4: [1, 2, 3, 4, 5, 6, None, 14, 15],
            5: [1, 2, 3, 4, 5, 6, 7, None, 14, 15],
            6: [1, 2, None, 4, 5, 6, 7, 8, None, 14, 15],
            7: [1, 2, None, 5, 6, 7, 8, 9, None, 14, 15],
            8: [1, 2, None, 6, 7, 8, 9, 10, None, 14, 15],
            9: [1, 2, None, 7, 8, 9, 10, 11, None, 14, 15],
            10: [1, 2, None, 8, 9, 10, 11, 12, None, 14, 15],
            11: [1, 2, None, 9, 10, 11, 12, 13, 14, 15],
            12: [1, 2, None, 10, 11, 12, 13, 14, 15],
            13: [1, 2, None, 11, 12, 13, 14, 15],
            14: [1, 2, None, 12, 13, 14, 15],
            15: [1, 2, None, 13, 14, 15],
        }

        for page_num, expected in test_input.items():
            self.assertEqual(expected, smart_page_range(paginator, page_num))

    def test_account_profile_view(self):
        url = reverse("account_profile")
        self.client.login(username="test", password="secret")
        response = self.client.get(url)

        expected = '<input type="text" value="Dataspace" class="form-control"'
        self.assertContains(response, expected)

        expected = '<input type="text" name="username" value="test"'
        self.assertContains(response, expected)

        expected = f'<input type="text" name="email" value="{self.super_user.email}"'
        self.assertContains(response, expected)

        expected = f'id="api_key" value="{self.super_user.auth_token.key}"'
        self.assertContains(response, expected)

        expected = '<input type="text" name="first_name"'
        self.assertContains(response, expected)

        expected = '<input type="checkbox" name="updates_email_notification"'
        with override_settings(ENABLE_SELF_REGISTRATION=True):
            response = self.client.get(url)
        self.assertContains(response, expected)

        with override_settings(ENABLE_SELF_REGISTRATION=False):
            response = self.client.get(url)
        self.assertNotContains(response, expected)

    def test_account_profile_view_homepage_layout_field(self):
        url = reverse("account_profile")
        self.client.login(username="test", password="secret")
        response = self.client.get(url)

        expected1 = "Homepage layout"
        expected2 = 'select name="homepage_layout"'
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        card_layout_1 = create("CardLayout", self.dataspace1)
        card_layout_2 = create("CardLayout", self.dataspace2)
        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, card_layout_1.name)
        self.assertNotContains(response, card_layout_2.name)

    def test_account_profile_view_edit_form(self):
        url = reverse("account_profile")
        self.client.login(username=self.user.username, password="secret")
        data = {
            "first_name": "First",
            "last_name": "Last",
            "data_email_notification": "on",
        }
        response = self.client.post(url, data=data, follow=True)
        self.assertContains(response, "Profile updated.")

        expected = "Profile updated."
        self.assertEqual(expected, list(response.context["messages"])[0].message)

        history = History.objects.get_for_object(self.user).get()
        expected = "Profile updated: first_name, last_name, data_email_notification."
        self.assertEqual(expected, history.change_message)

    def test_account_profile_view_regenerate_api_key(self):
        url = reverse("account_profile")
        self.client.login(username=self.user.username, password="secret")

        initial_key = str(self.user.auth_token.key)
        self.assertEqual(40, len(initial_key))

        self.client.post(url, data={"bad": "data"})
        self.user.refresh_from_db()
        new_key = str(self.user.auth_token.key)
        self.assertEqual(40, len(new_key))
        self.assertEqual(initial_key, new_key)

        response = self.client.post(url, data={"regenerate-api-key": "yes"}, follow=True)
        self.user.refresh_from_db()
        new_key = str(self.user.auth_token.key)
        self.assertEqual(40, len(new_key))
        self.assertNotEqual(initial_key, new_key)

        expected = "Your API key was regenerated."
        self.assertEqual(expected, list(response.context["messages"])[0].message)

    @override_settings(REFERENCE_DATASPACE="Dataspace", TEMPLATE_DATASPACE=None)
    def test_clone_dataset_view(self):
        template_dataspace = Dataspace.objects.create(name="Template")
        self.client.login(username=self.super_user.username, password="secret")
        clone_url = reverse("admin:dje_dataspace_clonedataset", args=[self.dataspace2.pk])
        changelist_url = reverse("admin:dje_dataspace_changelist")
        change_url = reverse("admin:dje_dataspace_change", args=[self.dataspace2.pk])

        # TEMPLATE_DATASPACE not defined
        response = self.client.get(clone_url)
        self.assertRedirects(response, changelist_url)
        response = self.client.get(change_url)
        self.assertNotContains(response, "Clone dataset from")

        expected = (
            "Cloning task in progress. An email will be sent to "
            "&quot;user@email.com&quot; on completion."
        )
        with override_settings(TEMPLATE_DATASPACE=template_dataspace):
            response = self.client.get(change_url)
            self.assertContains(response, "Clone dataset from")
            response = self.client.get(clone_url, follow=True)
            self.assertRedirects(response, changelist_url)
            self.assertContains(response, expected)

        self.assertEqual("[DejaCode] Dataspace cloning completed", mail.outbox[0].subject)
        self.assertTrue("Cloning process initiated at" in mail.outbox[0].body)
        self.assertTrue("Data copy completed." in mail.outbox[0].body)

    @override_settings(REFERENCE_DATASPACE="Dataspace")
    def test_global_search_list_view(self):
        self.client.login(username=self.user.username, password="secret")
        global_search_url = reverse("global_search")

        response = self.client.get(global_search_url)
        self.assertEqual(200, response.status_code)
        response = self.client.get(global_search_url, data={"q": "apache"})
        self.assertEqual(200, response.status_code)
        self.assertContains(response, f"{self.user.username}&nbsp;(Dataspa…)")

        self.assertContains(response, 'href="#components" data-scroll-to="#components_section"')
        self.assertContains(response, 'href="#packages" data-scroll-to="#packages_section"')
        self.assertContains(response, 'href="#licenses" data-scroll-to="#licenses_section"')
        self.assertContains(response, 'href="#owners" data-scroll-to="#owners_section"')
        self.assertNotContains(
            response, 'href="#reference_components" data-scroll-to="#reference_components_section"'
        )
        self.assertNotContains(
            response, 'href="#reference_packages" data-scroll-to="#reference_packages_section"'
        )
        self.assertNotContains(
            response, 'href="#reference_licenses" data-scroll-to="#reference_licenses_section"'
        )
        self.assertNotContains(
            response, 'href="#reference_owners" data-scroll-to="#reference_owners_section"'
        )

        self.client.login(username=self.alternate_user.username, password="secret")
        response = self.client.get(global_search_url)
        self.assertEqual(200, response.status_code)
        response = self.client.get(global_search_url, data={"q": "apache"})
        self.assertEqual(200, response.status_code)
        self.assertContains(response, f"{self.alternate_user.username}&nbsp;(Alterna…)")

        self.assertContains(response, 'href="#components" data-scroll-to="#components_section"')
        self.assertContains(response, 'href="#packages" data-scroll-to="#packages_section"')
        self.assertContains(response, 'href="#licenses" data-scroll-to="#licenses_section"')
        self.assertContains(response, 'href="#owners" data-scroll-to="#owners_section"')
        self.assertContains(
            response, 'href="#reference_components" data-scroll-to="#reference_components_section"'
        )
        self.assertContains(
            response, 'href="#reference_packages" data-scroll-to="#reference_packages_section"'
        )
        self.assertContains(
            response, 'href="#reference_licenses" data-scroll-to="#reference_licenses_section"'
        )
        self.assertContains(
            response, 'href="#reference_owners" data-scroll-to="#reference_owners_section"'
        )

    @override_settings(REFERENCE_DATASPACE="Dataspace")
    def test_global_search_list_view_product_availability(self):
        self.client.login(username=self.user.username, password="secret")
        global_search_url = reverse("global_search")
        product1 = Product.objects.create(name="Product1", dataspace=self.dataspace1)

        self.assertFalse(self.user.has_perm("product_portfolio.view_product"))
        expected1 = "products_section"
        expected2 = 'href="#products"'
        data = {"q": "product"}

        response = self.client.get(global_search_url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertFalse(response.context.get("include_products"))
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertIsNone(response.context.get("product_results"))

        self.user = add_perm(self.user, "view_product")
        response = self.client.get(global_search_url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.context.get("include_products"))
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertEqual(0, len(response.context.get("product_results").object_list))

        assign_perm("view_product", self.user, product1)
        self.user = add_perm(self.user, "view_product")
        response = self.client.get(global_search_url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.context.get("include_products"))
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertIn(product1, response.context.get("product_results").object_list)

        self.alternate_user = add_perm(self.alternate_user, "view_product")
        self.client.login(username=self.alternate_user.username, password="secret")
        response = self.client.get(global_search_url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.context.get("include_products"))
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertEqual(0, len(response.context.get("product_results").object_list))

    def test_tab_set_mixin_get_tabsets(self):
        from component_catalog.views import ComponentDetailsView

        component1 = Component.objects.create(
            name="c1", owner=self.owner1, notice_text="NOTICE", dataspace=self.dataspace1
        )

        tabset_view = ComponentDetailsView()
        tabset_view.model = Component
        tabset_view.object = component1
        tabset_view.request = lambda: None
        tabset_view.request.user = self.user
        self.assertEqual(0, self.user.groups.count())

        expected_tabs = ["Essentials", "Notice", "Owner", "History"]

        configuration = DataspaceConfiguration.objects.create(
            dataspace=self.dataspace1, tab_permissions=[]
        )
        self.assertEqual(expected_tabs, list(tabset_view.get_tabsets().keys()))

        configuration.tab_permissions = {}
        configuration.save()
        self.assertEqual(expected_tabs, list(tabset_view.get_tabsets().keys()))

        configuration.tab_permissions = ""
        configuration.save()
        self.assertEqual(expected_tabs, list(tabset_view.get_tabsets().keys()))

        self.user.groups.add(Group.objects.create(name="Group1"))
        configuration.tab_permissions = {"Group1": {"component": ["notice"]}}
        configuration.save()
        self.assertEqual(["Notice"], list(tabset_view.get_tabsets().keys()))

        self.user.groups.add(Group.objects.create(name="Group2"))
        configuration.tab_permissions = {
            "Group1": {"component": ["notice"]},
            "Group2": {"component": ["owner"]},
        }
        configuration.save()
        self.assertEqual(
            sorted(["Owner", "Notice"]), sorted(list(tabset_view.get_tabsets().keys()))
        )

    def test_manage_tab_permissions_view(self):
        url = reverse("admin:dje_dataspace_tab_permissions", args=[self.dataspace1.pk])
        data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "2",
            "form-0-package": ["license", "components"],
            "form-0-group_name": "Legal",
            "form-1-group_name": "Engineering",
        }
        self.assertEqual(302, self.client.post(url, data).status_code)

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.post(url, data)
        self.assertEqual("Tab permissions updated.", list(response.context["messages"])[0].message)
        expected = {"Legal": {"package": ["license", "components"]}}
        self.assertEqual(expected, self.dataspace1.configuration.tab_permissions)

        history = History.objects.get(
            content_type_id=get_content_type_for_model(self.dataspace1).pk,
            object_id=self.dataspace1.pk,
        )
        expected = "Changed tab permissions configuration."
        self.assertEqual(expected, history.change_message)

    def test_manage_copy_defaults_view(self):
        url = reverse("admin:dje_dataspace_copy_defaults", args=[self.dataspace1.pk])

        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-0-app_name": "DejaCode",
            "form-0-external source": "homepage_url",
        }
        self.assertEqual(302, self.client.post(url, data).status_code)

        self.assertFalse(self.dataspace1.has_configuration)
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(url)

        # See COPY_DEFAULT_EXCLUDE
        expected_default = [
            '<input type="checkbox" name="form-2-license" value="guidance" class="inline"'
            ' id="id_form-2-license_6" checked />',
            '<input type="checkbox" name="form-2-license" value="guidance_url" class="inline"'
            ' id="id_form-2-license_7" checked />',
            '<input type="checkbox" name="form-2-license" value="usage_policy" class="inline"'
            ' id="id_form-2-license_26" checked />',
            '<input type="checkbox" name="form-3-component" value="usage_policy" class="inline"'
            ' id="id_form-3-component_46" checked />',
            '<input type="checkbox" name="form-3-component" value="guidance" class="inline"'
            ' id="id_form-3-component_12" checked />',
            '<input type="checkbox" name="form-3-subcomponent relationship" value="usage_policy"'
            ' class="inline" id="id_form-3-subcomponent relationship_8" checked />',
            '<input type="checkbox" name="form-3-subcomponent relationship"'
            ' value="extra_attribution_text" class="inline"'
            ' id="id_form-3-subcomponent relationship_0" checked />',
        ]

        for expected in expected_default:
            self.assertContains(response, expected, html=True)

        response = self.client.post(url, data)
        self.assertEqual("Copy defaults updated.", list(response.context["messages"])[0].message)
        self.dataspace1.refresh_from_db()
        expected = {"DejaCode": {"external source": ["homepage_url"]}}
        self.assertEqual(expected, self.dataspace1.configuration.copy_defaults)

        history = History.objects.get(
            content_type_id=get_content_type_for_model(self.dataspace1).pk,
            object_id=self.dataspace1.pk,
        )
        expected = "Changed copy defaults configuration."
        self.assertEqual(expected, history.change_message)

        response = self.client.get(url)
        expected = (
            '<input type="checkbox" name="form-0-external source" value="homepage_url"'
            ' class="inline" id="id_form-0-external source_0" checked />'
        )
        self.assertContains(response, expected, html=True)

        # Let's make sure we do not have the following fields
        self.assertNotContains(response, "uuid")
        self.assertNotContains(response, "created_date")
        self.assertNotContains(response, "created_by")
        self.assertNotContains(response, "last_modified_date")
        self.assertNotContains(response, "last_modified_by")
        self.assertNotContains(response, "request_count")

    def test_integrations_status_view(self):
        url = reverse("integrations_status")
        self.client.login(username=self.user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

        self.user.is_staff = True
        self.user.save()
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, '<h5 class="card-header">PurlDB</h5>')
        self.assertContains(response, '<h5 class="card-header">ScanCode.io</h5>')
        self.assertContains(response, '<h5 class="card-header">VulnerableCode</h5>')
