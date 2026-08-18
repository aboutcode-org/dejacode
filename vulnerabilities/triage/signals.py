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

from vulnerabilities.triage.engine import delete_preset_analyses_for_product
from vulnerabilities.triage.engine import reevaluate_product_rulesets
from vulnerabilities.triage.models import TriageRecord


@receiver(post_delete, sender="vulnerabilities_triage.ProductTriageRuleset")
def delete_triage_records_on_unassign(sender, instance, **kwargs):
    """Delete triage records and associated preset analyses when a ruleset is de-assigned."""
    matching_records = TriageRecord.objects.filter(
        ruleset=instance.ruleset,
        product=instance.product,
    )
    stale_vulnerability_ids = list(matching_records.values_list("vulnerability_id", flat=True))
    # Records with an open Request are kept so reassigning the ruleset reconnects to it
    # instead of opening a duplicate Request.
    matching_records.filter(request__isnull=True).delete()
    if instance.ruleset.analysis_preset_id and stale_vulnerability_ids:
        delete_preset_analyses_for_product(
            preset_id=instance.ruleset.analysis_preset_id,
            product=instance.product,
            vulnerability_ids=stale_vulnerability_ids,
        )


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
