#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import cgi
import os
import socket
from urllib.parse import urlparse

from django.template.defaultfilters import filesizeformat

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
        response = requests.get(url, timeout=10, stream=True)
    except (requests.RequestException, socket.timeout) as e:
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
    value, params = cgi.parse_header(content_disposition)
    filename = params.get("filename") or os.path.basename(urlparse(url).path)

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
