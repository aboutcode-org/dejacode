#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging

from django_rq import job

from vulnerabilities.triage.engine import evaluate_ruleset
from vulnerabilities.triage.models import ProductTriageRuleset

logger = logging.getLogger(__name__)


@job
def evaluate_all_products_vulnerability_triage_task():
    """Evaluate all enabled triage rulesets against their assigned products."""
    assignments = (
        ProductTriageRuleset.objects.filter(ruleset__enabled=True)
        .select_related("product", "ruleset", "dataspace")
        .order_by("dataspace__name", "product__name", "product__version", "-ruleset__precedence")
    )

    count = assignments.count()
    logger.info(f"Starting triage evaluation for {count} ruleset assignment(s).")

    for assignment in assignments:
        logger.info(f"Evaluating triage ruleset {assignment.ruleset} for {assignment.product}")
        try:
            evaluate_ruleset(ruleset=assignment.ruleset, product=assignment.product)
        except Exception:
            logger.exception(
                f"Triage evaluation failed for {assignment.ruleset} / {assignment.product},"
                " skipping."
            )
            continue

    logger.info("Triage evaluation complete.")
