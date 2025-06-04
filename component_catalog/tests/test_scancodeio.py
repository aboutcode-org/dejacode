#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
from pathlib import Path
from unittest import mock

from django.test import TestCase

import requests

from component_catalog.models import Package
from component_catalog.tests import make_package
from dejacode_toolkit.scancodeio import ScanCodeIO
from dejacode_toolkit.scancodeio import check_for_existing_scan_workaround
from dejacode_toolkit.scancodeio import get_hash_uid
from dejacode_toolkit.scancodeio import get_notice_text_from_key_files
from dje.models import Dataspace
from dje.models import History
from dje.tasks import scancodeio_submit_scan
from dje.tests import create_superuser
from dje.tests import create_user
from license_library.models import License
from license_library.tests import make_license
from policy.tests import make_associated_policy
from policy.tests import make_usage_policy


class ScanCodeIOTestCase(TestCase):
    data = Path(__file__).parent / "testfiles"

    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Dataspace")
        self.basic_user = create_user("basic_user", self.dataspace)
        self.super_user = create_superuser("super_user", self.dataspace)

        self.license1 = make_license(key="l1", dataspace=self.dataspace)
        self.license2 = make_license(key="l2", dataspace=self.dataspace)
        self.package1 = make_package(
            filename="package1", download_url="http://url.com/package1", dataspace=self.dataspace
        )
        self.package1.license_expression = "{} AND {}".format(self.license1.key, self.license2.key)
        self.package1.save()

    @mock.patch("requests.head")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.submit_scan")
    def test_scancodeio_submit_scan_task(self, mock_submit_scan, mock_request_head):
        user_uuid = self.super_user.uuid
        dataspace_uuid = self.super_user.dataspace.uuid

        mock_request_head.side_effect = requests.RequestException
        scancodeio_submit_scan(["no_protocol.com"], user_uuid, dataspace_uuid)
        self.assertEqual([], mock_submit_scan.mock_calls)

        uris = {
            "http://okurl.com": mock.Mock(status_code=200),
            "https://okurl2.com": mock.Mock(status_code=200),
            "http://private_url.com": mock.Mock(status_code=404),
        }
        mock_request_head.side_effect = lambda arg, allow_redirects: uris[arg]
        scancodeio_submit_scan(list(uris.keys()), user_uuid, dataspace_uuid)

        expected = [
            mock.call("http://okurl.com", user_uuid, dataspace_uuid),
            mock.call().__bool__(),
            mock.call("https://okurl2.com", user_uuid, dataspace_uuid),
            mock.call().__bool__(),
        ]
        self.assertEqual(expected, mock_submit_scan.mock_calls)

    @mock.patch("requests.sessions.Session.get")
    def test_scancodeio_fetch_scan_list(self, mock_session_get):
        scancodeio = ScanCodeIO(self.dataspace)
        self.assertIsNone(scancodeio.fetch_scan_list())
        self.assertFalse(mock_session_get.called)

        scancodeio.fetch_scan_list(user=self.basic_user)
        params = mock_session_get.call_args.kwargs["params"]
        expected = {"format": "json", "name__endswith": get_hash_uid(self.basic_user.uuid)}
        self.assertEqual(expected, params)

        scancodeio.fetch_scan_list(dataspace=self.basic_user.dataspace)
        params = mock_session_get.call_args.kwargs["params"]
        expected = {
            "format": "json",
            "name__contains": get_hash_uid(self.basic_user.dataspace.uuid),
        }
        self.assertEqual(expected, params)

        scancodeio.fetch_scan_list(
            user=self.basic_user,
            dataspace=self.basic_user.dataspace,
            extra_params="extra",
        )
        params = mock_session_get.call_args.kwargs["params"]
        expected = {
            "format": "json",
            "name__contains": get_hash_uid(self.basic_user.dataspace.uuid),
            "name__endswith": get_hash_uid(self.basic_user.uuid),
            "extra_params": "extra",
        }
        self.assertEqual(expected, params)

    @mock.patch("requests.sessions.Session.get")
    def test_scancodeio_fetch_scan_info(self, mock_session_get):
        uri = "https://uri"
        scancodeio = ScanCodeIO(self.dataspace)

        scancodeio.fetch_scan_info(uri=uri)
        params = mock_session_get.call_args.kwargs["params"]
        expected = {
            "name__startswith": get_hash_uid(uri),
            "name__contains": get_hash_uid(self.basic_user.dataspace.uuid),
            "format": "json",
        }
        self.assertEqual(expected, params)

        scancodeio.fetch_scan_info(uri=uri, user=self.basic_user)
        params = mock_session_get.call_args.kwargs["params"]
        expected["name__endswith"] = get_hash_uid(self.basic_user.uuid)
        self.assertEqual(expected, params)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.request_get")
    def test_scancodeio_find_project(self, mock_request_get):
        scancodeio = ScanCodeIO(self.dataspace)
        scancodeio.find_project(name="project_name")
        params = mock_request_get.call_args.kwargs["params"]
        expected = {"name": "project_name"}
        self.assertEqual(expected, params)

        project_data = {
            "name": "project_name",
            "url": "/api/projects/f622d852-2d6a-4fb5-ab89-a90db54a4581/",
            "uuid": "f622d852-2d6a-4fb5-ab89-a90db54a4581",
        }
        mock_request_get.return_value = {
            "count": 1,
            "results": [
                project_data,
            ],
        }
        self.assertEqual(project_data, scancodeio.find_project(name="project_name"))

        mock_request_get.return_value = {
            "count": 0,
            "results": [],
        }
        self.assertIsNone(scancodeio.find_project(name="not-existing"))

        mock_request_get.return_value = {
            "count": 2,
            "results": [
                project_data,
                project_data,
            ],
        }
        self.assertIsNone(scancodeio.find_project(name="project_name"))

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.get_project_info")
    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.fetch_scan_data")
    def test_scancodeio_update_from_scan(self, mock_fetch_scan_data, mock_get_project_info):
        license_policy = make_usage_policy(self.dataspace, model=License)
        package_policy = make_usage_policy(self.dataspace, model=Package)
        make_associated_policy(license_policy, package_policy)
        license_mit = make_license(self.dataspace, key="mit", usage_policy=license_policy)
        self.dataspace.set_usage_policy_on_new_component_from_licenses = True
        self.dataspace.save()

        self.package1.license_expression = ""
        self.package1.save()
        scancodeio = ScanCodeIO(self.dataspace)

        mock_get_project_info.return_value = None
        mock_fetch_scan_data.return_value = None

        updated_fields = scancodeio.update_from_scan(self.package1, self.super_user)
        self.assertEqual([], updated_fields)

        mock_get_project_info.return_value = {"url": "https://scancode.io/"}
        updated_fields = scancodeio.update_from_scan(self.package1, self.super_user)
        self.assertEqual([], updated_fields)

        mock_fetch_scan_data.return_value = {"error": "Summary file not available"}
        updated_fields = scancodeio.update_from_scan(self.package1, self.super_user)
        self.assertEqual([], updated_fields)

        scan_summary_location = self.data / "summary" / "bulma-1.0.1-scancode.io-summary.json"
        with open(scan_summary_location) as f:
            scan_summary = json.load(f)

        mock_fetch_scan_data.return_value = scan_summary
        updated_fields = scancodeio.update_from_scan(self.package1, self.super_user)
        expected = [
            "license_expression",
            "declared_license_expression",
            "holder",
            "primary_language",
            "other_license_expression",
            "description",
            "homepage_url",
            "keywords",
            "copyright",
        ]
        self.assertEqual(expected, updated_fields)

        self.package1.refresh_from_db()
        self.assertEqual("mit", self.package1.license_expression)
        self.assertQuerySetEqual(self.package1.licenses.all(), [license_mit])
        self.assertEqual("mit", self.package1.declared_license_expression)
        self.assertEqual("apache-2.0", self.package1.other_license_expression)
        self.assertEqual("Jeremy Thomas", self.package1.holder)
        self.assertEqual("JavaScript", self.package1.primary_language)
        self.assertEqual("Modern CSS framework based on Flexbox", self.package1.description)
        self.assertEqual("https://bulma.io", self.package1.homepage_url)
        self.assertEqual("Copyright Jeremy Thomas", self.package1.copyright)
        expected_keywords = ["css", "sass", "scss", "flexbox", "grid", "responsive", "framework"]
        self.assertEqual(expected_keywords, self.package1.keywords)

        # Policy from license set in SetPolicyFromLicenseMixin.save()
        self.assertEqual(package_policy, self.package1.usage_policy)

        self.assertEqual(self.super_user, self.package1.last_modified_by)
        history_entry = History.objects.get_for_object(self.package1).get()
        expected = (
            "Automatically updated license_expression, declared_license_expression, holder, "
            "primary_language, other_license_expression, description, homepage_url, "
            "keywords, copyright from scan results"
        )
        self.assertEqual(expected, history_entry.change_message)

        # Inferred Copyright statement
        mock_fetch_scan_data.return_value = {"key_files_packages": [{"name": "package1"}]}
        self.package1.copyright = ""
        self.package1.save()
        updated_fields = scancodeio.update_from_scan(self.package1, self.super_user)
        self.assertEqual(["copyright"], updated_fields)
        self.package1.refresh_from_db()
        self.assertEqual("Copyright package1 project contributors", self.package1.copyright)

        mock_fetch_scan_data.return_value = {"some_key": "some_value"}
        self.package1.name = "bulma"
        self.package1.copyright = ""
        self.package1.save()
        updated_fields = scancodeio.update_from_scan(self.package1, self.super_user)
        self.assertEqual(["copyright"], updated_fields)
        self.package1.refresh_from_db()
        self.assertEqual("Copyright bulma project contributors", self.package1.copyright)

    def test_scancodeio_map_detected_package_data(self):
        detected_package = {
            "purl": "pkg:maven/aopalliance/aopalliance@1.0",
            "primary_language": "Java",
            "declared_license_expression": "mit AND mit",
            "other_license_expression": "apache-2.0 AND apache-2.0",
            "keywords": [
                "json",
                "Development Status :: 5 - Production/Stable",
                "Operating System :: OS Independent",
            ],
            # skipped, no values
            "description": "",
            # skipped, not a SCAN_PACKAGE_FIELD
            "is_key_file": 1,
        }

        expected = {
            "package_url": "pkg:maven/aopalliance/aopalliance@1.0",
            "purl": "pkg:maven/aopalliance/aopalliance@1.0",
            "license_expression": "mit",
            "declared_license_expression": "mit",
            "other_license_expression": "apache-2.0",
            "primary_language": "Java",
            "keywords": [
                "json",
                "Development Status :: 5 - Production/Stable",
                "Operating System :: OS Independent",
            ],
        }
        mapped_data = ScanCodeIO.map_detected_package_data(detected_package)
        self.assertEqual(expected, mapped_data)

    @mock.patch("dejacode_toolkit.scancodeio.ScanCodeIO.request_get")
    def test_scancodeio_fetch_project_packages(self, mock_request_get):
        scancodeio = ScanCodeIO(self.dataspace)

        mock_request_get.return_value = None
        with self.assertRaises(Exception):
            scancodeio.fetch_project_packages(project_uuid="abcd")

        mock_request_get.return_value = {
            "next": None,
            "results": ["p1", "p2"],
        }
        packages = scancodeio.fetch_project_packages(project_uuid="abcd")
        self.assertEqual(["p1", "p2"], packages)

    def test_scancodeio_get_notice_text_from_key_files(self):
        scan_summary = {}
        notice_text = get_notice_text_from_key_files(scan_summary)
        self.assertEqual("", notice_text)

        key_file_data1 = {
            "name": "NOTICE.md",
            "content": "  Content from file1  \n",
        }
        scan_summary = {"key_files": [key_file_data1]}
        notice_text = get_notice_text_from_key_files(scan_summary)
        self.assertEqual("Content from file1", notice_text)

        key_file_data2 = {
            "name": "about.NOTICE.txt",
            "content": "\n  Content from file2",
        }
        scan_summary = {"key_files": [key_file_data1, key_file_data2]}
        notice_text = get_notice_text_from_key_files(scan_summary)
        self.assertEqual("Content from file1\n\n---\n\nContent from file2", notice_text)

        key_file_data1["name"] = "README"
        scan_summary = {"key_files": [key_file_data1]}
        notice_text = get_notice_text_from_key_files(scan_summary)
        self.assertEqual("", notice_text)

    @mock.patch("component_catalog.models.Package.update_from_scan")
    def test_scancodeio_check_for_existing_scan_workaround(self, mock_update_from_scan):
        mock_update_from_scan.return_value = ["updated_field"]
        download_url = self.package1.download_url
        user = self.basic_user

        response_json = None
        results = check_for_existing_scan_workaround(response_json, download_url, user)
        self.assertIsNone(results)

        response_json = {"success": True}
        results = check_for_existing_scan_workaround(response_json, download_url, user)
        self.assertIsNone(results)

        response_json = {"name": "project with this name already exists."}
        results = check_for_existing_scan_workaround(response_json, download_url, user)
        self.assertEqual(["updated_field"], results)
