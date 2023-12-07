#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from dejacode_toolkit import BaseService


class PurlDB(BaseService):
    label = "PurlDB"
    settings_prefix = "PURLDB"
    url_field_name = "purldb_url"
    api_key_field_name = "purldb_api_key"

    def __init__(self, user):
        super().__init__(user)
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

    def find_packages(self, payload, timeout=None):
        """Get Packages details using provided `payload` filters on the PurlDB package list."""
        response = self.request_get(self.package_api_url, params=payload, timeout=timeout)
        if response and response.get("count") > 0:
            return response.get("results")
