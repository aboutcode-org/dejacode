#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from policy.tasks import evaluate_product_rules_task

logger = logging.getLogger(__name__)


@receiver(post_save, sender="product_portfolio.Product")
def evaluate_product_rules_on_save(sender, instance, **kwargs):
    """Queue a policy rule evaluation whenever a product is saved."""
    logger.debug(f"Queuing policy rule evaluation for product {instance.uuid}")
    evaluate_product_rules_task.delay(product_uuid=instance.uuid)
