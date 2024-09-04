#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from dje.tests import make_string
from vulnerabilities.models import Vulnerability


def make_vulnerability(dataspace, affecting=None, **data):
    """Create a vulnerability for test purposes."""
    if "vulnerability_id" not in data:
        data["vulnerability_id"] = f"VCID-0000-{make_string(4)}"

    vulnerability = Vulnerability.objects.create(
        dataspace=dataspace,
        **data,
    )

    if affecting:
        vulnerability.add_affected(affecting)

    return vulnerability
