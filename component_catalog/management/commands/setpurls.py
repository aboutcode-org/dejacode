#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import traceback

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import CommandError

from component_catalog.models import Package
from dje.management.commands import DataspacedCommand


class Command(DataspacedCommand):
    help = (
        'Set the Package URL "purl" generated from the Download URL field '
        "on Package instances in the given Dataspace."
    )

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("username", help="Your username, for History entries.")
        parser.add_argument(
            "--overwrite",
            action="store_true",
            dest="overwrite",
            default=False,
            help="Overwrite the existing Package URL values.",
        )
        parser.add_argument(
            "--save",
            action="store_true",
            dest="save",
            default=False,
            help="Use save() in place of update() (default) to trigger all "
            "associated logic and signals. Fields such as last_modified_date "
            "will be updated.",
        )
        parser.add_argument(
            "--history",
            action="store_true",
            dest="history",
            default=False,
            help="Create CHANGE History entries on Package when Package URL is set.",
        )

    @staticmethod
    def get_purl_summary(packages):
        package_count = packages.count()
        purl_count = packages.exclude(type="").count()
        no_purl_count = package_count - purl_count
        purl_percent = int(purl_count / package_count * 100)
        msg = (
            f"{package_count:,d} Packages, "
            f"{purl_count:,d} ({purl_percent}%) with a Package URL, "
            f"{no_purl_count:,d} without."
        )
        return msg

    def handle(self, *args, **options):
        super().handle(*args, **options)

        try:
            user = get_user_model().objects.get(
                username=options["username"],
                dataspace=self.dataspace,
            )
        except ObjectDoesNotExist:
            raise CommandError("The given username does not exist.")

        packages = Package.objects.scope(self.dataspace)
        pre_update_summary = self.get_purl_summary(packages)
        update_count = 0
        error_count = 0

        for package in packages.iterator(chunk_size=2000):
            try:
                package_url = package.update_package_url(
                    user=user,
                    save=options["save"],
                    overwrite=options["overwrite"],
                    history=options["history"],
                )
            except Exception:
                self.stderr.write(
                    f"Error encountered when processing Package:"
                    f" {str(package)} ({package.uuid})"
                )
                self.stderr.write(traceback.format_exc())
                error_count += 1
                continue

            if package_url:
                update_count += 1

                if options["verbosity"] > 1:
                    self.stdout.write(f"Set {package_url} from {package.download_url}")

        msg = (
            f"{update_count:,d} Package(s) updated with a Package URL in "
            f"the {self.dataspace} Dataspace."
        )
        self.stdout.write(self.style.SUCCESS(msg))
        self.stdout.write("Pre-update: " + pre_update_summary)
        self.stdout.write("Post-update: " + self.get_purl_summary(packages))
        self.stdout.write(f"Number of errors encountered when updating Packages: " f"{error_count}")
