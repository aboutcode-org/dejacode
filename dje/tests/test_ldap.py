#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging
from unittest import mock

from django.apps import apps
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

import ldap
import slapdtest
from django_auth_ldap.backend import _LDAPUserGroups
from django_auth_ldap.config import GroupOfNamesType
from django_auth_ldap.config import LDAPSearch
from guardian.shortcuts import assign_perm
from ldap.ldapobject import SimpleLDAPObject

from dje.ldap_backend import DejaCodeLDAPBackend
from dje.models import Dataspace
from dje.models import DataspaceConfiguration
from dje.tests import create_superuser
from dje.tests import create_user

DejacodeUser = get_user_model()
Component = apps.get_model("component_catalog", "Component")
Product = apps.get_model("product_portfolio", "Product")


LDIF = """
dn: o=test
objectClass: organization
o: test

dn: ou=people,o=test
objectClass: organizationalUnit
ou: people

dn: ou=groups,o=test
objectClass: organizationalUnit
ou: groups

dn: uid=bob,ou=people,o=test
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: posixAccount
cn: bob
uid: bob
userPassword: secret
uidNumber: 1001
gidNumber: 50
givenName: Robert
sn: Smith
homeDirectory: /home/bob
mail: bob@test.com

dn: cn=active,ou=groups,o=test
cn: active
objectClass: groupOfNames
member: uid=bob,ou=people,o=test
"""


@override_settings(
    AUTHENTICATION_BACKENDS=("dje.ldap_backend.DejaCodeLDAPBackend",),
    AUTH_LDAP_DATASPACE="nexB",
    AUTH_LDAP_START_TLS=False,
    AUTH_LDAP_USER_DN_TEMPLATE="uid=%(user)s,ou=people,o=test",
    AUTH_LDAP_USER_SEARCH=LDAPSearch("ou=people,o=test", ldap.SCOPE_SUBTREE, "(uid=%(user)s)"),
    AUTH_LDAP_UBIND_AS_AUTHENTICATING_USER=True,
    AUTH_LDAP_USER_ATTR_MAP={
        "first_name": "givenName",
        "last_name": "sn",
        "email": "mail",
    },
    AUTH_LDAP_GROUP_SEARCH=LDAPSearch(
        "ou=groups,o=test", ldap.SCOPE_SUBTREE, "(objectClass=groupOfNames)"
    ),
    AUTH_LDAP_GROUP_TYPE=GroupOfNamesType(),
)
class DejaCodeLDAPBackendTestCase(TestCase):
    server_class = slapdtest.SlapdObject
    ldap_object_class = SimpleLDAPObject

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.configure_logger()

        cls.server = cls.server_class()
        cls.server.suffix = "o=test"
        cls.server.openldap_schema_files = [
            "core.ldif",
            "cosine.ldif",
            "inetorgperson.ldif",
            "nis.ldif",
        ]
        cls.server.start()
        cls.server.ldapadd(LDIF)

        # Override the AUTH_LDAP_SERVER_URI with the dynamic URI
        cls._settings_override = override_settings(AUTH_LDAP_SERVER_URI=cls.server.ldap_uri)
        cls._settings_override.enable()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        # Disable the settings override
        cls._settings_override.disable()

    @classmethod
    def configure_logger(cls):
        logger = logging.getLogger("django_auth_ldap")
        # Set the following to logging.DEBUG for a verbose output
        logger.setLevel(logging.CRITICAL)

    def setUp(self):
        cache.clear()

        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.dejacode_group_active = Group.objects.create(name="active")
        self.dejacode_group1 = Group.objects.create(name="group1")
        change_license_perm = Permission.objects.get_by_natural_key(
            "change_license", "license_library", "license"
        )
        self.dejacode_group_active.permissions.add(change_license_perm)

    def test_ldap_authentication_populate_user(self):
        user = authenticate(username="bob", password="secret")
        self.assertEqual(user.username, "bob")
        self.assertEqual(user.first_name, "Robert")
        self.assertEqual(user.last_name, "Smith")
        self.assertEqual(user.email, "bob@test.com")

    def test_bind_and_search(self):
        # Connect to the temporary slapd server
        conn = self.ldap_object_class(self.server.ldap_uri)
        conn.simple_bind_s(self.server.root_dn, self.server.root_pw)

        # Search for the top entry
        result = conn.search_s(self.server.suffix, ldap.SCOPE_BASE)
        self.assertEqual(len(result), 1)
        dn, entry = result[0]
        self.assertEqual(dn, self.server.suffix)

    def test_ldap_group_active_properly_setup_and_searchable(self):
        conn = self.ldap_object_class(self.server.ldap_uri)
        results = conn.search_s("ou=groups,o=test", ldap.SCOPE_ONELEVEL, "(cn=active)")
        expected = [
            (
                "cn=active,ou=groups,o=test",
                {
                    "cn": [b"active"],
                    "objectClass": [b"groupOfNames"],
                    "member": [b"uid=bob,ou=people,o=test"],
                },
            )
        ]
        self.assertEqual(expected, results)

    @override_settings(AUTH_LDAP_AUTOCREATE_USER=False)
    def test_ldap_authentication_no_autocreate_user(self):
        # User 'bob' in LDAP but not in the database, authentication fails
        self.assertFalse(self.client.login(username="bob", password="secret"))

        create_superuser("bob", self.nexb_dataspace, email="bob@test.com")
        # User 'bob' in LDAP and in the database, authentication succeed
        self.assertTrue(self.client.login(username="bob", password="secret"))

    @override_settings(AUTH_LDAP_DATASPACE=None)
    def test_ldap_authentication_autocreate_user_no_dataspace(self):
        self.assertIsNone(getattr(settings, "AUTH_LDAP_DATASPACE", None))

        with self.assertRaises(ImproperlyConfigured):
            self.client.login(username="bob", password="secret")

    @override_settings(AUTH_LDAP_DATASPACE="non_existing")
    def test_ldap_authentication_autocreate_user_non_existing_dataspace(self):
        # AUTH_LDAP_DATASPACE set to a non-existing dataspace
        with self.assertRaises(ImproperlyConfigured):
            self.client.login(username="bob", password="secret")

    def test_ldap_authentication_autocreate_user_proper_dataspace(self):
        self.assertFalse(DejacodeUser.objects.filter(username="bob").exists())
        self.assertTrue(self.client.login(username="bob", password="secret"))

        # User was created on first login
        created_user = DejacodeUser.objects.get(username="bob")
        self.assertEqual("", created_user.first_name)
        self.assertEqual("", created_user.last_name)
        self.assertEqual("", created_user.email)
        self.assertEqual(self.nexb_dataspace, created_user.dataspace)

        self.assertTrue(created_user.is_active)
        self.assertFalse(created_user.is_staff)
        self.assertFalse(created_user.is_superuser)

        self.assertFalse(created_user.data_email_notification)
        self.assertFalse(created_user.workflow_email_notification)
        self.assertEqual("", created_user.company)

        # Next login, the DB user is re-used
        self.assertTrue(self.client.login(username="bob", password="secret"))

    # @override_settings(AUTH_LDAP_USER_ATTR_MAP=AUTH_LDAP_USER_ATTR_MAP)
    def test_ldap_authentication_autocreate_user_with_attr_map(self):
        self.assertFalse(DejacodeUser.objects.filter(username="bob").exists())

        self.assertTrue(self.client.login(username="bob", password="secret"))
        # User was created on first login
        created_user = DejacodeUser.objects.get(username="bob")
        self.assertEqual("Robert", created_user.first_name)
        self.assertEqual("Smith", created_user.last_name)
        self.assertEqual("bob@test.com", created_user.email)
        self.assertEqual(self.nexb_dataspace, created_user.dataspace)

    @override_settings(
        # AUTH_LDAP_USER_ATTR_MAP=AUTH_LDAP_USER_ATTR_MAP,
        AUTH_LDAP_ALWAYS_UPDATE_USER=True,
    )
    def test_ldap_authentication_update_user_with_attr_map(self):
        # Manually create the user first, then see if the values are updated
        create_user("bob", self.nexb_dataspace, email="other@mail.com")

        user = DejacodeUser.objects.get(username="bob")
        self.assertEqual("", user.first_name)
        self.assertEqual("", user.last_name)
        self.assertEqual("other@mail.com", user.email)
        self.assertEqual(self.nexb_dataspace, user.dataspace)

        # User is updated after authentication
        self.assertTrue(self.client.login(username="bob", password="secret"))
        # Refreshing the instance to reflect changes
        user = DejacodeUser.objects.get(username="bob")
        self.assertEqual("Robert", user.first_name)
        self.assertEqual("Smith", user.last_name)
        self.assertEqual("bob@test.com", user.email)
        self.assertEqual(self.nexb_dataspace, user.dataspace)

    @override_settings(AUTH_LDAP_FIND_GROUP_PERMS=True)
    def test_ldap_authentication_group_permissions(self):
        bob = create_user("bob", self.nexb_dataspace, email="bob@test.com", is_staff=True)
        bob.groups.add(self.dejacode_group1)

        self.assertFalse(bob.has_perm("license_library.change_license"))

        # Using the LDAPBackend adds the `ldap_user` to the `user` instance
        bob = DejaCodeLDAPBackend().authenticate(request=None, username="bob", password="secret")

        # Even if not available in the database `Group` table,
        # the LDAP groups assigned to the user are returned in `ldap_user.group_names`.
        # No permissions can be loaded from those though.
        self.assertFalse(Group.objects.filter(name="not_in_database").exists())
        self.assertEqual({"active", "not_in_database", "superuser"}, bob.ldap_user.group_names)
        expected_group_dns = {
            "cn=active,ou=groups,dc=nexb,dc=com",
            "cn=not_in_database,ou=groups,dc=nexb,dc=com",
            "cn=superuser,ou=groups,dc=nexb,dc=com",
        }
        self.assertEqual(expected_group_dns, bob.ldap_user.group_dns)

        expected_perms = "license_library.change_license"
        self.assertTrue(bob.has_perm(expected_perms))
        self.assertEqual({expected_perms}, bob.ldap_user.get_group_permissions())
        # WARNING: The permissions are properly available through `user.get_all_permissions()`
        # but the Group inherited from LDAP are not in `user.groups` since it's a DB relation.
        # Those are available from `user.ldap_user.group_names` and `user.get_group_names()`
        self.assertEqual({expected_perms}, bob.get_all_permissions())
        self.assertEqual([self.dejacode_group1], list(bob.groups.all()))
        expected_group = ["active", "group1", "not_in_database", "superuser"]
        self.assertEqual(expected_group, sorted(bob.get_group_names()))

        license_changelist_url = reverse("admin:license_library_license_changelist")
        component_changelist_url = reverse("admin:component_catalog_component_changelist")
        self.assertTrue(self.client.login(username="bob", password="secret"))
        self.assertEqual(200, self.client.get(license_changelist_url).status_code)
        self.assertEqual(403, self.client.get(component_changelist_url).status_code)

        with override_settings(AUTH_LDAP_FIND_GROUP_PERMS=False):
            bob = DejaCodeLDAPBackend().authenticate(
                request=None, username="bob", password="secret"
            )
            self.assertFalse(bob.get_all_permissions())

    # https://django-auth-ldap.readthedocs.io/en/stable/users.html#easy-attributes
    def test_ldap_user_flags_assigned_through_groups(self):
        bob = create_user("bob", self.nexb_dataspace)
        self.assertFalse(bob.is_superuser)

        bob = DejaCodeLDAPBackend().authenticate(request=None, username="bob", password="secret")
        self.assertFalse(bob.is_superuser)
        self.assertEqual({"active", "not_in_database", "superuser"}, bob.ldap_user.group_names)

        user_flags_by_group = {
            "is_superuser": "cn=superuser,ou=groups,dc=nexb,dc=com",
        }

        # WARNING: This is a workaround for a bug in mockldap.
        # There's a comparison issue in `mockldap.ldapobject.LDAPObject._compare_s`
        # where the `value` is bytes b'' and `values` is a list of strings.
        # For example:
        # value = b'cn=bob,ou=people,dc=nexb,dc=com'
        # values = ['cn=bob,ou=people,dc=nexb,dc=com']
        # Note that mockldap has been replaced by `slapdtest` in recent `python-ldap` versions.
        # The migration to `slapdtest` requires a slaptd daemon runnning plus the rewrite of this
        # whole TestCase.
        # https://www.python-ldap.org/en/latest/reference/slapdtest.html
        with mock.patch.object(_LDAPUserGroups, "is_member_of", return_value=True):
            with override_settings(AUTH_LDAP_USER_FLAGS_BY_GROUP=user_flags_by_group):
                bob = DejaCodeLDAPBackend().authenticate(
                    request=None, username="bob", password="secret"
                )
                self.assertTrue(bob.is_superuser)

    def test_ldap_tab_set_mixin_get_tabsets(self):
        from component_catalog.views import ComponentDetailsView

        create_user("bob", self.nexb_dataspace)
        bob = DejaCodeLDAPBackend().authenticate(request=None, username="bob", password="secret")

        component1 = Component.objects.create(
            name="c1", notice_text="NOTICE", dataspace=self.nexb_dataspace
        )
        tabset_view = ComponentDetailsView()
        tabset_view.model = Component
        tabset_view.object = component1
        tabset_view.request = lambda: None
        tabset_view.request.user = bob

        # No configuration, all tabs available
        self.assertEqual(
            ["Essentials", "Notice", "History"], list(tabset_view.get_tabsets().keys())
        )

        configuration = DataspaceConfiguration.objects.create(
            dataspace=self.nexb_dataspace,
            tab_permissions={"NotAssigned": {"component": ["notice"]}},
        )
        bob = DejaCodeLDAPBackend().authenticate(request=None, username="bob", password="secret")
        tabset_view.request.user = bob
        self.assertEqual([], list(tabset_view.get_tabsets().keys()))

        configuration.tab_permissions = {
            "active": {"component": ["notice"]},
        }
        configuration.save()
        bob = DejaCodeLDAPBackend().authenticate(request=None, username="bob", password="secret")
        tabset_view.request.user = bob
        self.assertEqual(["Notice"], list(tabset_view.get_tabsets().keys()))

        self.client.login(username="bob", password="secret")
        response = self.client.get(component1.get_absolute_url())
        self.assertContains(response, 'id="tab_notice"')
        self.assertNotContains(response, 'id="tab_essentials"')

    def test_ldap_object_secured_access(self):
        product1 = Product.objects.create(
            name="Product1", version="1.0", dataspace=self.nexb_dataspace
        )
        url = product1.get_absolute_url()

        self.assertTrue(self.client.login(username="bob", password="secret"))
        self.assertEqual(404, self.client.get(url).status_code)

        bob = DejacodeUser.objects.get(username="bob")
        self.assertFalse(bob.is_superuser)
        assign_perm("view_product", bob, product1)
        # The `ObjectPermissionBackend` is not needed since `ProductSecuredManager.get_queryset()`
        # calls directly `guardian.shortcuts.get_objects_for_user`
        self.assertEqual(200, self.client.get(url).status_code)


# class DejaCodeLDAPBackendTestCase(TestCase):
#     top = ("dc=com", {"dc": "com"})
#     nexb = ("dc=nexb,dc=com", {"dc": "nexb"})
#     people = ("ou=people,dc=nexb,dc=com", {"ou": "people"})
#     groups = ("ou=groups,dc=nexb,dc=com", {"ou": "groups"})
#
#     bob = (
#         "cn=bob,ou=people,dc=nexb,dc=com",
#         {
#             "cn": "bob",
#             "samaccountname": "bob",
#             "uid": ["bob"],
#             "userPassword": ["secret"],
#             "mail": ["bob@test.com"],
#             "givenName": ["Robert"],
#             "sn": ["Smith"],
#         },
#     )
#
#     group_active = (
#         "cn=active,ou=groups,dc=nexb,dc=com",
#         {
#             "cn": ["active"],
#             "objectClass": ["groupOfNames"],
#             "member": ["cn=bob,ou=people,dc=nexb,dc=com"],
#         },
#     )
#
#     group_not_in_database = (
#         "cn=not_in_database,ou=groups,dc=nexb,dc=com",
#         {
#             "cn": ["not_in_database"],
#             "objectClass": ["groupOfNames"],
#             "member": ["cn=bob,ou=people,dc=nexb,dc=com"],
#         },
#     )
#
#     group_superuser = (
#         "cn=superuser,ou=groups,dc=nexb,dc=com",
#         {
#             "cn": ["superuser"],
#             "objectClass": ["groupOfNames"],
#             "member": ["cn=bob,ou=people,dc=nexb,dc=com"],
#         },
#     )
#
#     # This is the content of our mock LDAP directory. It takes the form
#     # {dn: {attr: [value, ...], ...}, ...}.
#     directory = dict(
#         [
#             top,
#             nexb,
#             people,
#             groups,
#             bob,
#             group_active,
#             group_not_in_database,
#             group_superuser,
#         ]
#     )
