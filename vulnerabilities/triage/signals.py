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

from vulnerabilities.triage.models import TriageRecord


@receiver(post_save, sender="vulnerabilities_triage.TriageRuleset")
def delete_triage_records_on_disable(sender, instance, **kwargs):
    """Delete all package triage records when a ruleset is disabled."""
    if not instance.enabled:
        instance.triage_records.all().delete()


@receiver(post_delete, sender="vulnerabilities_triage.ProductTriageRuleset")
def delete_triage_records_on_unassign(sender, instance, **kwargs):
    """Delete triage records for a ruleset when it is de-assigned from a product."""
    TriageRecord.objects.filter(
        ruleset=instance.ruleset,
        product_package__product=instance.product,
    ).delete()
