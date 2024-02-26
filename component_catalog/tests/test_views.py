#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import uuid
from os.path import dirname
from os.path import join
from unittest import mock
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.backends.base import SessionBase
from django.http.response import Http404
from django.test import TestCase
from django.test import TransactionTestCase
from django.test.client import RequestFactory
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_str

import requests
from guardian.shortcuts import assign_perm
from notifications.models import Notification

from component_catalog.forms import ComponentAddToProductForm
from component_catalog.forms import ComponentForm
from component_catalog.forms import PackageAddToProductForm
from component_catalog.forms import PackageForm
from component_catalog.models import Component
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import ComponentKeyword
from component_catalog.models import ComponentStatus
from component_catalog.models import ComponentType
from component_catalog.models import Package
from component_catalog.models import Subcomponent
from component_catalog.views import ComponentListView
from component_catalog.views import PackageDetailsView
from component_catalog.views import PackageTabScanView
from dejacode_toolkit.scancodeio import ScanCodeIO
from dejacode_toolkit.scancodeio import get_hash_uid
from dejacode_toolkit.scancodeio import get_webhook_url
from dejacode_toolkit.vulnerablecode import VulnerableCode
from dejacode_toolkit.vulnerablecode import get_plain_purls
from dje.copier import copy_object
from dje.models import Dataspace
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.models import History
from dje.tasks import scancodeio_submit_scan
from dje.tests import add_perm
from dje.tests import add_perms
from dje.tests import create_superuser
from dje.tests import create_user
from license_library.models import License
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseTag
from license_library.models import LicenseTagGroup
from license_library.models import LicenseTagGroupAssignedTag
from organization.models import Owner
from organization.models import Subowner
from policy.models import UsagePolicy
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductItemPurpose
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductRelationStatus
from workflow.models import Request
from workflow.models import RequestTemplate

User = get_user_model()


class ComponentUserViewsTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.nexb_user = User.objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.basic_user = create_user("basic_user", self.nexb_dataspace)
        self.other_dataspace = Dataspace.objects.create(name="Other")
        self.other_user = User.objects.create_superuser(
            "other_user", "other@test.com", "t3st2", self.other_dataspace
        )
        self.owner1 = Owner.objects.create(name="Test Organization", dataspace=self.nexb_dataspace)
        self.owner2 = Owner.objects.create(
            name="Test Organization 2", dataspace=self.nexb_dataspace
        )
        self.type1 = ComponentType.objects.create(
            label="Type1", notes="notes", dataspace=self.nexb_dataspace
        )
        self.license1 = License.objects.create(
            key="license1",
            name="License1",
            short_name="License1",
            dataspace=self.nexb_dataspace,
            owner=self.owner1,
        )
        self.license_tag1 = LicenseTag.objects.create(
            label="Tag 1", text="Text for tag1", dataspace=self.nexb_dataspace
        )
        self.license_assigned_tag1 = LicenseAssignedTag.objects.create(
            license=self.license1,
            license_tag=self.license_tag1,
            value=True,
            dataspace=self.nexb_dataspace,
        )
        self.license2 = License.objects.create(
            key="license2",
            name="License2",
            short_name="License2",
            dataspace=self.nexb_dataspace,
            owner=self.owner1,
        )
        self.component1 = Component.objects.create(
            name="Component1",
            version="0.1",
            homepage_url="http://localhost.com",
            license_expression="{} AND {}".format(self.license1.key, self.license2.key),
            dataspace=self.nexb_dataspace,
        )
        self.component2 = Component.objects.create(
            name="Component2",
            version="0.2",
            homepage_url="http://localhost.com",
            dataspace=self.nexb_dataspace,
        )
        self.component3 = Component.objects.create(
            name="Component3",
            version="0.3",
            homepage_url="http://localhost.com",
            dataspace=self.nexb_dataspace,
        )
        self.component4 = Component.objects.create(
            name="Component4",
            version="0.4",
            homepage_url="http://localhost.com",
            dataspace=self.nexb_dataspace,
        )
        self.component5 = Component.objects.create(
            name="ArchLinux",
            version="2012.11.01",
            homepage_url="http://localhost.com",
            dataspace=self.nexb_dataspace,
        )
        self.component6 = Component.objects.create(
            name="Apache",
            version="2",
            homepage_url="http://localhost.com",
            dataspace=self.nexb_dataspace,
        )
        self.sub_2_1 = Subcomponent.objects.create(
            parent=self.component2, child=self.component1, dataspace=self.nexb_dataspace
        )
        self.sub_5_1 = Subcomponent.objects.create(
            parent=self.component5, child=self.component1, dataspace=self.nexb_dataspace
        )
        self.sub_1_3 = Subcomponent.objects.create(
            parent=self.component1, child=self.component3, dataspace=self.nexb_dataspace
        )
        self.sub_1_6 = Subcomponent.objects.create(
            parent=self.component1, child=self.component6, dataspace=self.nexb_dataspace
        )

    def test_component_catalog_detail_view_content(self):
        self.client.login(username="nexb_user", password="t3st")
        self.component1.is_active = False
        self.component1.save()

        url = self.component1.get_absolute_url()
        response = self.client.get(url)
        # Make sure it's not accessible if not is_active
        self.assertContains(response, "Page not found", status_code=404)

        # Make sure it's accessible if is_active
        self.component1.is_active = True
        self.component1.license_expression = "{} AND {}".format(
            self.license1.key, self.license2.key
        )
        self.component1.save()
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "{}".format(self.component1))

        # Check the relations tabs presence
        self.assertContains(response, 'id="tab_license"')
        self.assertContains(response, 'id="tab_hierarchy"')

        # Legal tab is only displayed if one a the legal field is set
        self.assertNotContains(response, 'id="tab_legal"')
        self.component1.legal_comments = "Comments"
        self.component1.save()
        response = self.client.get(url)
        self.assertContains(response, 'id="tab_legal"')

        # A user in any dataspace can look at reference data
        self.assertTrue(self.component1.dataspace.is_reference)
        self.client.login(username="other_user", password="t3st2")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)

        # Moving the component to a non-reference dataspace
        self.component1.dataspace = Dataspace.objects.create(name="NotReference")
        self.component1.save()
        response = self.client.get(url)
        self.assertContains(response, "Page not found", status_code=404)

    def test_component_catalog_detail_view_reference_data_label(self):
        url = self.component1.get_absolute_url()
        expected = '<span class="badge text-bg-warning reference-data-label"'
        self.assertTrue(self.component1.dataspace.is_reference)

        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(url)
        self.assertContains(response, expected)

        self.client.login(username="other_user", password="t3st2")
        response = self.client.get(url)
        self.assertContains(response, expected)

    def test_component_catalog_detail_view_is_user_dataspace(self):
        from workflow.models import Request
        from workflow.models import RequestTemplate

        request_template = RequestTemplate.objects.create(
            name="T",
            description="D",
            dataspace=self.nexb_user.dataspace,
            is_active=True,
            content_type=ContentType.objects.get_for_model(Component),
        )
        Request.objects.create(
            title="Title",
            request_template=request_template,
            requester=self.nexb_user,
            content_object=self.component1,
            dataspace=self.nexb_dataspace,
        )
        self.component1.refresh_from_db()
        self.assertEqual(1, self.component1.request_count)

        policy_approved = UsagePolicy.objects.create(
            label="Approved",
            icon="icon-ok-circle",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.component1.dataspace,
        )
        self.component1.usage_policy = policy_approved
        self.component1.save()

        url = self.component1.get_absolute_url()
        self.assertTrue(self.component1.dataspace.is_reference)
        self.nexb_dataspace.show_usage_policy_in_user_views = True
        self.nexb_dataspace.save()
        self.other_dataspace.show_usage_policy_in_user_views = True
        self.other_dataspace.save()

        # The following are displayed or not depending on if the user is looking
        # at Reference Data from a non-reference dataspace:
        # * Dataspace field in Essential tab
        expected0 = "{}".format(self.component1.dataspace)
        # * Activity tab
        expected1 = 'data-bs-target="#tab_activity"'
        # * Edit icon link as a superuser
        expected3 = '<i class="far fa-edit"></i>'
        # * Copy to my dataspace link
        expected4 = "Copy to my Dataspace"
        # * Check for Update link
        expected4_update = "Check for Updates"
        # * Hierarchy and Subcomponents tabs Requests links
        expected6 = 'data-bs-target="#tab_hierarchy"'
        expected7 = "text-bg-request"
        # * Usage policy respect the show_usage_policy_in_user_views
        # of the object.dataspace, rather than the user.dataspace
        expected8 = '<i class="icon-ok-circle" style="color: #000000;"></i>'

        self.assertTrue(self.nexb_user.is_superuser)
        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(url)
        self.assertContains(response, expected0, html=True)
        self.assertContains(response, expected1)
        self.assertContains(response, expected3)
        self.assertNotContains(response, expected4)
        self.assertNotContains(response, expected4_update)
        self.assertContains(response, expected6)
        self.assertContains(response, expected7)
        self.assertContains(response, expected8)

        self.nexb_dataspace.show_usage_policy_in_user_views = False
        self.nexb_dataspace.save()
        response = self.client.get(url)
        self.assertNotContains(response, expected8)

        self.assertTrue(self.other_user.is_superuser)
        self.client.login(username="other_user", password="t3st2")
        response = self.client.get(url)
        self.assertContains(response, expected0, html=True)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected3)
        self.assertContains(response, expected4)
        self.assertNotContains(response, expected4_update)
        self.assertContains(response, expected6)
        self.assertFalse(self.nexb_dataspace.show_usage_policy_in_user_views)
        self.assertTrue(self.other_dataspace.show_usage_policy_in_user_views)
        self.assertNotContains(response, expected8)

        copied_object = copy_object(self.component1, self.other_dataspace, self.other_user)
        response = self.client.get(url)
        self.assertNotContains(response, expected4)
        self.assertContains(response, expected4_update)

        response = self.client.get(copied_object.get_absolute_url())
        self.assertNotContains(response, expected4)
        self.assertContains(response, expected4_update)

        self.component1.delete()
        response = self.client.get(copied_object.get_absolute_url())
        self.assertNotContains(response, expected4)
        self.assertNotContains(response, expected4_update)

    def test_component_catalog_detail_view_access_with_slash_in_name(self):
        self.client.login(username="nexb_user", password="t3st")
        self.component1.name = "My/Component"
        self.component1.is_active = True
        self.component1.save()

        url = self.component1.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_component_catalog_detail_view_access_with_space_in_version(self):
        self.client.login(username="nexb_user", password="t3st")
        self.component1.name = "Component name with space"
        self.component1.version = "v 2015-11 beta"
        self.component1.is_active = True
        self.component1.save()
        url = self.component1.get_absolute_url()
        self.assertIn("/Component+name+with+space/v+2015-11+beta/", url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_component_catalog_detail_view_license_tab(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.component1.get_absolute_url()

        tag_group1 = LicenseTagGroup.objects.create(
            name="Group1", seq=1, dataspace=self.nexb_dataspace
        )
        LicenseTagGroupAssignedTag.objects.create(
            license_tag_group=tag_group1,
            license_tag=self.license_tag1,
            dataspace=self.nexb_dataspace,
        )

        # Some context for this test:
        # License1 is not the default license and is_active
        # License2 is the default license and not is_active
        # Adding Guidance data on License and Component License
        self.license1.is_active = True
        self.license1.guidance = "License1 guidance"
        self.license1.save()
        self.license2.is_active = False
        self.license2.save()

        license1_str = f"{self.license1.short_name} ({self.license1.key})"
        license2_str = f"{self.license2.short_name} ({self.license2.key})"
        response = self.client.get(url)

        self.assertContains(response, 'id="tab_license"')
        # Default but no link as not in LL
        self.assertContains(response, "<td>{}</td>".format(license2_str), html=True)
        # Link to the license as in LL
        self.assertContains(response, self.license1.key)
        # Check the Guidance for License1 is present
        self.assertContains(response, "<td>{}</td>".format(self.license1.guidance), html=True)

        # Check the tag set to True is displayed
        self.assertTrue(self.license_assigned_tag1.value)
        # self.assertContains(response, f'{self.license_tag1.label}</strong>')
        self.assertContains(response, f' data-bs-content="{self.license_tag1.text}"')

        # Check the ordering of the tables respect the license_expression ordering
        self.license1.is_active = False
        self.license1.save()
        response = self.client.get(url)
        self.assertEqual("license1 AND license2", self.component1.license_expression)

        def no_whitespace(s):
            return "".join(force_str(s).split())

        expected = "<td>{}</td><td>{}</td>".format(license1_str, license2_str)
        self.assertIn(no_whitespace(expected), no_whitespace(response.content))

        self.component1.license_expression = "{} AND {}".format(
            self.license2.key, self.license1.key
        )
        self.component1.save()
        response = self.client.get(url)
        expected = "<td>{}</td><td>{}</td>".format(license2_str, license1_str)
        self.assertIn(no_whitespace(expected), no_whitespace(response.content))

    def test_return_to_component_from_license_details(self):
        # Making sure a 'Return to Component' link is available on a License
        # details view when coming from a Component details view
        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(
            self.license1.get_absolute_url(), HTTP_REFERER=self.component1.get_absolute_url()
        )
        self.assertContains(response, "Return to component")

    def test_component_catalog_hierarchy_tab(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.component1.get_absolute_url()

        # Make component2 in CC and component3 not in CC
        self.component2.is_active = True
        self.component2.save()
        self.component3.is_active = False
        self.component3.save()

        response = self.client.get(url)
        self.assertContains(
            response,
            f'<a href="{self.component2.get_absolute_url()}#hierarchy">{self.component2}</a>',
        )
        self.assertNotContains(
            response,
            f'<a href="{self.component3.get_absolute_url()}#hierarchy">{self.component3}</a>',
        )

        self.assertTrue("Hierarchy" in response.context["tabsets"])
        hierarchy_fields = response.context["tabsets"]["Hierarchy"]["fields"]
        parents = hierarchy_fields[0][1]["related_parents"]
        children = hierarchy_fields[0][1]["related_children"]
        # Assert that parents and children are in alphabetical order
        self.assertEqual(["ArchLinux", "Component2"], [x.parent.name for x in parents])
        self.assertEqual(["Apache", "Component3"], [x.child.name for x in children])

        expected1 = f'<div id="component_{self.component1.id}" class="card bg-body-tertiary mb-2">'
        expected2 = f'<div id="component_{self.component2.id}" class="card bg-body-tertiary mb-2">'
        expected3 = f"source: 'component_{self.component1.id}'"
        expected4 = f"target: 'component_{self.component2.id}'"

        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertContains(response, expected4)

        expected = f"""
        <div class="card-body py-1 ps-2 pe-1">
          <ul class="list-inline float-end mb-0"></ul>
          <strong>
            <span data-bs-toggle="tooltip" title="Component">
              <i class="fa fa-puzzle-piece cursor-help"></i>
            </span>
            {self.component1}
          </strong>
          <div>
            {self.component1.get_license_expression_linked()}
          </div>
        </div>
        """
        self.assertContains(response, expected, html=True)

        product1 = Product.objects.create(
            name="Product1", version="1.0", dataspace=self.nexb_dataspace
        )
        ProductComponent.objects.create(
            product=product1, component=self.component1, dataspace=self.nexb_dataspace
        )
        self.assertEqual(1, product1.productcomponents.count())
        response = self.client.get(url)
        expected = f'<div id="product_{product1.id}" class="card bg-body-tertiary mb-2">'
        self.assertContains(response, expected)
        self.assertContains(response, f"target: 'product_{product1.id}'")

    def test_component_catalog_history_tab(self):
        url = self.component1.get_absolute_url()

        History.log_addition(self.nexb_user, self.component1)
        History.log_change(self.nexb_user, self.component1, "Changed name.")
        History.log_change(self.basic_user, self.component1, "Changed version.")

        with override_settings(ANONYMOUS_USERS_DATASPACE=self.nexb_dataspace.name):
            response = self.client.get(url)
        self.assertFalse("History" in response.context["tabsets"])

        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(url)
        self.assertTrue("History" in response.context["tabsets"])
        history_fields = response.context["tabsets"]["History"]["fields"]
        expected = [
            "Created date",
            "Created by",
            "Last modified date",
            "Last modified by",
            "Changes",
        ]
        self.assertEqual(expected, [field[0] for field in history_fields])

        self.assertContains(response, "now by <strong>basic_user</strong>")
        self.assertContains(response, "Changed version.")
        self.assertContains(response, "now by <strong>nexb_user</strong>")
        self.assertContains(response, "Changed name.")

    def test_component_catalog_productcomponent_secured_hierarchy_and_product_usage(self):
        component1 = Component.objects.create(name="c1", dataspace=self.nexb_dataspace)
        product1 = Product.objects.create(name="p1", dataspace=self.nexb_dataspace)
        ProductComponent.objects.create(
            product=product1, component=component1, dataspace=self.nexb_dataspace
        )
        url = component1.get_absolute_url()

        # Product data in Component views are not available for AnonymousUser for security reason
        with override_settings(ANONYMOUS_USERS_DATASPACE=self.nexb_dataspace.name):
            response = self.client.get(url)
            tabsets = response.context["tabsets"]
            self.assertIn("Essentials", tabsets)
            self.assertNotIn("Hierarchy", tabsets)
            self.assertNotIn("Product usage", tabsets)
            self.assertNotContains(response, product1.get_absolute_url())
            self.assertNotContains(response, product1.name)

        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(url)
        tabsets = response.context["tabsets"]
        self.assertIn("Hierarchy", tabsets)
        self.assertIn("Product usage", tabsets)
        self.assertContains(response, product1.get_absolute_url())
        self.assertContains(response, product1.name)

        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(url)
        tabsets = response.context["tabsets"]
        self.assertNotIn("Hierarchy", tabsets)
        self.assertNotIn("Product usage", tabsets)
        self.assertNotContains(response, product1.get_absolute_url())
        self.assertNotContains(response, product1.name)

        assign_perm("view_product", self.basic_user, product1)
        response = self.client.get(url)
        tabsets = response.context["tabsets"]
        self.assertIn("Hierarchy", tabsets)
        self.assertIn("Product usage", tabsets)
        self.assertContains(response, product1.get_absolute_url())
        self.assertContains(response, product1.name)

    def test_component_catalog_productpackage_secured_hierarchy_and_product_usage(self):
        package1 = Package.objects.create(filename="package1", dataspace=self.nexb_dataspace)
        product1 = Product.objects.create(name="product1", dataspace=self.nexb_dataspace)
        ProductPackage.objects.create(
            product=product1, package=package1, dataspace=self.nexb_dataspace
        )
        url = package1.get_absolute_url()

        # Product data in Package views are not available for AnonymousUser for security reason
        with override_settings(ANONYMOUS_USERS_DATASPACE=self.nexb_dataspace.name):
            response = self.client.get(url)
            tabsets = response.context["tabsets"]
            self.assertIn("Essentials", tabsets)
            self.assertNotIn("Product usage", tabsets)
            self.assertNotContains(response, product1.get_absolute_url())
            self.assertNotContains(response, product1.name)

        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(url)
        tabsets = response.context["tabsets"]
        self.assertIn("Product usage", tabsets)
        self.assertContains(response, product1.get_absolute_url())
        self.assertContains(response, product1.name)

        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(url)
        tabsets = response.context["tabsets"]
        self.assertNotIn("Product usage", tabsets)
        self.assertNotContains(response, product1.get_absolute_url())
        self.assertNotContains(response, product1.name)

        assign_perm("view_product", self.basic_user, product1)
        response = self.client.get(url)
        tabsets = response.context["tabsets"]
        self.assertIn("Product usage", tabsets)
        self.assertContains(response, product1.get_absolute_url())
        self.assertContains(response, product1.name)

    def test_component_catalog_detail_view_owner_tab_hierarchy_availability(self):
        # The js code related to the Owner hierarchy should is only embedded
        # is the Owner has relatives
        self.component1.owner = self.owner1
        self.component1.save()
        self.assertFalse(self.owner1.has_parent_or_child())
        self.client.login(username="nexb_user", password="t3st")
        url = self.component1.get_absolute_url()
        response = self.client.get(url)
        self.assertNotContains(response, "jsPlumbOwnerHierarchy")
        self.assertNotContains(response, "Selected Owner")
        self.assertNotContains(response, "Child Owners")

        child_owner = Owner.objects.create(name="ChildOwner", dataspace=self.nexb_dataspace)
        Subowner.objects.create(
            parent=self.owner1, child=child_owner, dataspace=self.nexb_dataspace
        )

        response = self.client.get(url)
        self.assertContains(response, "jsPlumb")
        self.assertContains(response, "Selected Owner")
        self.assertContains(response, "Child Owners")
        self.assertContains(response, child_owner.name)

        self.assertContains(
            response,
            '<div id="owner_{}" class="card bg-body-tertiary mb-2">'.format(self.owner1.id),
        )
        self.assertContains(
            response,
            '<div id="owner_{}" class="card bg-body-tertiary mb-2">'.format(child_owner.id),
        )
        self.assertContains(
            response, f"{{source: 'owner_{child_owner.id}', target: 'owner_{self.owner1.id}'}}"
        )

    def test_component_catalog_list_view_sort_keep_active_filters(self):
        self.client.login(username="nexb_user", password="t3st")

        url = reverse("component_catalog:component_list")
        data = {
            "q": "a",
            "licenses": self.license1.key,
        }
        response = self.client.get(url, data=data)

        # Sort filter
        self.assertContains(
            response,
            '<a href="?q=a&amp;licenses=license1&sort=name" class="sort" aria-label="Sort">',
        )
        # Sort in the headers
        self.assertContains(
            response,
            '<a href="?q=a&amp;licenses=license1&sort=name" class="sort" aria-label="Sort">',
        )
        self.assertContains(
            response,
            '<a href="?q=a&amp;licenses=license1&sort=primary_language" class="sort" '
            'aria-label="Sort">',
        )

        data["sort"] = "name"
        response = self.client.get(url, data=data)
        self.assertContains(
            response,
            '<a href="?q=a&amp;licenses=license1&sort=-name" class="sort active" '
            'aria-label="Sort">',
        )
        self.assertContains(
            response,
            '<a href="?q=a&amp;licenses=license1&sort=primary_language" class="sort" '
            'aria-label="Sort">',
        )

        data["sort"] = "-name"
        response = self.client.get(url, data=data)
        self.assertContains(
            response,
            '<a href="?q=a&amp;licenses=license1&sort=name" class="sort active" aria-label="Sort">',
        )
        self.assertContains(
            response,
            '<a href="?q=a&amp;licenses=license1&sort=primary_language" class="sort" '
            'aria-label="Sort">',
        )

    def test_component_catalog_list_view_filters_breadcrumbs(self):
        self.client.login(username="nexb_user", password="t3st")

        url = reverse("component_catalog:component_list")
        data = {
            "q": "a",
            "sort": "name",
            "licenses": [self.license1.key, self.license2.key],
            "not_a_valid_entry": "not_a_valid_entry",
            "type": "not_a_valid_entry",
        }
        response = self.client.get(url, data=data)

        href1 = (
            "?q=a&sort=name&amp;licenses=license1&amp;licenses=license2"
            "&amp;not_a_valid_entry=not_a_valid_entry"
        )
        href2 = (
            "?q=a&amp;sort=name&amp;not_a_valid_entry=not_a_valid_entry"
            "&amp;type=not_a_valid_entry&amp;licenses=license2"
        )
        href3 = (
            "?q=a&amp;sort=name&amp;not_a_valid_entry=not_a_valid_entry"
            "&amp;type=not_a_valid_entry&amp;licenses=license1"
        )
        href4 = (
            "?sort=name&amp;licenses=license1&amp;licenses=license2"
            "&amp;not_a_valid_entry=not_a_valid_entry&amp;type=not_a_valid_entry"
        )
        href5 = (
            "?q=a&amp;licenses=license1&amp;licenses=license2"
            "&amp;not_a_valid_entry=not_a_valid_entry&amp;type=not_a_valid_entry"
        )

        expected = f"""
        <div class="my-1">
            <a href="{href1}" class="text-decoration-none">
              <span class="badge text-bg-secondary rounded-pill">
                Type: "not_a_valid_entry" <i class="fas fa-times-circle"></i>
                </span>
            </a>
            <a href="{href2}" class="text-decoration-none">
              <span class="badge text-bg-secondary rounded-pill">
                License: "license1" <i class="fas fa-times-circle"></i>
                </span>
            </a>
            <a href="{href3}" class="text-decoration-none">
              <span class="badge text-bg-secondary rounded-pill">
                License: "license2" <i class="fas fa-times-circle"></i>
                </span>
            </a>
            <a href="{href4}" class="text-decoration-none">
              <span class="badge text-bg-secondary rounded-pill">
                Search: "a" <i class="fas fa-times-circle"></i>
                </span>
            </a>
            <a href="{href5}" class="text-decoration-none">
              <span class="badge text-bg-secondary rounded-pill">
                Sort: "name" <i class="fas fa-times-circle"></i>
                </span>
            </a>
        </div>
        """
        self.assertContains(response, expected, html=True)

    def test_component_catalog_list_view_bootstrap_select_filters(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("component_catalog:component_list")
        data = {
            "licenses": self.license1.key,
        }
        response = self.client.get(url, data=data)
        expected = """
        <select name="licenses" id="id_licenses"
         class="bootstrap-select-filter show-tick active"
          data-dropdown-align-right="true"
           data-header="Select all that apply" data-size="11"
            data-style="btn btn-outline-secondary btn-xs"
             data-selected-text-format="static" data-width="100%"
              data-dropup-auto="false" data-tick-icon="icon-ok"
               data-live-search="true" data-live-search-placeholder="Search licenses"
                multiple="multiple">
          <option value="license1" selected>License1 (license1)</option>
          <option value="license2">License2 (license2)</option>
        </select>
        """
        self.assertContains(response, expected, html=True)

    def test_component_catalog_component_list_view_add_to_product(self):
        self.client.login(username=self.basic_user.username, password="secret")
        url = reverse("component_catalog:component_list")

        expected1 = "column-selection"
        expected2 = (
            f'<input name="checkbox-for-selection" value="{self.component1.id}"'
            f' data-object-repr="{self.component1}" type="checkbox" aria-label="Select row">'
        )
        expected3 = 'data-bs-target="#add-to-product-modal"'
        expected4 = 'id="add-to-product-modal"'

        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, expected4)

        add_perm(self.basic_user, "add_productcomponent")
        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, expected4)

        product1 = Product.objects.create(name="Product1", dataspace=self.nexb_dataspace)
        assign_perm("change_product", self.basic_user, product1)
        assign_perm("view_product", self.basic_user, product1)
        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertContains(response, expected4)

        # form_invalid
        data = {
            "product": 999999,
            "ids": 999999,
            "submit": "Add to Product",
        }
        response = self.client.post(url, data)
        self.assertRedirects(response, url)

        data["product"] = product1.id
        data["ids"] = f"{self.component1.id}, {self.component2.id}"
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, f"2 component(s) added to &quot;{product1}&quot;.")
        self.assertEqual(2, product1.components.count())

        product1.refresh_from_db()
        history_entries = History.objects.get_for_object(product1)
        expected_messages = sorted(
            [
                'Added component "Component1 0.1"',
                'Added component "Component2 0.2"',
            ]
        )
        self.assertEqual(
            expected_messages, sorted([entry.change_message for entry in history_entries])
        )
        self.assertEqual(self.basic_user, product1.last_modified_by)

    def test_component_catalog_details_external_reference_tab(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.component1.get_absolute_url()

        response = self.client.get(url)
        expected = 'id="tab_external-references"'
        self.assertNotContains(response, expected)

        source1 = ExternalSource.objects.create(
            label="GitHub",
            dataspace=self.nexb_dataspace,
        )

        ext_ref1 = ExternalReference.objects.create_for_content_object(
            content_object=self.component1,
            external_source=source1,
            external_id="dejacode external id",
        )

        response = self.client.get(url)
        self.assertContains(response, expected)
        self.assertContains(response, ext_ref1.external_id)
        self.assertContains(response, source1.label)

    def test_component_catalog_detail_view_admin_edit_component_admin_link(self):
        url = self.component1.get_absolute_url()
        perm = "component_catalog.change_component"

        expected1 = "Edit Component"
        expected2 = self.component1.get_admin_url()

        self.nexb_user.is_superuser = False
        self.nexb_user.save()
        self.assertTrue(self.nexb_user.is_staff)
        self.assertEqual(self.nexb_user.dataspace, self.component1.dataspace)
        self.assertFalse(self.nexb_user.has_perm(perm))

        self.client.login(username=self.nexb_user.username, password="t3st")
        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        self.nexb_user = add_perm(self.nexb_user, "change_component")
        self.assertTrue(self.nexb_user.has_perm(perm))
        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

        self.client.login(username=self.other_user.username, password="t3st2")
        response = self.client.get(url)
        self.assertTrue(self.other_user.is_superuser)
        self.assertTrue(self.other_user.has_perm(perm))
        self.assertNotEqual(self.other_user.dataspace, self.component1.dataspace)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

    def test_component_catalog_detail_view_admin_manage_subcomponent_relationships_link(self):
        url = self.component1.get_absolute_url()
        perm = "component_catalog.change_subcomponent"

        expected1 = "Manage Subcomponent relationships"
        expected2 = "{}?parent__id__exact={}".format(
            reverse("admin:component_catalog_subcomponent_changelist"), self.component1.pk
        )

        self.nexb_user.is_superuser = False
        self.nexb_user.save()
        self.assertTrue(self.nexb_user.is_staff)
        self.assertEqual(self.nexb_user.dataspace, self.component1.dataspace)
        self.assertFalse(self.nexb_user.has_perm(perm))

        self.client.login(username=self.nexb_user.username, password="t3st")
        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        self.nexb_user = add_perm(self.nexb_user, "change_subcomponent")
        self.assertTrue(self.nexb_user.has_perm(perm))
        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

        self.client.login(username=self.other_user.username, password="t3st2")
        response = self.client.get(url)
        self.assertTrue(self.other_user.is_superuser)
        self.assertTrue(self.other_user.has_perm(perm))
        self.assertNotEqual(self.other_user.dataspace, self.component1.dataspace)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

    def test_component_catalog_detail_view_admin_manage_packages_link(self):
        url = self.component1.get_absolute_url()
        perm = "component_catalog.change_package"

        expected1 = "Manage Packages"
        expected2 = "{}?component__id__exact={}".format(
            reverse("admin:component_catalog_package_changelist"), self.component1.pk
        )

        self.nexb_user.is_superuser = False
        self.nexb_user.save()
        self.assertTrue(self.nexb_user.is_staff)
        self.assertEqual(self.nexb_user.dataspace, self.component1.dataspace)
        self.assertFalse(self.nexb_user.has_perm(perm))

        self.client.login(username=self.nexb_user.username, password="t3st")
        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        self.nexb_user = add_perm(self.nexb_user, "change_package")
        self.assertTrue(self.nexb_user.has_perm(perm))
        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

        self.client.login(username=self.other_user.username, password="t3st2")
        response = self.client.get(url)
        self.assertTrue(self.other_user.is_superuser)
        self.assertTrue(self.other_user.has_perm(perm))
        self.assertNotEqual(self.other_user.dataspace, self.component1.dataspace)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

    def test_component_catalog_details_view_num_queries(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.component1.get_absolute_url()

        package1 = Package.objects.create(filename="package1", dataspace=self.nexb_dataspace)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.nexb_dataspace
        )
        package2 = Package.objects.create(filename="package2", dataspace=self.nexb_dataspace)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package2, dataspace=self.nexb_dataspace
        )
        self.assertEqual(2, self.component1.packages.count())

        self.assertEqual(2, self.component1.licenses.count())
        self.assertEqual(2, self.component1.related_parents.count())
        self.assertEqual(2, self.component1.related_children.count())

        History.log_change(self.nexb_user, self.component1, "Changed name.")
        History.log_change(self.basic_user, self.component1, "Changed version.")
        History.log_change(self.nexb_user, self.component1, "Changed notes.")

        with self.assertNumQueries(31):
            self.client.get(url)

    def test_component_catalog_details_view_package_tab_fields_visibility(self):
        self.client.login(username="nexb_user", password="t3st")
        url = self.component1.get_absolute_url()

        package1 = Package.objects.create(filename="package1", dataspace=self.nexb_dataspace)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.nexb_dataspace
        )

        title = (
            "The date that the package file was created, or when it was posted to"
            " its original download source."
        )
        expected = f"""
        <span class="help_text" data-bs-placement="right" data-bs-toggle="tooltip"
              data-bs-title="{title}">
          Release date
        </span>
        """

        response = self.client.get(url)
        self.assertContains(response, 'id="tab_packages"')
        self.assertContains(response, "Filename")
        self.assertNotContains(response, expected, html=True)

        package1.release_date = timezone.now()
        package1.save()
        response = self.client.get(url)
        self.assertContains(response, expected, html=True)

    def test_component_catalog_details_view_hide_empty_fields(self):
        self.client.login(username="nexb_user", password="t3st")
        details_url = self.component1.get_absolute_url()
        expected = '<pre class="pre-bg-body-tertiary mb-1 field-description">&nbsp;</pre>'

        self.assertFalse(self.nexb_dataspace.hide_empty_fields_in_component_details_view)
        response = self.client.get(details_url)
        self.assertContains(response, expected, html=True)

        self.nexb_dataspace.hide_empty_fields_in_component_details_view = True
        self.nexb_dataspace.save()
        response = self.client.get(details_url)
        self.assertNotContains(response, expected, html=True)

    def test_component_catalog_details_view_acceptable_linkages_in_policy_tab(self):
        self.client.login(username="nexb_user", password="t3st")
        details_url = self.component1.get_absolute_url()
        self.component1.acceptable_linkages = ["linkage1", "linkage2"]
        self.component1.save()

        response = self.client.get(details_url)
        expected = (
            '<pre class="pre-bg-body-tertiary mb-1 field-acceptable-linkages">'
            "  linkage1 linkage2"
            "</pre>"
        )
        self.assertContains(response, expected, html=True)

    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.get_vulnerabilities_by_cpe")
    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.is_configured")
    def test_component_details_view_tab_vulnerabilities(
        self, mock_is_configured, mock_get_vulnerabilities_by_cpe
    ):
        mock_is_configured.return_value = True

        self.nexb_dataspace.enable_vulnerablecodedb_access = True
        self.nexb_dataspace.save()

        self.component1.cpe = "cpe:2.3:a:djangoproject:django:0.95:*:*:*:*:*:*:*"
        self.component1.save()

        mock_get_vulnerabilities_by_cpe.return_value = [
            {
                "vulnerability_id": "VULCOID-5U6",
                "summary": "django.contrib.sessions in Django before 1.2.7",
                "references": [
                    {
                        "reference_url": "https://nvd.nist.gov/vuln/detail/CVE-2011-4136",
                        "reference_id": "CVE-2011-4136",
                    }
                ],
            }
        ]

        self.client.login(username="nexb_user", password="t3st")
        response = self.client.get(self.component1.details_url)

        expected = (
            '<button class="nav-link" id="tab_vulnerabilities-tab" data-bs-toggle="tab"'
            ' data-bs-target="#tab_vulnerabilities" type="button" role="tab"'
            ' aria-controls="tab_vulnerabilities" aria-selected="false">'
        )
        self.assertContains(response, expected)
        self.assertContains(response, 'id="tab_vulnerabilities"')
        expected = (
            '<a href="https://nvd.nist.gov/vuln/detail/CVE-2011-4136" target="_blank">'
            "CVE-2011-4136</a>"
        )
        self.assertContains(response, expected)

    def test_component_catalog_component_create_ajax_view(self):
        component_create_ajax_url = reverse("component_catalog:component_add_ajax")

        response = self.client.get(component_create_ajax_url)
        self.assertEqual(405, response.status_code)

        response = self.client.post(component_create_ajax_url)
        self.assertRedirects(response, f"/login/?next={quote(component_create_ajax_url)}")

        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.post(component_create_ajax_url)
        self.assertEqual(403, response.status_code)

        add_perms(self.basic_user, ["add_component"])
        response = self.client.post(component_create_ajax_url)
        self.assertEqual(200, response.status_code)

        data = {
            "name": "New Component",
            "version": "1.0",
        }
        response = self.client.post(component_create_ajax_url, data)
        self.assertEqual(200, response.status_code)
        created_component = Component.objects.get(**data)
        expected = {
            "serialized_data": {
                "id": created_component.pk,
                "object_repr": "New Component 1.0",
                "license_expression": "",
            }
        }
        self.assertEqual(expected, response.json())

        response = self.client.post(component_create_ajax_url, data)
        self.assertEqual(200, response.status_code)
        expected = "<li>Component with this Dataspace, Name and Version already exists.</li>"
        self.assertContains(response, expected, html=True)


class PackageUserViewsTestCase(TestCase):
    testfiles_location = join(dirname(__file__), "testfiles")

    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Dataspace")
        self.basic_user = create_user("basic_user", self.dataspace)
        self.super_user = create_superuser("super_user", self.dataspace)

        self.owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        self.license1 = License.objects.create(
            key="l1", name="L1", short_name="L1", dataspace=self.dataspace, owner=self.owner1
        )
        self.license2 = License.objects.create(
            key="l2", name="L2", short_name="L2", dataspace=self.dataspace, owner=self.owner1
        )

        self.component1 = Component.objects.create(name="C1", dataspace=self.dataspace)
        self.component2 = Component.objects.create(name="C2", dataspace=self.dataspace)

        self.package1 = Package.objects.create(
            filename="package1", download_url="http://url.com/package1", dataspace=self.dataspace
        )
        self.package1.license_expression = "{} AND {}".format(self.license1.key, self.license2.key)
        self.package1.save()
        self.package1_tab_scan_url = self.package1.get_url("tab_scan")

        ComponentAssignedPackage.objects.create(
            component=self.component1, package=self.package1, dataspace=self.dataspace
        )
        ComponentAssignedPackage.objects.create(
            component=self.component2, package=self.package1, dataspace=self.dataspace
        )

        self.package2 = Package.objects.create(filename="package2", dataspace=self.dataspace)

    def test_package_list_view_num_queries(self):
        self.client.login(username=self.super_user.username, password="secret")
        with self.assertNumQueries(17):
            self.client.get(reverse("component_catalog:package_list"))

    def test_package_views_urls(self):
        p1 = Package(
            filename="filename.zip",
            uuid="dd0afd00-89bd-46d6-b1f0-57b553c44d32",
            dataspace=self.dataspace,
        )
        p2 = Package(
            filename="",
            type="pypi",
            name="django",
            version="1.0",
            subpath="sub/path/",
            uuid="0c895367-e565-426b-9a63-589432fffa8c",
            dataspace=self.dataspace,
        )

        args = [p1.dataspace.name, p1.uuid]
        url = reverse("component_catalog:package_details", args=args)
        expected = "/packages/Dataspace/dd0afd00-89bd-46d6-b1f0-57b553c44d32/"
        self.assertEqual(expected, url)

        args = [p1.dataspace.name, p1.identifier, p1.uuid]
        url = reverse("component_catalog:package_details", args=args)
        expected = "/packages/Dataspace/filename.zip/dd0afd00-89bd-46d6-b1f0-57b553c44d32/"
        self.assertEqual(expected, url)

        args = [p2.dataspace.name, p2.uuid]
        url = reverse("component_catalog:package_details", args=args)
        expected = "/packages/Dataspace/0c895367-e565-426b-9a63-589432fffa8c/"
        self.assertEqual(expected, url)

        args = [p2.dataspace.name, p2.identifier, p2.uuid]
        url = reverse("component_catalog:package_details", args=args)
        expected = "/packages/Dataspace/pypi/django@1.0/0c895367-e565-426b-9a63-589432fffa8c/"
        self.assertEqual(expected, url)

    def test_package_list_view_content(self):
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(reverse("component_catalog:package_list"))
        self.assertContains(response, self.package1.get_absolute_link())
        self.assertContains(response, self.package2.get_absolute_link())
        self.assertContains(response, self.component1)
        self.assertContains(response, self.component2)

    def test_package_list_view_download_column(self):
        self.client.login(username=self.super_user.username, password="secret")

        self.package1.filename = "p1.zip"
        self.package1.download_url = "https://download.url/p1.zip"
        self.package1.save()

        self.package2.filename = ""
        self.package2.set_package_url("pkg:pypi/p2@1.0")
        self.package2.download_url = "https://download.url/p2.zip"
        self.package2.save()

        response = self.client.get(reverse("component_catalog:package_list"))

        expected = f"""
        <td title="{self.package1.download_url}">
          <a href="{self.package1.download_url}">
              {self.package1.filename}
          </a>
        </td>
        """
        self.assertContains(response, expected, html=True)

        expected = f"""
        <td title="{self.package2.download_url}" class="text-truncate">
          <a href="{self.package2.download_url}">
            {self.package2.download_url}
          </a>
        </td>
        """
        self.assertContains(response, expected, html=True)

    def test_package_list_multi_send_about_files_view(self):
        multi_about_files_url = reverse("component_catalog:package_multi_about_files")
        response = self.client.get(multi_about_files_url)
        self.assertEqual(302, response.status_code)

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(reverse("component_catalog:package_list"))

        self.assertContains(response, 'id="download-aboutcode-files"')
        self.assertContains(response, f'href="{multi_about_files_url}"')

        response = self.client.get(multi_about_files_url)
        self.assertEqual(404, response.status_code)

        response = self.client.get(f"{multi_about_files_url}?ids=not-good")
        self.assertEqual(404, response.status_code)

        response = self.client.get(
            f"{multi_about_files_url}?ids={self.package1.id},{self.package2.id}"
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual("application/zip", response["Content-Type"])
        self.assertEqual("585", response["Content-Length"])
        self.assertEqual(
            'attachment; filename="package_about.zip"', response["Content-Disposition"]
        )

    def test_package_details_view_num_queries(self):
        self.client.login(username=self.super_user.username, password="secret")
        with self.assertNumQueries(26):
            self.client.get(self.package1.get_absolute_url())

    def test_package_details_view_content(self):
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.package1.get_absolute_url())

        self.assertContains(response, self.package1)
        self.assertContains(response, self.package1.get_change_url())
        expected = (
            '<button class="nav-link active" id="tab_essentials-tab" data-bs-toggle="tab" '
            'data-bs-target="#tab_essentials" type="button" role="tab" '
            'aria-controls="tab_essentials" aria-selected="true">'
        )
        self.assertContains(response, expected)
        self.assertContains(response, 'id="tab_license"')
        self.assertContains(response, 'id="tab_components"')

    def test_package_details_view_package_url(self):
        self.client.login(username=self.super_user.username, password="secret")
        expected_label = "Package URL"
        expected_purl = "pkg:pypi/django@2.1"

        self.assertFalse(self.package1.package_url)
        response = self.client.get(self.package1.get_absolute_url())
        self.assertContains(response, expected_label)
        self.assertNotContains(response, expected_purl)

        self.package1.type = "pypi"
        self.package1.name = "django"
        self.package1.version = "2.1"
        self.package1.save()

        self.assertEqual(expected_purl, self.package1.package_url)
        response = self.client.get(self.package1.get_absolute_url())
        self.assertContains(response, expected_label)
        self.assertContains(response, expected_purl)

    def test_package_details_view_inferred_url(self):
        self.client.login(username=self.super_user.username, password="secret")
        expected_label = "Inferred URL"
        purl = "pkg:pypi/toml@0.10.2"
        expected_url = "https://pypi.org/project/toml/0.10.2/"

        self.assertFalse(self.package1.package_url)
        response = self.client.get(self.package1.get_absolute_url())
        self.assertNotContains(response, expected_label)
        self.assertNotContains(response, expected_url)

        self.package1.set_package_url(purl)
        self.package1.save()

        self.assertEqual(purl, self.package1.package_url)
        response = self.client.get(self.package1.get_absolute_url())
        self.assertContains(response, expected_label)
        self.assertContains(response, expected_url)

    def test_package_details_view_add_package_links(self):
        details_url = self.package1.get_absolute_url()

        add_url = reverse("component_catalog:package_add")
        import_url = reverse("admin:component_catalog_package_import")

        expecteds = [
            "Add another Package",
            "#add-package-modal",
            'id="add-package-modal"',
            f'<a href="{add_url}" class="dropdown-item">Add Package form</a>',
            f'<a href="{import_url}" class="dropdown-item">Import packages</a>',
        ]

        user = create_user("user", self.dataspace)
        self.client.login(username=user.username, password="secret")

        response = self.client.get(details_url)
        for expected in expecteds:
            self.assertNotContains(response, expected)

        add_perm(user, "add_package")
        response = self.client.get(details_url)
        for expected in expecteds:
            self.assertContains(response, expected)

    def test_package_list_view_add_to_product(self):
        user = create_user("user", self.dataspace)
        self.client.login(username=user.username, password="secret")
        url = reverse("component_catalog:package_list")

        expected1 = "column-selection"
        expected2 = (
            f'<input name="checkbox-for-selection" value="{self.package1.id}"'
            f' data-object-repr="{self.package1}" type="checkbox" aria-label="Select row">'
        )
        expected3 = 'data-bs-target="#add-to-product-modal"'
        expected4 = 'id="add-to-product-modal"'

        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, expected4)

        add_perm(user, "add_productpackage")
        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, expected4)

        product1 = Product.objects.create(name="Product1", dataspace=self.dataspace)
        assign_perm("change_product", user, product1)
        assign_perm("view_product", user, product1)
        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertContains(response, expected4)

        # form_invalid
        data = {
            "product": 999999,
            "ids": 999999,
            "submit": "Add to Product",
        }
        response = self.client.post(url, data)
        self.assertRedirects(response, url)

        data["product"] = product1.id
        data["ids"] = f"{self.package1.id}, {self.package2.id}"
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, f"2 package(s) added to &quot;{product1}&quot;.")
        self.assertEqual(2, product1.packages.count())

        product1.refresh_from_db()
        history_entries = History.objects.get_for_object(product1)
        expected_messages = sorted(
            [
                'Added package "package2"',
                'Added package "package1"',
            ]
        )
        self.assertEqual(
            expected_messages, sorted([entry.change_message for entry in history_entries])
        )
        self.assertEqual(user, product1.last_modified_by)

    def test_package_list_view_add_to_component(self):
        user = create_user("user", self.dataspace)
        self.client.login(username=user.username, password="secret")
        url = reverse("component_catalog:package_list")

        expected1 = "column-selection"
        expected2 = (
            f'<input name="checkbox-for-selection" value="{self.package1.id}"'
            f' data-object-repr="{self.package1}" type="checkbox" aria-label="Select row">'
        )
        expected3 = 'data-bs-target="#add-to-component-modal"'
        expected4 = 'id="add-to-component-modal"'
        expected5 = (
            '<input type="text" name="component" placeholder="Start typing for'
            ' suggestions..." style="width: 400px !important;"'
            ' data-api_url="/api/v2/components/" class="autocompleteinput form-control"'
            ' required id="id_component"> '
        )
        expected_js = """
        <script>
          AutocompleteWidget.init("input#id_component.autocompleteinput", "#id_object_id",
           "#id_component_link", "display_name");
        </script>
        """

        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, expected4)
        self.assertNotContains(response, expected5)
        self.assertNotContains(response, expected_js, html=True)

        add_perm(user, "change_component")
        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertContains(response, expected4)
        self.assertContains(response, expected5)
        self.assertContains(response, expected_js, html=True)

        # form_invalid
        data = {
            "component": 999999,
            "ids": 999999,
            "submit-add-to-component-form": 1,
        }
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, url)
        self.assertContains(response, "Error assigning packages to a component.")
        self.assertContains(response, "is not a valid UUID")

        c1 = Component.objects.create(name="new_component", dataspace=self.dataspace)
        data["object_id"] = c1.uuid
        data["component"] = str(c1)
        data["ids"] = f"{self.package1.id}, {self.package2.id}"
        self.assertTrue(c1.is_active)
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, f"{c1.get_absolute_url()}#packages")
        self.assertContains(response, f"2 package(s) added to &quot;{c1}&quot;.")
        self.assertEqual(2, c1.packages.count())

        c1.refresh_from_db()
        history_entries = History.objects.get_for_object(c1)
        expected_messages = sorted(
            [
                'Added package "package2"',
                'Added package "package1"',
            ]
        )
        self.assertEqual(
            expected_messages, sorted([entry.change_message for entry in history_entries])
        )
        self.assertEqual(user, c1.last_modified_by)

    def test_package_list_view_add_to_component_from_package_data(self):
        self.client.login(username=self.super_user.username, password="secret")
        url = reverse("component_catalog:package_list")
        response = self.client.get(url)
        self.assertContains(response, 'id="new-component-link"')
        self.assertContains(response, "Add Component from Package data")

        p1 = Package.objects.create(
            filename="p1",
            name="common_name",
            version="1.0",
            homepage_url="https://p1.com",
            dataspace=self.dataspace,
        )
        p2 = Package.objects.create(
            filename="p1",
            name="common_name",
            version="",
            homepage_url="https://p2.com",
            dataspace=self.dataspace,
        )
        component_add_url = reverse("component_catalog:component_add")
        url = f"{component_add_url}?package_ids={p1.id},{p2.id}"
        response = self.client.get(url)
        self.assertContains(response, 'value="common_name"')
        self.assertContains(response, 'value="1.0"')
        self.assertContains(
            response,
            '<input type="url" name="homepage_url" maxlength="1024"'
            ' class="urlinput form-control" id="id_homepage_url">',
        )

    def test_package_list_view_usage_policy_availability(self):
        self.client.login(username=self.super_user.username, password="secret")
        list_url = reverse("component_catalog:package_list")
        details_url = self.package1.get_absolute_url()

        policy_approved = UsagePolicy.objects.create(
            label="Approved",
            icon="icon-ok-circle",
            content_type=ContentType.objects.get_for_model(Package),
            dataspace=self.package1.dataspace,
        )
        self.package1.usage_policy = policy_approved
        self.package1.save()

        self.dataspace.show_usage_policy_in_user_views = False
        self.dataspace.save()

        response = self.client.get(list_url)
        self.assertNotContains(response, "Usage policy")
        response = self.client.get(details_url)
        self.assertNotContains(response, "Usage policy")

        # Let's enable the display of usage_policy
        self.dataspace.show_usage_policy_in_user_views = True
        self.dataspace.save()

        response = self.client.get(list_url)
        self.assertContains(response, "Policy")
        self.assertContains(response, '<th class="column-usage_policy" scope="col">')
        expected = """
        <span class="cursor-help policy-icon" data-bs-toggle="tooltip" title="Approved">
            <i class="icon-ok-circle" style="color: #000000;"></i>
        </span>
        """

        self.assertContains(response, expected, html=True)
        response = self.client.get(details_url)
        self.assertContains(response, "Usage policy")

    def test_package_send_about_files_view(self):
        self.client.login(username=self.super_user.username, password="secret")
        package = Package.objects.create(dataspace=self.dataspace, type="pypi", name="django")

        response = self.client.get(package.get_absolute_url())
        about_url = reverse(
            "component_catalog:package_about_files", args=[self.dataspace, package.uuid]
        )
        self.assertContains(response, about_url)

        self.assertEqual(0, package.component_set.count())
        response = self.client.get(about_url)
        self.assertEqual("application/zip", response["content-type"])
        self.assertEqual(
            'attachment; filename="pypi/django_about.zip"', response["content-disposition"]
        )

        package.filename = "django.whl"
        package.save()
        response = self.client.get(about_url)
        self.assertEqual("application/zip", response["content-type"])
        self.assertEqual(
            'attachment; filename="django.whl_about.zip"', response["content-disposition"]
        )

        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package, dataspace=self.dataspace
        )
        self.assertEqual(1, package.component_set.count())
        response = self.client.get(about_url)
        self.assertEqual("application/zip", response["content-type"])
        self.assertEqual(
            'attachment; filename="django.whl_about.zip"', response["content-disposition"]
        )

        ComponentAssignedPackage.objects.create(
            component=self.component2, package=package, dataspace=self.dataspace
        )
        self.assertEqual(2, package.component_set.count())
        response = self.client.get(about_url)
        self.assertEqual("application/zip", response["content-type"])
        self.assertEqual(
            'attachment; filename="django.whl_about.zip"', response["content-disposition"]
        )

    def test_component_send_about_files_view(self):
        self.client.login(username=self.super_user.username, password="secret")
        about_url = self.component1.get_about_files_url()

        self.component1.is_active = True
        self.component1.save()

        self.assertTrue(self.component1.packages.exists())
        response = self.client.get(self.component1.get_absolute_url())
        self.assertContains(response, about_url)

        response = self.client.get(about_url)
        self.assertEqual("application/zip", response["content-type"])
        self.assertEqual('attachment; filename="C1_about.zip"', response["content-disposition"])

        self.component1.packages.all().delete()
        self.assertFalse(self.component1.packages.exists())
        response = self.client.get(self.component1.get_absolute_url())
        self.assertNotContains(response, about_url)

    def test_package_create_ajax_view(self):
        package_add_url = reverse("component_catalog:package_add_urls")

        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(package_add_url)
        self.assertEqual(403, response.status_code)
        expected = {"error_message": "Permission denied"}
        self.assertEqual(expected, response.json())

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(package_add_url)
        self.assertEqual(400, response.status_code)
        expected = {"error_message": "Missing Download URL"}
        self.assertEqual(expected, response.json())

        data = {"download_urls": "wrong"}
        response = self.client.post(package_add_url, data)
        self.assertEqual(200, response.status_code)
        expected = {"redirect_url": "/packages/"}
        self.assertEqual(expected, response.json())

        response = self.client.get("/packages/")
        messages = list(response.context["messages"])
        msg = "Invalid URL 'wrong': No scheme supplied. Perhaps you meant https://wrong?"
        self.assertEqual(str(messages[0]), msg)

        self.package1.download_url = "https://dejacode.com/archive.zip"
        self.package1.save()
        data = {"download_urls": self.package1.download_url}
        response = self.client.post(package_add_url, data)
        self.assertEqual(200, response.status_code)
        expected = {"redirect_url": "/packages/"}
        self.assertEqual(expected, response.json())

        response = self.client.get("/packages/")
        messages = list(response.context["messages"])
        msg = (
            f"URL https://dejacode.com/archive.zip already exists in your Dataspace as "
            f'<a href="{self.package1.get_absolute_url()}">package1</a>'
        )
        self.assertEqual(str(messages[0]), msg)

        maven_url = "http://central.maven.org/maven2/xom/xom/1.1/xom-1.1-sources.jar"
        data = {"download_urls": maven_url}
        collected_data = {
            "download_url": maven_url,
            "filename": "xom-1.1-sources.jar",
            "size": 1,
            "sha1": "5ba93c9db0cff93f52b521d7420e43f6eda2784f",
            "md5": "93b885adfe0da089cdf634904fd59f71",
        }
        with mock.patch("component_catalog.views.collect_package_data") as collect:
            collect.return_value = collected_data
            response = self.client.post(package_add_url, data)

        self.assertEqual(200, response.status_code)
        new_package = Package.objects.get(download_url=data["download_urls"])
        expected = {"redirect_url": new_package.get_absolute_url()}
        self.assertEqual(expected, response.json())
        self.assertEqual(self.super_user, new_package.created_by)
        self.assertEqual("pkg:maven/xom/xom@1.1?classifier=sources", new_package.package_url)

        self.assertFalse(History.objects.get_for_object(new_package).exists())
        self.assertEqual(self.super_user, new_package.created_by)
        self.assertTrue(new_package.created_date)
        self.assertEqual(collected_data["sha1"], new_package.sha1)

        response = self.client.get("/packages/")
        messages = list(response.context["messages"])
        self.assertEqual("The Package was successfully created.", str(messages[0]))

        # Different URL but sha1 match in the db
        data = {"download_urls": "https://url.com/file.ext"}
        collected_data["download_url"] = data["download_urls"]
        with mock.patch("component_catalog.views.collect_package_data") as collect:
            collect.return_value = collected_data
            response = self.client.post(package_add_url, data)

        self.assertEqual(200, response.status_code)
        response = self.client.get("/packages/")
        messages = list(response.context["messages"])
        msg = (
            f'The package at URL {collected_data["download_url"]} already exists in'
            f' your Dataspace as <a href="{new_package.get_absolute_url()}">{new_package}</a>'
        )
        self.assertEqual(str(messages[0]), msg)
        self.assertFalse(
            Package.objects.filter(download_url=collected_data["download_url"]).exists()
        )

    def test_package_details_view_add_to_product(self):
        self.client.login(username=self.basic_user.username, password="secret")

        package_url = self.package1.get_absolute_url()
        product1 = Product.objects.create(name="Product1", dataspace=self.dataspace)
        status1 = ProductRelationStatus.objects.create(
            label="status1", default_on_addition=True, dataspace=self.dataspace
        )
        purpose1 = ProductItemPurpose.objects.create(
            label="Core", text="t", dataspace=self.dataspace
        )

        expected = "Add to Product"
        response = self.client.get(package_url)
        self.assertNotContains(response, expected)
        self.assertIsNone(response.context_data["form"])

        user = add_perm(self.basic_user, "add_productpackage")
        assign_perm("change_product", user, product1)
        assign_perm("view_product", user, product1)

        response = self.client.get(package_url)
        self.assertContains(response, expected)
        self.assertIsNotNone(response.context_data["form"])

        expected_status_select = '<select name="review_status" class="select form-select" disabled'
        self.assertContains(response, expected_status_select)
        self.assertContains(response, f'<option value="{purpose1.pk}">Core</option>')

        user = add_perm(user, "change_review_status_on_productpackage")
        purpose1.default_on_addition = True
        purpose1.save()
        response = self.client.get(package_url)
        self.assertContains(response, expected)
        self.assertIsNotNone(response.context_data["form"])
        status_option = f'<option value="{status1.pk}" selected>status1 (default)</option>'
        self.assertContains(response, status_option, html=True)
        purpose_option = f'<option value="{purpose1.pk}" selected>Core (default)</option>'
        self.assertContains(response, purpose_option, html=True)
        self.assertFalse(response.context_data["open_add_to_package_modal"])

        data = {"invalid_form": True}
        response = self.client.post(package_url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "<strong>This field is required.</strong>", html=True)
        self.assertFalse(ProductPackage.objects.count())
        self.assertTrue(response.context_data["open_add_to_package_modal"])

        data = {
            "product": product1.pk,
            "package": 0,
            "license_expression": self.license1.key,
            "review_status": status1.pk,
            "purpose": purpose1.pk,
            "notes": "Notes",
            "is_deployed": "on",
            "is_modified": "on",
            "extra_attribution_text": "Extra",
            "feature": "feature",
        }

        response = self.client.post(package_url, data=data, follow=True)
        self.assertFalse(response.context_data["form"].is_valid())
        expected_errors = {
            "package": ["Select a valid choice. That choice is not one of the available choices."],
        }
        self.assertEqual(expected_errors, response.context_data["form"].errors)

        data["package"] = self.package1.pk
        response = self.client.post(package_url, data=data, follow=True)
        product1_redirect_url = f"{product1.get_absolute_url()}#packages"
        self.assertRedirects(response, product1_redirect_url)
        messages = list(response.context["messages"])
        msg = f'Package "{self.package1}" added to product "{product1}".'
        self.assertEqual(str(messages[0]), msg)
        pp1 = ProductPackage.objects.get(package=self.package1)
        self.assertEqual(data["license_expression"], pp1.license_expression)
        self.assertEqual(status1, pp1.review_status)
        self.assertEqual(purpose1, pp1.purpose)
        self.assertEqual(data["notes"], pp1.notes)
        self.assertTrue(pp1.is_deployed)
        self.assertTrue(pp1.is_modified)
        self.assertEqual(data["extra_attribution_text"], pp1.extra_attribution_text)
        self.assertEqual(data["feature"], pp1.feature)
        self.assertEqual(user.dataspace, pp1.dataspace)
        self.assertEqual(user, pp1.created_by)

        self.assertFalse(History.objects.get_for_object(pp1).exists())
        self.assertEqual(user, pp1.created_by)
        self.assertTrue(pp1.created_date)

        product1.refresh_from_db()
        expected_messages = ['Added package "package1"']
        self.assertEqual(
            expected_messages,
            ['Added package "package1"'],
        )
        self.assertEqual(user, product1.last_modified_by)

        response = self.client.post(package_url, data=data)
        expected_errors = {
            "__all__": [
                "Product package relationship with this Product and Package already exists."
            ],
        }
        self.assertEqual(expected_errors, response.context_data["form"].errors)

        pp1.delete()
        data["license_expression"] = "wrong"
        response = self.client.post(package_url, data=data)
        expected_errors = {
            "license_expression": ["Unknown license key(s): wrong<br>Available licenses: l1, l2"],
        }
        self.assertEqual(expected_errors, response.context_data["form"].errors)

        product1.delete()
        response = self.client.get(package_url)
        self.assertNotContains(response, expected)

    def test_package_details_view_add_to_component(self):
        self.client.login(username=self.basic_user.username, password="secret")

        package_url = self.package1.get_absolute_url()

        expected = 'data-bs-target="#add-to-component-modal"'
        response = self.client.get(package_url)
        self.assertNotContains(response, expected)
        self.assertIsNone(response.context_data.get("add_to_component_form"))

        add_perm(self.basic_user, "change_component")
        response = self.client.get(package_url)
        self.assertContains(response, expected)

        expected1 = (
            '<input type="text" name="component"'
            ' placeholder="Start typing for suggestions..."'
            ' style="width: 400px !important;" data-api_url="/api/v2/components/"'
            ' class="autocompleteinput form-control" required id="id_component"> '
        )

        expected_js = """
        <script>
          AutocompleteWidget.init("input#id_component.autocompleteinput",
             "#id_object_id", "#id_component_link", "display_name");
        </script>
        """
        self.assertContains(response, expected1, html=True)
        self.assertContains(response, expected_js, html=True)

        self.assertIsNotNone(response.context_data.get("add_to_component_form"))

        data = {
            "invalid_form": True,
            "submit-add-to-component-form": True,
        }
        response = self.client.post(package_url, data=data, follow=True)
        self.assertContains(response, "Error assigning the package to a component.")

        c1 = Component.objects.create(name="new_component", dataspace=self.dataspace)
        data.update(
            {
                "object_id": c1.uuid,
                "component": str(c1),
                "package": self.package1.id,
            }
        )
        c1.is_active = True
        c1.save()
        response = self.client.post(package_url, data=data, follow=True)
        self.assertRedirects(response, f"{c1.get_absolute_url()}#packages")
        self.assertContains(response, 'added to "new_component"')
        self.assertEqual(1, c1.packages.count())

    def test_package_component_add_to_product_form(self):
        request = mock.Mock()
        request.user = self.super_user

        alternate_dataspace = Dataspace.objects.create(name="alternate")
        self.package2.dataspace = alternate_dataspace
        self.package2.save()
        status1 = ProductRelationStatus.objects.create(
            label="status1", default_on_addition=True, dataspace=self.dataspace
        )
        status2 = ProductRelationStatus.objects.create(label="s2", dataspace=alternate_dataspace)
        product1 = Product.objects.create(name="P1", dataspace=self.dataspace)
        product2 = Product.objects.create(name="P2", dataspace=alternate_dataspace)

        form = PackageAddToProductForm(request.user, self.package1)

        package_qs = form.fields["package"].queryset
        self.assertIn(self.package1, package_qs)
        self.assertNotIn(self.package2, package_qs)

        status_qs = form.fields["review_status"].queryset
        self.assertIn(status1, status_qs)
        self.assertNotIn(status2, status_qs)
        self.assertEqual(status1, form.fields["review_status"].initial)

        product_qs = form.fields["product"].queryset
        self.assertIn(product1, product_qs)
        self.assertNotIn(product2, product_qs)

        self.component2.dataspace = alternate_dataspace
        self.component2.save()
        form = ComponentAddToProductForm(request.user, self.component1)

        component_qs = form.fields["component"].queryset
        self.assertIn(self.component1, component_qs)
        self.assertNotIn(self.component2, component_qs)

        status_qs = form.fields["review_status"].queryset
        self.assertIn(status1, status_qs)
        self.assertNotIn(status2, status_qs)
        self.assertEqual(status1, form.fields["review_status"].initial)

        product_qs = form.fields["product"].queryset
        self.assertIn(product1, product_qs)
        self.assertNotIn(product2, product_qs)

    @override_settings(REFERENCE_DATASPACE="Dataspace")
    def test_package_details_view_scan_package_button(self):
        self.client.login(username=self.super_user.username, password="secret")
        expected1 = "Submit Scan Request"
        expected2 = 'data-bs-target="#scan-package-modal"'

        response = self.client.get(self.package1_tab_scan_url)
        self.assertEqual(response.status_code, 404)

        self.dataspace.enable_package_scanning = True
        self.dataspace.save()
        response = self.client.get(self.package1_tab_scan_url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

        alternate = Dataspace.objects.create(name="Alternate")
        alternate_user = create_superuser("alternate_user", alternate)
        alternate_package = Package.objects.create(
            filename="alternate_package", download_url="alternate_package", dataspace=alternate
        )
        alternate_package_tab_scan_url = alternate_package.get_url("tab_scan")

        self.client.login(username=alternate_user.username, password="secret")
        response = self.client.get(alternate_package_tab_scan_url)
        self.assertEqual(response.status_code, 404)

        alternate.enable_package_scanning = True
        alternate.save()
        response = self.client.get(alternate_package_tab_scan_url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

        response = self.client.get(self.package1_tab_scan_url)
        self.assertEqual(response.status_code, 404)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_info")
    def test_package_details_view_scan_tab_report_scan_issue_button(
        self, mock_fetch_scan_info, mock_fetch_scan_data
    ):
        self.client.login(username=self.super_user.username, password="secret")
        self.dataspace.enable_package_scanning = True
        self.dataspace.save()

        mock_fetch_scan_data.return_value = {}
        mock_fetch_scan_info.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "70265cfaec8cab26f8c88e968e84f23efd886ced663c10bfe408ff20c26a103f",
                    "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
                    "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
                    "runs": [
                        {
                            "status": "success",
                        }
                    ],
                }
            ],
        }

        expected = "Report Scan Issues"
        response = self.client.get(self.package1_tab_scan_url)
        self.assertNotContains(response, expected)

        with override_settings(SCAN_ISSUE_REQUEST_TEMPLATE={self.dataspace.name: uuid.uuid4()}):
            response = self.client.get(self.package1_tab_scan_url)
            self.assertContains(response, expected)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_info")
    def test_package_details_view_scan_tab_scan_in_progress(
        self, mock_fetch_scan_info, mock_fetch_scan_data
    ):
        self.client.login(username=self.super_user.username, password="secret")

        mock_fetch_scan_data.return_value = {}
        mock_fetch_scan_info.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "70265cfaec8cab26f8c88e968e84f23efd886ced663c10bfe408ff20c26a103f",
                    "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
                    "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
                    "runs": [
                        {
                            "status": "running",
                            "created_date": "2018-06-21T12:32:17.860882Z",
                            "task_start_date": "2018-06-21T12:32:17.879153Z",
                            "task_end_date": None,
                            "scancodeio_version": "31.0.0",
                        }
                    ],
                }
            ],
        }

        response = self.client.get(self.package1_tab_scan_url)
        self.assertEqual(response.status_code, 404)

        self.dataspace.enable_package_scanning = True
        self.dataspace.save()
        response = self.client.get(self.package1_tab_scan_url)

        expected = """
        <dl class="row mb-0">
        <dt class="col-sm-2 text-end pt-2 pe-0">Status</dt>
        <dd class="col-sm-10 clipboard">
          <button class="btn-clipboard" data-bs-toggle="tooltip" title="Copy to clipboard">
          <i class="fas fa-clipboard"></i></button>
          <pre class="pre-bg-body-tertiary mb-1 field-status">Scan running</pre>
        </dd>
        <dt class="col-sm-2 text-end pt-2 pe-0">Created date</dt>
        <dd class="col-sm-10 clipboard">
          <button class="btn-clipboard" data-bs-toggle="tooltip" title="Copy to clipboard">
          <i class="fas fa-clipboard"></i></button>
          <pre class="pre-bg-body-tertiary mb-1 field-created-date">
            June 21, 2018, 12:32 PM UTC
          </pre>
        </dd>
        <dt class="col-sm-2 text-end pt-2 pe-0">Start date</dt>
        <dd class="col-sm-10 clipboard">
          <button class="btn-clipboard" data-bs-toggle="tooltip" title="Copy to clipboard">
          <i class="fas fa-clipboard"></i></button>
          <pre class="pre-bg-body-tertiary mb-1 field-start-date">June 21, 2018, 12:32 PM UTC</pre>
        </dd>
        <dt class="col-sm-2 text-end pt-2 pe-0">End date</dt>
        <dd class="col-sm-10 clipboard">
          <pre class="pre-bg-body-tertiary mb-1 field-end-date">&nbsp;</pre>
        </dd>
        <dt class="col-sm-2 text-end pt-2 pe-0">ScanCode.io version</dt>
        <dd class="col-sm-10 clipboard">
          <button class="btn-clipboard" data-bs-toggle="tooltip" title="Copy to clipboard">
          <i class="fas fa-clipboard"></i></button>
          <pre class="pre-bg-body-tertiary mb-1 field-scancodeio-version">31.0.0</pre>
        </dd>
        </dl>
        """
        self.assertContains(response, expected, html=True)
        self.assertNotContains(response, "Set values to Package")

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_info")
    def test_package_details_view_scan_tab_scan_success(
        self, mock_fetch_scan_info, mock_fetch_scan_data
    ):
        self.client.login(username=self.super_user.username, password="secret")

        mock_fetch_scan_info.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "70265cfaec8cab26f8c88e968e84f23efd886ced663c10bfe408ff20c26a103f",
                    "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
                    "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
                    "runs": [
                        {
                            "status": "success",
                        }
                    ],
                }
            ],
        }

        exception = License.objects.create(
            key="e",
            name="e",
            short_name="e",
            is_exception=True,
            owner=self.owner1,
            dataspace=self.dataspace,
        )
        license_expression = f"{self.license1.key} AND {self.license2.key} WITH {exception.key}"

        mock_fetch_scan_data.return_value = {
            "declared_license_expression": license_expression,
            "license_clarity_score": {
                "score": 90,
                "declared_license": True,
                "identification_precision": True,
                "has_license_text": True,
                "declared_copyrights": True,
                "conflicting_license_categories": False,
                "ambiguous_compound_licensing": False,
            },
            "declared_holder": "Hank Hill",
            "primary_language": "C++",
            "other_license_expressions": [{"value": "mit", "count": 3}],
            "other_holders": [{"value": "Alex Gaynor", "count": 2}],
            "other_languages": [{"value": "Python", "count": 39}],
        }

        response = self.client.get(self.package1_tab_scan_url)
        self.assertEqual(response.status_code, 404)

        self.dataspace.enable_package_scanning = True
        self.dataspace.save()
        response = self.client.get(self.package1_tab_scan_url)

        expected_declared_license = """
        <span class="license-expression">
          <input type="checkbox" name="license_expression" value="l1 AND l2 WITH e" checked>
          <a href="/licenses/Dataspace/l1/" title="L1">l1</a>
          AND (<a href="/licenses/Dataspace/l2/" title="L2">l2</a>
           WITH <a href="/licenses/Dataspace/e/" title="e">e</a>)
        </span>
        """
        expected_declared_holder = (
            '<input type="checkbox" name="holder" value="Hank Hill" checked> Hank Hill'
        )
        expected_primary_language = (
            '<input type="radio" name="primary_language" value="C++" checked> C++'
        )
        expected_other_licenses = """
        <span class="license-expression"><input type="checkbox" name="license_expression"
        value="mit" > mit <span class="badge text-bg-secondary rounded-pill">3</span></span>
        """
        expected_other_holders = (
            '<input type="checkbox" name="holder" value="Alex Gaynor"> Alex Gaynor '
            '<span class="badge text-bg-secondary rounded-pill">2</span>'
        )
        expected_other_languages = (
            '<input type="radio" name="primary_language" value="Python"> Python '
            '<span class="badge text-bg-secondary rounded-pill">39</span>'
        )
        self.assertContains(response, expected_declared_license, html=True)
        self.assertContains(response, expected_declared_holder, html=True)
        self.assertContains(response, expected_primary_language, html=True)
        self.assertContains(response, expected_other_licenses, html=True)
        self.assertContains(response, expected_other_holders, html=True)
        self.assertContains(response, expected_other_languages, html=True)
        self.assertContains(response, "Scan Summary")
        self.assertContains(response, "Set values to Package")
        self.assertContains(response, "Download Scan data")

        scan_data_as_file_url = reverse(
            "component_catalog:scan_data_as_file",
            args=["f622d852-2d6a-4fb5-ab89-a90db54a4581", self.package1.filename],
        )
        self.assertContains(response, scan_data_as_file_url)

        self.package1.filename = ""
        self.package1.type = "deb"
        self.package1.name = "name"
        self.package1.version = "1.0"
        self.package1.save()
        scan_data_as_file_url = reverse(
            "component_catalog:scan_data_as_file",
            args=["f622d852-2d6a-4fb5-ab89-a90db54a4581", self.package1.package_url_filename],
        )
        response = self.client.get(self.package1_tab_scan_url)
        self.assertContains(response, scan_data_as_file_url)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_info")
    def test_package_details_view_scan_tab_scan_failed(
        self, mock_fetch_scan_info, mock_fetch_scan_data
    ):
        self.client.login(username=self.super_user.username, password="secret")

        mock_fetch_scan_data.return_value = {}
        mock_fetch_scan_info.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "70265cfaec8cab26f8c88e968e84f23efd886ced663c10bfe408ff20c26a103f",
                    "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
                    "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
                    "runs": [
                        {
                            "status": "failure",
                            "task_output": "task_output_value",
                            "log": "log_value",
                        }
                    ],
                }
            ],
        }

        response = self.client.get(self.package1_tab_scan_url)
        self.assertEqual(response.status_code, 404)

        self.dataspace.enable_package_scanning = True
        self.dataspace.save()
        response = self.client.get(self.package1_tab_scan_url)

        self.assertContains(response, "Scan failure")
        self.assertContains(response, "Task output")
        self.assertContains(response, "task_output_value")
        self.assertContains(response, "Log")
        self.assertContains(response, "log_value")

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_info")
    def test_package_details_view_scan_tab_detected_package(
        self, mock_fetch_scan_info, mock_fetch_scan_data
    ):
        self.client.login(username=self.super_user.username, password="secret")
        self.dataspace.enable_package_scanning = True
        self.dataspace.save()

        mock_fetch_scan_info.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "70265cfaec8cab26f8c88e968e84f23efd886ced663c10bfe408ff20c26a103f",
                    "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
                    "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
                }
            ],
        }

        detected_package = {
            "primary_language": "Java",
            "description": "AOP alliance\nAOP Alliance",
            "release_date": "2018-01-01",
            "homepage_url": "http://aopalliance.sourceforge.net",
            "copyright": "Copyright",
            "declared_license_expression": "public-domain",
            # "other_license_expression": "bsd-simplified",
            "notice_text": "NoticeText",
            "purl": "pkg:maven/aopalliance/aopalliance@1.0",
        }

        mock_fetch_scan_data.return_value = {
            "key_files_packages": [detected_package],
        }

        response = self.client.get(self.package1_tab_scan_url)
        self.assertContains(response, "Detected Package")
        for value in detected_package.values():
            self.assertContains(response, value)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_info")
    def test_package_details_view_scan_tab_license_clarity(
        self, mock_fetch_scan_info, mock_fetch_scan_data
    ):
        self.client.login(username=self.super_user.username, password="secret")
        self.dataspace.enable_package_scanning = True
        self.dataspace.save()

        mock_fetch_scan_info.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "70265cfaec8cab26f8c88e968e84f23efd886ced663c10bfe408ff20c26a103f",
                    "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
                    "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
                }
            ],
        }

        mock_fetch_scan_data.return_value = {
            "license_clarity_score": {},
        }

        response = self.client.get(self.package1_tab_scan_url)
        self.assertNotContains(response, "License Clarity")

        mock_fetch_scan_data.return_value = {
            "license_clarity_score": {
                "score": 90,
                "declared_license": True,
                "identification_precision": True,
                "has_license_text": True,
                "declared_copyrights": True,
                "conflicting_license_categories": False,
                "ambiguous_compound_licensing": True,
            }
        }

        response = self.client.get(self.package1_tab_scan_url)
        self.assertContains(response, "License Clarity")
        expected = """
        <tr>
          <td class="text-center"><span class="badge text-bg-success fs-85pct">+40</span></td>
          <td class="text-center"><span class="badge text-bg-success fs-85pct">+40</span></td>
          <td class="text-center"><span class="badge text-bg-success fs-85pct">+10</span></td>
          <td class="text-center"><span class="badge text-bg-success fs-85pct">+10</span></td>
          <td class="text-center"><span class="badge text-bg-danger fs-85pct">-10</span></td>
          <td class="text-center"></td>
          <td class="text-center bg-body-tertiary">
            <span class="badge text-bg-primary fs-85pct">90</span>
          </td>
        </tr>
        """
        self.assertContains(response, expected, html=True)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_info")
    def test_package_details_view_scan_tab_key_files(
        self, mock_fetch_scan_info, mock_fetch_scan_data
    ):
        self.client.login(username=self.super_user.username, password="secret")
        self.dataspace.enable_package_scanning = True
        self.dataspace.save()

        mock_fetch_scan_info.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "70265cfaec8cab26f8c88e968e84f23efd886ced663c10bfe408ff20c26a103f",
                    "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
                    "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
                }
            ],
        }

        mock_fetch_scan_data.return_value = {}
        expected_label = "Key files"
        response = self.client.get(self.package1_tab_scan_url)
        self.assertNotContains(response, expected_label)

        mock_fetch_scan_data.return_value = {
            "key_files": [],
        }
        response = self.client.get(self.package1_tab_scan_url)
        self.assertNotContains(response, expected_label)

        key_file_data = {
            "authors": [],
            "compliance_alert": "ok",
            "content": "Copyright 2011 Gary Court.",
            "copyrights": [
                {"copyright": "Copyright 2011 Gary Court", "end_line": 1, "start_line": 1}
            ],
            "detected_license_expression": "bsd-2-clause-views",
            "detected_license_expression_spdx": "BSD-2-Clause-Views",
            "emails": [],
            "extension": "",
            "extra_data": {},
            "file_type": "ASCII text, with very long lines (717)",
            "for_packages": ["pkg:npm/uri-js@4.4.1?uuid=8e657f21-de14-4bc7-bd45-a47e0169e5a2"],
            "holders": [{"end_line": 1, "holder": "Gary Court", "start_line": 1}],
            "is_archive": False,
            "is_binary": False,
            "is_key_file": True,
            "is_media": False,
            "is_text": True,
            "license_clues": [],
            "license_detections": [
                {
                    "identifier": "bsd_2_clause_views-884555cb-5e8e-",
                    "license_expression": "bsd-2-clause-views",
                    "matches": [
                        {
                            "end_line": 11,
                            "license_expression": "bsd-2-clause-views",
                            "match_coverage": 100.0,
                            "matched_length": 206,
                            "matched_text": "Redistribution",
                            "matcher": "3-seq",
                            "rule_identifier": "bsd-2-clause-views_11.RULE",
                            "rule_relevance": 100,
                            "score": 98.1,
                            "start_line": 3,
                        }
                    ],
                }
            ],
            "md5": "3b55dad4a98748003b5b423477713da1",
            "mime_type": "text/plain",
            "name": "LICENSE",
            "package_data": [],
            "path": "package/LICENSE",
            "percentage_of_license_text": 94.06,
            "programming_language": "",
            "sha1": "dc45ad0fa775735dfad6f590f126dee709763efc",
            "sha256": "0af366eff4c01ec147c9c61ea9e8ffad64a4294754c9d79355f3fd1b97cb2fb9",
            "sha512": "",
            "size": 1452,
            "status": "application-package",
            "tag": "",
            "type": "file",
            "urls": [],
        }

        mock_fetch_scan_data.return_value = {"key_files": [key_file_data]}
        response = self.client.get(self.package1_tab_scan_url)
        self.assertContains(response, expected_label)
        self.assertContains(response, 'data-bs-target="#key-files-modal"')
        self.assertContains(response, 'data-filename="LICENSE"')
        self.assertContains(response, 'data-size="1.4 KB"')
        self.assertContains(response, 'id="key-files-modal"')
        self.assertContains(response, 'data-matched-texts="Redistribution // Copyright')

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_info")
    def test_package_details_view_scan_tab_license_matches(
        self, mock_fetch_scan_info, mock_fetch_scan_data
    ):
        self.client.login(username=self.super_user.username, password="secret")
        self.dataspace.enable_package_scanning = True
        self.dataspace.save()

        mock_fetch_scan_info.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "70265cfaec8cab26f8c88e968e84f23efd886ced663c10bfe408ff20c26a103f",
                    "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
                    "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
                }
            ],
        }

        mock_fetch_scan_data.return_value = {
            "other_license_expressions": [
                {"value": "apache-2.0", "count": 3},
                {"value": "mit", "count": 2},
            ],
        }

        expected1 = (
            '<span class="license-expression"><input type="checkbox" name="license_expression" '
            'value="apache-2.0" > apache-2.0 <span class="badge text-bg-secondary rounded-pill">3'
            "</span></span>"
        )
        expected2 = (
            '<span class="license-expression"><input type="checkbox" name="license_expression" '
            'value="mit" > mit <span class="badge text-bg-secondary rounded-pill">2</span></span>'
        )
        response = self.client.get(self.package1_tab_scan_url)
        self.assertContains(response, expected1, html=True)
        self.assertContains(response, expected2, html=True)

        # Using {} in `path` and `matched_text` to test the proper escaping
        mock_fetch_scan_data.return_value["license_matches"] = {
            "mit": {
                "${NameLower}_amethyst-0.11.1/Cargo.toml": [
                    {
                        "license_expression": "mit",
                        "matches": [
                            {
                                "license_expression": "mit",
                                "matched_text": 'license = "MIT/Apache-2.0"',
                            }
                        ],
                    }
                ],
                "amethyst_animation/Cargo.toml": [
                    {
                        "license_expression": "mit",
                        "matches": [
                            {"license_expression": "mit", "matched_text": "[hide].[o].[j55]{[at]}["}
                        ],
                    }
                ],
            },
            "apache-2.0": {
                "amethyst-0.11.1/README.md": [
                    {
                        "license_expression": "apache-2.0",
                        "matches": [
                            {
                                "license_expression": "apache-2.0",
                                "matched_text": "Apache License 2.0][",
                            }
                        ],
                    }
                ],
            },
        }

        response = self.client.get(self.package1_tab_scan_url)
        self.assertContains(response, "&lt;div class=&quot;card mb-3&quot;&gt;")
        self.assertContains(
            response,
            'data-bs-target="#scan-matches-modal" data-license-key="apache-2.0"',
        )
        self.assertContains(
            response, "[hide].[o].[j55]&amp;lbrace;[at]&amp;rbrace;[&lt;/code&gt;&lt;/pre&gt;"
        )

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_info")
    def test_package_details_view_scan_to_package(self, mock_fetch_scan_info, mock_fetch_scan_data):
        url = self.package1.get_absolute_url()
        self.client.login(username=self.basic_user.username, password="secret")
        self.dataspace.enable_package_scanning = True
        self.dataspace.save()

        mock_fetch_scan_info.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "70265cfaec8cab26f8c88e968e84f23efd886ced663c10bfe408ff20c26a103f",
                    "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
                    "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
                }
            ],
        }

        detected_package = {
            "primary_language": "Java",
            "description": "AOP alliance\nAOP Alliance",
            "release_date": "2018-01-01",
            "homepage_url": "http://aopalliance.sourceforge.net",
            "copyright": "Copyright",
            "declared_license_expression": "public-domain",
            "notice_text": "NoticeText",
            "purl": "pkg:maven/aopalliance/aopalliance@1.0",
            "is_key_file": 1,
        }

        mock_fetch_scan_data.return_value = {
            "key_files_packages": [detected_package],
        }

        expected1 = "#scan-to-package-modal"
        expected2 = 'id="scan-to-package-form"'

        response = self.client.get(self.package1_tab_scan_url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        add_perm(self.basic_user, "change_package")
        response = self.client.get(self.package1_tab_scan_url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

        detected_package.pop("is_key_file")
        for expected_value in detected_package.values():
            self.assertContains(response, f"{expected_value}")

        post_data = {
            "scan-to-package-primary_language": "Java",
            "scan-to-package-description": "AOP alliance\nAOP Alliance",
            "scan-to-package-release_date": "2018-01-01",
            "scan-to-package-homepage_url": "http://aopalliance.sourceforge.net",
            "scan-to-package-copyright": "Copyright",
            "scan-to-package-license_expression": "public-domain",
            "scan-to-package-notice_text": "NoticeText",
            "scan-to-package-package_url": "pkg:maven/aopalliance/aopalliance@1.0",
            "submit-scan-to-package-form": "Set values",
        }

        response = self.client.post(url, post_data, follow=True)
        messages = list(response.context["messages"])
        self.assertIn("Error assigning values to the package.", str(messages[0]))
        self.assertIn("Unknown license key(s): public-domain", str(messages[0]))

        detected_package["declared_license_expression"] = self.license1.key
        post_data["scan-to-package-license_expression"] = self.license1.key
        response = self.client.post(url, post_data, follow=True)
        messages = list(response.context["messages"])
        expected = (
            "Values for package_url, license_expression, copyright, primary_language, "
            "description, homepage_url, release_date, notice_text assigned to the package."
        )
        self.assertEqual(expected, str(messages[0]))

        self.package1.refresh_from_db()
        for field_name, form_value in detected_package.items():
            if field_name == "purl":
                field_name = "package_url"
            elif field_name == "declared_license_expression":
                field_name = "license_expression"
            instance_value = getattr(self.package1, field_name, None)
            self.assertEqual(str(form_value), str(instance_value), msg=field_name)

        history = History.objects.get_for_object(self.package1, action_flag=History.CHANGE).get()
        expected = (
            "Changed Package URL, License expression, Copyright, Primary language, Description, "
            "Homepage URL, Release date and Notice text."
        )
        self.assertEqual(expected, history.get_change_message())

        response = self.client.post(url, post_data, follow=True)
        messages = list(response.context["messages"])
        self.assertEqual("No new values to assign.", str(messages[0]))

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_info")
    def test_package_details_view_scan_summary_to_package(
        self, mock_fetch_scan_info, mock_fetch_scan_data
    ):
        url = self.package1.get_absolute_url()
        self.client.login(username=self.basic_user.username, password="secret")
        self.dataspace.enable_package_scanning = True
        self.dataspace.save()

        mock_fetch_scan_info.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "70265cfaec8cab26f8c88e968e84f23efd886ced663c10bfe408ff20c26a103f",
                    "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
                    "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
                }
            ],
        }

        scan_summary = {
            "declared_license_expression": "bsd-new",
            "license_clarity_score": {
                "score": 90,
                "declared_license": True,
                "identification_precision": True,
                "has_license_text": True,
                "declared_copyrights": True,
                "conflicting_license_categories": True,
                "ambiguous_compound_licensing": True,
            },
            "declared_holder": "The Rust Project Developers",
            "primary_programming_language": "Rust",
            "other_license_expressions": [
                {"value": "apache-2.0", "count": 5},
                {"value": "mit", "count": 3},
                {"value": "unknown-license-reference", "count": 2},
            ],
            "other_holders": [
                {"value": None, "count": 211},
                {"value": "The Rust Project", "count": 1},
            ],
            "other_programming_languages": [{"value": "C", "count": 1}],
        }

        mock_fetch_scan_data.return_value = scan_summary

        expected1 = "#scan-summary-to-package-modal"
        expected2 = 'id="scan-summary-to-package-form"'

        self.basic_user.has_perm("component_catalog.change_package")
        response = self.client.get(self.package1_tab_scan_url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        add_perm(self.basic_user, "change_package")
        response = self.client.get(self.package1_tab_scan_url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

        post_data = {
            "scan-summary-to-package-license_expression": "mit OR apache-2.0",
            "scan-summary-to-package-primary_language": "Rust",
            "scan-summary-to-package-holder": "The Rust Project Developers",
            "submit-scan-summary-to-package-form": "Set values",
        }

        response = self.client.post(url, post_data, follow=True)
        messages = list(response.context["messages"])
        self.assertIn("Error assigning values to the package.", str(messages[0]))
        self.assertIn("Unknown license key(s): mit, apache-2.0", str(messages[0]))

        post_data["scan-summary-to-package-license_expression"] = self.license1.key
        response = self.client.post(url, post_data, follow=True)
        messages = list(response.context["messages"])
        expected = (
            "Values for license_expression, primary_language, holder assigned to the package."
        )
        self.assertEqual(expected, str(messages[0]))

        self.package1.refresh_from_db()
        self.assertEqual(self.license1.key, self.package1.license_expression)
        self.assertEqual("Rust", self.package1.primary_language)
        self.assertEqual("The Rust Project Developers", self.package1.holder)

        history = History.objects.get_for_object(self.package1, action_flag=History.CHANGE).get()
        expected = "Changed License expression, Primary language and Holder."
        self.assertEqual(expected, history.get_change_message())

        response = self.client.post(url, post_data, follow=True)
        messages = list(response.context["messages"])
        self.assertEqual("No new values to assign.", str(messages[0]))

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_info")
    def test_package_details_view_scan_summary_to_package_libc(
        self, mock_fetch_scan_info, mock_fetch_scan_data
    ):
        # https://github.com/rust-lang/libc/archive/refs/tags/0.2.121.tar.gz
        url = self.package1.get_absolute_url()
        self.client.login(username=self.basic_user.username, password="secret")
        self.dataspace.enable_package_scanning = True
        self.dataspace.save()

        mock_fetch_scan_info.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "70265cfaec8cab26f8c88e968e84f23efd886ced663c10bfe408ff20c26a103f",
                    "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
                    "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
                }
            ],
        }

        scan_summary_location = join(
            self.testfiles_location, "summary", "libc-0.2.121-scancode.io-summary.json"
        )
        with open(scan_summary_location) as f:
            scan_summary = json.load(f)
            expected_license_expression = scan_summary["declared_license_expression"]
            expected_holder = scan_summary["declared_holder"]
            expected_primary_language = scan_summary["primary_language"]

        mock_fetch_scan_data.return_value = scan_summary

        response = self.client.get(self.package1_tab_scan_url)
        expected_license_expression_html = (
            '<span class="license-expression">'
            '<input type="checkbox" name="license_expression" value="apache-2.0 OR mit" checked> '
            "apache-2.0 OR mit</span>"
        )
        expected_holder_html = (
            '<input type="checkbox" name="holder" value="The Rust Project" checked> '
            "The Rust Project"
        )
        expected_primary_language_html = (
            '<input type="radio" name="primary_language" value="Rust" checked> Rust'
        )
        self.assertContains(response, expected_license_expression_html, html=True)
        self.assertContains(response, expected_holder_html, html=True)
        self.assertContains(response, expected_primary_language_html, html=True)

        expected1 = "#scan-summary-to-package-modal"
        expected2 = 'id="scan-summary-to-package-form"'

        self.basic_user.has_perm("component_catalog.change_package")
        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        add_perm(self.basic_user, "change_package")
        response = self.client.get(self.package1_tab_scan_url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

        post_data = {
            "scan-summary-to-package-license_expression": expected_license_expression,
            "scan-summary-to-package-primary_language": expected_primary_language,
            "scan-summary-to-package-holder": expected_holder,
            "submit-scan-summary-to-package-form": "Set values",
        }
        response = self.client.post(url, post_data, follow=True)
        messages = list(response.context["messages"])
        self.assertIn("Error assigning values to the package.", str(messages[0]))
        self.assertIn("Unknown license key(s): apache-2.0, mit", str(messages[0]))

        post_data["scan-summary-to-package-license_expression"] = self.license1.key
        response = self.client.post(url, post_data, follow=True)
        messages = list(response.context["messages"])
        expected = (
            "Values for license_expression, primary_language, holder assigned to the package."
        )
        self.assertEqual(expected, str(messages[0]))

        self.package1.refresh_from_db()
        self.assertEqual(self.license1.key, self.package1.license_expression)
        self.assertEqual(expected_primary_language, self.package1.primary_language)
        self.assertEqual(expected_holder, self.package1.holder)

        history = History.objects.get_for_object(self.package1, action_flag=History.CHANGE).get()
        expected = "Changed License expression, Primary language and Holder."
        self.assertEqual(expected, history.get_change_message())

        response = self.client.post(url, post_data, follow=True)
        messages = list(response.context["messages"])
        self.assertEqual("No new values to assign.", str(messages[0]))

    def test_package_details_view_get_license_expressions_scan_values(self):
        field_data = [{"value": "mit OR apache-2.0", "count": None}]
        input_type = "checkbox"
        license_matches = {
            "mit OR apache-2.0": {
                "libc-0.2.121/Cargo.toml.orig": [
                    {
                        "license_expression": "mit OR apache-2.0",
                        "matches": [
                            {"license_expression": "mit OR apache-2.0", "matched_text": "<MATCH>"}
                        ],
                    }
                ]
            }
        }

        values = PackageTabScanView.get_license_expressions_scan_values(
            self.dataspace, field_data, input_type, license_matches
        )
        self.assertEqual(1, len(values))
        self.assertIn("MATCH", values[0])

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_list")
    def test_scan_list_view(self, mock_fetch_scan_list):
        scan_list_url = reverse("component_catalog:scan_list")
        project_uuid = "f622d852-2d6a-4fb5-ab89-a90db54a4581"

        mock_fetch_scan_list.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "70265cfaec8cab26f8c88e968e84f23efd886ced663c10bfe408ff20c26a103f",
                    "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
                    "uuid": project_uuid,
                    "created_date": "2018-06-21T12:32:17.860882Z",
                    "input_sources": [
                        {
                            "filename": self.package1.filename,
                            "download_url": self.package1.download_url,
                            "is_uploaded": False,
                            "tag": "",
                            "exists": True,
                            "uuid": "8e454229-70f4-476f-a56f-2967eb2e8f4c",
                        }
                    ],
                    "runs": [
                        {
                            "status": "success",
                        }
                    ],
                }
            ],
        }

        response = self.client.get(scan_list_url)
        self.assertRedirects(response, f"/login/?next={scan_list_url}")

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(scan_list_url)
        self.assertEqual(404, response.status_code)

        self.dataspace.enable_package_scanning = True
        self.dataspace.save()
        response = self.client.get(scan_list_url)
        self.assertContains(response, "Scans: 1 results")
        self.assertContains(response, '<strong class="ms-1">Success</strong>', html=True)
        self.assertContains(response, self.package1.get_absolute_url())

        expected = '<a class="nav-link active" href="/scans/?all=true">All</a>'
        self.assertContains(response, expected, html=True)
        expected = '<a class="nav-link" href="?created_by_me=1">Created by me</a>'
        self.assertContains(response, expected, html=True)

        self.assertContains(response, 'id="scan-delete-modal"')
        delete_url = reverse("component_catalog:scan_delete", args=[project_uuid])
        self.assertContains(response, f'data-delete-url="{delete_url}"')

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.delete_scan")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_list")
    def test_delete_scan_view(self, mock_fetch_scan_list, mock_delete_scan):
        project_uuid = "348df847-f48f-4ac7-b864-5785b44c65e2"
        delete_url = reverse("component_catalog:scan_delete", args=[project_uuid])

        response = self.client.get(delete_url)
        self.assertRedirects(response, f"/login/?next={delete_url}")

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(delete_url)
        self.assertEqual(404, response.status_code)

        self.dataspace.enable_package_scanning = True
        self.dataspace.save()
        mock_fetch_scan_list.return_value = None
        response = self.client.get(delete_url)
        self.assertEqual(404, response.status_code)

        mock_fetch_scan_list.return_value = {"count": 1}
        mock_delete_scan.return_value = True
        response = self.client.get(delete_url, follow=True)
        scan_list_url = reverse("component_catalog:scan_list")
        self.assertRedirects(response, scan_list_url)
        self.assertContains(response, "Scan deleted.")

        mock_delete_scan.return_value = False
        response = self.client.get(delete_url)
        self.assertEqual(404, response.status_code)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    def test_send_scan_data_as_file_view(self, mock_fetch_scan_data):
        mock_fetch_scan_data.return_value = {}

        project_uuid = "348df847-f48f-4ac7-b864-5785b44c65e2"
        url = reverse(
            "component_catalog:scan_data_as_file", args=[project_uuid, self.package1.filename]
        )

        response = self.client.get(url)
        self.assertRedirects(response, f"/login/?next={url}")

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

        self.dataspace.enable_package_scanning = True
        self.dataspace.save()
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("application/zip", response["content-type"])
        self.assertEqual(
            'attachment; filename="package1_scan.zip"', response["content-disposition"]
        )

    @mock.patch("requests.head")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.submit_scan")
    def test_scancodeio_submit_scan_task(self, mock_submit_scan, mock_request_head):
        user_uuid = self.super_user.uuid
        dataspace_uuid = self.super_user.dataspace.uuid

        mock_request_head.side_effect = requests.RequestException
        scancodeio_submit_scan(["no_protocol.com"], user_uuid, dataspace_uuid)
        self.assertEqual([], mock_submit_scan.mock_calls)

        uris = {
            "http://okurl.com": mock.Mock(status_code=200),
            "https://okurl2.com": mock.Mock(status_code=200),
            "http://private_url.com": mock.Mock(status_code=404),
        }
        mock_request_head.side_effect = lambda arg, allow_redirects: uris[arg]
        scancodeio_submit_scan(list(uris.keys()), user_uuid, dataspace_uuid)

        expected = [
            mock.call("http://okurl.com", user_uuid, dataspace_uuid),
            mock.call("https://okurl2.com", user_uuid, dataspace_uuid),
        ]
        self.assertEqual(expected, mock_submit_scan.mock_calls)

    @mock.patch("requests.sessions.Session.get")
    def test_scancodeio_fetch_scan_list(self, mock_session_get):
        scancodeio = ScanCodeIO(self.basic_user)
        self.assertIsNone(scancodeio.fetch_scan_list())
        self.assertFalse(mock_session_get.called)

        scancodeio.fetch_scan_list(user=self.basic_user)
        params = mock_session_get.call_args.kwargs["params"]
        expected = {"format": "json", "name__endswith": get_hash_uid(self.basic_user.uuid)}
        self.assertEqual(expected, params)

        scancodeio.fetch_scan_list(dataspace=self.basic_user.dataspace)
        params = mock_session_get.call_args.kwargs["params"]
        expected = {
            "format": "json",
            "name__contains": get_hash_uid(self.basic_user.dataspace.uuid),
        }
        self.assertEqual(expected, params)

        scancodeio.fetch_scan_list(
            user=self.basic_user,
            dataspace=self.basic_user.dataspace,
            extra_params="extra",
        )
        params = mock_session_get.call_args.kwargs["params"]
        expected = {
            "format": "json",
            "name__contains": get_hash_uid(self.basic_user.dataspace.uuid),
            "name__endswith": get_hash_uid(self.basic_user.uuid),
            "extra_params": "extra",
        }
        self.assertEqual(expected, params)

    @mock.patch("requests.sessions.Session.get")
    def test_scancodeio_fetch_scan_info(self, mock_session_get):
        uri = "https://uri"
        scancodeio = ScanCodeIO(self.basic_user)

        scancodeio.fetch_scan_info(uri=uri)
        params = mock_session_get.call_args.kwargs["params"]
        expected = {"format": "json", "name__startswith": get_hash_uid(uri)}
        self.assertEqual(expected, params)

        scancodeio.fetch_scan_info(
            uri=uri,
            user=self.basic_user,
            dataspace=self.basic_user.dataspace,
        )
        params = mock_session_get.call_args.kwargs["params"]
        expected = {
            "format": "json",
            "name__startswith": get_hash_uid(uri),
            "name__contains": get_hash_uid(self.basic_user.dataspace.uuid),
            "name__endswith": get_hash_uid(self.basic_user.uuid),
        }
        self.assertEqual(expected, params)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.request_get")
    def test_scancodeio_find_project(self, mock_request_get):
        scancodeio = ScanCodeIO(self.basic_user)
        scancodeio.find_project(name="project_name")
        params = mock_request_get.call_args.kwargs["params"]
        expected = {"name": "project_name"}
        self.assertEqual(expected, params)

        project_data = {
            "name": "project_name",
            "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
            "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
        }
        mock_request_get.return_value = {
            "count": 1,
            "results": [
                project_data,
            ],
        }
        self.assertEqual(project_data, scancodeio.find_project(name="project_name"))

        mock_request_get.return_value = {
            "count": 0,
            "results": [],
        }
        self.assertIsNone(scancodeio.find_project(name="not-existing"))

        mock_request_get.return_value = {
            "count": 2,
            "results": [
                project_data,
                project_data,
            ],
        }
        self.assertIsNone(scancodeio.find_project(name="project_name"))

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.get_scan_results")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    def test_scancodeio_update_from_scan(self, mock_fetch_scan_data, mock_get_scan_results):
        scancodeio = ScanCodeIO(self.basic_user)

        mock_get_scan_results.return_value = None
        mock_fetch_scan_data.return_value = None

        updated_fields = scancodeio.update_from_scan(self.package1, self.super_user)
        self.assertEqual([], updated_fields)

        mock_get_scan_results.return_value = {"url": "https://scancode.io/"}
        updated_fields = scancodeio.update_from_scan(self.package1, self.super_user)
        self.assertEqual([], updated_fields)

        mock_fetch_scan_data.return_value = {"error": "Summary file not available"}
        updated_fields = scancodeio.update_from_scan(self.package1, self.super_user)
        self.assertEqual([], updated_fields)

        mock_fetch_scan_data.return_value = {
            "declared_license_expression": "mit",
            "declared_holder": "Jeremy Thomas",
            "primary_language": "JavaScript",
            "key_files_packages": [
                {
                    "purl": "pkg:npm/bulma@0.9.4",
                    "type": "npm",
                    "namespace": "",
                    "name": "bulma",
                    "version": "0.9.4",
                    "qualifiers": "",
                    "subpath": "",
                    "primary_language": "JavaScript_from_package",
                    "description": "Modern CSS framework",
                    "release_date": None,
                    "homepage_url": "https://bulma.io",
                    "bug_tracking_url": "https://github.com/jgthms/bulma/issues",
                    "code_view_url": "",
                    "vcs_url": "git+https://github.com/jgthms/bulma.git",
                    "copyright": "",
                    "license_expression": "mit",
                    "notice_text": "",
                    "dependencies": [],
                    "keywords": ["css", "sass", "flexbox", "responsive", "framework"],
                }
            ],
        }
        updated_fields = scancodeio.update_from_scan(self.package1, self.super_user)
        expected = ["holder", "primary_language", "description", "homepage_url", "copyright"]
        self.assertEqual(expected, updated_fields)

        self.package1.refresh_from_db()
        self.assertEqual("Jeremy Thomas", self.package1.holder)
        self.assertEqual("JavaScript_from_package", self.package1.primary_language)
        self.assertEqual("Modern CSS framework", self.package1.description)
        self.assertEqual("https://bulma.io", self.package1.homepage_url)
        self.assertEqual("Copyright Jeremy Thomas", self.package1.copyright)
        # expected_keywords = ['css', 'sass', 'flexbox', 'responsive', 'framework']
        # self.assertEqual(expected_keywords, self.package1.keywords)

        self.assertEqual(self.super_user, self.package1.last_modified_by)
        history_entry = History.objects.get_for_object(self.package1).get()
        expected = (
            "Automatically updated holder, primary_language, description, "
            "homepage_url, copyright from scan results"
        )
        self.assertEqual(expected, history_entry.change_message)

        # Inferred Copyright statement
        mock_fetch_scan_data.return_value = {"key_files_packages": [{"name": "package1"}]}
        self.package1.copyright = ""
        self.package1.save()
        updated_fields = scancodeio.update_from_scan(self.package1, self.super_user)
        self.assertEqual(["copyright"], updated_fields)
        self.package1.refresh_from_db()
        self.assertEqual("Copyright package1 project contributors", self.package1.copyright)

        mock_fetch_scan_data.return_value = {"some_key": "some_value"}
        self.package1.name = "bulma"
        self.package1.copyright = ""
        self.package1.save()
        updated_fields = scancodeio.update_from_scan(self.package1, self.super_user)
        self.assertEqual(["copyright"], updated_fields)
        self.package1.refresh_from_db()
        self.assertEqual("Copyright bulma project contributors", self.package1.copyright)

    def test_scancodeio_map_detected_package_data(self):
        detected_package = {
            "purl": "pkg:maven/aopalliance/aopalliance@1.0",
            "primary_language": "Java",
            "declared_license_expression": "mit AND mit",
            "other_license_expression": "apache-20 AND apache-20",
            "keywords": [
                "json",
                "Development Status :: 5 - Production/Stable",
                "Operating System :: OS Independent",
            ],
            # skipped, no values
            "description": "",
            # skipped, not a SCAN_PACKAGE_FIELD
            "is_key_file": 1,
        }

        expected = {
            "package_url": "pkg:maven/aopalliance/aopalliance@1.0",
            "purl": "pkg:maven/aopalliance/aopalliance@1.0",
            "license_expression": "mit",
            "primary_language": "Java",
            # 'keywords': [
            #     'json',
            #     'Development Status :: 5 - Production/Stable',
            #     'Operating System :: OS Independent',
            # ],
        }
        mapped_data = ScanCodeIO.map_detected_package_data(detected_package)
        self.assertEqual(expected, mapped_data)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.request_get")
    def test_scancodeio_fetch_project_packages(self, mock_request_get):
        scancodeio = ScanCodeIO(self.basic_user)

        mock_request_get.return_value = None
        with self.assertRaises(Exception):
            scancodeio.fetch_project_packages(project_uuid="abcd")

        mock_request_get.return_value = {
            "next": None,
            "results": ["p1", "p2"],
        }
        packages = scancodeio.fetch_project_packages(project_uuid="abcd")
        self.assertEqual(["p1", "p2"], packages)

    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.get_vulnerable_purls")
    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.is_configured")
    def test_package_list_view_vulnerabilities(self, mock_is_configured, mock_vulnerable_purls):
        purl = "pkg:pypi/django@2.1"
        mock_is_configured.return_value = True

        self.package1.set_package_url(purl)
        self.package1.save()

        self.dataspace.enable_vulnerablecodedb_access = True
        self.dataspace.save()

        mock_vulnerable_purls.return_value = [purl]

        self.client.login(username=self.super_user.username, password="secret")
        package_list_url = reverse("component_catalog:package_list")
        response = self.client.get(package_list_url)

        self.assertContains(response, self.package1.identifier)
        self.assertContains(response, "#vulnerabilities")
        expected = '<i class="fas fa-bug vulnerability"></i>'
        self.assertContains(response, expected, html=True)

    def test_package_details_view_get_vulnerability_fields(self):
        self.package1.set_package_url("pkg:nginx/nginx@1.11.1")
        self.package1.save()
        copy_object(self.package1, Dataspace.objects.create(name="Other"), self.basic_user)

        get_vulnerability_fields = PackageDetailsView.get_vulnerability_fields
        fields = get_vulnerability_fields(vulnerability={}, dataspace=self.dataspace)
        self.assertEqual(fields[0], ("Summary", None, "Summary of the vulnerability"))

        vulnerability = {
            "vulnerability_id": "42d0a7c4-99e9-4506-b0c6-338ec2993147",
            "summary": "SQL Injection",
            "references": [
                {
                    "reference_id": "",
                    "reference_url": "http://www.openwall.com/lists/oss-security/2022/01/18/4",
                    "scores": [],
                },
                {
                    "reference_id": "CVE-2022-23305",
                    "reference_url": "https://nvd.nist.gov/vuln/detail/CVE-2022-23305",
                    "scores": [],
                },
            ],
            "fixed_packages": [
                {"purl": "pkg:nginx/nginx@1.11.1"},
                {"purl": "pkg:nginx/nginx@1.10.1"},
            ],
        }
        fields = get_vulnerability_fields(
            vulnerability=vulnerability,
            dataspace=self.dataspace,
        )
        self.assertEqual(fields[0], ("Summary", "SQL Injection", "Summary of the vulnerability"))
        self.assertEqual(fields[1][0], "Fixed packages")
        fixed_package_values = fields[1][1]
        self.assertIn("nginx/nginx@1.10.1", fixed_package_values)
        self.assertIn(
            '<a href="/packages/add/?package_url=pkg:nginx/nginx@1.10.1"',
            fixed_package_values,
        )
        self.assertIn(
            f'<a href="{self.package1.get_absolute_url()}">nginx/nginx@1.11.1</a>',
            fixed_package_values,
        )
        self.assertEqual(
            fields[2][0:2],
            (
                "Reference IDs",
                '<a href="https://nvd.nist.gov/vuln/detail/CVE-2022-23305" target="_blank">'
                "CVE-2022-23305"
                "</a>",
            ),
        )
        self.assertEqual(
            fields[3][0:2],
            (
                "Reference URLs",
                '<a target="_blank" href="http://www.openwall.com/lists/oss-security/2022/01/18/4" '
                'rel="nofollow">http://www.openwall.com/lists/oss-security/2022/01/18/4</a>',
            ),
        )

    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.get_vulnerabilities_by_purl")
    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.is_configured")
    def test_package_details_view_tab_vulnerabilities(
        self, mock_is_configured, mock_get_vulnerabilities_by_purl
    ):
        purl = "pkg:pypi/django@2.1"
        mock_is_configured.return_value = True

        self.package1.set_package_url(purl)
        self.package1.save()

        self.dataspace.enable_vulnerablecodedb_access = True
        self.dataspace.save()

        mock_get_vulnerabilities_by_purl.return_value = [
            {
                "purl": "pkg:pypi/django@2.1",
                "affected_by_vulnerabilities": [
                    {
                        "summary": "SQL Injection",
                        "references": [
                            {
                                "reference_id": "CVE-2022-23305",
                                "reference_url": "https://nvd.nist.gov/vuln/detail/CVE-2022-23305",
                            }
                        ],
                    },
                ],
            }
        ]

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(self.package1.details_url)

        expected = (
            '<button class="nav-link" id="tab_vulnerabilities-tab" data-bs-toggle="tab"'
            ' data-bs-target="#tab_vulnerabilities" type="button" role="tab"'
            ' aria-controls="tab_vulnerabilities" aria-selected="false">'
        )
        self.assertContains(response, expected)
        self.assertContains(response, 'id="tab_vulnerabilities"')
        expected = (
            '<a href="https://nvd.nist.gov/vuln/detail/CVE-2022-23305" target="_blank">'
            "CVE-2022-23305"
            "</a>"
        )
        self.assertContains(response, expected)

    def test_vulnerablecode_get_plain_purls(self):
        purls = get_plain_purls(packages=[])
        self.assertEqual([], purls)

        purls = get_plain_purls(packages=[self.package1, self.package2])
        self.assertEqual([], purls)

        self.package1.set_package_url("pkg:pypi/django@2.1")
        self.package1.save()

        purls = get_plain_purls(packages=[self.package1, self.package2])
        self.assertEqual(["pkg:pypi/django@2.1"], purls)

        self.package1.set_package_url("pkg:pypi/django@2.1?qualifier=1#subpath/")
        self.package1.save()
        purls = get_plain_purls(packages=[self.package1, self.package2])
        self.assertEqual(["pkg:pypi/django@2.1"], purls)

    def test_vulnerablecode_get_vulnerable_purls(self):
        vulnerablecode = VulnerableCode(self.basic_user)
        vulnerable_purls = vulnerablecode.get_vulnerable_purls(packages=[])
        self.assertEqual([], vulnerable_purls)

        vulnerable_purls = vulnerablecode.get_vulnerable_purls(
            packages=[self.package1, self.package2]
        )
        self.assertEqual([], vulnerable_purls)

        self.package1.set_package_url("pkg:pypi/django@2.1?qualifier=1#subpath")
        self.package1.save()

        with mock.patch(
            "dejacode_toolkit.vulnerablecode.VulnerableCode.bulk_search_by_purl"
        ) as bulk_search:
            bulk_search.return_value = []
            vulnerable_purls = vulnerablecode.get_vulnerable_purls(packages=[self.package1])
            self.assertEqual([], vulnerable_purls)

            bulk_search.return_value = ["pkg:pypi/django@2.1"]
            vulnerable_purls = vulnerablecode.get_vulnerable_purls(packages=[self.package1])
            self.assertEqual(["pkg:pypi/django@2.1"], vulnerable_purls)

    def test_vulnerablecode_get_vulnerable_cpes(self):
        vulnerablecode = VulnerableCode(self.basic_user)
        vulnerable_cpes = vulnerablecode.get_vulnerable_cpes(components=[])
        self.assertEqual([], vulnerable_cpes)

        components = [self.component1, self.component2]
        vulnerable_cpes = vulnerablecode.get_vulnerable_cpes(components=components)
        self.assertEqual([], vulnerable_cpes)

        self.component1.cpe = "cpe:2.3:a:djangoproject:django:0.95:*:*:*:*:*:*:*"
        self.component1.save()

        with mock.patch(
            "dejacode_toolkit.vulnerablecode.VulnerableCode.bulk_search_by_cpes"
        ) as bulk_search:
            bulk_search.return_value = [
                {
                    "vulnerability_id": "VCID-188m-1bke-aaae",
                    "summary": "The administrative interface in django.contrib.admin ",
                    "references": [
                        {"reference_id": ""},
                    ],
                }
            ]
            vulnerable_cpes = vulnerablecode.get_vulnerable_cpes(components=components)
            self.assertEqual([], vulnerable_cpes)

            bulk_search.return_value[0]["references"] = [{"reference_id": self.component1.cpe}]
            vulnerable_cpes = vulnerablecode.get_vulnerable_cpes(components=components)
            self.assertEqual([self.component1.cpe], vulnerable_cpes)

    @mock.patch("dejacode_toolkit.vulnerablecode.VulnerableCode.request_get")
    def test_vulnerablecode_get_vulnerabilities_cache(self, mock_request_get):
        vulnerablecode = VulnerableCode(self.basic_user)

        self.package1.set_package_url("pkg:pypi/django@2.1")
        self.package1.save()

        mock_request_get.return_value = {
            "count": 1,
            "results": True,
        }

        results = vulnerablecode.get_vulnerabilities_by_purl(self.package1.package_url)
        self.assertEqual(1, mock_request_get.call_count)
        self.assertTrue(results)

        results = vulnerablecode.get_vulnerabilities_by_purl(self.package1.package_url)
        # request.get was only called once since the results are returned from the cached
        # on the second call of `get_vulnerabilities_by_purl`.
        self.assertEqual(1, mock_request_get.call_count)
        self.assertTrue(results)

    def test_send_scan_notification(self):
        self.client.login(username=self.super_user.username, password="secret")
        view_name = "notifications:send_scan_notification"
        webhook_url = get_webhook_url(view_name, "wrong_uuid")
        self.assertIn("/notifications/send_scan_notification/", webhook_url)
        response = self.client.get(webhook_url)
        self.assertEqual(405, response.status_code)

        response = self.client.post(webhook_url)
        self.assertEqual(404, response.status_code)

        data = {
            "project": {
                "uuid": "5f2cdda6-fe86-4587-81f1-4d407d4d2c02",
                "name": "project_name",
                "input_sources": [
                    {
                        "uuid": "8e454229-70f4-476f-a56f-2967eb2e8f4c",
                        "filename": self.package1.filename,
                        "download_url": self.package1.download_url,
                        "is_uploaded": False,
                        "tag": "",
                        "size": 8731,
                        "is_file": True,
                        "exists": True,
                    }
                ],
            },
            "run": {
                "uuid": "b45149cf-9e4c-41e5-8824-6abe7207551a",
                "pipeline_name": "scan_single_package",
                "status": "success",
            },
        }

        response = self.client.post(webhook_url, data=data, content_type="application/json")
        self.assertEqual(404, response.status_code)

        webhook_url = get_webhook_url(view_name, self.super_user.uuid)
        response = self.client.post(webhook_url, data=data, content_type="application/json")
        self.assertEqual(200, response.status_code)
        self.assertEqual(b'{"message": "Notification created"}', response.content)

        notif = Notification.objects.get()
        self.assertTrue(notif.unread)
        self.assertEqual(self.super_user, notif.actor)
        self.assertEqual("Scan success", notif.verb)
        self.assertEqual(self.package1, notif.action_object)
        self.assertEqual(self.super_user, notif.recipient)
        self.assertEqual(self.package1.download_url, notif.description)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.update_from_scan")
    def test_send_scan_notification_update_package_from_scan(self, mock_update_from_scan):
        self.client.login(username=self.super_user.username, password="secret")

        data = {
            "project": {
                "uuid": "5f2cdda6-fe86-4587-81f1-4d407d4d2c02",
                "name": "project_name",
                "input_sources": [
                    {
                        "uuid": "8e454229-70f4-476f-a56f-2967eb2e8f4c",
                        "filename": self.package1.filename,
                        "download_url": self.package1.download_url,
                        "is_uploaded": False,
                        "tag": "",
                        "size": 8731,
                        "is_file": True,
                        "exists": True,
                    }
                ],
            },
            "run": {
                "uuid": "b45149cf-9e4c-41e5-8824-6abe7207551a",
                "pipeline_name": "scan_single_package",
                "status": "success",
            },
        }

        view_name = "notifications:send_scan_notification"
        webhook_url = get_webhook_url(view_name, self.super_user.uuid)
        response = self.client.post(webhook_url, data=data, content_type="application/json")
        self.assertEqual(200, response.status_code)
        self.assertEqual(b'{"message": "Notification created"}', response.content)
        mock_update_from_scan.assert_not_called()

        mock_update_from_scan.return_value = ["license_expression", "homepage_url"]
        self.dataspace.enable_package_scanning = True
        self.dataspace.update_packages_from_scan = True
        self.dataspace.save()
        response = self.client.post(webhook_url, data=data, content_type="application/json")
        self.assertEqual(200, response.status_code)
        self.assertEqual(b'{"message": "Notification created"}', response.content)
        mock_update_from_scan.assert_called_once()
        notif = Notification.objects.latest("timestamp")
        expected = "Automatically updated license_expression, homepage_url from scan results"
        self.assertIn(expected, notif.description)

    def test_package_details_mark_notifications_as_read(self):
        package_url = self.package1.get_absolute_url()
        self.client.login(username=self.super_user.username, password="secret")
        self.client.get(package_url)

        notification = Notification.objects.create(
            actor=self.super_user,
            verb="Scan completed",
            action_object=self.package1,
            recipient=self.super_user,
            description=self.package1.download_url,
        )
        self.assertTrue(notification.unread)

        self.client.get(package_url)
        notification.refresh_from_db()
        self.assertFalse(notification.unread)

    @mock.patch("dejacode_toolkit.purldb.PurlDB.request_get")
    @mock.patch("dejacode_toolkit.purldb.PurlDB.is_configured")
    def test_package_details_view_purldb_tab(self, mock_is_configured, mock_request_get):
        self.client.login(username=self.super_user.username, password="secret")

        mock_is_configured.return_value = True
        mock_request_get.return_value = {
            "count": 1,
            "results": [
                {
                    "uuid": "7b947095-ab4c-45e3-8af3-6a73bd88e31d",
                    "uri": "http://repo1.maven.org/maven2/abbot/abbot/1.4.0/abbot-1.4.0.jar",
                    "filename": "abbot-1.4.0.jar",
                    "release_date": "2015-09-22",
                    "type": "maven",
                    "namespace": "abbot",
                    "name": "abbot",
                    "version": "1.4.0",
                    "qualifiers": None,
                    "subpath": None,
                    "primary_language": "Java",
                    "description": "Abbot Java GUI Test Library",
                    "parties": [
                        {
                            "type": "person",
                            "role": "developper",
                            "name": "Gerard Davisonr",
                            "email": "gerard.davison@oracle.com",
                            "url": None,
                        }
                    ],
                    "keywords": [],
                    "homepage_url": "http://abbot.sf.net/",
                    "download_url": "http://repo1.maven.org/maven2/abbot/abbot/"
                    "1.4.0/abbot-1.4.0.jar",
                    "size": 687192,
                    "sha1": "a2363646a9dd05955633b450010b59a21af8a423",
                    "md5": None,
                    "bug_tracking_url": None,
                    "code_view_url": None,
                    "vcs_url": None,
                    "copyright": None,
                    "license_expression": "(bsd-new OR eps-1.0 OR apache-2.0 OR mit) AND unknown",
                    "declared_license": "EPL\nhttps://www.eclipse.org/legal/eps-v10.html",
                    "notice_text": None,
                    "contains_source_code": None,
                    "manifest_path": None,
                    "dependencies": [],
                    "source_packages": ["pkg:maven/abbot/abbot@1.4.0?classifier=sources"],
                    "package_url": "pkg:maven/abbot/abbot@1.4.0",
                }
            ],
        }

        self.assertFalse(self.super_user.dataspace.enable_purldb_access)
        expected = 'id="tab_purldb"'
        response = self.client.get(self.package1.get_absolute_url())
        self.assertNotContains(response, expected)

        self.dataspace.enable_purldb_access = True
        self.dataspace.save()
        self.super_user.refresh_from_db()
        self.assertTrue(self.super_user.dataspace.enable_purldb_access)
        response = self.client.get(self.package1.get_absolute_url())
        self.assertContains(response, expected)
        self.assertContains(response, '<pre class="pre-bg-body-tertiary mb-1 field-download-url">')

        response = self.client.get(self.package1.get_url("tab_purldb"))
        self.assertContains(
            response,
            '<pre class="pre-bg-body-tertiary mb-1 field-sha1">'
            "a2363646a9dd05955633b450010b59a21af8a423"
            "</pre>",
        )
        self.assertContains(
            response, '<pre class="pre-bg-body-tertiary mb-1 field-release-date">2015-09-22</pre>'
        )
        self.assertContains(
            response, '<pre class="pre-bg-body-tertiary mb-1 field-primary-language">Java</pre>'
        )
        self.assertContains(response, '<pre class="pre-bg-body-tertiary mb-1 field-homepage-url">')

    def test_component_catalog_package_add_view_permission_access(self):
        add_url = reverse("component_catalog:package_add")
        response = self.client.get(add_url)
        self.assertEqual(302, response.status_code)
        self.assertRedirects(response, f"/login/?next={add_url}")

        self.super_user.is_superuser = False
        self.super_user.is_staff = False
        self.super_user.save()
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(add_url)
        self.assertEqual(403, response.status_code)

        self.super_user = add_perm(self.super_user, "add_package")
        response = self.client.get(add_url)
        self.assertEqual(200, response.status_code)

    def test_component_catalog_package_update_view_permission_access(self):
        change_url = self.package1.get_change_url()
        response = self.client.get(change_url)
        self.assertEqual(302, response.status_code)
        self.assertRedirects(response, f"/login/?next={quote(change_url)}")

        self.super_user.is_superuser = False
        self.super_user.is_staff = False
        self.super_user.save()
        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get(change_url)
        self.assertEqual(403, response.status_code)

        self.super_user = add_perm(self.super_user, "change_package")
        response = self.client.get(change_url)
        self.assertEqual(200, response.status_code)

    def test_component_catalog_package_add_view_create_proper(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.assertTrue(self.super_user.is_superuser)
        add_url = reverse("component_catalog:package_add")

        response = self.client.post(add_url, data={}, follow=True)
        expected = "<li>A Filename or a Package URL (type + name) is required.</li>"
        self.assertContains(response, expected, html=True)

        data = {
            "filename": "name.zip",
            "license_expression": self.license1.key,
            "copyright": "Copyright",
            "notice_text": "Notice",
            "description": "Description",
            "primary_language": "Python",
            "homepage_url": "https://nexb.com",
            "release_date": "2019-03-01",
            "submit": "Add Package",
        }

        response = self.client.post(add_url, data, follow=True)
        package = Package.objects.get(filename="name.zip")
        self.assertEqual(self.license1.key, package.license_expression)
        expected = "Package &quot;name.zip&quot; was successfully created."
        self.assertContains(response, expected)

    @mock.patch("dejacode_toolkit.purldb.PurlDB.request_get")
    @mock.patch("dejacode_toolkit.purldb.PurlDB.is_configured")
    def test_component_catalog_package_add_view_initial_data(
        self, mock_is_configured, mock_request_get
    ):
        self.client.login(username=self.super_user.username, password="secret")
        add_url = reverse("component_catalog:package_add")

        mock_is_configured.return_value = True
        self.dataspace.enable_purldb_access = True
        self.dataspace.save()

        puyrldb_entry = {
            "filename": "abbot-1.4.0.jar",
            "release_date": "2015-09-22",
            "type": "maven",
            "namespace": "abbot",
            "name": "abbot",
            "version": "1.4.0",
            "qualifiers": "",
            "subpath": "",
            "primary_language": "Java",
            "description": "Abbot Java GUI Test Library",
            "declared_license_expression": "bsd-new OR eps-1.0 OR apache-2.0 OR mit",
        }
        mock_request_get.return_value = {
            "count": 1,
            "results": [puyrldb_entry],
        }

        response = self.client.get(add_url)
        self.assertEqual({}, response.context["form"].initial)

        response = self.client.get(add_url + "?package_url=pkg:maven/abbot/abbot@1.4.0")
        expected = {
            "filename": "abbot-1.4.0.jar",
            "release_date": "2015-09-22",
            "type": "maven",
            "namespace": "abbot",
            "name": "abbot",
            "version": "1.4.0",
            "primary_language": "Java",
            "description": "Abbot Java GUI Test Library",
            "license_expression": "bsd-new OR eps-1.0 OR apache-2.0 OR mit",
        }
        self.assertEqual(expected, response.context["form"].initial)

    @mock.patch("dje.tasks.scancodeio_submit_scan.delay")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.is_configured")
    def test_component_catalog_package_add_view_create_with_submit_scan(
        self, mock_is_configured, mock_submit_scan
    ):
        mock_is_configured.return_value = True

        self.client.login(username=self.super_user.username, password="secret")
        self.assertTrue(self.super_user.is_superuser)
        add_url = reverse("component_catalog:package_add")

        expected_get = "Package scanning is enabled in your Dataspace"
        response = self.client.get(add_url)
        self.assertNotContains(response, expected_get)

        data = {
            "filename": "name.zip",
            "download_url": "https://nexb.com",
            "submit": "Add Package",
        }
        response = self.client.post(add_url, data, follow=True)
        expected_post = "The Package Download URL was submitted to ScanCode.io for scanning"
        self.assertNotContains(response, expected_post)
        self.assertEqual(0, mock_submit_scan.call_count)

        self.dataspace.enable_package_scanning = True
        self.dataspace.save()

        response = self.client.get(add_url)
        self.assertContains(response, expected_get)
        data["filename"] = "name1.zip"
        response = self.client.post(add_url, data, follow=True)
        self.assertContains(response, expected_post)
        self.assertEqual(1, mock_submit_scan.call_count)

    def test_component_catalog_package_update_view_proper(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.assertTrue(self.super_user.is_superuser)
        change_url = self.package1.get_change_url()

        data = {
            "filename": "name.zip",
            "license_expression": self.license1.key,
            "copyright": "Copyright",
            "notice_text": "Notice",
            "description": "Description",
            "primary_language": "Python",
            "homepage_url": "https://nexb.com",
            "release_date": "2019-03-01",
            "submit": "Update Package",
        }

        response = self.client.post(change_url, data, follow=True)
        package = Package.objects.get(filename="name.zip")
        self.assertEqual(self.license1.key, package.license_expression)
        expected = "Package &quot;name.zip&quot; was successfully updated."
        self.assertContains(response, expected)

    def test_component_catalog_package_update_view_no_changes(self):
        self.client.login(username=self.super_user.username, password="secret")
        self.assertTrue(self.super_user.is_superuser)

        data = {
            "filename": self.package1.filename,
            "download_url": self.package1.download_url,
            "license_expression": self.package1.license_expression,
            "collect_data": 0,
            "submit": "Update Package",
        }

        change_url = self.package1.get_change_url()
        response = self.client.post(change_url, data, follow=True)
        expected = "No fields changed."
        self.assertContains(response, expected)

    def test_component_catalog_package_delete_view(self):
        delete_url = self.package1.get_delete_url()
        details_url = self.package1.details_url
        self.client.login(username=self.basic_user.username, password="secret")

        response = self.client.get(details_url)
        self.assertEqual(200, response.status_code)
        self.assertNotContains(response, delete_url)

        response = self.client.get(delete_url)
        self.assertEqual(403, response.status_code)

        self.basic_user = add_perm(self.basic_user, "delete_package")
        response = self.client.get(details_url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, delete_url)

        package1_id = self.package1.id
        response = self.client.get(delete_url)
        self.assertTrue(self.package1.component_set.exists())
        self.assertEqual(200, response.status_code)
        self.assertContains(response, f"Delete {self.package1}")
        expected = f'Are you sure you want to delete "{self.package1}"?'
        self.assertContains(response, expected, html=True)
        expected = '<input type="submit" class="btn btn-danger" value="Confirm deletion">'
        self.assertContains(response, expected, html=True)
        response = self.client.post(delete_url, follow=True)
        self.assertRedirects(response, reverse("component_catalog:package_list"))
        self.assertContains(response, "was successfully deleted.")
        self.assertFalse(Package.objects.filter(id=package1_id).exists())

    def test_component_catalog_package_form_add(self):
        self.super_user.is_superuser = False
        self.super_user.is_staff = False
        self.super_user.save()
        self.super_user = add_perm(self.super_user, "add_package")

        # `change_usage_policy_on_package` permission
        self.assertFalse(self.super_user.has_perm("change_usage_policy_on_package"))

        UsagePolicy.objects.create(
            label="Approved",
            icon="icon-ok-circle",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.dataspace,
        )
        policy_approved = UsagePolicy.objects.create(
            label="Approved",
            icon="icon-ok-circle",
            content_type=ContentType.objects.get_for_model(Package),
            dataspace=self.dataspace,
        )
        data = {
            "filename": "a filename",
            "usage_policy": policy_approved.pk,
        }
        form = PackageForm(user=self.super_user, data=data)
        self.assertEqual(0, len(form.fields["usage_policy"].queryset))
        self.assertTrue(form.is_valid())
        package = form.save()
        self.assertIsNone(package.usage_policy)

        data["filename"] = "with policy"
        self.super_user = add_perm(self.super_user, "change_usage_policy_on_package")
        form = PackageForm(user=self.super_user, data=data)
        self.assertEqual(1, len(form.fields["usage_policy"].queryset))
        self.assertTrue(form.is_valid())
        package = form.save()
        self.assertEqual(policy_approved, package.usage_policy)

    def test_component_catalog_package_form_add_package_url_validation(self):
        data = {"filename": "filename"}
        form = PackageForm(user=self.super_user, data=data)
        self.assertTrue(form.is_valid())

        data = {
            "filename": "filename",
            "type": "type",
            "namespace": "namespace",
            "name": "name",
            "version": "version",
            "qualifiers": "qualifiers",
            "subpath": "subpath",
        }
        form = PackageForm(user=self.super_user, data=data)
        self.assertFalse(form.is_valid())
        errors = {
            "__all__": ["Invalid qualifier. Must be a string of key=value pairs:['qualifiers']"]
        }
        self.assertEqual(errors, form.errors)

        data.update(
            {
                "type": "".join(map(str, range(100))),
                "qualifiers": "valid=value",
            }
        )
        form = PackageForm(user=self.super_user, data=data)
        self.assertFalse(form.is_valid())
        errors = {
            "__all__": ["Invalid purl: type is a required argument."],
            "type": ["Ensure this value has at most 16 characters (it has 190)."],
        }
        self.assertEqual(errors, form.errors)

        data.update({"type": "valid_type"})
        form = PackageForm(user=self.super_user, data=data)
        self.assertTrue(form.is_valid())
        package = form.save()
        self.assertEqual(
            "pkg:valid_type/namespace/name@version?valid=value#subpath", package.package_url
        )

    def test_component_catalog_package_form_identifiter_validation(self):
        data = {
            "type": "type",
            "name": "name",
        }
        form = PackageForm(user=self.super_user, data=data)
        self.assertTrue(form.is_valid())

        data = {
            "filename": "filename",
        }
        form = PackageForm(user=self.super_user, data=data)
        self.assertTrue(form.is_valid())

        data = {
            "type": "type",
        }
        form = PackageForm(user=self.super_user, data=data)
        self.assertFalse(form.is_valid())

        data = {
            "type": "type",
            "name": "name",
            "qualifiers": "not valid",
        }
        form = PackageForm(user=self.super_user, data=data)
        self.assertFalse(form.is_valid())

        data = {
            "download_url": "http://download.url",
        }
        form = PackageForm(user=self.super_user, data=data)
        self.assertFalse(form.is_valid())

    def test_component_catalog_package_form_unicity_validation(self):
        package1 = Package.objects.create(filename="p1.zip", dataspace=self.dataspace)

        errors = {
            "__all__": [
                "Package with this Dataspace, Type, Namespace, Name, Version, Qualifiers, Subpath, "
                "Download URL and Filename already exists."
            ]
        }

        data = {"filename": package1.filename}
        form = PackageForm(user=self.super_user, data=data)
        self.assertFalse(form.is_valid())
        self.assertEqual(errors, form.errors)

        package1.download_url = "https://download.url"
        package1.save()
        data["download_url"] = package1.download_url
        form = PackageForm(user=self.super_user, data=data)
        self.assertFalse(form.is_valid())
        self.assertEqual(errors, form.errors)

        data["type"] = "purl_type"
        form = PackageForm(user=self.super_user, data=data)
        self.assertFalse(form.is_valid())
        self.assertEqual({"__all__": ["Invalid purl: name is a required argument."]}, form.errors)

        data["name"] = "purl_name"
        form = PackageForm(user=self.super_user, data=data)
        self.assertTrue(form.is_valid())


class PackageCollectDataTestCase(TransactionTestCase):
    """
    Django's TestCase class Wrap each test in a transaction and rolls back
    that transaction after each test, in order to provide test isolation.
    This means that no transaction is ever actually committed, thus your
    on_commit() callbacks will never be run.
    If you need to test the results of an on_commit() callback, use a
    TransactionTestCase instead.
    https://code.djangoproject.com/ticket/30457
    See https://adamj.eu/tech/2020/05/20/
    the-fast-way-to-test-django-transaction-on-commit-callbacks/
    """

    @mock.patch("dje.tasks.package_collect_data")
    def test_component_catalog_package_add_view_create_with_collect_data(self, mock_collect_data):
        dataspace = Dataspace.objects.create(name="Dataspace")
        super_user = create_superuser("super_user", dataspace)

        self.client.login(username=super_user.username, password="secret")
        add_url = reverse("component_catalog:package_add")

        expected_get = "Automatically collect the SHA1, MD5, and Size"
        response = self.client.get(add_url)
        self.assertContains(response, expected_get)

        data = {
            "filename": "name.zip",
            "download_url": "https://nexb.com",
            "submit": "Add Package",
        }
        response = self.client.post(add_url, data, follow=True)
        expected_post = "SHA1, MD5, and Size data collection in progress"
        self.assertNotContains(response, expected_post)
        self.assertEqual(0, len(mock_collect_data.mock_calls))

        data["filename"] = "name1.zip"
        data["collect_data"] = True
        response = self.client.post(add_url, data, follow=True)
        self.assertContains(response, expected_post)
        self.assertEqual(1, len(mock_collect_data.mock_calls))

    @mock.patch("dje.tasks.package_collect_data")
    def test_component_catalog_package_update_view_with_collect_data(self, mock_collect_data):
        dataspace = Dataspace.objects.create(name="Dataspace")
        super_user = create_superuser("super_user", dataspace)
        self.client.login(username=super_user.username, password="secret")

        package = Package.objects.create(dataspace=dataspace, type="pypi", name="django")
        change_url = package.get_change_url()

        expected_get = "Automatically collect the SHA1, MD5, and Size"
        response = self.client.get(change_url)
        self.assertContains(response, expected_get)

        data = {
            "filename": "name.zip",
            "download_url": "https://nexb.com",
            "submit": "Update Package",
            "collect_data": True,
        }
        response = self.client.post(change_url, data, follow=True)
        self.assertContains(response, "was successfully updated")
        self.assertEqual(1, len(mock_collect_data.mock_calls))

    @mock.patch("dje.tasks.package_collect_data")
    def test_component_catalog_package_update_view_save_as_with_collect_data(
        self, mock_collect_data
    ):
        dataspace = Dataspace.objects.create(name="Dataspace")
        super_user = create_superuser("super_user", dataspace)
        self.client.login(username=super_user.username, password="secret")

        package = Package.objects.create(dataspace=dataspace, type="pypi", name="django")
        change_url = package.get_change_url()

        expected_get = "Automatically collect the SHA1, MD5, and Size"
        response = self.client.get(change_url)
        self.assertContains(response, expected_get)

        data = {
            "type": package.type,
            "name": package.name,
            "version": "1.0",
            "download_url": "https://nexb.com",
            "save_as_new": "Save as new",
            "collect_data": True,
        }
        response = self.client.post(change_url, data, follow=True)
        self.assertContains(response, "was successfully cloned")
        self.assertEqual(1, len(mock_collect_data.mock_calls))


class ComponentListViewTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(
            name="nexB",
            show_type_in_component_list_view=True,
            show_usage_policy_in_user_views=False,
        )
        self.user = User.objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.dataspace
        )
        self.basic_user = create_user("basic_user", self.dataspace)
        self.owner1 = Owner.objects.create(
            name="Organization1",
            homepage_url="http://www.example.com",
            contact_info="john.doe@example.com",
            notes="More information",
            dataspace=self.dataspace,
        )
        self.owner2 = Owner.objects.create(name="Organization2", dataspace=self.dataspace)
        self.type1 = ComponentType.objects.create(
            label="Type1", notes="notes", dataspace=self.dataspace
        )
        self.type2 = ComponentType.objects.create(
            label="Type2", notes="notes", dataspace=self.dataspace
        )
        self.type3 = ComponentType.objects.create(
            label="Type3", notes="notes", dataspace=self.dataspace
        )
        self.type4 = ComponentType.objects.create(
            label="Type4", notes="notes", dataspace=self.dataspace
        )
        self.component1 = Component.objects.create(
            owner=self.owner1,
            name="Component ABC",
            type=self.type1,
            version="2.0.10",
            description="A very useful component.",
            copyright="Foobar Software 2012",
            primary_language="Python",
            keywords=["Django Tool"],
            dataspace=self.dataspace,
        )
        self.component1_dup1 = Component.objects.create(
            owner=self.owner1,
            type=self.type1,
            name="Component ABC",
            version="2.0.2",
            primary_language="JavaScript",
            dataspace=self.dataspace,
        )
        self.component1_dup2 = Component.objects.create(
            owner=self.owner1,
            name="Component ABC",
            version="2.0.1",
            primary_language="Python",
            dataspace=self.dataspace,
        )
        self.component1_dup3 = Component.objects.create(
            owner=self.owner1,
            name="Component ABC",
            version="",
            primary_language="Python",
            dataspace=self.dataspace,
        )
        self.c1 = Component.objects.create(
            name="c1 foo",
            owner=self.owner1,
            dataspace=self.dataspace,
            type=self.type1,
            primary_language="Python",
        )
        self.c2 = Component.objects.create(
            name="c2 foo",
            owner=self.owner1,
            dataspace=self.dataspace,
            type=self.type2,
            primary_language="Python",
        )
        self.c3 = Component.objects.create(
            name="c3", owner=self.owner2, dataspace=self.dataspace, type=self.type3
        )
        self.c4 = Component.objects.create(
            name="c4", owner=self.owner2, dataspace=self.dataspace, type=self.type4
        )
        self.Z1 = Component.objects.create(
            name="Z1", owner=self.owner2, dataspace=self.dataspace, type=self.type4
        )

    def test_component_catalog_list_view_num_queries(self):
        self.client.login(username="nexb_user", password="t3st")
        with self.assertNumQueries(18):
            self.client.get(reverse("component_catalog:component_list"))

    def test_component_catalog_list_view_default(self):
        self.client.login(username="nexb_user", password="t3st")

        url = reverse("component_catalog:component_list")
        response = self.client.get(url)
        self.assertEqual(9, len(response.context["object_list"]))
        expected = '<strong><a href="{}">{}</a></strong>'.format(
            self.component1.get_absolute_url(), self.component1.name
        )
        self.assertContains(response, expected, html=True)
        expected = '<a href="{}#owner">{}</a>'.format(
            self.component1.get_absolute_url(), self.owner1.name
        )
        self.assertContains(response, expected, html=True)

    def test_component_catalog_list_view_search(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("component_catalog:component_list")
        data = {"q": self.component1.name}
        response = self.client.get(url, data)
        object_list = list(response.context["object_list"])
        expected = [
            self.component1_dup3,
            self.component1_dup2,
            self.component1,
            self.component1_dup1,
        ]
        self.assertEqual(expected, object_list)

    def test_component_catalog_list_view_version_grouping(self):
        view = ComponentListView.as_view()
        factory = RequestFactory()
        request = factory.get(reverse("component_catalog:component_list"))
        request.user = self.user
        request.session = SessionBase()

        response = view(request)
        name_version_groups = response.context_data["name_version_groups"]

        # The collation is different on Ubuntu (good) and OSX (bad)
        # using assertIn to ensure the test to work locally
        self.assertIn([self.Z1], name_version_groups)
        self.assertIn([self.c1], name_version_groups)
        self.assertIn([self.c2], name_version_groups)
        self.assertIn([self.c3], name_version_groups)
        self.assertIn([self.c4], name_version_groups)
        expected = [
            self.component1_dup3,
            self.component1,
            self.component1_dup1,
            self.component1_dup2,
        ]
        self.assertIn(expected, name_version_groups)

    def test_component_catalog_list_view_version_grouping_order_is_highest_version_first(self):
        view = ComponentListView.as_view()
        factory = RequestFactory()
        request = factory.get(reverse("component_catalog:component_list"))
        request.user = self.user
        request.session = SessionBase()

        response = view(request)
        name_version_groups = response.context_data["name_version_groups"]
        # Force a sort since the original ordering from the DB differ between OS (Ubuntu vs. OSX)
        group = sorted(name_version_groups, key=lambda group: len(group))[-1]
        expected = ["", "2.0.10", "2.0.2", "2.0.1"]
        self.assertEqual(expected, [x.version for x in group])

    def test_component_catalog_list_view_version_grouping_is_only_when_no_sort(self):
        self.client.login(username="nexb_user", password="t3st")
        url = reverse("component_catalog:component_list")

        response = self.client.get(url, {"sort": "primary_language"})
        self.assertFalse(response.context["is_grouping_active"])

        response = self.client.get(url, {"sort": ""})
        self.assertTrue(response.context["is_grouping_active"])

    def test_component_catalog_list_view_usage_policy_availability(self):
        self.client.login(username="nexb_user", password="t3st")
        list_url = reverse("component_catalog:component_list")
        details_url = self.component1.get_absolute_url()

        policy_approved = UsagePolicy.objects.create(
            label="Approved",
            icon="icon-ok-circle",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.component1.dataspace,
        )
        self.component1.usage_policy = policy_approved
        self.component1.save()

        self.assertFalse(self.dataspace.show_usage_policy_in_user_views)

        response = self.client.get(list_url)
        self.assertNotContains(response, "Usage policy")
        response = self.client.get(details_url)
        self.assertNotContains(response, "Usage policy")

        # Let's enable the display of usage_policy
        self.dataspace.show_usage_policy_in_user_views = True
        self.dataspace.save()

        response = self.client.get(list_url)
        self.assertContains(response, "Policy")
        self.assertContains(response, '<th class="column-usage_policy" scope="col">')
        expected = """
        <span class="cursor-help policy-icon" data-bs-toggle="tooltip" title="Approved">
            <i class="icon-ok-circle" style="color: #000000;"></i>
        </span>
        """

        self.assertContains(response, expected, html=True)
        response = self.client.get(details_url)
        self.assertContains(response, "Usage policy")

    def test_component_catalog_list_view_admin_links(self):
        self.client.login(username=self.user.username, password="t3st")
        url = reverse("component_catalog:component_list")
        response = self.client.get(url)

        expected1 = '<a class="btn btn-success pe-2" href="/components/add/">Add Component</a>'
        expected2 = (
            '<a href="/admin/component_catalog/component/import/" class="dropdown-item">'
            "Import components</a>"
        )

        self.assertContains(response, expected1, html=True)
        self.assertContains(response, expected2, html=True)

        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.save()
        response = self.client.get(url)
        self.assertNotContains(response, expected1, html=True)
        self.assertNotContains(response, expected2, html=True)

        self.user.is_staff = True
        self.user.save()
        response = self.client.get(url)
        self.assertNotContains(response, expected1, html=True)
        self.assertNotContains(response, expected2, html=True)

        self.user.is_staff = False
        self.user.save()
        self.user = add_perm(self.user, "add_component")
        response = self.client.get(url)
        self.assertContains(response, expected1, html=True)
        self.assertContains(response, expected2, html=True)

    def test_component_catalog_list_view_request_links(self):
        self.client.login(username="nexb_user", password="t3st")

        component_ct = ContentType.objects.get_for_model(Component)
        request_template_product = RequestTemplate.objects.create(
            name="P",
            description="D",
            dataspace=self.user.dataspace,
            is_active=True,
            content_type=component_ct,
        )
        Request.objects.create(
            title="Title",
            request_template=request_template_product,
            requester=self.user,
            content_object=self.component1,
            dataspace=self.dataspace,
        )

        response = self.client.get(reverse("component_catalog:component_list"))
        expected = """
        <a href="{}#activity" class="r-link">
            <span class="badge text-bg-request">R</span>
        </a>""".format(
            self.component1.get_absolute_url()
        )
        self.assertContains(response, expected, html=True)

    def test_component_list_multi_send_about_files_view(self):
        multi_about_files_url = reverse("component_catalog:component_multi_about_files")
        response = self.client.get(multi_about_files_url)
        self.assertEqual(302, response.status_code)

        self.assertTrue(self.user.is_superuser)
        self.client.login(username=self.user.username, password="t3st")
        response = self.client.get(reverse("component_catalog:component_list"))

        self.assertContains(response, 'id="download-aboutcode-files"')
        self.assertContains(response, f'href="{multi_about_files_url}"')

        response = self.client.get(multi_about_files_url)
        self.assertEqual(404, response.status_code)

        response = self.client.get(f"{multi_about_files_url}?ids=not-good")
        self.assertEqual(404, response.status_code)

        response = self.client.get(f"{multi_about_files_url}?ids={self.component1.id},{self.c2.id}")
        self.assertEqual(200, response.status_code)
        self.assertEqual("application/zip", response["Content-Type"])
        self.assertEqual("22", response["Content-Length"])
        self.assertEqual(
            'attachment; filename="component_about.zip"', response["Content-Disposition"]
        )

    def test_component_catalog_list_view_license_expression(self):
        self.client.login(username="nexb_user", password="t3st")
        component_list_url = reverse("component_catalog:component_list")

        l1 = License.objects.create(
            key="l1", name="L1", short_name="L1", owner=self.owner1, dataspace=self.dataspace
        )

        self.component1.license_expression = l1.key
        self.component1.save()
        self.assertIn(l1, self.component1.licenses.all())

        response = self.client.get(component_list_url)
        expected = (
            f'<td class="text-break"><span class="license-expression">'
            f'<a href="{l1.get_absolute_url()}" title="{l1.short_name}">{l1.key}</a>'
            f"</span></td>"
        )
        self.assertNotContains(response, expected, html=True)

        self.dataspace.show_usage_policy_in_user_views = True
        self.dataspace.save()
        response = self.client.get(component_list_url)
        self.assertContains(response, expected, html=True)

    def test_component_catalog_component_add_view_permission_access(self):
        add_url = reverse("component_catalog:component_add")
        response = self.client.get(add_url)
        self.assertEqual(302, response.status_code)
        self.assertRedirects(response, f"/login/?next={add_url}")

        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.save()
        self.client.login(username=self.user.username, password="t3st")
        response = self.client.get(add_url)
        self.assertEqual(403, response.status_code)

        self.user = add_perm(self.user, "add_component")
        response = self.client.get(add_url)
        self.assertEqual(200, response.status_code)

    def test_component_catalog_component_update_view_permission_access(self):
        change_url = self.component1.get_change_url()
        response = self.client.get(change_url)
        self.assertEqual(302, response.status_code)
        self.assertRedirects(response, f"/login/?next={quote(change_url)}")

        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.save()
        self.client.login(username=self.user.username, password="t3st")
        response = self.client.get(change_url)
        self.assertEqual(403, response.status_code)

        self.user = add_perm(self.user, "change_component")
        response = self.client.get(change_url)
        self.assertEqual(200, response.status_code)

    def test_component_catalog_component_add_view_create_proper(self):
        self.client.login(username=self.user.username, password="t3st")
        self.assertTrue(self.user.is_superuser)
        add_url = reverse("component_catalog:component_add")

        l1 = License.objects.create(
            key="l1", name="L1", short_name="L1", owner=self.owner1, dataspace=self.dataspace
        )
        configuration_status = ComponentStatus.objects.create(
            label="Status1", dataspace=self.dataspace
        )
        keyword = ComponentKeyword.objects.create(label="Keyword1", dataspace=self.dataspace)

        data = {
            "name": "Name",
            "version": "1.0",
            "owner": self.owner1.name,
            "license_expression": l1.key,
            "copyright": "Copyright",
            "notice_text": "Notice",
            "description": "Description",
            "keywords": keyword.label,
            "primary_language": "Python",
            "homepage_url": "https://nexb.com",
            "configuration_status": configuration_status.pk,
            "release_date": "2019-03-01",
            "submit": "Add Component",
        }

        response = self.client.post(add_url, data, follow=True)
        component = Component.objects.get(name="Name", version="1.0")
        self.assertEqual(self.owner1, component.owner)
        self.assertEqual(configuration_status, component.configuration_status)
        self.assertEqual(l1.key, component.license_expression)
        self.assertTrue(component.is_active)
        expected = "Component &quot;Name 1.0&quot; was successfully created."
        self.assertContains(response, expected)

    def test_component_catalog_component_update_view_proper(self):
        self.client.login(username=self.user.username, password="t3st")
        self.assertTrue(self.user.is_superuser)
        change_url = self.component1.get_change_url()

        l1 = License.objects.create(
            key="l1", name="L1", short_name="L1", owner=self.owner1, dataspace=self.dataspace
        )
        configuration_status = ComponentStatus.objects.create(
            label="Status1", dataspace=self.dataspace
        )
        keyword = ComponentKeyword.objects.create(label="Keyword1", dataspace=self.dataspace)

        data = {
            "name": "Name",
            "version": "1.0",
            "owner": self.owner1.name,
            "license_expression": l1.key,
            "copyright": "Copyright",
            "notice_text": "Notice",
            "description": "Description",
            "keywords": keyword.label,
            "primary_language": "Python",
            "homepage_url": "https://nexb.com",
            "configuration_status": configuration_status.pk,
            "release_date": "2019-03-01",
            "submit": "Update Product",
        }

        response = self.client.post(change_url, data, follow=True)
        component = Component.objects.get(name="Name", version="1.0")
        self.assertEqual(self.owner1, component.owner)
        self.assertEqual(configuration_status, component.configuration_status)
        self.assertEqual(l1.key, component.license_expression)
        self.assertEqual([keyword.label], component.keywords)
        expected = "Component &quot;Name 1.0&quot; was successfully updated."
        self.assertContains(response, expected)

        keyword2 = ComponentKeyword.objects.create(label="Keyword2", dataspace=self.dataspace)
        data["keywords"] = keyword2.label
        change_url = component.get_change_url()
        response = self.client.post(change_url, data, follow=True)
        self.assertContains(response, expected)
        component = Component.objects.get(name="Name", version="1.0")
        self.assertEqual([keyword2.label], component.keywords)

        data["keywords"] = f"{keyword.label}, {keyword2.label}"
        response = self.client.post(change_url, data, follow=True)
        self.assertContains(response, expected)
        component = Component.objects.get(name="Name", version="1.0")
        self.assertEqual(sorted([keyword.label, keyword2.label]), sorted(component.keywords))

        data["keywords"] = ""
        response = self.client.post(change_url, data, follow=True)
        self.assertContains(response, expected)
        component = Component.objects.get(name="Name", version="1.0")
        self.assertEqual(0, len(component.keywords))

    def test_component_catalog_component_update_view_no_changes(self):
        self.client.login(username=self.user.username, password="t3st")
        self.assertTrue(self.user.is_superuser)

        c1 = Component.objects.create(name="C", version="1", dataspace=self.dataspace)
        data = {
            "name": c1.name,
            "version": c1.version,
            "submit": "Update Component",
        }

        change_url = c1.get_change_url()
        response = self.client.post(change_url, data, follow=True)
        self.assertContains(response, "No fields changed.")

    def test_component_catalog_component_delete_view(self):
        delete_url = self.component1.get_delete_url()
        details_url = self.component1.details_url
        self.client.login(username=self.basic_user.username, password="secret")

        response = self.client.get(details_url)
        self.assertEqual(200, response.status_code)
        self.assertNotContains(response, delete_url)

        response = self.client.get(delete_url)
        self.assertEqual(403, response.status_code)

        self.basic_user = add_perm(self.basic_user, "delete_component")
        response = self.client.get(details_url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, delete_url)

        component1_id = self.component1.id
        response = self.client.get(delete_url)
        self.assertFalse(self.component1.packages.exists())
        self.assertEqual(200, response.status_code)
        self.assertContains(response, f"Delete {self.component1}")
        expected = f'Are you sure you want to delete "{self.component1}"?'
        self.assertContains(response, expected, html=True)
        expected = '<input type="submit" class="btn btn-danger" value="Confirm deletion">'
        self.assertContains(response, expected, html=True)
        response = self.client.post(delete_url, follow=True)
        self.assertRedirects(response, reverse("component_catalog:component_list"))
        self.assertContains(response, "was successfully deleted.")
        self.assertFalse(Package.objects.filter(id=component1_id).exists())

    def test_component_catalog_component_update_save_as_new(self):
        self.client.login(username=self.user.username, password="t3st")

        self.assertTrue(self.user.is_superuser)
        add_url = reverse("component_catalog:component_add")
        response = self.client.get(add_url)
        expected = 'value="Save as new"'
        self.assertNotContains(response, expected)

        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.save()
        self.user = add_perm(self.user, "change_component")
        change_url = self.component1.get_change_url()
        response = self.client.get(change_url)
        self.assertNotContains(response, expected)

        self.user = add_perm(self.user, "add_component")
        response = self.client.get(change_url)
        self.assertContains(response, expected)

        package1 = Package.objects.create(filename="package1", dataspace=self.dataspace)
        ComponentAssignedPackage.objects.create(
            component=self.component1, package=package1, dataspace=self.dataspace
        )
        Subcomponent.objects.create(
            parent=self.component1, child=self.component1_dup2, dataspace=self.dataspace
        )
        initial_count = Component.objects.count()

        data = {
            "name": self.component1.name,
            "version": "new version",
            "save_as_new": "Save as new",
        }

        response = self.client.post(change_url, data, follow=True)

        new_count = Component.objects.count()
        self.assertEqual(new_count, initial_count + 1)
        cloned_component = Component.objects.latest("id")
        self.assertRedirects(response, cloned_component.get_absolute_url())

        expected = f"Component &quot;{cloned_component}&quot; was successfully cloned."
        self.assertContains(response, expected)

        self.assertNotEqual(self.component1.id, cloned_component.id)
        self.assertEqual(1, len(cloned_component.keywords))
        self.assertEqual(1, cloned_component.packages.count())
        self.assertEqual(1, cloned_component.children.count())

    def test_component_catalog_component_form_add(self):
        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.save()
        self.user = add_perm(self.user, "add_component")

        owner = Owner.objects.create(name="Own", dataspace=self.dataspace)
        status = ComponentStatus.objects.create(label="Status1", dataspace=self.dataspace)
        keyword = ComponentKeyword.objects.create(label="Key1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="l1",
            name="L1",
            short_name="L1",
            owner=owner,
            is_active=False,
            dataspace=self.dataspace,
        )

        alternate_dataspace = Dataspace.objects.create(name="Alternate")
        alternate_owner = Owner.objects.create(name="Owner1", dataspace=alternate_dataspace)
        alternate_status = ComponentStatus.objects.create(
            label="Status1", dataspace=alternate_dataspace
        )
        ComponentKeyword.objects.create(label="Alternate", dataspace=alternate_dataspace)

        form = ComponentForm(user=self.user)

        # Dataspace scoping
        self.assertEqual(3, len(form.fields["owner"].queryset))
        self.assertIn(owner, form.fields["owner"].queryset)
        self.assertNotIn(alternate_owner, form.fields["owner"].queryset)

        self.assertEqual(1, len(form.fields["configuration_status"].queryset))
        self.assertIn(status, form.fields["configuration_status"].queryset)
        self.assertNotIn(alternate_status, form.fields["configuration_status"].queryset)

        self.assertEqual([(keyword.label, keyword.label)], form.fields["keywords"].choices)

        # NameVersionValidationFormMixin
        data = {
            "name": self.component1.name,
            "version": self.component1.version,
        }
        form = ComponentForm(user=self.user, data=data)
        self.assertFalse(form.is_valid())
        errors = {"__all__": ["Component with this Dataspace, Name and Version already exists."]}
        self.assertEqual(errors, form.errors)

        # `change_usage_policy_on_component` permission
        self.assertFalse(self.user.has_perm("change_usage_policy_on_component"))
        policy_approved = UsagePolicy.objects.create(
            label="Approved",
            icon="icon-ok-circle",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=self.component1.dataspace,
        )
        data = {
            "name": "a name",
            "usage_policy": policy_approved.pk,
        }
        form = ComponentForm(user=self.user, data=data)
        self.assertEqual(0, len(form.fields["usage_policy"].queryset))
        self.assertTrue(form.is_valid())
        component = form.save()
        self.assertIsNone(component.usage_policy)

        data["version"] = "with policy"
        self.user = add_perm(self.user, "change_usage_policy_on_component")
        form = ComponentForm(user=self.user, data=data)
        self.assertEqual(1, len(form.fields["usage_policy"].queryset))
        self.assertTrue(form.is_valid())
        component = form.save()
        self.assertEqual(policy_approved, component.usage_policy)

        # Save
        data = {
            "name": "Name",
            "version": "1.0",
            "owner": owner.name,
            "license_expression": license1.key,
            "copyright": "Copyright",
            "notice_text": "Notice",
            "description": "Description",
            "keywords": [keyword.label],
            "primary_language": "Python",
            "homepage_url": "https://nexb.com",
            "configuration_status": status.pk,
            "release_date": "2019-03-01",
            "submit": "Add Component",
        }
        form = ComponentForm(user=self.user, data=data)
        self.assertTrue(form.is_valid())
        component = form.save()
        self.assertEqual(owner, component.owner)
        self.assertEqual(status, component.configuration_status)
        self.assertEqual(license1.key, component.license_expression)

    def test_component_catalog_component_form_assigned_packages(self):
        data = {
            "name": "Name",
            "version": "1.0",
            "packages_ids": "",
            "submit": "Add Component",
        }

        form = ComponentForm(user=self.user, data=data)
        self.assertTrue(form.is_valid())

        data["packages_ids"] = []
        form = ComponentForm(user=self.user, data=data)
        self.assertTrue(form.is_valid())

        data["packages_ids"] = "bad,value"
        form = ComponentForm(user=self.user, data=data)
        self.assertFalse(form.is_valid())
        expected = {"packages_ids": ["Wrong value type for bad"]}
        self.assertEqual(expected, form.errors)

        data["packages_ids"] = ["bad", "values"]
        form = ComponentForm(user=self.user, data=data)
        self.assertFalse(form.is_valid())
        expected = {"packages_ids": ["Wrong value type for ['bad'"]}
        self.assertEqual(expected, form.errors)

        data["packages_ids"] = "888,999"
        form = ComponentForm(user=self.user, data=data)
        self.assertTrue(form.is_valid())
        component = form.save()
        self.assertEqual(0, component.packages.count())
        component.delete()

        package1 = Package.objects.create(filename="p1", dataspace=self.dataspace)
        data["packages_ids"] = f"{package1.id}"
        form = ComponentForm(user=self.user, data=data)
        self.assertTrue(form.is_valid())
        component = form.save()
        self.assertEqual(1, component.packages.count())


class GrappelliRelatedViewTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="other")
        self.user = User.objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.dataspace
        )
        self.other_user = User.objects.create_superuser(
            "other_user", "test@test.com", "t3st", self.other_dataspace
        )

        self.owner = Owner.objects.create(name="Owner", dataspace=self.dataspace)
        self.other_owner = Owner.objects.create(name="Other_Org", dataspace=self.other_dataspace)
        self.c1 = Component.objects.create(name="c1", dataspace=self.dataspace)
        self.other_component = Component.objects.create(
            owner=self.other_owner, name="Other Component", dataspace=self.other_dataspace
        )

    def test_related_label_has_correct_target(self):
        self.client.login(username="nexb_user", password="t3st")
        url = "{}?object_id={}&app_label=component_catalog&model_name=component".format(
            reverse("grp_related_lookup"), self.c1.pk
        )
        response = self.client.get(url)
        expected = [{"label": "{0}".format(self.c1), "safe": False, "value": str(self.c1.pk)}]
        self.assertEqual(expected, json.loads(response.content))

    def test_reference_dataspace_users_access_another_dataspaces_through_grappelli_lookup(self):
        # Users in the reference dataspace can see all objects
        self.client.login(username="nexb_user", password="t3st")
        self.assertTrue(self.user.dataspace.is_reference)
        url = "{}?object_id={}&app_label=component_catalog&model_name=component".format(
            reverse("grp_related_lookup"), self.other_component.pk
        )
        response = self.client.get(url)
        expected = [
            {
                "label": "{0}".format(self.other_component),
                "safe": False,
                "value": str(self.other_component.pk),
            }
        ]
        self.assertEqual(expected, json.loads(response.content))
        self.assertEqual(200, response.status_code)

    def test_non_reference_dataspace_users_cannot_access_another_objects_through_grappelli(self):
        # Users in a non-reference dataspace cannot see objects in other
        # dataspaces
        self.client.login(username="other_user", password="t3st")
        self.assertFalse(self.other_user.dataspace.is_reference)
        url = "{}?object_id={}&app_label=component_catalog&model_name=component".format(
            reverse("grp_related_lookup"), self.c1.pk
        )
        response = self.client.get(url)
        expected = [{"value": str(self.c1.pk), "safe": False, "label": "?"}]
        self.assertEqual(expected, json.loads(response.content))
        self.assertEqual(200, response.status_code)

    def test_non_reference_dataspace_users_access_grappelli_autocomplete_lookup(self):
        # Users in a non-reference dataspace cannot see objects in other dataspaces
        self.client.login(username="other_user", password="t3st")
        self.assertFalse(self.other_user.dataspace.is_reference)
        url = (
            reverse("grp_autocomplete_lookup")
            + "?term=c1&app_label=component_catalog&model_name=component"
        )
        response = self.client.get(url)
        expected = [{"label": "0 results", "value": None}]
        self.assertEqual(expected, json.loads(response.content))
        self.assertEqual(200, response.status_code)

    def test_reference_dataspace_users_grappelli_autocomplete_lookup_scope(self):
        # Editing an object from another dataspace as a reference user
        self.client.login(username="nexb_user", password="t3st")
        self.assertTrue(self.user.dataspace.is_reference)
        url = (
            reverse("grp_autocomplete_lookup")
            + "?term=other&app_label=organization&model_name=owner"
        )
        response = self.client.get(url)
        # No referer, search is scope to the current user dataspace
        expected = [{"label": "0 results", "value": None}]
        self.assertEqual(expected, json.loads(response.content))
        self.assertEqual(200, response.status_code)

        # Fake referer, search is scope to the current user dataspace
        response = self.client.get(url, HTTP_REFERER="/some/location/")
        expected = [{"label": "0 results", "value": None}]
        self.assertEqual(expected, json.loads(response.content))
        self.assertEqual(200, response.status_code)

        # Now with a proper referer, we manage to find in the other dataspace
        referer = self.other_component.get_admin_url()
        response = self.client.get(url, HTTP_REFERER=referer)
        expected = [{"label": f"{self.other_owner}", "value": self.other_owner.pk}]
        self.assertEqual(expected, json.loads(response.content))
        self.assertEqual(200, response.status_code)

        # Addition case, should always be the user dataspace
        referer = reverse("admin:component_catalog_component_add")
        url = (
            reverse("grp_autocomplete_lookup") + "?term=own&app_label=organization&model_name=owner"
        )
        response = self.client.get(url, HTTP_REFERER=referer)
        expected = [{"label": f"{self.owner}", "value": self.owner.pk}]
        self.assertEqual(expected, json.loads(response.content))
        self.assertEqual(200, response.status_code)

    def test_grappelli_autocomplete_missing_model_declaration(self):
        # We're looking in a Model that has neither the
        # autocomplete_search_fields() defined nor an entry in
        # AUTOCOMPLETE_SEARCH_FIELDS
        # See https://github.com/sehmaschine/django-grappelli/pull/440
        self.client.login(username="nexb_user", password="t3st")
        self.assertTrue(self.user.dataspace.is_reference)
        url = (
            reverse("grp_autocomplete_lookup")
            + "?term=other&app_label=license_library&model_name=licensetag"
        )
        response = self.client.get(url)
        self.assertContains(response, '[{"value": null, "label": "0 results"}]')

    def test_grappelli_m2m_lookup_url_is_disabled(self):
        self.client.login(username="nexb_user", password="t3st")
        url = "grappelli/lookup/m2m/"
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)


class ComponentCrossDataspaceAccessControlTestCase(TestCase):
    def setUp(self):
        from product_portfolio.models import Product

        self.pw = "ch3tst"

        self.dnx = Dataspace.objects.create(name="nexB")
        self.unx = self.create_user(self.dnx, "udnx", True, True)
        self.nxc1 = Component.objects.create(name="dnxc1", dataspace=self.dnx)
        self.nxc2 = Component.objects.create(name="dnxc2", version="v2", dataspace=self.dnx)
        self.nxp1 = Product.objects.create(name="nxp1", dataspace=self.dnx)
        self.nxp2 = Product.objects.create(name="nxp2", version="v2", dataspace=self.dnx)

        self.dano = Dataspace.objects.create(name="public")
        self.udano = self.create_user(self.dano, "udano")
        self.dmc1 = Component.objects.create(name="danoc1", dataspace=self.dano)
        self.dmc2 = Component.objects.create(name="danoc2", version="v2", dataspace=self.dano)
        self.dmp1 = Product.objects.create(name="danop1", dataspace=self.dano)
        self.dmp2 = Product.objects.create(name="danop2", version="v2", dataspace=self.dano)

        self.d1 = Dataspace.objects.create(name="d1")
        self.ud1 = self.create_user(self.d1, "ud1")
        self.sd1 = self.create_user(self.d1, "sd1", True)
        self.supd1 = self.create_user(self.d1, "supd1", True, True)
        self.d1o1 = Owner.objects.create(name="d1o1", dataspace=self.d1)
        self.d1c1 = Component.objects.create(name="d1c1", dataspace=self.d1)
        self.d1c2 = Component.objects.create(name="d1c2", version="v2", dataspace=self.d1)
        self.d1p1 = Product.objects.create(name="d1p1", dataspace=self.d1)
        self.d1p2 = Product.objects.create(name="d1p2", version="v2", dataspace=self.d1)

        self.d2 = Dataspace.objects.create(name="d2")
        self.ud2 = self.create_user(self.d2, "ud2")
        self.sd2 = self.create_user(self.d2, "sd2", True)
        self.supd2 = self.create_user(self.d2, "supd2", True, True)
        self.d2c1 = Component.objects.create(name="d2c1", dataspace=self.d2)
        self.d2c2 = Component.objects.create(name="d2c2", version="v2", dataspace=self.d2)
        self.d2p1 = Product.objects.create(name="d2p1", dataspace=self.d2)
        self.d2p2 = Product.objects.create(name="d2p2", version="v2", dataspace=self.d2)

    def create_user(self, dataspace, name, is_staff=False, is_super=False):
        user = User.objects.create_user(name, "t@t.com", self.pw, dataspace)
        user.is_staff = is_staff
        user.is_superuser = is_super
        user.save()
        return user

    def ensure_dataspace_is_authorized_or_404(self, request, dataspace):
        """
        Given a request and a `dataspace1 object, ensure that the request user
        dataspace is the same as the `dataspace`. If not raise a 404 exception.
        """
        # the request must contain a user and a dataspace.
        user_ds = request.user.dataspace
        if not user_ds or not dataspace or user_ds != dataspace:
            raise Http404()

    def ensure_not_authorized_http302(self, url):
        response = self.client.get(url)
        self.assertContains(response, "", status_code=302)

    def ensure_page_not_found_http404(self, url):
        response = self.client.get(url)
        self.assertContains(response, "Page not found", status_code=404)

    def ensure_attrib_ok_http200(self, url):
        response = self.client.get(url)  # Attribution configuration
        self.assertEqual(200, response.status_code)
        response = self.client.get(url + "?submit=1")  # Attribution generation
        self.assertContains(response, "<h1>Attribution for", status_code=200)

    def ensure_attrib_not_found_http404(self, url):
        response = self.client.get(url)  # Attribution configuration
        self.assertEqual(404, response.status_code)
        response = self.client.get(url + "?submit=1")  # Attribution generation
        self.assertEqual(404, response.status_code)

    def login(self, user):
        self.client.login(username=user.username, password=self.pw)

    def ensure_user_authorized_in_ds(self, user, ds):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        self.ensure_dataspace_is_authorized_or_404(request, ds)

    def ensure_user_not_authorized_in_ds(self, user, ds):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        self.assertRaises(Http404, self.ensure_dataspace_is_authorized_or_404, request, ds)

    @override_settings(ANONYMOUS_USERS_DATASPACE="public")
    def test_ensure_dataspace_is_authorized_or_404(self):
        authorized_ds = [
            (self.ud1, self.d1),
            (self.sd1, self.d1),
            (self.supd1, self.d1),
            (self.udano, self.dano),
            (self.unx, self.dnx),
        ]
        for user, ds in authorized_ds:
            self.ensure_user_authorized_in_ds(user, ds)

    @override_settings(ANONYMOUS_USERS_DATASPACE="public")
    def test_ensure_dataspace_is_authorized_or_404_not_authorized(self):
        authorized_ds = [
            (self.ud1, self.d2),
            (self.sd1, self.d2),
            (self.supd1, self.d2),
            (self.udano, self.d2),
            (self.unx, self.d2),
        ]
        for user, ds in authorized_ds:
            self.ensure_user_not_authorized_in_ds(user, ds)

    @override_settings(ANONYMOUS_USERS_DATASPACE="public")
    def test_anonymous_user_cannot_generate_attribution_anywhere(self):
        user_attrib_urls = [
            "/products/nexB/dnxc1/attribution/",
            "/products/nexB/dnxc2/v2/attribution/",
            "/products/public/danoc1/attribution/",
            "/products/public/danoc2/v2/attribution/",
            "/products/d1/d1c1/attribution/",
            "/products/d1/d1c2/v2/attribution/",
            "/products/d2/d2c1/attribution/",
            "/products/d2/d2c2/v2/attribution/",
        ]
        for url in user_attrib_urls:
            self.ensure_not_authorized_http302(url)

    @override_settings(ANONYMOUS_USERS_DATASPACE="public")
    def test_logged_in_demo_user_cannot_generate_attribution_elsewhere(self):
        user_attrib_urls = [
            "/products/nexB/dnxc1/attribution/",
            "/products/nexB/dnxc2/v2/attribution/",
            "/products/d1/d1c1/attribution/",
            "/products/d1/d1c2/v2/attribution/",
            "/products/d2/d2c1/attribution/",
            "/products/d2/d2c2/v2/attribution/",
        ]
        self.login(self.udano)
        for url in user_attrib_urls:
            self.ensure_page_not_found_http404(url)

    @override_settings(ANONYMOUS_USERS_DATASPACE="public")
    def test_logged_in_demo_user_can_generate_attribution_in_demo(self):
        import guardian.shortcuts

        user_attrib_urls = [
            self.dmp1.get_attribution_url(),  # '/products/public/danop1/attribution/'
            self.dmp2.get_attribution_url(),  # '/products/public/danop2/v2/attribution/'
        ]
        self.login(self.udano)

        self.assertFalse(len(guardian.shortcuts.get_user_perms(self.udano, Product)))
        for url in user_attrib_urls:
            self.ensure_attrib_not_found_http404(url)

        guardian.shortcuts.assign_perm("product_portfolio.view_product", self.udano, self.dmp1)
        guardian.shortcuts.assign_perm("product_portfolio.view_product", self.udano, self.dmp2)

        for url in user_attrib_urls:
            self.ensure_attrib_ok_http200(url)

    def test_superuser_in_regular_ds_cannot_generate_attribution_elsewhere(self):
        user_attrib_urls = [
            "/products/nexB/dnxp1/attribution/",
            "/products/nexB/dnxp2/v2/attribution/",
            "/products/public/danop1/attribution/",
            "/products/public/danop2/v2/attribution/",
            "/products/d2/d2p1/attribution/",
            "/products/d2/d2p2/v2/attribution/",
        ]
        self.login(self.supd1)
        for url in user_attrib_urls:
            self.ensure_page_not_found_http404(url)

    def test_superuser_in_regular_ds_can_generate_attribution_in_own_ds(self):
        user_attrib_urls = [
            "/products/d1/d1p1/attribution/",
            "/products/d1/d1p2/v2/attribution/",
        ]
        self.login(self.supd1)
        for url in user_attrib_urls:
            self.ensure_attrib_ok_http200(url)

    def test_standard_user_in_regular_ds_cannot_generate_attribution_elsewhere(self):
        user_attrib_urls = [
            "/products/nexB/dnxp1/attribution/",
            "/products/nexB/dnxp2/v2/attribution/",
            "/products/public/danop1/attribution/",
            "/products/public/danop2/v2/attribution/",
            "/products/d2/d2p1/attribution/",
            "/products/d2/d2p2/v2/attribution/",
        ]
        self.login(self.supd1)
        for url in user_attrib_urls:
            self.ensure_page_not_found_http404(url)

    def test_standard_user_in_regular_ds_can_generate_attribution_in_own_ds(self):
        user_attrib_urls = [
            "/products/d1/d1p1/attribution/",
            "/products/d1/d1p2/v2/attribution/",
        ]
        self.login(self.supd1)
        for url in user_attrib_urls:
            self.ensure_attrib_ok_http200(url)

    @override_settings(ANONYMOUS_USERS_DATASPACE="public", REFERENCE_DATASPACE="nexB")
    def test_anonymous_user_cannot_access_reference_data(self):
        url = reverse("component_catalog:component_list")
        self.assertEqual(200, self.client.get(url).status_code)

        url = reverse("component_catalog:component_list", args=[self.dano])
        self.assertEqual(404, self.client.get(url).status_code)

        url = reverse("component_catalog:component_list", args=[self.dnx])
        self.assertEqual(404, self.client.get(url).status_code)

        self.nxc1.is_active = True
        self.nxc1.save()
        self.nxc2.is_active = True
        self.nxc2.save()
        self.d1c1.is_active = True
        self.d1c1.save()
        self.d1c2.is_active = True
        self.d1c2.save()
        self.dmc1.is_active = True
        self.dmc1.save()
        self.dmc2.is_active = True
        self.dmc2.save()

        self.assertEqual(404, self.client.get(self.nxc1.get_absolute_url()).status_code)
        self.assertEqual(404, self.client.get(self.nxc2.get_absolute_url()).status_code)
        self.assertEqual(404, self.client.get(self.d1c1.get_absolute_url()).status_code)
        self.assertEqual(404, self.client.get(self.d1c2.get_absolute_url()).status_code)
        self.assertEqual(200, self.client.get(self.dmc1.get_absolute_url()).status_code)
        self.assertEqual(200, self.client.get(self.dmc2.get_absolute_url()).status_code)
