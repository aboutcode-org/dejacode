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
from vulnerabilities.triage.engine import evaluate_ruleset
from vulnerabilities.triage.models import ProductTriageRuleset
from vulnerabilities.triage.models import TriageRecord


def reevaluate_product_rulesets(product, apply_preset=True):
    """Re-evaluate all enabled triage rulesets currently assigned to the product."""
    assignments = ProductTriageRuleset.objects.filter(
        product=product, ruleset__enabled=True
    ).select_related("ruleset", "ruleset__analysis_preset")

    for assignment in assignments:
        evaluate_ruleset(ruleset=assignment.ruleset, product=product, apply_preset=apply_preset)


@receiver(post_save, sender="vulnerabilities_triage.TriageRuleset")
def reevaluate_or_delete_on_ruleset_save(sender, instance, created, **kwargs):
    """Re-evaluate assigned products on config change; delete records when disabled."""
    if not instance.enabled:
        instance.triage_records.all().delete()
        return

    if created:
        return

    for assignment in instance.product_triage_rulesets.select_related("product"):
        evaluate_ruleset(ruleset=instance, product=assignment.product)


@receiver(post_delete, sender="vulnerabilities_triage.ProductTriageRuleset")
def delete_triage_records_on_unassign(sender, instance, **kwargs):
    """Delete triage records and associated preset analyses when a ruleset is de-assigned."""
    stale_vulnerability_ids = list(
        TriageRecord.objects.filter(
            ruleset=instance.ruleset,
            product=instance.product,
        ).values_list("vulnerability_id", flat=True)
    )
    TriageRecord.objects.filter(
        ruleset=instance.ruleset,
        product=instance.product,
    ).delete()
    if instance.ruleset.analysis_preset_id and stale_vulnerability_ids:
        delete_preset_analyses_for_product(
            preset_id=instance.ruleset.analysis_preset_id,
            product=instance.product,
            vulnerability_ids=stale_vulnerability_ids,
        )


@receiver([post_save, post_delete], sender="vulnerabilities.VulnerabilityAnalysis")
def reevaluate_on_analysis_change(sender, instance, **kwargs):
    """Re-evaluate triage when an analysis state or reachability is updated."""
    signal = kwargs.get("signal")
    if signal == post_save and instance.applied_by_preset_id:
        return  # Written by the triage engine itself -- re-evaluating would loop
    # When a human explicitly deletes their analysis, skip preset application to avoid
    # having the engine immediately recreate it.
    is_human_delete = signal == post_delete and not instance.applied_by_preset_id
    reevaluate_product_rulesets(
        instance.product_package.product,
        apply_preset=not is_human_delete,
    )


@receiver([post_save, post_delete], sender="product_portfolio.ProductPackage")
def reevaluate_on_product_package_change(sender, instance, **kwargs):
    """Re-evaluate triage when a package is added, removed, or updated in a product."""
    reevaluate_product_rulesets(instance.product)
