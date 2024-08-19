#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import sys

from django.conf import settings
from django.core.management.base import BaseCommand

import django_rq

from dje.tasks import update_vulnerabilies

# **Regular RQ jobs** are tasks that run once when you enqueue them.
# **Scheduled RQ jobs** are tasks that are set to run automatically at specific times
# or intervals, like every day or every hour.
# The scheduler keeps track of these jobs and enqueues them when it's time for them to
# run.


class Command(BaseCommand):
    help = (
        "Sets up the application's scheduled cron jobs. "
        "Cron jobs are tasks that run automatically at specified intervals."
    )

    def handle(self, *args, **kwargs):
        if not settings.DEJACODE_ASYNC:
            self.stdout.write("SYNC mode detected, skipping cron job setup.")
            sys.exit(0)

        scheduler = django_rq.get_scheduler("default")

        # Cancel all existing cron jobs in the scheduler.
        # This ensures that the cron entries are always up-to-date in case their
        # configuration has changed. It also prevents any duplicate or orphaned jobs
        # from remaining in the scheduler, maintaining a clean and accurate schedule.
        cancel_all_scheduled_jobs(scheduler)

        self.stdout.write("Schedule vulnerabilities update")
        daily_at_3am = "0 3 * * *"
        scheduler.cron(
            cron_string=daily_at_3am,
            func=update_vulnerabilies,
            result_ttl=300,
            repeat=None,  # None means repeat forever
        )

        self.stdout.write(self.style.SUCCESS("Successfully set up cron jobs."))


def cancel_all_scheduled_jobs(scheduler):
    """
    Cancel all scheduled jobs in the given scheduler.

    This function iterates over all jobs currently scheduled in the scheduler
    and cancels each one, effectively clearing the schedule.
    """
    for job in scheduler.get_jobs():
        scheduler.cancel(job)
