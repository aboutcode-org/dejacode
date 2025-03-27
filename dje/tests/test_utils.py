#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import zipfile
import zoneinfo
from unittest import mock

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models.functions import Lower
from django.http import QueryDict
from django.test import TestCase
from django.test.client import RequestFactory
from django.urls import ResolverMatch
from django.urls import resolve
from django.utils import timezone

from dejacode_toolkit.utils import md5
from dejacode_toolkit.utils import sha1
from dje.copier import copy_object
from dje.models import Dataspace
from dje.utils import database_re_escape
from dje.utils import extract_name_version
from dje.utils import get_duplicates
from dje.utils import get_instance_from_referer
from dje.utils import get_instance_from_resolver
from dje.utils import get_object_compare_diff
from dje.utils import get_referer_resolver
from dje.utils import get_zipfile
from dje.utils import group_by_name_version
from dje.utils import is_available
from dje.utils import is_purl_fragment
from dje.utils import is_purl_str
from dje.utils import localized_datetime
from dje.utils import merge_relations
from dje.utils import normalize_newlines_as_CR_plus_LF
from dje.utils import remove_field_from_query_dict
from dje.utils import str_to_id_list
from dje.views import get_previous_next

Package = apps.get_model("component_catalog", "package")
Component = apps.get_model("component_catalog", "component")
UsagePolicy = apps.get_model("policy", "usagepolicy")
Owner = apps.get_model("organization", "owner")
License = apps.get_model("license_library", "license")
ExternalReference = apps.get_model("dje", "ExternalReference")
ExternalSource = apps.get_model("dje", "ExternalSource")


class DJEUtilsTestCase(TestCase):
    def test_normalize_newlines_as_CR_plus_LF(self):
        inputs = [
            # (text, expected)
            ("TMate\nTMate", "TMate\r\nTMate"),
            ("TMate\r\nTMate", "TMate\r\nTMate"),
            ("TMate\n\nTMate", "TMate\r\n\r\nTMate"),
            ("TMate\rTMate", "TMate\rTMate"),
            (
                "Lise\n\n1. PRE\n\n\tThis license [...] \n\tAPI.",
                "Lise\r\n\r\n1. PRE\r\n\r\n\tThis license [...] \r\n\tAPI.",
            ),
        ]

        for text, expected in inputs:
            self.assertEqual(expected, normalize_newlines_as_CR_plus_LF(text))

    def test_utils_sha1(self):
        expected = "a17c9aaa61e80a1bf71d0d850af4e5baa9800bbd"
        self.assertEqual(expected, sha1(b"data"))

    def test_utils_md5(self):
        expected = "8d777f385d3dfec8815d20f7496026dc"
        self.assertEqual(expected, md5(b"data"))

    def test_extract_name_version(self):
        inputs = [
            # (text, expected)
            [":", ("", "")],
            [":::::", ("::::", "")],
            ["a:1.0", ("a", "1.0")],
            ["  a  :  1.0", ("  a  ", "  1.0")],
            ["a:", ("a", "")],
            [":1.0", ("", "1.0")],
            ["a:b:c:1.0", ("a:b:c", "1.0")],
            ["a:b:c:", ("a:b:c", "")],
            ["a:b:c", ("a:b", "c")],
            ["a :: b :: c:1.0", ("a :: b :: c", "1.0")],
        ]

        for text, expected in inputs:
            self.assertEqual(expected, extract_name_version(text))

        for text in [None, "", "a"]:
            with self.assertRaises(SyntaxError):
                extract_name_version(text)

    def test_get_object_compare_diff(self):
        nexb_dataspace = Dataspace.objects.create(name="nexB")
        other_dataspace = Dataspace.objects.create(name="Other")
        nexb_user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", nexb_dataspace
        )

        package1 = Package.objects.create(filename="package1", dataspace=nexb_dataspace)

        copied_package = copy_object(package1, other_dataspace, nexb_user)
        copied_package.filename = "new name"
        copied_package.save()

        compare_diff, compare_diff_m2m = get_object_compare_diff(package1, copied_package)
        opts = Package._meta
        expected = {
            opts.get_field("filename"): ["package1", "new name"],
        }
        self.assertEqual(expected, compare_diff)
        self.assertEqual({}, compare_diff_m2m)

    def test_get_object_compare_diff_with_fk_none(self):
        # The purpose is to have one FK set on the source and nothing on the target
        nexb_dataspace = Dataspace.objects.create(name="nexB")

        component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=ContentType.objects.get_for_model(Component),
            dataspace=nexb_dataspace,
        )

        component1 = Component.objects.create(
            name="c1",
            version="1.0",
            dataspace=nexb_dataspace,
            usage_policy=component_policy,
        )

        component2 = Component.objects.create(
            name="c1",
            version="2.0",
            dataspace=nexb_dataspace,
        )

        result = str(get_object_compare_diff(component1, component2))
        self.assertTrue("usage_policy" in result)
        self.assertTrue("[<UsagePolicy: ComponentPolicy>, None]" in result)

    def test_get_object_compare_diff_user_fk_fields_excluded(self):
        nexb_dataspace = Dataspace.objects.create(name="nexB")
        other_dataspace = Dataspace.objects.create(name="Other")
        nexb_user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", nexb_dataspace
        )
        other_user = get_user_model().objects.create_superuser(
            "other_user", "test2@test.com", "t3st", other_dataspace
        )

        package1 = Package.objects.create(filename="package1", dataspace=nexb_dataspace)
        package1.created_by = nexb_user
        package1.last_modified_by = nexb_user
        package1.save()

        copied = copy_object(package1, other_dataspace, other_user)
        self.assertEqual(other_user, copied.created_by)
        self.assertEqual(other_user, copied.last_modified_by)

        compare_diff, compare_diff_m2m = get_object_compare_diff(package1, copied)

        self.assertEqual({}, compare_diff)
        self.assertEqual({}, compare_diff_m2m)

    def test_dje_utils_get_duplicates(self):
        nexb_dataspace = Dataspace.objects.create(name="nexB")
        Owner.objects.create(name="owner1", notes="a", dataspace=nexb_dataspace)
        Owner.objects.create(name="OwNer1", notes="a", dataspace=nexb_dataspace)
        Owner.objects.create(name="owner2", notes="b", dataspace=nexb_dataspace)
        queryset = Owner.objects.scope_by_name("nexB")

        self.assertEqual([], get_duplicates(queryset, "name"))
        self.assertEqual(["owner1"], get_duplicates(queryset, "name", Lower))
        self.assertEqual(["a"], get_duplicates(queryset, "notes"))

    def test_dje_utils_merge_relations(self):
        nexb_dataspace = Dataspace.objects.create(name="nexB")
        alternate_dataspace = Dataspace.objects.create(name="Alternate")
        original = Owner.objects.create(name="OwNer1", dataspace=nexb_dataspace)
        duplicate = Owner.objects.create(name="owner1", dataspace=nexb_dataspace)

        component1 = Component.objects.create(name="c1", owner=duplicate, dataspace=nexb_dataspace)
        license1 = License.objects.create(key="l1", owner=duplicate, dataspace=nexb_dataspace)
        external_source = ExternalSource.objects.create(label="Source1", dataspace=nexb_dataspace)
        er1 = ExternalReference.objects.create_for_content_object(duplicate, external_source, "id")

        self.assertEqual(0, original.component_set.count())
        self.assertEqual(0, original.license_set.count())
        self.assertEqual(0, original.external_references.count())

        self.assertEqual(1, duplicate.component_set.count())
        self.assertEqual(1, duplicate.license_set.count())
        self.assertEqual(1, duplicate.external_references.count())

        merge_relations(original, duplicate)

        self.assertEqual(1, original.component_set.count())
        self.assertEqual(1, original.license_set.count())
        self.assertEqual(1, original.external_references.count())

        self.assertEqual(component1, original.component_set.get())
        self.assertEqual(license1, original.license_set.get())
        self.assertEqual(er1, original.external_references.get())

        self.assertEqual(0, duplicate.component_set.count())
        self.assertEqual(0, duplicate.license_set.count())
        self.assertEqual(0, duplicate.external_references.count())

        with self.assertRaises(AssertionError):
            merge_relations(component1, license1)

        alternate_owner = Owner.objects.create(name="OwNer1", dataspace=alternate_dataspace)
        with self.assertRaises(AssertionError):
            merge_relations(original, alternate_owner)

    def test_dje_utils_group_by_name_version(self):
        test_cases = [
            {
                "input": [
                    "1.2",
                    "1.2rc1",
                    "1.2beta2",
                    "1.2beta",
                    "1.2alpha",
                    "1.2.1",
                    "1.1",
                    "1.3",
                ],
                "expected": [
                    "1.3",
                    "1.2.1",
                    "1.2",
                    "1.2rc1",
                    "1.2beta",
                    "1.2beta2",
                    "1.2alpha",
                    "1.1",
                ],
            },
            {
                "input": [
                    "1.9.9a",
                    "1.11",
                    "1.9.9b",
                    "1.11.4",
                    "1.10.1",
                    "1.11a",
                ],
                "expected": [
                    "1.11.4",
                    "1.11",
                    "1.11a",
                    "1.10.1",
                    "1.9.9b",
                    "1.9.9a",
                ],
            },
            {
                "input": [
                    "1.0",
                    "",
                    "1.0.0",
                ],
                "expected": [
                    "",
                    "1.0.0",
                    "1.0",
                ],
            },
            {
                "input": [
                    "0.9.6",
                    "2.2.10",
                    "2.3.0",
                    "2.2.9",
                    "0.99.3",
                    "1.0.0",
                    "0.99.5",
                    "1.0.1",
                    "0.99.4.2",
                    "0.9.4.pre1",
                    "0.9.4.1",
                    "1.0.0.rc1",
                    "0.99.4",
                ],
                "expected": [
                    "2.3.0",
                    "2.2.10",
                    "2.2.9",
                    "1.0.1",
                    "1.0.0.rc1",
                    "1.0.0",
                    "0.99.5",
                    "0.99.4.2",
                    "0.99.4",
                    "0.99.3",
                    "0.9.6",
                    "0.9.4.pre1",
                    "0.9.4.1",
                ],
            },
            {
                "input": [
                    "4.5.1",
                    "4.4rc2",
                    "4.4rc1",
                    "4.4.2",
                    " ",
                ],
                "expected": [
                    " ",
                    "4.5.1",
                    "4.4.2",
                    "4.4rc2",
                    "4.4rc1",
                ],
            },
            {
                "input": [
                    "1.1.0-rc1",
                    "1.1.0",
                    "1.1.1",
                    "1.1.0-rc2",
                ],
                "expected": [
                    "1.1.1",
                    "1.1.0",
                    "1.1.0-rc2",
                    "1.1.0-rc1",
                ],
            },
        ]

        for test in test_cases:
            object_list = [Component(name="a", version=version) for version in test["input"]]

            results = [
                component.version
                for components in group_by_name_version(object_list)
                for component in components
            ]

            self.assertEqual(test["expected"], results)

    def test_remove_field_from_query_dict(self):
        self.assertEqual("", remove_field_from_query_dict({}, "a"))
        self.assertEqual("", remove_field_from_query_dict(QueryDict(), "a"))

        query_string = "q=ORBit2&primary_language=C&primary_language=ABC&keywords=Library"
        query_dict = QueryDict(query_string)

        expected = "q=ORBit2&primary_language=C&primary_language=ABC&keywords=Library"
        self.assertEqual(expected, remove_field_from_query_dict(query_dict, "not_existing"))

        expected = "primary_language=C&primary_language=ABC&keywords=Library"
        self.assertEqual(expected, remove_field_from_query_dict(query_dict, "q"))

        expected = "q=ORBit2&keywords=Library"
        self.assertEqual(expected, remove_field_from_query_dict(query_dict, "primary_language"))

        expected = "q=ORBit2&keywords=Library"
        self.assertEqual(
            expected, remove_field_from_query_dict(query_dict, "primary_language", "bad_value")
        )

        expected = "q=ORBit2&keywords=Library&primary_language=C"
        self.assertEqual(
            expected, remove_field_from_query_dict(query_dict, "primary_language", "ABC")
        )

        expected = "q=ORBit2&keywords=Library"
        self.assertEqual(expected, remove_field_from_query_dict(query_dict, "primary_language", ""))

    def test_database_re_escape(self):
        self.assertEqual("Araújo", database_re_escape("Araújo"))
        self.assertEqual("c\\+\\+", database_re_escape("c++"))
        self.assertEqual("\\y\\$\\^", database_re_escape("\\y$^"))

    def test_get_referer_resolver(self):
        factory = RequestFactory()

        request = factory.request()
        resolver = get_referer_resolver(request)
        self.assertIsNone(resolver)

        request = factory.request(HTTP_REFERER="cannot_be_resolved")
        resolver = get_referer_resolver(request)
        self.assertIsNone(resolver)

        nexb_dataspace = Dataspace.objects.create(name="nexB")
        component1 = Component.objects.create(name="c1", dataspace=nexb_dataspace)
        request = factory.request(HTTP_REFERER=component1.get_absolute_url())
        resolver = get_referer_resolver(request)
        self.assertEqual(ResolverMatch, type(resolver))
        self.assertEqual(resolver.kwargs, {"dataspace": "nexB", "name": "c1"})
        self.assertEqual(resolver.url_name, "component_details")

    def test_get_instance_from_resolver(self):
        instance = get_instance_from_resolver(None)
        self.assertIsNone(instance)

        nexb_dataspace = Dataspace.objects.create(name="nexB")
        component1 = Component.objects.create(name="c1", dataspace=nexb_dataspace)
        resolver = resolve(component1.get_absolute_url())
        instance = get_instance_from_resolver(resolver)
        self.assertIsNone(instance)

        resolver = resolve(component1.get_admin_url())
        instance = get_instance_from_resolver(resolver)
        self.assertEqual(instance, component1)

    def test_get_instance_from_referer(self):
        factory = RequestFactory()

        request = factory.request()
        resolver = get_instance_from_referer(request)
        self.assertIsNone(resolver)

        request = factory.request(HTTP_REFERER="cannot_be_resolved")
        resolver = get_instance_from_referer(request)
        self.assertIsNone(resolver)

        nexb_dataspace = Dataspace.objects.create(name="nexB")
        component1 = Component.objects.create(name="c1", dataspace=nexb_dataspace)
        request = factory.request(HTTP_REFERER=component1.get_absolute_url())
        instance = get_instance_from_referer(request)
        self.assertIsNone(instance)

        request = factory.request(HTTP_REFERER=component1.get_admin_url())
        instance = get_instance_from_referer(request)
        self.assertEqual(instance, component1)

    @mock.patch("dje.utils.requests.get")
    @mock.patch("dje.utils.requests.head")
    def test_utils_is_available_download_url(self, mock_head, mock_get):
        url = "https://available.nexb"

        mock_head.return_value = mock.Mock(status_code=200)
        mock_get.return_value = mock.Mock(status_code=200)
        self.assertTrue(is_available(url))

        mock_head.return_value = mock.Mock(status_code=404)
        mock_get.return_value = mock.Mock(status_code=404)
        self.assertFalse(is_available(url))

        mock_head.return_value = mock.Mock(status_code=403)
        mock_get.return_value = mock.Mock(status_code=200)
        self.assertTrue(is_available(url))

    def test_utils_get_zipfile(self):
        files = [
            ("/ibus-/hangul-1.5.0./tar.gz.ABOUT", "about_resource: ibus-/hangul-1.5.0.//tar.gz\n"),
            ("6rd-init_1.0.tar.gz.NOTICE", "Copyright(c) 6rd Project"),
        ]

        output = get_zipfile(files)
        self.assertTrue(zipfile.is_zipfile(output))

        zip_file = zipfile.ZipFile(output)
        expected_namelist = [
            "_ibus-_hangul-1.5.0._tar.gz.ABOUT",
            "6rd-init_1.0.tar.gz.NOTICE",
        ]
        self.assertEqual(expected_namelist, zip_file.namelist())

    def test_utils_str_to_id_list(self):
        self.assertEqual([], str_to_id_list(None))
        self.assertEqual([], str_to_id_list([]))
        self.assertEqual([], str_to_id_list(""))
        self.assertEqual([], str_to_id_list("a"))

        self.assertEqual([1], str_to_id_list(1))
        self.assertEqual([1], str_to_id_list("1"))
        self.assertEqual([1, 2, 3], str_to_id_list("1,2,3,a"))

    def test_utils_get_previous_next(self):
        self.assertEqual((2, 4), get_previous_next([1, 2, 3, 4], 3))
        self.assertEqual((None, 2), get_previous_next([1, 2, 3, 4], 1))
        self.assertEqual((3, None), get_previous_next([1, 2, 3, 4], 4))
        self.assertEqual((None, None), get_previous_next([1, 2, 3, 4], 8))
        self.assertEqual(("a", "c"), get_previous_next(["a", "b", "c"], "b"))
        self.assertEqual((None, None), get_previous_next(["a", "b", "c"], 2))

    def test_utils_is_purl_str(self):
        self.assertFalse(is_purl_str(""))
        self.assertFalse(is_purl_str("a"))
        self.assertFalse(is_purl_str("not:a/purl"))

        self.assertTrue(is_purl_str("pkg:"))
        self.assertFalse(is_purl_str("pkg:", validate=True))

        self.assertTrue(is_purl_str("pkg:npm/is-npm@1.0.0"))
        self.assertTrue(is_purl_str("pkg:npm/is-npm@1.0.0", validate=True))

    def test_utils_is_purl_fragment(self):
        valid_fragments = [
            "pkg:npm/package@1.0.0",  # Valid full PURL
            "npm/package@1.0.0",  # PURL without pkg: prefix
            "npm/type",  # Fragment with type and namespace
            "name@version",  # Fragment with name and version
            "namespace/name",  # Fragment with namespace and name
            "npm/package",  # Type and package name
            "package@1.0.0",  # Name and version
        ]

        invalid_fragments = [
            "package",  # Just the package name
            "package 1.0.0",  # No connector
        ]

        for fragment in valid_fragments:
            self.assertTrue(is_purl_fragment(fragment), msg=fragment)

        for fragment in invalid_fragments:
            self.assertFalse(is_purl_fragment(fragment), msg=fragment)

    def test_utils_localized_datetime(self):
        self.assertIsNone(localized_datetime(None))

        timezone.deactivate()
        dt = "2025-01-13T19:11:08.216188"
        self.assertEqual("Jan 13, 2025, 7:11 PM UTC", localized_datetime(dt))
        dt = "2025-01-13T19:11:08.216188+01:00"
        self.assertEqual("Jan 13, 2025, 6:11 PM UTC", localized_datetime(dt))

        timezone.activate(zoneinfo.ZoneInfo("America/Los_Angeles"))
        dt = "2025-01-13T19:11:08.216188"
        self.assertEqual("Jan 13, 2025, 11:11 AM PST", localized_datetime(dt))
        dt = "2025-01-13T19:11:08.216188+01:00"
        self.assertEqual("Jan 13, 2025, 10:11 AM PST", localized_datetime(dt))
