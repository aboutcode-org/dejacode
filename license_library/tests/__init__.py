#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from license_library.models import License
from organization.tests import make_owner


def make_license(dataspace, key, **data):
    if "owner" not in data:
        data["owner"] = make_owner(dataspace)

    if "name" not in data:
        data["name"] = key

    if "short_name" not in data:
        data["short_name"] = key

    return License.objects.create(
        dataspace=dataspace,
        key=key,
        **data,
    )
