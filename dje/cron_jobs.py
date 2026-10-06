#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.conf import settings

from rq import cron

from dje.tasks import update_vulnerabilities
from policy.tasks import evaluate_all_products_rules_task
from vulnerabilities.triage.tasks import evaluate_all_products_vulnerability_triage_task

two_hours = 7200
ten_minutes = 600

cron.register(
    func=update_vulnerabilities,
    queue_name="default",
    cron=settings.DEJACODE_VULNERABILITIES_CRON,  # Daily at 3am by default
    job_timeout=two_hours,
)

cron.register(
    func=evaluate_all_products_rules_task,
    queue_name="default",
    cron=settings.DEJACODE_POLICY_RULES_CRON,  # Hourly by default
    job_timeout=two_hours,
)

cron.register(
    func=evaluate_all_products_vulnerability_triage_task,
    queue_name="default",
    cron=settings.DEJACODE_VULNERABILITY_TRIAGE_CRON,  # Hourly by default
    job_timeout=ten_minutes,
)
