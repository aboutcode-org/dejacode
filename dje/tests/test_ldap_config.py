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

from dejacode_toolkit.ldap import build_user_search


class BuildUserSearchTestCase(SimpleTestCase):
    def test_build_user_search_fallback_to_single_search_when_empty(self):
        result = build_user_search("", "ou=users,dc=example,dc=com", "(uid=%(user)s)")
        self.assertIsInstance(result, LDAPSearch)

    def test_build_user_search_valid_json_returns_union(self):
        raw = (
            '[{"base": "ou=a,dc=example,dc=com", "filter": "(uid=%(user)s)"},'
            ' {"base": "ou=b,dc=example,dc=com", "filter": "(uid=%(user)s)"}]'
        )
        result = build_user_search(raw, "", "")
        self.assertIsInstance(result, LDAPSearchUnion)

    def test_build_user_search_single_entry_still_returns_union(self):
        raw = '[{"base": "ou=a,dc=example,dc=com", "filter": "(uid=%(user)s)"}]'
        result = build_user_search(raw, "", "")
        self.assertIsInstance(result, LDAPSearchUnion)

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
        raw = '[{"filter": "(uid=%(user)s)"}]'
        with self.assertRaisesMessage(ImproperlyConfigured, "[0] must define 'base' and 'filter'"):
            build_user_search(raw, "", "")

    def test_build_user_search_missing_filter_raises(self):
        raw = '[{"base": "ou=a,dc=example,dc=com"}]'
        with self.assertRaisesMessage(ImproperlyConfigured, "[0] must define 'base' and 'filter'"):
            build_user_search(raw, "", "")

    def test_build_user_search_error_index_points_to_bad_entry(self):
        raw = (
            '[{"base": "ou=a,dc=example,dc=com", "filter": "(uid=%(user)s)"},'
            ' {"base": "ou=b,dc=example,dc=com"}]'
        )
        with self.assertRaisesMessage(ImproperlyConfigured, "[1] must define 'base' and 'filter'"):
            build_user_search(raw, "", "")
