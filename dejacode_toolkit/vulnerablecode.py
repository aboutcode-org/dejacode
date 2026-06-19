#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.cache import caches

from dejacode_toolkit import BaseService
from dejacode_toolkit import get_settings
from dejacode_toolkit import logger

cache = caches["vulnerabilities"]


class VulnerableCode(BaseService):
    label = "VulnerableCode"
    settings_prefix = "VULNERABLECODE"
    url_field_name = "vulnerablecode_url"
    api_key_field_name = "vulnerablecode_api_key"
    api_version = "v3"
    user_agent = get_settings("VULNERABLECODE_USER_AGENT", default="VCIO_API_AGENT")

    def get_session(self):
        session = super().get_session()
        session.headers.update({"User-Agent": self.user_agent})
        return session

    def get_vulnerabilities_by_purl(
        self,
        purl,
        timeout=None,
    ):
        """Get list of vulnerabilities providing a package `purl`."""
        plain_purl = get_plain_purl(purl)

        cached_results = cache.get(plain_purl)
        if cached_results:
            return cached_results

        response = self.bulk_search_by_purl(purls=[plain_purl], timeout=timeout)
        if response and response.get("count"):
            results = response["results"]
            cache.set(plain_purl, results)
            return results

    def bulk_search_by_purl(
        self,
        purls,
        details=True,
        timeout=None,
    ):
        """Bulk search of vulnerabilities using the provided list of `purls`."""
        url = f"{self.api_url}packages"

        data = {
            "purls": purls,
            "details": details,
        }

        logger.debug(f"VulnerableCode: url={url} purls_count={len(purls)}")
        return self.request_post(url=url, json=data, timeout=timeout)

    def get_vulnerable_purls(self, packages, details=False, timeout=10):
        """
        Return a list of PURLs for which at least one `affected_by_vulnerabilities`
        was found in the VulnerableCodeDB for the given list of `packages`.
        Returns None when the API call fails (e.g. timeout or network error).
        """
        plain_purls = get_plain_purls(packages)

        if not plain_purls:
            return []

        vulnerable_purls = self.bulk_search_by_purl(
            purls=plain_purls,
            details=details,
            timeout=timeout,
        )
        if vulnerable_purls is None:
            return None
        return vulnerable_purls.get("results") or []

    def get_package_url_available_types(self):
        """Return the list of supported package types from the VulnerableCode API."""
        response = self.request_get(f"{self.api_url}package-types")
        if isinstance(response, list):
            return response
        return []


def get_plain_purl(purl_str):
    """Remove the PURL qualifiers and subpath from the search lookups."""
    return purl_str.split("?")[0]


def get_plain_purls(packages):
    """
    Return the PURLs for the given list of `packages`.
    List comprehension is not used on purpose to avoid crafting each
    PURL twice.
    """
    unique_plain_purls = set(
        plain_package_url
        for package in packages
        if (plain_package_url := package.plain_package_url)
    )
    return list(unique_plain_purls)
