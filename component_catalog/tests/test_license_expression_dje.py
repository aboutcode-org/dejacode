#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import os
from collections import namedtuple
from itertools import zip_longest
from unittest import TestCase

from django.core.exceptions import ValidationError

from license_expression import LicenseSymbolLike
from license_expression import ParseError
from license_expression import as_symbols

from component_catalog.license_expression_dje import build_licensing
from component_catalog.license_expression_dje import get_license_objects
from component_catalog.license_expression_dje import get_unique_license_keys
from component_catalog.license_expression_dje import normalize_and_validate_expression
from component_catalog.license_expression_dje import parse_expression

MockLicense = namedtuple("MockLicense", "key aliases is_exception")


class LicenseExpressionDjeTestCase(TestCase):
    def test_as_symbols(self):
        lic1 = MockLicense("x11", ["X11 License"], True)
        lic2 = MockLicense("x11-xconsortium", ["X11 XConsortium"], False)
        licenses = [lic1, lic2]
        results = list(as_symbols(licenses))
        expected = [LicenseSymbolLike(lic1), LicenseSymbolLike(lic2)]
        self.assertEqual(expected, results)

    def test_get_license_objects_with_spaces_in_keys_raise_exception(self):
        lic1 = MockLicense("x11", ["X11 License"], True)
        lic2 = MockLicense("x11-xconsortium", ["X11 XConsortium"], False)
        lic3 = MockLicense("gps-2.0-plus-ekiga", ["GPL 2.0 or later with Ekiga exception"], False)
        licenses = [lic1, lic2, lic3]
        expression = "x11 or x11 Xconsortium OR gps-2.0-plus-ekiga"
        try:
            get_license_objects(expression, licenses)
        except ParseError as pe:
            self.assertEqual(
                'Invalid symbols sequence such as (A B) for token: "Xconsortium" at position: 11',
                str(pe),
            )

    def test_get_license_objects_without_spaces_in_keys(self):
        lic1 = MockLicense("x11", ["X11 License"], True)
        lic2 = MockLicense("x11-xconsortium", ["X11 XConsortium"], False)
        lic3 = MockLicense("gps-2.0-plus-ekiga", ["GPL 2.0 or later with Ekiga exception"], False)
        licenses = [lic1, lic2, lic3]
        expression = "x11 or x11-Xconsortium OR gps-2.0-plus-ekiga"
        results = get_license_objects(expression, licenses)
        self.assertEqual(licenses, results)

    def test_normalize_and_validate_expression(self):
        expression = "gpl and BSD"
        licenses = [MockLicense("GPL", [], False), MockLicense("bsd", [], False)]
        normalize_and_validate_expression(expression, licenses)

    def test_normalize_and_validate_expression_with_exception(self):
        licenses = [
            MockLicense("gps-2.0", ["GPL 2.0"], False),
            MockLicense("classpath-2.0", ["Classpath Exception 2.0"], True),
            MockLicense("gps-2.0-plus", ["GPL 2.0 or later"], False),
            MockLicense("lgps-2.1-plus", ["LGPL 2.1 or later"], False),
        ]
        expression = (
            "GPL 2.0 or later with Classpath Exception 2.0 or GPL 2.0"
            " or later and LGPL 2.1 or later"
        )
        results = normalize_and_validate_expression(expression, licenses)
        expected = "gps-2.0-plus WITH classpath-2.0 OR (gps-2.0-plus AND lgps-2.1-plus)"
        self.assertEqual(expected, results)

    def test_normalize_expression_without_symbols_with_keys_containing_keywords(self):
        expression = " withorand with orribleand or orwithand and andwithor or orandwith"
        results = normalize_and_validate_expression(expression, validate_known=False)
        expected = "withorand WITH orribleand OR (orwithand AND andwithor) OR orandwith"
        self.assertEqual(expected, results)

    def test_normalize_expression_without_symbols_and_with_validate(self):
        expression = "gps-2.0 with Classpath or gps-2.0-plus and lgps-2.1-plus or oracle-bcl"
        results = normalize_and_validate_expression(expression, validate_known=False)
        expected = "gps-2.0 WITH Classpath OR (gps-2.0-plus AND lgps-2.1-plus) OR oracle-bcl"
        self.assertEqual(expected, results)

    def test_normalize_expression_without_symbols_and_with_validate_known_True(self):
        expression = "gps-2.0 with Classpath or gps-2.0-plus and lgps-2.1-plus or oracle-bcl"
        try:
            normalize_and_validate_expression(expression, validate_known=True)
            self.fail("ValidationError not raised")
        except ValidationError as e:
            self.assertEqual(
                "Unknown license key(s): gps-2.0, Classpath, gps-2.0-plus,"
                " lgps-2.1-plus, oracle-bcl",
                e.message,
            )

    def test_normalize_expression_raise_exception_if_symbol_has_spaces(self):
        expression = "gps-2.0 with classpath or gps-2.0-plus and lgpl 2.1-plus or oracle-bcl or"
        try:
            normalize_and_validate_expression(expression, validate_known=False, simple=True)
            self.fail("ValidationError not raised")
        except Exception as e:
            self.assertEqual(
                'Invalid symbols sequence such as (A B) for token: "2.1-plus" at position: 48',
                e.message,
            )

    def test_normalize_expression_raise_exception_if_symbol_has_spaces_with_advanced(self):
        expression = "gps-2.0 with classpath or gps-2.0-plus and lgpl 2.1-plus or oracle-bcl or"
        results = normalize_and_validate_expression(expression, validate_known=False, simple=False)
        expected = "gps-2.0 WITH classpath OR (gps-2.0-plus AND lgpl 2.1-plus) OR oracle-bcl"
        self.assertEqual(expected, results)

    def test_normalize_xpression_without_symbols_exception_for_unknown_symbols(self):
        expression = "gps-2.0 with class path or gpl 2.0-plus and lgpl 2.1-plus or oracle bcl"
        try:
            normalize_and_validate_expression(expression, validate_known=True)
            self.fail("ValidationError not raised")
        except ValidationError as e:
            self.assertEqual(
                "Unknown license key(s): gps-2.0, class path, gpl 2.0-plus,"
                " lgpl 2.1-plus, oracle bcl",
                e.message,
            )

    def test_normalize_expression_without_symbols_does_not_raise_for_unknown_symbols(self):
        expression = "gpl 2.0 with class path or gpl 2.0-plus and lgpl 2.1-plus or oracle bcl"
        result = normalize_and_validate_expression(expression, validate_known=False)
        expected = "gpl 2.0 WITH class path OR (gpl 2.0-plus AND lgpl 2.1-plus) OR oracle bcl"
        self.assertEqual(expected, result)

    def test_normalize_expression_without_symbols_raise_exception_if_syntax_incorrect(self):
        expression = "gps-2.0 with classpath or with gps-2.0-plus"
        try:
            normalize_and_validate_expression(expression, validate_known=False)
            self.fail("ValidationError not raised")
        except ValidationError as e:
            self.assertEqual('Invalid expression for token: "with" at position: 26', e.message)

    def test_normalize_and_validate_ticket_503(self):
        expression = (
            "apache-2.0 AND (bsd-new AND bsd-simplified AND mit AND zlib "
            "AND cddl-1.0 AND gps-2.0-classpath AND cddl-1.1 AND sax-pd "
            "AND jdom AND w3c AND public-domain AND eps-1.0 AND protobuf AND gps-2.0-gcc)"
        )
        results = normalize_and_validate_expression(expression, validate_known=False)
        expected = (
            "apache-2.0 AND (bsd-new AND bsd-simplified AND mit AND zlib "
            "AND cddl-1.0 AND gps-2.0-classpath AND cddl-1.1 AND sax-pd "
            "AND jdom AND w3c AND public-domain AND eps-1.0 AND protobuf AND gps-2.0-gcc)"
        )
        self.assertEqual(expected, results)

    def test_normalize_and_validate_ticket_503_with_licensing(self):
        licenses = [
            MockLicense("mit", ["MIT"], False),
            MockLicense("zlib", ["zlib"], False),
            MockLicense("d-zlib", ["D zlib"], False),
            MockLicense("mitr", ["mit or"], False),
        ]

        expression = "mit AND zlib or mit or mit"
        try:
            normalize_and_validate_expression(expression, licenses, validate_known=True)
            self.fail("Exception not raised")
        except ValidationError as e:
            expected = 'Invalid symbols sequence such as (A B) for token: "mit" at position: 23'
            self.assertEqual(expected, e.message)

    def test_normalize_and_validate_ticket_503_with_licensing_valid(self):
        licenses = [
            MockLicense("mit", ["MIT"], False),
            MockLicense("zlib", ["zlib"], False),
            MockLicense("d-zlib", ["D zlib"], False),
            MockLicense("mitr", ["mit or"], False),
        ]

        expression = "mit AND zlib or mit or and mit"
        results = normalize_and_validate_expression(expression, licenses, validate_known=True)
        expected = "(mit AND zlib) OR (mitr AND mit)"
        self.assertEqual(expected, results)

    def test_normalize_and_validate_ticket_503_with_licensing_2(self):
        licenses = [
            MockLicense("mit", ["MIT"], False),
            MockLicense("zlib", ["zlib"], False),
            MockLicense("d-zlib", ["D zlib"], False),
            MockLicense("mitr", ["mit or NOT"], False),
        ]

        expression = "mit AND zlib or mit or mit"
        results = normalize_and_validate_expression(expression, licenses, validate_known=True)
        expected = "(mit AND zlib) OR mit OR mit"
        self.assertEqual(expected, results)

    def test_expression_is_equivalent(self):
        licenses = [
            MockLicense("gps-2.0", ["GPL 2.0"], False),
            MockLicense("classpath-2.0", ["Classpath Exception 2.0"], True),
            MockLicense("gps-2.0-plus", ["GPL 2.0 or later"], False),
            MockLicense("lgps-2.1-plus", ["LGPL 2.1 or later"], False),
        ]
        ex1 = (
            "(GPL 2.0 or later with Classpath Exception 2.0 or GPL 2.0 or later)"
            " and LGPL 2.1 or later"
        )
        expression1 = parse_expression(ex1, licenses)
        ex2 = (
            "LGPL 2.1 or later and (GPL 2.0 or later oR"
            " GPL 2.0 or later with Classpath Exception 2.0)"
        )
        expression2 = parse_expression(ex2, licenses)
        ex3 = "LGPL 2.1 or later and (GPL 2.0 or later oR GPL 2.0 or later)"
        expression3 = parse_expression(ex3, licenses)

        licensing = build_licensing(licenses)
        self.assertTrue(licensing.is_equivalent(expression1, expression2))
        self.assertTrue(licensing.is_equivalent(expression2, expression1))
        self.assertFalse(licensing.is_equivalent(expression1, expression3))
        self.assertFalse(licensing.is_equivalent(expression2, expression3))

    def test_expression_is_equivalent_no_spaces(self):
        licenses = [
            MockLicense("gps-2.0", ["GPL-2.0"], False),
            MockLicense("classpath-2.0", ["Classpath-Exception-2.0"], True),
            MockLicense("gps-2.0-plus", ["GPL-2.0-or-later"], False),
            MockLicense("lgps-2.1-plus", ["LGPL-2.1-or-later"], False),
        ]
        ex1 = (
            "(GPL-2.0-or-later with Classpath-Exception-2.0 or GPL-2.0-or-later)"
            " and LGPL-2.1-or-later"
        )
        expression1 = parse_expression(ex1, licenses)
        ex2 = (
            "LGPL-2.1-or-later and (GPL-2.0-or-later oR GPL-2.0-or-later"
            " with Classpath-Exception-2.0)"
        )
        expression2 = parse_expression(ex2, licenses)
        ex3 = "LGPL-2.1-or-later and (GPL-2.0-or-later oR GPL-2.0-or-later)"
        expression3 = parse_expression(ex3, licenses)

        licensing = build_licensing(licenses)
        self.assertTrue(licensing.is_equivalent(expression1, expression2))
        self.assertTrue(licensing.is_equivalent(expression2, expression1))
        self.assertFalse(licensing.is_equivalent(expression1, expression3))
        self.assertFalse(licensing.is_equivalent(expression2, expression3))

    def test_get_unique_license_keys(self):
        expression = "(bsd-new OR eps-1.0 OR apache-2.0 OR mit) AND unknown AND bsd-new"
        expected = {"unknown", "bsd-new", "apache-2.0", "mit", "eps-1.0"}
        self.assertEqual(expected, get_unique_license_keys(expression))

        expression = "gps-2.0 WITH classpath OR (gps-2.0 AND lgpl) OR oracle-bcl"
        expected = {"lgpl", "oracle-bcl", "gps-2.0", "classpath"}
        self.assertEqual(expected, get_unique_license_keys(expression))


def _print_sequence_diff(left, right):
    for lft, rht in zip_longest(left.split(), right.split()):
        if lft == rht:
            continue
        print("left:", lft, "!= right:", rht)


class LicenseExpressionDataTestCase(TestCase):
    def check_parse(self, keyword, expression_items, keys, licenses):
        expression = keyword.join(expression_items)
        expected = keyword.upper().join(keys)
        result = normalize_and_validate_expression(
            expression,
            licenses=licenses,
            validate_known=True,
            validate_strict=False,
            include_available=False,
        )
        if expected != result:
            _print_sequence_diff(expected, result)
            self.assertEqual(expected, result)

    def test_normalize_and_validate_expression_on_all_licenses(self):
        # See testfiles/all_licenses.py to recreate this test data set
        self.maxDiff = None

        test_data = os.path.join(os.path.dirname(__file__), "testfiles", "all_licenses.json")
        with open(test_data) as f:
            licenses = json.load(f)

        keys = [key for key, _, _ in licenses]

        # using keys only
        key_only_symbols = [MockLicense(key, [], False) for key, _, _ in licenses]
        expression_items = keys
        self.check_parse(" and ", expression_items, keys=keys, licenses=key_only_symbols)
        self.check_parse(" or ", expression_items, keys=keys, licenses=key_only_symbols)

        # using key + short name
        short_name_alias_symbols = [
            MockLicense(key, [short_name], False) for key, _, short_name in licenses
        ]
        expression_items = keys
        self.check_parse(" and ", expression_items, keys=keys, licenses=short_name_alias_symbols)
        self.check_parse(" or ", expression_items, keys=keys, licenses=short_name_alias_symbols)

        short_names = [short_name for _, _, short_name in licenses]
        expression_items = short_names
        self.check_parse(" and ", expression_items, keys=keys, licenses=short_name_alias_symbols)
        self.check_parse(" or ", expression_items, keys=keys, licenses=short_name_alias_symbols)

        expression_items = keys + short_names
        self.check_parse(
            " and ", expression_items, keys=keys + keys, licenses=short_name_alias_symbols
        )
        self.check_parse(
            " or ", expression_items, keys=keys + keys, licenses=short_name_alias_symbols
        )

        # using full aliases
        full_alias_symbols = [
            MockLicense(key, [short_name, name], False) for key, name, short_name in licenses
        ]
        expression_items = keys
        self.check_parse(" and ", expression_items, keys=keys, licenses=full_alias_symbols)
        self.check_parse(" or ", expression_items, keys=keys, licenses=full_alias_symbols)

        expression_items = short_names
        self.check_parse(" and ", expression_items, keys=keys, licenses=full_alias_symbols)
        self.check_parse(" or ", expression_items, keys=keys, licenses=full_alias_symbols)

        expression_items = keys + short_names
        self.check_parse(" and ", expression_items, keys=keys + keys, licenses=full_alias_symbols)
        self.check_parse(" or ", expression_items, keys=keys + keys, licenses=full_alias_symbols)

        names = [name for _, name, _ in licenses]
        expression_items = names
        self.check_parse(" and ", expression_items, keys=keys, licenses=full_alias_symbols)
        self.check_parse(" or ", expression_items, keys=keys, licenses=full_alias_symbols)

        expression_items = keys + names
        self.check_parse(" and ", expression_items, keys=keys + keys, licenses=full_alias_symbols)
        self.check_parse(" or ", expression_items, keys=keys + keys, licenses=full_alias_symbols)

        expression_items = short_names + keys + names
        self.check_parse(
            " and ", expression_items, keys=keys + keys + keys, licenses=full_alias_symbols
        )
        self.check_parse(
            " or ", expression_items, keys=keys + keys + keys, licenses=full_alias_symbols
        )

        # using full aliases and with
        expression = " and ".join(" with ".join([x, y]) for x, y in zip(keys, names))
        expected = " AND ".join(" WITH ".join([x, y]) for x, y in zip(keys, keys))
        result = normalize_and_validate_expression(
            expression,
            licenses=full_alias_symbols,
            validate_known=True,
            validate_strict=False,
            include_available=False,
        )
        if expected != result:
            _print_sequence_diff(expected, result)
            self.assertEqual(expected, result)

        expression = " or ".join(" with ".join([x, y]) for x, y in zip(keys, names))
        expected = " OR ".join(" WITH ".join([x, y]) for x, y in zip(keys, keys))
        result = normalize_and_validate_expression(
            expression,
            licenses=full_alias_symbols,
            validate_known=True,
            validate_strict=False,
            include_available=False,
        )
        if expected != result:
            _print_sequence_diff(expected, result)
            self.assertEqual(expected, result)
