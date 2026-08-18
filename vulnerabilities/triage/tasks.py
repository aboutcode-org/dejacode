#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging

from django.apps import apps

from django_rq import job

from dje.models import get_unsecured_manager
from vulnerabilities.triage.engine import evaluate_ruleset
from vulnerabilities.triage.engine import reevaluate_product_rulesets
from vulnerabilities.triage.models import ProductTriageRuleset

logger = logging.getLogger(__name__)


@job
def reevaluate_product_triage_rulesets_task(product_uuid):
    """Re-evaluate all enabled triage rulesets assigned to the given product."""
    Product = apps.get_model("product_portfolio", "product")

    try:
        product = get_unsecured_manager(Product).get(uuid=product_uuid)
    except Product.DoesNotExist:
        logger.error(
            f"reevaluate_product_triage_rulesets_task: product {product_uuid} not found,"
            " skipping."
        )
        return

    logger.info(f"Evaluating triage rulesets for product {product}")
    reevaluate_product_rulesets(product)


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
