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
    signal = kwargs.get("signal")
    if signal == post_save and instance.applied_by_preset_id:
        # When the analysis is created by the triage engine itself, the evaluation is skipped.
        return

    # When a user explicitly deletes their analysis, skip preset application to avoid
    # having the engine immediately recreate it.
    is_user_delete = signal == post_delete and not instance.applied_by_preset_id
    reevaluate_product_rulesets(
        instance.product_package.product,
        apply_preset=not is_user_delete,
    )


@receiver([post_save, post_delete], sender="product_portfolio.ProductPackage")
def reevaluate_on_product_package_change(sender, instance, **kwargs):
    """Re-evaluate triage when a package is added, removed, or updated in a product."""
    reevaluate_product_rulesets(instance.product)
