#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import hashlib


def sha1(content):
    """Return the sha1 hash of the given content."""
    return hashlib.sha1(content).hexdigest()  # nosec


def sha256(content):
    """Return the sha256 hash of the given content."""
    return hashlib.sha256(content).hexdigest()


def sha512(content):
    """Return the sha512 hash of the given content."""
    return hashlib.sha512(content).hexdigest()


def md5(content):
    """Return the md5 hash of the given content."""
    return hashlib.md5(content).hexdigest()  # nosec
