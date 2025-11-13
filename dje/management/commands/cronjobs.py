#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

"""
Management command to manage RQ CronScheduler instances.

Usage:
    ./manage.py cronjobs  # Start the cron scheduler
"""

import sys

from django.conf import settings
from django.core.management.base import BaseCommand

import django_rq
from rq.cron import CronScheduler


class Command(BaseCommand):
    help = (
        "Manage RQ CronScheduler instances. "
        "The CronScheduler enqueues jobs at regular intervals based on cron configuration."
    )

    def handle(self, *args, **options):
        if not settings.DEJACODE_ASYNC:
            self.stdout.write("SYNC mode detected, cron scheduler is not needed.")
            sys.exit(0)

        connection = django_rq.get_connection("default")
        self.start_scheduler(connection)

    def start_scheduler(self, connection):
        """Start the cron scheduler."""
        self.stdout.write(self.style.SUCCESS("Starting cron scheduler..."))
        self.stdout.write("(Press Ctrl+C to stop)")

        cron = CronScheduler(connection=connection, logging_level="INFO")

        # Register jobs
        cron.register(print, queue_name="default", cron="* * * * *")

        # Start the scheduler (this will block until interrupted)
        try:
            cron.start()
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("\nShutting down cron scheduler..."))
            sys.exit(0)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error starting cron scheduler: {e}"))
            sys.exit(1)


# self.stdout.write("Schedule vulnerabilities update:")
# forever = None
# scheduler.cron(
#     cron_string=settings.DEJACODE_VULNERABILITIES_CRON,  # 3am daily by default
#     func=update_vulnerabilities,
#     result_ttl=300,
#     repeat=forever,
#     timeout="3h",
#     use_local_timezone=True,
# )
#
# self.stdout.write(self.style.SUCCESS("Successfully set up cron jobs."))
# self.print_scheduled_jobs(scheduler)
