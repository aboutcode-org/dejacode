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
from policy.engine import evaluate_rules

logger = logging.getLogger(__name__)


@job
def evaluate_product_rules_task(product_uuid):
    """Evaluate all active PolicyRules for the given product."""
    Product = apps.get_model("product_portfolio", "product")

    try:
        product = Product.unsecured_objects.select_related("dataspace").get(uuid=product_uuid)
    except Product.DoesNotExist:
        logger.error(f"evaluate_product_rules_task: product {product_uuid} not found, skipping.")
        return

    logger.info(f"Evaluating policy rules for product {product}")
    violations = evaluate_rules(product)
    logger.info(f"Policy rules evaluated for {product}: {len(violations)} active violation(s).")


@job
def evaluate_all_products_rules_task(include_locked=False):
    """Enqueue evaluate_product_rules_task for every product, skipping locked ones by default."""
    Product = apps.get_model("product_portfolio", "product")

    products = Product.unsecured_objects.select_related("dataspace")
    if not include_locked:
        products = products.exclude_locked()

    count = products.count()
    logger.info(f"Queuing policy rule evaluation for {count} product(s).")
    for product in products:
        evaluate_product_rules_task.delay(product_uuid=product.uuid)
