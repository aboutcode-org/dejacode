#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from rq import cron

from dje.tasks import update_vulnerabilities


cron.register(
    func=update_vulnerabilities,
    queue_name="default",
    # cron=settings.DEJACODE_VULNERABILITIES_CRON,  # 3am daily by default
    cron="0 * * * *",  # Every hour
    job_timeout=3600,  # 1 hour
)
