#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from contextlib import suppress
from pathlib import Path
from urllib.parse import unquote
from urllib.parse import urlparse

from django.template.defaultfilters import filesizeformat
from django.utils.http import parse_header_parameters

import requests
from packageurl import PackageURL
from packageurl.contrib import purl2url

from dejacode_toolkit.utils import md5
from dejacode_toolkit.utils import sha1
from dejacode_toolkit.utils import sha256
from dejacode_toolkit.utils import sha512

CONTENT_MAX_LENGTH = 536870912  # 512 MB
DEFAULT_TIMEOUT = 5


class DataCollectionException(Exception):
    pass


def collect_package_data(url):
    try:
        response = requests.get(url, timeout=DEFAULT_TIMEOUT, stream=True)
    except (TimeoutError, requests.RequestException) as e:
        raise DataCollectionException(e)

    if response.status_code != 200:
        raise DataCollectionException(f"Could not download content: {url}")

    content_type = response.headers.get("content-type", "").lower()
    if "html" in content_type:
        raise DataCollectionException("Content not downloadable.")

    # Since we use stream=True, exceptions may occur on accessing response.content
    # for the first time.
    try:
        size = int(len(response.content))
    except requests.RequestException as e:
        raise DataCollectionException(e)

    # We cannot rely on the 'content-length' header as it is not always available.
    if size > CONTENT_MAX_LENGTH:
        raise DataCollectionException(
            f"Downloaded content too large (Max: {filesizeformat(CONTENT_MAX_LENGTH)})."
        )

    content_disposition = response.headers.get("content-disposition", "")
    _, params = parse_header_parameters(content_disposition)

    filename = params.get("filename")
    if not filename:
        # Using ``response.url`` in place of provided ``url`` arg since the former
        # will be more accurate in case of HTTP redirect.
        filename = unquote(Path(urlparse(response.url).path).name)

    package_data = {
        "download_url": url,
        "filename": filename,
        "size": size,
        "md5": md5(response.content),
        "sha1": sha1(response.content),
        "sha256": sha256(response.content),
        "sha512": sha512(response.content),
    }

    return package_data


class PyPIFetcher:
    """
    Handle PyPI Package URL (PURL) resolution and download URL retrieval.

    Adapted from fetchcode
    https://github.com/aboutcode-org/fetchcode/issues/190
    """

    purl_pattern = "pkg:pypi/.*"
    base_url = "https://pypi.org/pypi"

    @staticmethod
    def fetch_json_response(url):
        """Fetch a JSON response from the given URL and return the parsed JSON data."""
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch {url}: {response.status_code} {response.reason}")

        try:
            return response.json()
        except ValueError as e:
            raise Exception(f"Failed to parse JSON from {url}: {str(e)}")

    @classmethod
    def get_package_data(cls, purl):
        """Fetch package data from PyPI API."""
        parsed_purl = PackageURL.from_string(purl)

        if parsed_purl.version:
            api_url = f"{cls.base_url}/{parsed_purl.name}/{parsed_purl.version}/json"
        else:
            api_url = f"{cls.base_url}/{parsed_purl.name}/json"

        return cls.fetch_json_response(api_url)

    @classmethod
    def get_urls_info(cls, purl):
        """Collect URL info dicts from PyPI API."""
        data = cls.get_package_data(purl)
        return data.get("urls", [])

    @classmethod
    def get_download_url(cls, purl, preferred_type="sdist"):
        """
        Get a single download URL from PyPI API.
        If no version is specified in the PURL, fetches the latest version.
        """
        urls_info = cls.get_urls_info(purl)

        if not urls_info:
            return

        for url_info in urls_info:
            if url_info.get("packagetype") == preferred_type:
                return url_info["url"]

        return urls_info[0]["url"]

    @classmethod
    def get_all_download_urls(cls, purl):
        """
        Get all download URLs from PyPI API.
        If no version is specified in the PURL, fetches the latest version.
        """
        urls_info = cls.get_urls_info(purl)
        return [url_info["url"] for url_info in urls_info if "url" in url_info]


def infer_download_url(purl):
    """
    Infer the download URL for a package from its Package URL (purl).

    Attempts resolution via ``purl2url`` first. Falls back to package-type-specific
    resolvers (which may make HTTP requests) when ``purl2url`` cannot resolve the URL.
    """
    if isinstance(purl, PackageURL):
        purl_data = purl
        purl_str = str(purl)
    else:
        purl_data = PackageURL.from_string(purl)
        purl_str = purl

    if download_url := purl2url.get_download_url(purl_str):
        return download_url

    # PyPI is not supported by ``purl2url``, it requires an API call to resolve download URLs.
    if purl_data.type == "pypi":
        with suppress(Exception):
            return PyPIFetcher.get_download_url(purl_str, preferred_type="sdist")
