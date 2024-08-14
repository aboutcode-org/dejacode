#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from urllib.parse import parse_qsl
from urllib.parse import urlparse
from urllib.parse import urlunparse

from django.contrib.humanize.templatetags.humanize import NaturalTimeFormatter
from django.shortcuts import resolve_url
from django.template import Library
from django.template.defaultfilters import stringfilter
from django.templatetags.static import static
from django.urls import Resolver404
from django.urls import get_script_prefix
from django.urls import resolve
from django.utils.html import format_html
from django.utils.html import urlize as _urlize
from django.utils.http import urlencode

register = Library()


@register.filter(is_safe=True)
def get_item(obj, field_name):
    """Get item from a given object, useful to get a field from a Form."""
    return obj.__getitem__(field_name)


@register.filter(is_safe=True)
def as_icon(field_value):
    """Return the proper icon based on the field_value (True/False/None)."""
    icon = {
        True: "fa-solid fa-circle-check color-true",
        False: "far fa-circle color-false",
        None: "far fa-question-circle color-none",
    }.get(field_value)

    if icon:
        return format_html('<i class="{}"></i>', icon)


@register.filter(is_safe=True)
def as_icon_admin(field_value):
    """
    Return the <img> for the icon based on the field_value (True/False/None).
    Using the staticfiles templatetags 'static' to generate the proper path.
    """
    cleaned_value = {True: "yes", False: "no",
                     None: "unknown"}.get(field_value)

    if not cleaned_value:
        return ""

    icon_url = static(f"img/icon-{cleaned_value}.png")
    return format_html('<img src="{}" alt="{}">', icon_url, field_value)


@register.filter
def smart_page_range(paginator, page_num):
    """
    Generate the series of links to the pages in a paginated list.
    Inspired by django.contrib.admin.templatetags.admin_list.pagination
    """
    ON_EACH_SIDE = 2
    ON_ENDS = 2

    # If there are 10 or fewer pages, display links to every page.
    if paginator.num_pages <= 10:
        return paginator.page_range

    page_range = []
    if page_num > (ON_EACH_SIDE + ON_ENDS + 1):
        page_range.extend(range(1, ON_ENDS + 1))
        page_range.append(None)
        page_range.extend(range(page_num - ON_EACH_SIDE, page_num + 1))
    else:
        page_range.extend(range(1, page_num + 1))

    if page_num < (paginator.num_pages - ON_EACH_SIDE - ON_ENDS):
        page_range.extend(range(page_num + 1, page_num + ON_EACH_SIDE + 1))
        page_range.append(None)
        page_range.extend(range(paginator.num_pages -
                          ON_ENDS + 1, paginator.num_pages + 1))
    else:
        page_range.extend(range(page_num + 1, paginator.num_pages + 1))

    return page_range


@register.simple_tag(takes_context=True)
def inject_preserved_filters(context, url):
    """
    Fork from django.contrib.admin.templatetags.admin_urls
    Renamed to inject_preserved_filters to avoid confusion with original
    add_preserved_filters
    """
    opts = context.get("opts")
    preserved_filters = context.get("preserved_filters")

    url = resolve_url(url)  # supports for viewname
    parsed_url = list(urlparse(url))
    parsed_qs = dict(parse_qsl(parsed_url[4]))
    merged_qs = dict()

    if opts and preserved_filters:
        preserved_filters = dict(parse_qsl(preserved_filters))

        match_url = "/{}".format(url.partition(get_script_prefix())[2])
        try:
            match = resolve(match_url)
        except Resolver404:
            pass
        else:
            current_url = f"{match.app_name}:{match.url_name}"
            list_url = f"{opts.app_label}:{opts.model_name}_list"
            if list_url == current_url and "_list_filters" in preserved_filters:
                preserved_filters = dict(
                    parse_qsl(preserved_filters["_list_filters"]))

        merged_qs.update(preserved_filters)

    merged_qs.update(parsed_qs)

    parsed_url[4] = urlencode(merged_qs)
    return urlunparse(parsed_url)


@register.filter(is_safe=True, needs_autoescape=True)
@stringfilter
def urlize_target_blank(value, autoescape=True):
    """
    Wrap `urlize` to inject the `target="_blank"` attribute.
    Also adds support for `ftp://`.
    """
    if value.startswith("ftp://"):
        link = f'<a target="_blank" href="{value}" rel="noreferrer nofollow">{value}</a>'
    else:
        link = _urlize(value, nofollow=True, autoescape=autoescape)
        link = link.replace("<a", '<a target="_blank"')
    return format_html(link)


@register.filter
def naturaltime_short(value):
    """
    Short version of `naturaltime`.
    Remove the second part following the comma, if any.
    "1 day, 2 hours ago" becomes "1 day ago"
    """
    natural_time = NaturalTimeFormatter.string_for(value)

    parts = natural_time.split(",")
    if len(parts) > 1:
        return f"{parts[0]} ago"

    return natural_time
