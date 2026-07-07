#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import apps

from django_rq import job

from policy.engine import evaluate_rules


@job
def evaluate_product_rules_task(product_uuid):
    """Evaluate all active PolicyRules for the given product UUID."""
    Product = apps.get_model("product_portfolio", "product")

    try:
        product = Product.objects.select_related("dataspace").get(uuid=product_uuid)
    except Product.DoesNotExist:
        return

    evaluate_rules(product)


@job
def evaluate_all_products_rules_task():
    """Enqueue evaluate_product_rules_task for every product."""
    Product = apps.get_model("product_portfolio", "product")

    for product in Product.objects.select_related("dataspace").all():
        evaluate_product_rules_task.delay(product_uuid=product.uuid)
