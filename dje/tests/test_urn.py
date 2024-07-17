#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest.case import TestCase

from dje import urn


class URNTestCase(TestCase):
    def test_urn_build_license(self):
        u1 = urn.build("license", key="somekey")
        self.assertEqual("urn:dje:license:somekey", u1)

    def test_urn_build_owner(self):
        u1 = urn.build("owner", name="somekey")
        self.assertEqual("urn:dje:owner:somekey", u1)

    def test_urn_build_component(self):
        u1 = urn.build("component", name="name", version="version")
        self.assertEqual("urn:dje:component:name:version", u1)

    def test_urn_build_component_no_version(self):
        u1 = urn.build("component", name="name", version="")
        self.assertEqual("urn:dje:component:name:", u1)

    def test_urn_build_license_extra_fields_are_ignored(self):
        u1 = urn.build("license", key="somekey", junk="somejunk")
        self.assertEqual("urn:dje:license:somekey", u1)

    def test_urn_build_missing_field_raise_key_error(self):
        with self.assertRaises(KeyError):
            urn.build("license")

    def test_urn_build_missing_field_component_raise_key_error(self):
        with self.assertRaises(KeyError):
            urn.build("component", name="this")

    def test_urn_build_unknown_object_raise_key_error(self):
        with self.assertRaises(KeyError):
            urn.build("some", key="somekey")

    def test_urn_build_component_with_spaces_are_properly_quoted(self):
        u1 = urn.build("component", name="name space", version="version space")
        self.assertEqual("urn:dje:component:name+space:version+space", u1)

    def test_urn_build_component_leading_and_trailing_spaces_are_trimmed_and_ignored(self):
        u1 = urn.build(" component ", name=" name space    ", version="""  version space """)
        self.assertEqual("urn:dje:component:name+space:version+space", u1)

    def test_urn_build_component_with_semicolon_are_properly_quoted(self):
        u1 = urn.build("component", name="name:", version=":version")
        self.assertEqual("urn:dje:component:name%3A:%3Aversion", u1)

    def test_urn_build_component_with_plus_are_properly_quoted(self):
        u1 = urn.build("component", name="name+", version="version+")
        self.assertEqual("urn:dje:component:name%2B:version%2B", u1)

    def test_urn_build_component_with_percent_are_properly_quoted(self):
        u1 = urn.build("component", name="name%", version="version%")
        self.assertEqual("urn:dje:component:name%25:version%25", u1)

    def test_urn_build_object_case_is_not_significant(self):
        u1 = urn.build("license", key="key")
        u2 = urn.build("lICENSe", key="key")
        self.assertEqual(u1, u2)

    def test_urn_parse_component(self):
        u = "urn:dje:component:name:version"
        parsed = ("component", {"name": "name", "version": "version"})
        self.assertEqual(parsed, urn.parse(u))

    def test_urn_parse_license(self):
        u = "urn:dje:license:lic"
        parsed = ("license", {"key": "lic"})
        self.assertEqual(parsed, urn.parse(u))

    def test_urn_parse_org(self):
        u = "urn:dje:owner:name"
        parsed = ("owner", {"name": "name"})
        self.assertEqual(parsed, urn.parse(u))

    def test_urn_parse_build_is_idempotent(self):
        u1 = urn.build("component", owner__name="org%", name="name%", version="version%")
        m, f = urn.parse(u1)
        u3 = urn.build(m, **f)
        self.assertEqual(u1, u3)

    def test_urn_build_utf8_unicode_support(self):
        u1 = urn.build("owner", name="Vázquez Araújo")
        expected = "urn:dje:owner:V%C3%A1zquez+Ara%C3%BAjo"
        self.assertEqual(expected, u1)

        self.assertEqual(("owner", {"name": "V\xe1zquez Ara\xfajo"}), urn.parse(u1))

        u1 = urn.build("owner", name="V\xe1zquez Ara\xfajo")
        self.assertEqual(expected, u1)

    def test_urn_parse_raise_exception_if_incorrect_prefix_or_ns(self):
        test_cases = [
            "arn:dje:a:a",
            "urn:x:x:x",
            "x:x:x:x",
        ]

        for value in test_cases:
            with self.assertRaises(urn.URNValidationError):
                urn.parse(value)

    def test_urn_parse_raise_exception_if_too_short(self):
        test_cases = [
            "urn:dje:license",
            "urn:dje:component",
            "urn:dje:organization",
            "urn:dje:owner:o:n",
        ]

        for value in test_cases:
            with self.assertRaises(urn.URNValidationError):
                urn.parse(value)

    def test_urn_parse_raise_exception_if_too_long(self):
        test_cases = [
            "urn:dje:component:o:n:v:junk",
            "urn:dje:owner:org:junk",
            "urn:dje:license:key:junk",
        ]

        for value in test_cases:
            with self.assertRaises(urn.URNValidationError):
                urn.parse(value)

    def test_urn_parse_raise_exception_if_unknown_object(self):
        test_cases = [
            "urn:dje:marshmallows:dsds",
            "urn:dje::dsds",
        ]

        for value in test_cases:
            with self.assertRaises(urn.URNValidationError):
                urn.parse(value)

    def test_urn_parse_raise_exception_messages(self):
        test_cases = [
            (
                "urn:not_dje:license:license1",
                'Invalid URN prefix or namespace. Expected "urn:dje" and not "urn:not_dje" in URN:'
                ' "urn:not_dje:license:license1".',
            ),
            (
                "urn:dje:aaa",
                'Invalid URN format: "urn:dje:aaa". Expected format is:'
                ' "urn:<namespace>:<object>:<segments>".',
            ),
            (
                "urn:dje:license:license1:extra_segment",
                'Invalid number of segments in URN: "urn:dje:license:license1:extra_segment".',
            ),
            (
                "urn:not_dje:license:license1",
                'Invalid URN prefix or namespace. Expected "urn:dje" and not "urn:not_dje" in URN:'
                ' "urn:not_dje:license:license1".',
            ),
            (
                "urn:dje:not_supported_model:license1",
                "Unsupported URN object: not_supported_model in URN:"
                ' "urn:dje:not_supported_model:license1".'
                " Expected one of: license,owner,component.",
            ),
        ]

        for value, msg in test_cases:
            try:
                urn.parse(value)
            except urn.URNValidationError as e:
                self.assertEqual(msg, str(e))
