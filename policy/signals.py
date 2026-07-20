#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging

from django.apps import apps
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import receiver

from dje.models import get_unsecured_manager
from policy.tasks import evaluate_all_products_rules_task
from policy.tasks import evaluate_product_rules_task

logger = logging.getLogger(__name__)


@receiver(post_save, sender="product_portfolio.Product")
def evaluate_product_rules_on_product_save(sender, instance, **kwargs):
    """Queue a policy rule evaluation whenever a product is saved."""
    evaluate_product_rules_task.delay(product_uuid=instance.uuid)


@receiver(post_save, sender="product_portfolio.ProductPackage")
def evaluate_product_rules_on_productpackage_save(sender, instance, **kwargs):
    """Queue a policy rule evaluation whenever a package is added or updated in a product."""
    evaluate_product_rules_task.delay(product_uuid=instance.product.uuid)


@receiver(post_delete, sender="product_portfolio.ProductPackage")
def evaluate_product_rules_on_productpackage_delete(sender, instance, **kwargs):
    """Queue a policy rule evaluation whenever a package is removed from a product."""
    evaluate_product_rules_task.delay(product_uuid=instance.product.uuid)


@receiver(post_save, sender="component_catalog.Package")
def evaluate_product_rules_on_package_save(sender, instance, created, **kwargs):
    """Queue a policy rule evaluation for all products containing this package."""
    if created:
        return  # A newly created package has no ProductPackage relations yet.

    product_uuids = list(instance.productpackages.values_list("product__uuid", flat=True))
    if product_uuids:
        evaluate_all_products_rules_task.delay(product_uuids=product_uuids)


@receiver(post_save, sender="dje.DataspaceConfiguration")
def evaluate_products_on_policy_rules_config_save(sender, instance, update_fields, **kwargs):
    """Queue re-evaluation for all products in the dataspace when policy rules config changes."""
    if update_fields is not None and "policy_rules_config" not in update_fields:
        return

    Product = apps.get_model("product_portfolio", "product")
    product_uuids = list(
        get_unsecured_manager(Product)
        .filter(dataspace=instance.dataspace)
        .values_list("uuid", flat=True)
    )
    if product_uuids:
        evaluate_all_products_rules_task.delay(product_uuids=product_uuids)
