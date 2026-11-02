#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest import TestCase

from dejacode_toolkit import aboutcode


class AboutCodeTestCase(TestCase):
    def test_aboutcode_dumps_field_order(self):
        about_data = {
            "licenses": [{"key": "mit", "name": "MIT License", "file": "mit.LICENSE"}],
            "checksum_sha1": "sha1",
            "owner": "Owner",
            "attribute": True,
            "license_expression": "mit",
            "version": "1.0",
            "name": "name",
            "about_resource": "package.zip",
        }
        expected = (
            "about_resource: package.zip\n"
            "name: name\n"
            "version: '1.0'\n"
            "license_expression: mit\n"
            "attribute: yes\n"
            "owner: Owner\n"
            "checksum_sha1: sha1\n"
            "licenses:\n"
            "  - key: mit\n"
            "    name: MIT License\n"
            "    file: mit.LICENSE\n"
        )
        self.assertEqual(expected, aboutcode.dumps(about_data))

    def test_aboutcode_dumps_skips_empty_false_and_unsupported_values(self):
        about_data = {
            "name": "name",
            "version": "",
            "description": "  \n ",
            "notes": None,
            "redistribute": False,
            "track_changes": True,
            "licenses": [],
            "unsupported_field": "value",
        }
        expected = "name: name\ntrack_changes: yes\n"
        self.assertEqual(expected, aboutcode.dumps(about_data))

    def test_aboutcode_dumps_normalizes_text(self):
        about_data = {
            "name": "  name  ",
            "copyright": "Copyright A  \r\nCopyright B\r\n",
        }
        expected = "name: name\ncopyright: |\n  Copyright A\n  Copyright B\n"
        self.assertEqual(expected, aboutcode.dumps(about_data))

    def test_aboutcode_normalize_text(self):
        inputs = [
            # (text, expected)
            ("", ""),
            ("text", "text"),
            ("  text  ", "text"),
            ("line1 \r\nline2\t\r\n", "line1\nline2"),
            ("\n\nline1\n\n  indented\n\n", "line1\n\n  indented"),
        ]
        for text, expected in inputs:
            self.assertEqual(expected, aboutcode.normalize_text(text))
