#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from dje.tests import make_string
from vulnerabilities.models import Vulnerability
from vulnerabilities.models import VulnerabilityAnalysis


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


def make_vulnerability_analysis(product_package, vulnerability, **data):
    default_data = {
        "state": VulnerabilityAnalysis.State.RESOLVED,
        "justification": VulnerabilityAnalysis.Justification.CODE_NOT_PRESENT,
        "responses": [
            VulnerabilityAnalysis.Response.CAN_NOT_FIX,
            VulnerabilityAnalysis.Response.ROLLBACK,
        ],
        "detail": "detail",
    }

    return VulnerabilityAnalysis.objects.create(
        dataspace=product_package.dataspace,
        product_package=product_package,
        vulnerability=vulnerability,
        **{**default_data, **data},
    )
