#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import receiver

from vulnerabilities.triage.engine import reevaluate_product_rulesets


@receiver([post_save, post_delete], sender="vulnerabilities.VulnerabilityAnalysis")
def reevaluate_on_analysis_change(sender, instance, **kwargs):
    """Re-evaluate triage on a product when an vulnerability analysis is updated."""
    if instance.applied_by_preset_id:
        # A write or delete made by the triage engine itself always happens inside an
        # evaluation pass that already covers every ruleset assigned to the product.
        return

    # Skip preset re-application on a user's own delete, to avoid the engine
    # immediately recreating the analysis they just removed.
    apply_preset = kwargs.get("signal") != post_delete
    reevaluate_product_rulesets(instance.product_package.product, apply_preset=apply_preset)


@receiver([post_save, post_delete], sender="product_portfolio.ProductPackage")
def reevaluate_on_product_package_change(sender, instance, **kwargs):
    """Re-evaluate triage when a package is added, removed, or updated in a product."""
    reevaluate_product_rulesets(instance.product)
