#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

"""
Serialize data as an ABOUT file.
https://github.com/aboutcode-org/aboutcode-toolkit/blob/develop/SPECIFICATION.rst
"""

import saneyaml

# Supported fields, in the order they are written in the ABOUT file
ABOUT_FIELD_NAMES = [
    "about_resource",
    "name",
    "version",
    "download_url",
    "description",
    "homepage_url",
    "package_url",
    "notes",
    "license_expression",
    "copyright",
    "notice_file",
    "notice_url",
    "redistribute",
    "attribute",
    "track_changes",
    "owner",
    "owner_url",
    "contact",
    "vcs_repository",
    "checksum_md5",
    "checksum_sha1",
    "licenses",
]


def normalize_text(text):
    """Return `text` with LF line endings, without trailing spaces and surrounding blank lines."""
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def dumps(about_data):
    """
    Return the `about_data` dict as an ABOUT file YAML string.
    Fields are written in the `ABOUT_FIELD_NAMES` order, empty and False values are skipped.
    """
    about_fields = {}
    for field_name in ABOUT_FIELD_NAMES:
        value = about_data.get(field_name)
        if isinstance(value, str):
            value = normalize_text(value)
        if value:
            about_fields[field_name] = value

    return saneyaml.dump(about_fields)
