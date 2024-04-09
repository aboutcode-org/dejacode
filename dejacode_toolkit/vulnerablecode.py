#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#
from django.core.cache import caches

from dejacode_toolkit import BaseService
from dejacode_toolkit import logger

cache = caches["vulnerabilities"]


class VulnerableCode(BaseService):
    label = "VulnerableCode"
    settings_prefix = "VULNERABLECODE"
    url_field_name = "vulnerablecode_url"
    api_key_field_name = "vulnerablecode_api_key"

    def get_vulnerabilities(
        self,
        url,
        field_name,
        field_value,
        timeout=None,
    ):
        """Get list of vulnerabilities."""
        cached_results = cache.get(field_value)
        if cached_results:
            return cached_results

        payload = {field_name: field_value}

        response = self.request_get(url=url, params=payload, timeout=timeout)
        if response and response.get("count"):
            results = response["results"]
            cache.set(field_value, results)
            return results

    def get_vulnerabilities_by_purl(
        self,
        purl,
        timeout=None,
    ):
        """Get list of vulnerabilities providing a package `purl`."""
        return self.get_vulnerabilities(
            url=f"{self.api_url}packages/",
            field_name="purl",
            field_value=get_plain_purl(purl),
            timeout=timeout,
        )

    def get_vulnerabilities_by_cpe(
        self,
        cpe,
        timeout=None,
    ):
        """Get list of vulnerabilities providing a package or component `cpe`."""
        return self.get_vulnerabilities(
            url=f"{self.api_url}cpes/",
            field_name="cpe",
            field_value=cpe,
            timeout=timeout,
        )

    def bulk_search_by_purl(
        self,
        purls,
        timeout=None,
    ):
        """Bulk search of vulnerabilities using the provided list of `purls`."""
        url = f"{self.api_url}packages/bulk_search"

        data = {
            "purls": purls,
            "purl_only": True,
            "plain_purl": True,
        }

        logger.debug(f"VulnerableCode: url={url} purls_count={len(purls)}")
        return self.request_post(url=url, json=data, timeout=timeout)

    def bulk_search_by_cpes(
        self,
        cpes,
        timeout=None,
    ):
        """Bulk search of vulnerabilities using the provided list of `cpes`."""
        url = f"{self.api_url}cpes/bulk_search"

        data = {
            "cpes": cpes,
        }

        logger.debug(f"VulnerableCode: url={url} cpes_count={len(cpes)}")
        return self.request_post(url, json=data, timeout=timeout)

    def get_vulnerable_purls(self, packages):
        """
        Return a list of PURLs for which at least one `affected_by_vulnerabilities`
        was found in the VulnerableCodeDB for the given list of `packages`.
        """
        plain_purls = get_plain_purls(packages)

        if not plain_purls:
            return []

        vulnerable_purls = self.bulk_search_by_purl(plain_purls, timeout=5)
        return vulnerable_purls or []

    def get_vulnerable_cpes(self, components):
        """
        Return a list of vulnerable CPEs found in the VulnerableCodeDB for the given
        list of `components`.
        """
        cpes = [component.cpe for component in components if component.cpe]

        if not cpes:
            return []

        search_results = self.bulk_search_by_cpes(cpes, timeout=5)
        if not search_results:
            return []

        vulnerable_cpes = [
            reference.get("reference_id")
            for entry in search_results
            for reference in entry.get("references")
            if reference.get("reference_id").startswith("cpe")
        ]

        return list(set(vulnerable_cpes))


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
