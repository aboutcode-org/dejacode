#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import sys

from django.conf import settings
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.core.management.base import BaseCommand

import django_rq

from dje.tasks import update_vulnerabilities

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

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--list",
            action="store_true",
            help="List the current scheduled cron jobs.",
        )

    def handle(self, *args, **options):
        if not settings.DEJACODE_ASYNC:
            self.stdout.write("SYNC mode detected, skipping cron job setup.")
            sys.exit(0)

        scheduler = django_rq.get_scheduler("default")

        if options["list"]:
            self.print_scheduled_jobs(scheduler)
            sys.exit(0)

        # Cancel all existing cron jobs in the scheduler.
        # This ensures that the cron entries are always up-to-date in case their
        # configuration has changed. It also prevents any duplicate or orphaned jobs
        # from remaining in the scheduler, maintaining a clean and accurate schedule.
        cancel_all_scheduled_jobs(scheduler)

        self.stdout.write("Schedule vulnerabilities update:")
        forever = None
        scheduler.cron(
            cron_string=settings.DEJACODE_VULNERABILITIES_CRON,  # 3am daily by default
            func=update_vulnerabilities,
            result_ttl=300,
            repeat=forever,
            timeout="3h",
            use_local_timezone=True,
        )

        self.stdout.write(self.style.SUCCESS("Successfully set up cron jobs."))
        self.print_scheduled_jobs(scheduler)

    def print_scheduled_jobs(self, scheduler):
        self.stdout.write("Scheduled jobs next execution:")
        for job, scheduled_time in scheduler.get_jobs(with_times=True):
            msg = f" > {job.description} in {naturaltime(scheduled_time)} ({scheduled_time})"
            self.stdout.write(msg)


def cancel_all_scheduled_jobs(scheduler):
    """
    Cancel all scheduled jobs in the given scheduler.

    This function iterates over all jobs currently scheduled in the scheduler
    and cancels each one, effectively clearing the schedule.
    """
    for job in scheduler.get_jobs():
        scheduler.cancel(job)
