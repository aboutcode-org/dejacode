#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import apps
from django.contrib.auth.models import Group
from django.test import TestCase

from dje.models import Dataspace
from dje.models import DataspaceConfiguration
from dje.permissions import get_all_tabsets
from dje.permissions import get_authorized_tabs
from dje.permissions import get_protected_fields
from dje.permissions import get_tabset_for_model
from dje.tests import add_perms
from dje.tests import create_superuser
from dje.tests import create_user

Owner = apps.get_model("organization", "Owner")
License = apps.get_model("license_library", "License")
Component = apps.get_model("component_catalog", "Component")
Subcomponent = apps.get_model("component_catalog", "Subcomponent")
Package = apps.get_model("component_catalog", "Package")
ProductComponent = apps.get_model("product_portfolio", "ProductComponent")


class DejaCodePermissionTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("super_user", self.dataspace)
        self.basic_user = create_user("basic_user", self.dataspace)

    def test_permissions_get_protected_fields(self):
        test_input = [
            # permission_protected_fields not defined on Owner
            ([], Owner, self.super_user),
            ([], License, self.super_user),
            ([], Component, self.super_user),
            ([], Subcomponent, self.super_user),
            ([], ProductComponent, self.super_user),
            ([], Owner, self.basic_user),
            (["usage_policy"], License, self.basic_user),
            (["usage_policy"], Component, self.basic_user),
            (["usage_policy"], Subcomponent, self.basic_user),
            (["usage_policy"], Package, self.basic_user),
            (["review_status"], ProductComponent, self.basic_user),
        ]

        for expected, model_class, user in test_input:
            self.assertEqual(expected, get_protected_fields(model_class, user))

        perms = [
            "change_usage_policy_on_license",
            "change_usage_policy_on_component",
            "change_usage_policy_on_subcomponent",
            "change_usage_policy_on_package",
            "change_review_status_on_productcomponent",
        ]
        self.basic_user = add_perms(self.basic_user, perms)

        test_input = [
            # permission_protected_fields not defined on Owner
            ([], Owner, self.basic_user),
            ([], License, self.basic_user),
            ([], Component, self.basic_user),
            ([], Subcomponent, self.basic_user),
            ([], Package, self.basic_user),
            ([], ProductComponent, self.basic_user),
        ]

        for expected, model_class, user in test_input:
            self.assertEqual(expected, get_protected_fields(model_class, user))

    def test_permissions_get_all_tabsets(self):
        expected = {
            "owner": [
                "essentials",
                "licenses",
                "components",
                "hierarchy",
                "external_references",
                "history",
            ],
            "component": [
                "essentials",
                "notice",
                "owner",
                "license",
                "hierarchy",
                "subcomponents",
                "product_usage",
                "packages",
                "activity",
                "external_references",
                "usage_policy",
                "legal",
                "vulnerabilities",
                "history",
            ],
            "package": [
                "essentials",
                "license",
                "terms",
                "urls",
                "checksums",
                "others",
                "components",
                "product_usage",
                "activity",
                "external_references",
                "usage_policy",
                "scan",
                "purldb",
                "vulnerabilities",
                "aboutcode",
                "history",
            ],
            "license": [
                "essentials",
                "license_text",
                "license_conditions",
                "urls",
                "owner",
                "activity",
                "external_references",
                "usage_policy",
                "history",
            ],
            "product": [
                "essentials",
                "inventory",
                "codebase",
                "hierarchy",
                "notice",
                "license",
                "owner",
                "dependencies",
                "activity",
                "imports",
                "history",
            ],
        }

        tabsets = get_all_tabsets()
        tabs = {model_name: list(tabset.keys()) for model_name, tabset in tabsets.items()}
        self.assertEqual(expected, tabs)

    def test_permissions_get_tabset_for_model(self):
        self.assertEqual(None, get_tabset_for_model(Dataspace))

        expected = {
            "essentials": {
                "fields": [
                    "name",
                    "homepage_url",
                    "type",
                    "contact_info",
                    "alias",
                    "notes",
                    "urn",
                    "dataspace",
                ],
            },
            "licenses": {
                "fields": ["licenses"],
            },
            "components": {
                "fields": ["components"],
            },
            "hierarchy": {},
            "external_references": {
                "fields": ["external_references"],
            },
            "history": {
                "fields": [
                    "created_date",
                    "created_by",
                    "last_modified_date",
                    "last_modified_by",
                ],
            },
        }
        self.assertEqual(expected, get_tabset_for_model(Owner))

        expected = [
            "essentials",
            "license_text",
            "license_conditions",
            "urls",
            "owner",
            "activity",
            "external_references",
            "usage_policy",
            "history",
        ]
        self.assertEqual(expected, list(get_tabset_for_model(License).keys()))

    def test_permissions_get_authorized_tabs(self):
        self.assertEqual(0, self.basic_user.groups.count())

        self.assertIsNone(get_authorized_tabs(Owner, self.basic_user))

        configuration = DataspaceConfiguration.objects.create(
            dataspace=self.dataspace, tab_permissions=[]
        )
        self.assertIsNone(get_authorized_tabs(Owner, self.basic_user))

        configuration.tab_permissions = {}
        configuration.save()
        self.assertIsNone(get_authorized_tabs(Owner, self.basic_user))

        configuration.tab_permissions = ""
        configuration.save()
        self.assertIsNone(get_authorized_tabs(Owner, self.basic_user))

        group1 = Group.objects.create(name="Group1")
        configuration.tab_permissions = {"Group1": {"owner": ["licenses"]}}
        configuration.save()
        self.assertEqual([None], get_authorized_tabs(Owner, self.basic_user))

        self.basic_user.groups.add(group1)
        self.assertEqual(["licenses"], get_authorized_tabs(Owner, self.basic_user))

        self.basic_user.groups.add(Group.objects.create(name="Group2"))
        configuration.tab_permissions = {
            "Group1": {"owner": ["licenses"]},
            "Group2": {"owner": ["components"]},
        }
        configuration.save()
        self.assertEqual(
            sorted(["components", "licenses"]), sorted(get_authorized_tabs(Owner, self.basic_user))
        )

        # Superuser users see all the tabs
        self.assertIsNone(get_authorized_tabs(Owner, self.super_user))
