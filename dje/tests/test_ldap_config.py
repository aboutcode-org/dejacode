#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from django_auth_ldap.config import LDAPSearch
from django_auth_ldap.config import LDAPSearchUnion

from dejacode.ldap_config import build_user_search


class BuildUserSearchTestCase(SimpleTestCase):
    def test_build_user_search_fallback_to_single_search_when_empty(self):
        user_search = build_user_search("", "ou=users,dc=example,dc=com", "(uid=%(user)s)")
        self.assertIsInstance(user_search, LDAPSearch)
        self.assertEqual("ou=users,dc=example,dc=com", user_search.base_dn)
        self.assertEqual("(uid=%(user)s)", user_search.filterstr)

    def test_build_user_search_valid_json_returns_union(self):
        user_searches = (
            '[{"base": "ou=a,dc=example,dc=com", "filter": "(uid=%(user)s)"},'
            ' {"base": "ou=b,dc=example,dc=com", "filter": "(cn=%(user)s)"}]'
        )
        user_search = build_user_search(user_searches, "", "")
        self.assertIsInstance(user_search, LDAPSearchUnion)
        search_values = [(search.base_dn, search.filterstr) for search in user_search.searches]
        expected = [
            ("ou=a,dc=example,dc=com", "(uid=%(user)s)"),
            ("ou=b,dc=example,dc=com", "(cn=%(user)s)"),
        ]
        self.assertEqual(expected, search_values)

    def test_build_user_search_single_entry_still_returns_union(self):
        user_searches = '[{"base": "ou=a,dc=example,dc=com", "filter": "(uid=%(user)s)"}]'
        user_search = build_user_search(user_searches, "", "")
        self.assertIsInstance(user_search, LDAPSearchUnion)
        search_values = [(search.base_dn, search.filterstr) for search in user_search.searches]
        self.assertEqual([("ou=a,dc=example,dc=com", "(uid=%(user)s)")], search_values)

    def test_build_user_search_invalid_json_raises(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "Invalid JSON"):
            build_user_search("{not json", "", "")

    def test_build_user_search_not_a_list_raises(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "must be a JSON list"):
            build_user_search('{"base": "x", "filter": "y"}', "", "")

    def test_build_user_search_empty_list_raises(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "cannot be empty"):
            build_user_search("[]", "", "")

    def test_build_user_search_entry_not_object_raises(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "[0] must be a JSON object"):
            build_user_search('["not an object"]', "", "")

    def test_build_user_search_missing_base_raises(self):
        user_searches = '[{"filter": "(uid=%(user)s)"}]'
        with self.assertRaisesMessage(ImproperlyConfigured, "[0] must define 'base' and 'filter'"):
            build_user_search(user_searches, "", "")

    def test_build_user_search_missing_filter_raises(self):
        user_searches = '[{"base": "ou=a,dc=example,dc=com"}]'
        with self.assertRaisesMessage(ImproperlyConfigured, "[0] must define 'base' and 'filter'"):
            build_user_search(user_searches, "", "")

    def test_build_user_search_filter_without_user_placeholder_raises(self):
        user_searches = '[{"base": "ou=a,dc=example,dc=com", "filter": "(objectClass=person)"}]'
        expected_message = "[0] 'filter' must include the %(user)s placeholder"
        with self.assertRaisesMessage(ImproperlyConfigured, expected_message):
            build_user_search(user_searches, "", "")

    def test_build_user_search_error_index_points_to_bad_entry(self):
        user_searches = (
            '[{"base": "ou=a,dc=example,dc=com", "filter": "(uid=%(user)s)"},'
            ' {"base": "ou=b,dc=example,dc=com"}]'
        )
        with self.assertRaisesMessage(ImproperlyConfigured, "[1] must define 'base' and 'filter'"):
            build_user_search(user_searches, "", "")
