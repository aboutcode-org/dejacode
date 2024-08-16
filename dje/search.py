#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import shlex
from functools import reduce
from operator import or_

from django.db import models
from django.utils.encoding import force_str


def split_search_terms(search_terms):
    """
    Use shlex.split to keep double quoted strings together.
    https://docs.python.org/2/library/shlex.html#parsing-rules

    Single quote `'` are escaped and to be kept as apostrophes.
    """
    search_terms = search_terms.replace("'", "\\'")
    terms = shlex.split(force_str(search_terms))
    return terms


def advanced_search(search_terms, search_fields):
    lookup_types = {
        ":": "icontains",
        "=": "iexact",
        "^": "istartswith",
    }
    or_queries = []

    for term in split_search_terms(search_terms):
        lookup_type = "icontains"  # default
        lookup_fields = search_fields
        lookup_operators = [force_str(key) for key in lookup_types.keys()]

        # 'apache', '^apache', '=apache', , ':apache'
        if term.startswith(tuple(lookup_operators)):
            term, lookup_type = term[1:], lookup_types.get(term[0])

        # 'name:apache', 'name^apache', 'name=apache'
        else:
            for field_name in lookup_fields:
                missing_operator = term == field_name
                if not term.startswith(field_name) or missing_operator:
                    continue

                operator = term[len(field_name)]
                if operator in lookup_operators:
                    lookup_type = lookup_types.get(operator)
                    lookup_fields = [field_name]
                    _, term = term.split(f"{field_name}{operator}", 1)
                    break

        if not term:
            continue

        orm_lookups = [f"{field}__{lookup_type}" for field in lookup_fields]
        or_queries.extend([models.Q(**{orm_lookup: term}) for orm_lookup in orm_lookups])

    if or_queries:
        return reduce(or_, or_queries)
