#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from pathlib import Path
from urllib.parse import unquote
from urllib.parse import urlparse

from django.template.defaultfilters import filesizeformat
from django.utils.http import parse_header_parameters

import requests

from dejacode_toolkit.utils import md5
from dejacode_toolkit.utils import sha1
from dejacode_toolkit.utils import sha256
from dejacode_toolkit.utils import sha512

CONTENT_MAX_LENGTH = 536870912  # 512 MB


class DataCollectionException(Exception):
    pass


def collect_package_data(url):
    try:
        response = requests.get(url, timeout=5, stream=True)
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
