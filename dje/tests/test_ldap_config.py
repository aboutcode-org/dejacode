#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

import ldap
from django_auth_ldap.config import LDAPSearch
from django_auth_ldap.config import LDAPSearchUnion

from dejacode.ldap_config import build_user_search_union
from dejacode.ldap_config import get_user_search


class LDAPConfigTestCase(SimpleTestCase):
    def test_ldap_config_get_user_search(self):
        search_definition = {"base": "ou=users,dc=example,dc=com", "filter": "(uid=%(user)s)"}
        user_search = get_user_search(0, search_definition)
        self.assertIsInstance(user_search, LDAPSearch)
        self.assertEqual("ou=users,dc=example,dc=com", user_search.base_dn)
        self.assertEqual(ldap.SCOPE_SUBTREE, user_search.scope)
        self.assertEqual("(uid=%(user)s)", user_search.filterstr)

    def test_ldap_config_get_user_search_not_an_object(self):
        expected_message = "AUTH_LDAP_USER_SEARCHES[2] must be a JSON object"
        with self.assertRaisesMessage(ImproperlyConfigured, expected_message):
            get_user_search(2, "ou=users,dc=example,dc=com")

    def test_ldap_config_get_user_search_invalid_base_or_filter(self):
        invalid_definitions = [
            {"filter": "(uid=%(user)s)"},
            {"base": "ou=users,dc=example,dc=com"},
            {"base": "", "filter": "(uid=%(user)s)"},
            {"base": ["ou=users,dc=example,dc=com"], "filter": "(uid=%(user)s)"},
            {"base": "ou=users,dc=example,dc=com", "filter": 123},
        ]
        expected_message = (
            "AUTH_LDAP_USER_SEARCHES[0] must define 'base' and 'filter' as non-empty strings"
        )
        for search_definition in invalid_definitions:
            with self.subTest(search_definition=search_definition):
                with self.assertRaisesMessage(ImproperlyConfigured, expected_message):
                    get_user_search(0, search_definition)

    def test_ldap_config_get_user_search_filter_without_user_placeholder(self):
        search_definition = {"base": "ou=users,dc=example,dc=com", "filter": "(objectClass=person)"}
        expected_message = (
            "AUTH_LDAP_USER_SEARCHES[0] 'filter' must include the %(user)s placeholder"
        )
        with self.assertRaisesMessage(ImproperlyConfigured, expected_message):
            get_user_search(0, search_definition)

    def test_ldap_config_build_user_search_union(self):
        user_searches = (
            '[{"base": "ou=users,dc=example,dc=com", "filter": "(uid=%(user)s)"},'
            ' {"base": "ou=staff,dc=example,dc=com", "filter": "(cn=%(user)s)"}]'
        )
        user_search_union = build_user_search_union(user_searches)
        self.assertIsInstance(user_search_union, LDAPSearchUnion)
        search_values = [
            (search.base_dn, search.filterstr) for search in user_search_union.searches
        ]
        expected = [
            ("ou=users,dc=example,dc=com", "(uid=%(user)s)"),
            ("ou=staff,dc=example,dc=com", "(cn=%(user)s)"),
        ]
        self.assertEqual(expected, search_values)

    def test_ldap_config_build_user_search_union_invalid_json(self):
        expected_message = "Invalid JSON in AUTH_LDAP_USER_SEARCHES"
        with self.assertRaisesMessage(ImproperlyConfigured, expected_message):
            build_user_search_union("{not json")

    def test_ldap_config_build_user_search_union_not_a_non_empty_list(self):
        expected_message = "AUTH_LDAP_USER_SEARCHES must be a non-empty JSON list"
        for user_searches in ["[]", '{"base": "ou=users,dc=example,dc=com"}', '"text"']:
            with self.subTest(user_searches=user_searches):
                with self.assertRaisesMessage(ImproperlyConfigured, expected_message):
                    build_user_search_union(user_searches)

    def test_ldap_config_build_user_search_union_invalid_entry_index(self):
        user_searches = (
            '[{"base": "ou=users,dc=example,dc=com", "filter": "(uid=%(user)s)"},'
            ' {"base": "ou=staff,dc=example,dc=com"}]'
        )
        expected_message = "AUTH_LDAP_USER_SEARCHES[1] must define 'base' and 'filter'"
        with self.assertRaisesMessage(ImproperlyConfigured, expected_message):
            build_user_search_union(user_searches)
