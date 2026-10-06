#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json

from django.core.exceptions import ImproperlyConfigured

import ldap
from django_auth_ldap.config import LDAPSearch
from django_auth_ldap.config import LDAPSearchUnion


def get_user_search(index, search_definition):
    """Return an ``LDAPSearch`` from one ``AUTH_LDAP_USER_SEARCHES`` entry."""
    entry_name = f"AUTH_LDAP_USER_SEARCHES[{index}]"

    if not isinstance(search_definition, dict):
        raise ImproperlyConfigured(f"{entry_name} must be a JSON object")

    base_dn = search_definition.get("base")
    filterstr = search_definition.get("filter")

    has_base_and_filter = all(isinstance(value, str) and value for value in (base_dn, filterstr))
    if not has_base_and_filter:
        raise ImproperlyConfigured(
            f"{entry_name} must define 'base' and 'filter' as non-empty strings"
        )

    if "%(user)s" not in filterstr:
        raise ImproperlyConfigured(f"{entry_name} 'filter' must include the %(user)s placeholder")

    return LDAPSearch(base_dn, ldap.SCOPE_SUBTREE, filterstr)


def build_user_search_union(user_searches):
    """Return an ``LDAPSearchUnion`` from the ``AUTH_LDAP_USER_SEARCHES`` JSON string."""
    try:
        search_definitions = json.loads(user_searches)
    except json.JSONDecodeError as error:
        raise ImproperlyConfigured(f"Invalid JSON in AUTH_LDAP_USER_SEARCHES: {error}") from error

    if not isinstance(search_definitions, list) or not search_definitions:
        raise ImproperlyConfigured("AUTH_LDAP_USER_SEARCHES must be a non-empty JSON list")

    searches = [
        get_user_search(index, search_definition)
        for index, search_definition in enumerate(search_definitions)
    ]
    return LDAPSearchUnion(*searches)
