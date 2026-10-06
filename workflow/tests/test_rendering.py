#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.test import SimpleTestCase
from django.utils.safestring import SafeString

from workflow.rendering import markdown_to_safe_html


class RenderingTestCase(SimpleTestCase):
    def test_rendering_markdown_to_safe_html_returns_safe_string(self):
        self.assertIsInstance(markdown_to_safe_html("text"), SafeString)

    def test_rendering_markdown_to_safe_html_allowed_tags_and_attributes(self):
        cases = [
            ("# Title", "<h1>Title</h1>"),
            ("line1\nline2", "<p>line1<br>\nline2</p>"),
            ("`code`", "<p><code>code</code></p>"),
            ('<span id="anchor">text</span>', '<p><span id="anchor">text</span></p>'),
            ('<span class="custom">text</span>', "<p><span>text</span></p>"),
            (
                '![alt](https://image.url "title")',
                '<p><img alt="alt" src="https://image.url" title="title"></p>',
            ),
            ('<img src="x" onerror="evil()">', '<p><img src="x"></p>'),
            (
                '<iframe src="https://evil.url"></iframe>',
                '&lt;iframe src="https://evil.url"&gt;&lt;/iframe&gt;',
            ),
        ]

        for text, expected in cases:
            self.assertEqual(expected, markdown_to_safe_html(text))
