#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
from hashlib import md5
from urllib.parse import quote_plus

from django.apps import apps
from django.conf import settings
from django.core import signing
from django.urls import reverse

import requests
from license_expression import Licensing

from dejacode_toolkit import BaseService
from dejacode_toolkit import logger


class ScanCodeIO(BaseService):
    label = "ScanCode.io"
    settings_prefix = "SCANCODEIO"
    url_field_name = "scancodeio_url"
    api_key_field_name = "scancodeio_api_key"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_api_url = f"{self.api_url}projects/"

    def get_scan_detail_url(self, project_uuid):
        return f"{self.project_api_url}{project_uuid}/"

    def get_scan_action_url(self, project_uuid, action_name):
        detail_url = self.get_scan_detail_url(project_uuid)
        return f"{detail_url}{action_name}/"

    def get_scan_results(self, download_url, dataspace):
        scan_info = self.fetch_scan_info(uri=download_url, dataspace=dataspace)

        if not scan_info or scan_info.get("count") < 1:
            return

        # In case multiple results entries are returned for the `download_url`
        # within this `dataspace`, the first one (most recent scan,
        # latest created date) is always used.
        # This could happen if a scan was trigger for the same URL by a
        # different user within a common Dataspace.
        # Note that this possibility is not available from the DejaCode UI if
        # scan results are already available (Scan button is hidden in that case).
        scan_results = scan_info.get("results")[0]
        return scan_results

    def submit_scan(self, uri, user_uuid, dataspace_uuid):
        data = {
            "name": get_project_name(uri, user_uuid, dataspace_uuid),
            "input_urls": uri,
            "pipeline": "scan_single_package",
            "execute_now": True,
        }

        webhook_url = get_webhook_url("notifications:send_scan_notification", user_uuid)
        data["webhook_url"] = webhook_url

        logger.debug(f'{self.label}: submit scan uri="{uri}" webhook_url="{webhook_url}"')
        return self.request_post(url=self.project_api_url, json=data)

    def submit_project(
        self, project_name, pipeline_name, file_location, user_uuid, execute_now=False
    ):
        data = {
            "name": project_name,
            "pipeline": pipeline_name,
            "execute_now": execute_now,
        }
        files = {
            "upload_file": open(file_location, "rb"),
        }

        webhook_url = get_webhook_url(
            "product_portfolio:import_packages_from_scancodeio", user_uuid
        )
        data["webhook_url"] = webhook_url

        logger.debug(
            f"{self.label}: submit pipeline={pipeline_name} "
            f'project_name="{project_name}" webhook_url="{webhook_url}"'
        )
        return self.request_post(url=self.project_api_url, data=data, files=files)

    def start_pipeline(self, run_url):
        start_pipeline_url = run_url + "start_pipeline/"
        return self.request_post(url=start_pipeline_url)

    def fetch_scan_list(self, user=None, dataspace=None, **extra_payload):
        payload = {}

        if dataspace:
            payload["name__contains"] = get_hash_uid(dataspace.uuid)

        if user:
            payload["name__endswith"] = get_hash_uid(user.uuid)

        payload.update(extra_payload)
        if not payload:
            return

        logger.debug(f'{self.label}: fetch scan list payload="{payload}"')
        return self.request_get(url=self.project_api_url, params=payload)

    def fetch_scan_by_project_names(self, names):
        payload = {"names": ",".join(names)}

        logger.debug(f'{self.label}: fetch scan fetch_scan_by_project_names payload="{payload}"')
        return self.request_get(url=self.project_api_url, params=payload)

    def find_project(self, **kwargs):
        """Search the project list using the provided `kwargs` as payload."""
        logger.debug(f'{self.label}: find_project payload="{kwargs}"')
        if response := self.request_get(url=self.project_api_url, params=kwargs):
            if response.get("count") == 1:
                return response.get("results")[0]

    def fetch_scan_info(self, uri, user=None, dataspace=None):
        payload = {
            "name__startswith": get_hash_uid(uri),
        }

        if dataspace:
            payload["name__contains"] = get_hash_uid(dataspace.uuid)

        if user:
            payload["name__endswith"] = get_hash_uid(user.uuid)

        logger.debug(f'{self.label}: fetch scan info uri="{uri}"')
        return self.request_get(url=self.project_api_url, params=payload)

    def fetch_scan_data(self, data_url):
        logger.debug(f"{self.label}: get scan data data_url={data_url}")
        return self.request_get(url=data_url)

    def stream_scan_data(self, data_url):
        logger.debug(f"{self.label}: stream scan data data_url={data_url}")
        return self.session.get(url=data_url, stream=True)

    def delete_scan(self, detail_url):
        logger.debug(f"{self.label}: delete scan detail_url={detail_url}")
        try:
            response = self.session.delete(url=detail_url)
            return response.status_code == 204
        except (requests.RequestException, ValueError, TypeError) as exception:
            logger.debug(f"{self.label} [Exception] {exception}")
        return False

    def update_from_scan(self, package, user):
        """
        Update the provided `package` instance using values from Scan results.
        Only blank/null fields are updated. Fields with existing values are skipped.
        An entry is logged in the `package` history using the provided `user`.
        """
        logger.debug(f'{self.label}: Start "update from scan" for package="{package}"')

        History = apps.get_model("dje", "History")
        values_from_scan = {}  # {'model_field': 'value_from_scan'}
        updated_fields = []

        scan_results = self.get_scan_results(
            download_url=package.download_url,
            dataspace=package.dataspace,
        )

        if not scan_results:
            logger.debug(f'{self.label}: scan not available for package="{package}"')
            return []

        summary_url = scan_results.get("url").split("?")[0] + "summary/"
        scan_summary = self.fetch_scan_data(summary_url)

        if not scan_summary:
            logger.debug(f'{self.label}: scan summary not available for package="{package}"')
            return []

        # 1. Summary fields: declared_license_expression, license_expression,
        #   declared_holder, primary_language
        for summary_field, model_field in self.AUTO_UPDATE_FIELDS:
            summary_field_value = scan_summary.get(summary_field)
            if summary_field_value:
                values_from_scan[model_field] = summary_field_value

        # 2. Detected Package fields: SCAN_PACKAGE_FIELD
        key_files_packages = scan_summary.get("key_files_packages", [])
        detected_package = {}
        if key_files_packages:
            detected_package = key_files_packages[0]
            detected_package_data = self.map_detected_package_data(detected_package)
            for model_field, scan_value in detected_package_data.items():
                if scan_value and model_field not in ["package_url", "purl"]:
                    values_from_scan[model_field] = scan_value

        # 3a. Inferred values: copyright
        if not values_from_scan.get("copyright", None):
            if holder := values_from_scan.get("holder"):
                values_from_scan["copyright"] = f"Copyright {holder}"
            elif package.name:
                values_from_scan["copyright"] = f"Copyright {package.name} project contributors"
            elif package_name := detected_package.get("name"):
                values_from_scan["copyright"] = f"Copyright {package_name} project contributors"

        # 3b. Inferred values: notice_text, generated from key fields.
        if not values_from_scan.get("notice_text", None):
            if notice_text := get_notice_text_from_key_files(scan_summary):
                values_from_scan["notice_text"] = notice_text

        if values_from_scan:
            updated_fields = package.update_from_data(
                user,
                values_from_scan,
                override=False,
                override_unknown=True,
            )
            if updated_fields:
                msg = f"Automatically updated {', '.join(updated_fields)} from scan results"
                logger.debug(f"{self.label}: {msg}")
                History.log_change(user, package, message=msg)

        return updated_fields

    def fetch_results(self, api_url):
        results = []

        next_url = api_url
        while next_url:
            logger.debug(f"{self.label}: fetch results from api_url={next_url}")
            response = self.request_get(url=next_url)
            if not response:
                raise Exception("Error fetching results")

            results.extend(response["results"])
            next_url = response["next"]

        return results

    def fetch_project_packages(self, project_uuid):
        """Return the list of packages for the provided `project_uuid`."""
        api_url = self.get_scan_action_url(project_uuid, "packages")
        return self.fetch_results(api_url)

    def fetch_project_dependencies(self, project_uuid):
        """Return the list of dependencies for the provided `project_uuid`."""
        api_url = self.get_scan_action_url(project_uuid, "dependencies")
        return self.fetch_results(api_url)

    # (label, scan_field, model_field, input_type)
    SCAN_SUMMARY_FIELDS = [
        (
            "Declared license",
            "declared_license_expression",
            "declared_license_expression",
            "checkbox",
        ),
        ("Declared holder", "declared_holder", "holder", "checkbox"),
        ("Primary language", "primary_language", "primary_language", "radio"),
        ("Other licenses", "other_license_expressions", "other_license_expression", "checkbox"),
        ("Other holders", "other_holders", "holder", "checkbox"),
        ("Other languages", "other_languages", "primary_language", "radio"),
    ]

    # (label, scan_field)
    SCAN_PACKAGE_FIELD = [
        ("Package URL", "purl"),
        ("Declared license", "declared_license_expression"),
        ("Other license", "other_license_expression"),
        ("Copyright", "copyright"),
        ("Holder", "holder"),
        ("Description", "description"),
        ("Primary language", "primary_language"),
        ("Homepage URL", "homepage_url"),
        ("Keywords", "keywords"),
        ("Release date", "release_date"),
        ("Notice text", "notice_text"),
        # ('Dependencies', 'dependencies'),
    ]

    # (label, field_name, value_key)
    KEY_FILE_DETECTION_FIELDS = [
        ("Detected license", "detected_license_expression", None),
        ("Programming language", "programming_language", None),
        ("Copyrights", "copyrights", "copyright"),
        ("Holders", "holders", "holder"),
        ("Authors", "authors", "author"),
        ("Emails", "emails", "email"),
        ("URLs", "urls", "url"),
    ]

    LICENSE_CLARITY_FIELDS = [
        (
            "Declared license",
            "declared_license",
            "Indicates that the software package licensing is documented at top-level or "
            "well-known locations in the software project, typically in a package "
            "manifest, NOTICE, LICENSE, COPYING or README file. "
            "Scoring Weight = 40.",
            "+40",
        ),
        (
            "Identification precision",
            "identification_precision",
            "Indicates how well the license statement(s) of the software identify known "
            "licenses that can be designated by precise keys (identifiers) as provided in "
            "a publicly available license list, such as the ScanCode LicenseDB, the SPDX "
            "license list, the OSI license list, or a URL pointing to a specific license "
            "text in a project or organization website. "
            "Scoring Weight = 40.",
            "+40",
        ),
        (
            "License text",
            "has_license_text",
            "Indicates that license texts are provided to support the declared license "
            "expression in files such as a package manifest, NOTICE, LICENSE, COPYING or "
            "README. "
            "Scoring Weight = 10.",
            "+10",
        ),
        (
            "Declared copyrights",
            "declared_copyrights",
            "Indicates that the software package copyright is documented at top-level or "
            "well-known locations in the software project, typically in a package "
            "manifest, NOTICE, LICENSE, COPYING or README file. "
            "Scoring Weight = 10.",
            "+10",
        ),
        (
            "Ambiguous compound licensing",
            "ambiguous_compound_licensing",
            "Indicates that the software has a license declaration that makes it "
            "difficult to construct a reliable license expression, such as in the case "
            "of multiple licenses where the conjunctive versus disjunctive relationship "
            "is not well defined. "
            "Scoring Weight = -10.",
            "-10",
        ),
        (
            "Conflicting license categories",
            "conflicting_license_categories",
            "Indicates the declared license expression of the software is in the "
            "permissive category, but that other potentially conflicting categories, "
            "such as copyleft and proprietary, have been detected in lower level code. "
            "Scoring Weight = -20.",
            "-20",
        ),
        (
            "Score",
            "score",
            "The license clarity score is a value from 0-100 calculated by combining the "
            "weighted values determined for each of the scoring elements: Declared license,"
            " Identification precision, License text, Declared copyrights, Ambiguous "
            "compound licensing, and Conflicting license categories.",
            None,
        ),
    ]

    # (scan_field, model_field)
    AUTO_UPDATE_FIELDS = [
        # declared_license_expression goes in both license fields.
        ("declared_license_expression", "license_expression"),
        ("declared_license_expression", "declared_license_expression"),
        ("other_license_expression", "other_license_expression"),
        ("declared_holder", "holder"),
        ("primary_language", "primary_language"),
    ]

    @classmethod
    def map_detected_package_data(cls, detected_package):
        """
        Convert the data from the Scan results `detected_package` to data ready to be set
        on the Package model instance.
        """
        package_data_for_model = {}

        for _, scan_data_field in cls.SCAN_PACKAGE_FIELD:
            value = detected_package.get(scan_data_field)
            if not value:
                continue

            if scan_data_field == "dependencies":
                value = json.dumps(value, indent=2)

            # Add `package_url` alias to be used in place of `purl` depending on the context
            if scan_data_field == "purl":
                package_data_for_model["package_url"] = value

            elif scan_data_field.endswith("license_expression"):
                value = str(Licensing().dedup(value))
                if scan_data_field == "declared_license_expression":
                    package_data_for_model["license_expression"] = value

            package_data_for_model[scan_data_field] = value

        return package_data_for_model


def get_hash_uid(value):
    """Return a Unique ID based on a 10 characters hash of the provided `value`."""
    return md5(str(value).encode("utf-8"), usedforsecurity=False).hexdigest()[:10]


def get_project_name(uri, user_uuid, dataspace_uuid):
    """
    Return a project name based on a hash of the provided `uri` combined with a hash
    of the `user_uuid` and `dataspace_uuid`.

    project_name = "uri_hash.dataspace_uuid_hash.user_uuid_hash"
    """
    uri_hash = get_hash_uid(uri)
    dataspace_hash = get_hash_uid(dataspace_uuid)
    user_hash = get_hash_uid(user_uuid)

    return f"{uri_hash}.{dataspace_hash}.{user_hash}"


def get_webhook_url(view_name, user_uuid):
    """
    Return a Webhook target URL based on the `user_uuid`.
    This URL is used to create notifications for this user.
    """
    user_key = signing.dumps(str(user_uuid))
    target_url = reverse(view_name, args=[user_key])
    site_url = settings.SITE_URL.rstrip("/")
    webhook_url = site_url + target_url
    return webhook_url


def get_project_input_source(project_data):
    return project_data.get("input_sources", [])


def get_package_filename(project_data):
    input_sources = get_project_input_source(project_data)
    if len(input_sources) == 1:
        return input_sources[0].get("filename", None)


def get_scan_results_as_file_url(project_data):
    uuid = project_data.get("uuid")
    filename = get_package_filename(project_data)

    if filename:
        view_name = "component_catalog:scan_data_as_file"
        view_args = [uuid, quote_plus(filename)]
        return reverse(view_name, args=view_args)


def get_package_download_url(project_data):
    input_sources = get_project_input_source(project_data)
    if len(input_sources) == 1:
        return input_sources[0].get("download_url", None)


def get_notice_text_from_key_files(scan_summary, separator="\n\n---\n\n"):
    """
    Return a generate notice_text from the key files contained in the provided
    ``scan_summary``.
    """
    key_files = scan_summary.get("key_files", [])

    # See https://github.com/nexB/scancode-toolkit/issues/3822 about the addition
    # of a `is_notice` attribute.
    notice_files = [key_file for key_file in key_files if "notice" in key_file.get("name").lower()]

    notice_text = separator.join(
        [notice_file.get("content").strip() for notice_file in notice_files]
    )
    return notice_text
