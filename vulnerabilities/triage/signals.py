#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="vulnerabilities_triage.TriageRuleset")
def delete_triage_records_on_disable(sender, instance, **kwargs):
    """Delete all package triage records when a ruleset is disabled."""
    if not instance.enabled:
        instance.triage_records.all().delete()
