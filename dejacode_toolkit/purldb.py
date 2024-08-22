#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from dejacode_toolkit import BaseService


class PurlDB(BaseService):
    label = "PurlDB"
    settings_prefix = "PURLDB"
    url_field_name = "purldb_url"
    api_key_field_name = "purldb_api_key"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.package_api_url = f"{self.api_url}packages/"

    def get_package_list(
        self,
        search=None,
        page_size=None,
        page=None,
        timeout=None,
        extra_payload=None,
    ):
        """
        Get the PurlDB packages list.
        An optional `search` can be providing for global search.
        Pagination is managed with `page_size` and `page`.
        """
        payload = {}

        if search:
            # If the search string looks like a purl, use the purl filter
            field = "purl" if "/" in search else "search"
            payload[field] = search

        if page_size:
            payload["page_size"] = page_size

        if page:
            payload["page"] = page

        if extra_payload:
            payload.update(extra_payload)

        return self.request_get(self.package_api_url, params=payload, timeout=timeout)

    def get_package(self, uuid):
        """Get a Package details entry providing its `uuid`."""
        return self.request_get(url=f"{self.package_api_url}{uuid}/")

    def get_package_by_purl(self, package_url):
        """Get a Package details entry providing its `package_url`."""
        if results := self.find_packages({"purl": package_url}):
            return results[0]

    def find_packages(self, payload, timeout=None):
        """Get Packages details using provided `payload` filters on the PurlDB package list."""
        response = self.request_get(self.package_api_url, params=payload, timeout=timeout)
        if response and response.get("count") > 0:
            return response.get("results")


def pick_purldb_entry(purldb_entries, purl=None):
    """
    Select a single entry from a list of PurlDB package entries.

    This function takes a list of PurlDB package entries and optionally a purl string,
    and returns a single entry based on the following logic:

    - If the list is empty, returns None.
    - If there is exactly one entry in the list, returns that entry.
    - If a purl string is provided and exactly one entry matches that purl,
      returns that entry.
    """
    if not purldb_entries:
        return

    if len(purldb_entries) == 1:
        return purldb_entries[0]

    if purl:
        matches = [entry for entry in purldb_entries if entry.get("purl") == purl]
        if len(matches) == 1:
            return matches[0]
