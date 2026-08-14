#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import random

from dje.tests import make_string
from vulnerabilities.triage.models import AnalysisPreset
from vulnerabilities.triage.models import ProductTriageRuleset
from vulnerabilities.triage.models import TriageRuleset


def make_triage_ruleset(dataspace, **data):
    """Create a TriageRuleset for test purposes."""
    if "name" not in data:
        data["name"] = f"ruleset-{make_string(10)}"

    if "precedence" not in data:
        # `precedence` is unique per dataspace: randomize the default so tests creating
        # several rulesets without an explicit precedence do not collide with each other.
        data["precedence"] = random.randint(1, 1_000_000)

    return TriageRuleset.objects.create(
        dataspace=dataspace,
        **data,
    )


def make_analysis_preset(dataspace, **data):
    """Create an AnalysisPreset for test purposes."""
    if "name" not in data:
        data["name"] = f"preset-{make_string(10)}"

    if not any(data.get(field) for field in ("state", "justification", "responses", "detail")):
        data["state"] = AnalysisPreset.State.NOT_AFFECTED

    return AnalysisPreset.objects.create(
        dataspace=dataspace,
        **data,
    )


def make_product_triage_ruleset(product, ruleset=None, **data):
    """Activate a TriageRuleset for the given product."""
    dataspace = product.dataspace

    if not ruleset:
        ruleset = make_triage_ruleset(dataspace)

    return ProductTriageRuleset.objects.create(
        product=product,
        ruleset=ruleset,
        dataspace=dataspace,
        **data,
    )
