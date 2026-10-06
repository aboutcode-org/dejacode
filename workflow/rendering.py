#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.utils.html import mark_safe

import markdown
from bleach import Cleaner
from bleach.linkifier import LinkifyFilter

# HTML tags and attributes allowed in the Markdown rendered content.
# Copied from the `bleach-allowlist` library, which only provided these two constants.
MARKDOWN_ALLOWED_TAGS = [
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "b",
    "i",
    "strong",
    "em",
    "tt",
    "p",
    "br",
    "span",
    "div",
    "blockquote",
    "code",
    "pre",
    "hr",
    "ul",
    "ol",
    "li",
    "dd",
    "dt",
    "img",
    "a",
    "sub",
    "sup",
]
MARKDOWN_ALLOWED_ATTRIBUTES = {
    "*": ["id"],
    "img": ["src", "alt", "title"],
    "a": ["href", "alt", "title"],
}


def markdown_to_safe_html(text):
    """
    Convert user provided `text` into HTML using markdown.
    The URLs are converted into links using the bleach Linkify feature.
    The HTML code is sanitized using bleach to prevent XSS attacks.
    The clean needs to be applied to the Markdown's output, not the input.

    See https://michelf.ca/blog/2010/markdown-and-xss/ for details.

    See also the chapter about safe mode in
    https://python-markdown.github.io/change_log/release-3.0/
    """
    unsafe_html = markdown.markdown(
        text=text,
        extensions=["markdown.extensions.nl2br"],
    )

    # Using `Cleaner()` with the 1LinkifyFilter1 to clean and linkify in one pass.
    # See https://bleach.readthedocs.io/en/latest/linkify.html notes
    cleaner = Cleaner(
        tags=MARKDOWN_ALLOWED_TAGS,
        attributes=MARKDOWN_ALLOWED_ATTRIBUTES,
        filters=[LinkifyFilter],
    )
    html = cleaner.clean(unsafe_html)

    return mark_safe(html)
