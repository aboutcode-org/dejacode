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

from vulnerabilities.triage.engine import evaluate_ruleset
from vulnerabilities.triage.models import ProductTriageRuleset
from vulnerabilities.triage.models import TriageRecord


def reevaluate_product_rulesets(product):
    """Re-evaluate all enabled triage rulesets currently assigned to the product."""
    assignments = ProductTriageRuleset.objects.filter(
        product=product, ruleset__enabled=True
    ).select_related("ruleset")

    for assignment in assignments:
        evaluate_ruleset(ruleset=assignment.ruleset, product=product)


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
    """Delete triage records for a ruleset when it is de-assigned from a product."""
    TriageRecord.objects.filter(
        ruleset=instance.ruleset,
        product=instance.product,
    ).delete()


@receiver([post_save, post_delete], sender="vulnerabilities.VulnerabilityAnalysis")
def reevaluate_on_analysis_change(sender, instance, **kwargs):
    """Re-evaluate triage when an analysis state or reachability is updated."""
    reevaluate_product_rulesets(instance.product_package.product)


@receiver([post_save, post_delete], sender="product_portfolio.ProductPackage")
def reevaluate_on_product_package_change(sender, instance, **kwargs):
    """Re-evaluate triage when a package is added, removed, or updated in a product."""
    reevaluate_product_rulesets(instance.product)
