#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import template

register = template.Library()


@register.inclusion_tag("product_portfolio/attribution/hierarchy_toc.html")
def show_hierarchy_toc(node, children):
    return {
        "node": node,
        "children": children,
    }


@register.filter(is_safe=True)
def get_html_id(node):
    """Return a unique identifier for use in the HTML id="" parameter."""
    return str(hash(node)).replace("-", "a")
