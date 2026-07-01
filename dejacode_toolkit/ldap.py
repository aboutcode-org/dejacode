#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json

import ldap
from django.core.exceptions import ImproperlyConfigured
from django_auth_ldap.config import LDAPSearch
from django_auth_ldap.config import LDAPSearchUnion


def build_user_search(user_searches, user_dn, user_filterstr):
    """Return the ``AUTH_LDAP_USER_SEARCH`` object.

    When ``user_searches`` (a raw JSON string) is provided, parse and validate
    it and return an ``LDAPSearchUnion``. Otherwise, fall back to a single
    ``LDAPSearch`` built from ``user_dn`` and ``user_filterstr``.
    """
    if not user_searches:
        return LDAPSearch(user_dn, ldap.SCOPE_SUBTREE, user_filterstr)

    try:
        definitions = json.loads(user_searches)
    except json.JSONDecodeError as e:
        raise ImproperlyConfigured(
            f"Invalid JSON in AUTH_LDAP_USER_SEARCHES: {e}"
        ) from e

    if not isinstance(definitions, list):
        raise ImproperlyConfigured("AUTH_LDAP_USER_SEARCHES must be a JSON list")

    if not definitions:
        raise ImproperlyConfigured("AUTH_LDAP_USER_SEARCHES cannot be empty")

    searches = []
    for index, entry in enumerate(definitions):
        if not isinstance(entry, dict):
            raise ImproperlyConfigured(
                f"AUTH_LDAP_USER_SEARCHES[{index}] must be a JSON object"
            )

        base_dn = entry.get("base")
        filterstr = entry.get("filter")

        if not base_dn or not filterstr:
            raise ImproperlyConfigured(
                f"AUTH_LDAP_USER_SEARCHES[{index}] must define 'base' and 'filter'"
            )

        searches.append(LDAPSearch(base_dn, ldap.SCOPE_SUBTREE, filterstr))

    return LDAPSearchUnion(*searches)
