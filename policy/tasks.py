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
from notification.models import fire_webhooks
from policy.engine import evaluate_rules

logger = logging.getLogger(__name__)


def fire_policy_webhooks(product, new_violations, resolved_count):
    """Fire policy webhooks for newly detected or resolved violations."""
    if new_violations:
        lines = [
            f"- {violation.rule_label}: {violation.violation_count} violation(s)"
            for violation in new_violations
        ]
        payload = {
            "text": (f"[DejaCode] Policy violations detected for {product}\n" + "\n".join(lines))
        }
        fire_webhooks("policy.violation_detected", instance=product, payload_override=payload)

    if resolved_count:
        payload = {
            "text": (f"[DejaCode] {resolved_count} policy violation(s) resolved for {product}")
        }
        fire_webhooks("policy.violation_resolved", instance=product, payload_override=payload)


@job
def evaluate_product_rules_task(product_uuid):
    """Evaluate all active policy rules for the given product and fire webhooks on changes."""
    Product = apps.get_model("product_portfolio", "product")

    try:
        product = get_unsecured_manager(Product).get(uuid=product_uuid)
    except Product.DoesNotExist:
        logger.error(f"evaluate_product_rules_task: product {product_uuid} not found, skipping.")
        return

    logger.info(f"Evaluating policy rules for product {product}")
    new_violations, resolved_count = evaluate_rules(product)
    logger.info(
        f"Policy rules evaluated for {product}: "
        f"{len(new_violations)} new violation(s), {resolved_count} resolved."
    )
    fire_policy_webhooks(product, new_violations, resolved_count)


@job
def evaluate_all_products_rules_task(include_locked=False, product_uuids=None):
    """
    Evaluate policy rules for products, skipping locked ones by default.
    When product_uuids is provided, only those products are evaluated.
    """
    Product = apps.get_model("product_portfolio", "product")

    products = get_unsecured_manager(Product).select_related("dataspace")
    if product_uuids is not None:
        products = products.filter(uuid__in=product_uuids)
    elif not include_locked:
        products = products.exclude_locked()

    count = products.count()
    logger.info(f"Starting policy rule evaluation for {count} product(s).")

    for product in products:
        logger.info(f"Evaluating policy rules for product {product}")
        new_violations, resolved_count = evaluate_rules(product)
        logger.info(
            f"Policy rules evaluated for {product}: "
            f"{len(new_violations)} new violation(s), {resolved_count} resolved."
        )
        fire_policy_webhooks(product, new_violations, resolved_count)

    logger.info(f"Policy rule evaluation complete for {count} product(s).")
