#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.checks.registry import registry
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

# WARNING: This import is required to register the checks
from dje.management.commands import checks  # noqa
from dje.models import Dataspace


class Command(BaseCommand):
    help = "Checks the given Dataspace for potential data problems."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("dataspace", nargs="?", help="Name of the Dataspace.")
        parser.add_argument(
            "--tag",
            "-t",
            action="append",
            dest="tags",
            help="Run only checks labeled with given tag.",
        )
        parser.add_argument(
            "--list-tags", action="store_true", dest="list_tags", help="List available tags."
        )
        parser.add_argument(
            "--all-dataspaces",
            action="store_true",
            dest="all_dataspaces",
            help="Run the checks on all Dataspaces.",
        )

    def handle(self, *args, **options):
        if options["list_tags"]:
            self.stdout.write("\n".join(sorted(registry.tags_available())))
            return

        dataspace = options.get("dataspace")
        tags = options.get("tags")

        if not dataspace and not options["all_dataspaces"]:
            raise CommandError("Enter a Dataspace.")

        special_tags = ["reporting"], ["expression"]
        if options["all_dataspaces"] and tags not in special_tags:
            raise CommandError(
                "--all-dataspaces only usable with `--tag reporting` or " "`--tag expression`"
            )

        app_configs = {}

        if dataspace:
            try:
                dataspace = Dataspace.objects.get(name=dataspace)
            except Dataspace.DoesNotExist:
                raise CommandError(f"The Dataspace {dataspace} does not exit.")

            # Using `app_configs` as a workaround to provide the dataspace to
            # the check commands.
            app_configs = {"dataspace": dataspace}

        if tags:
            try:
                invalid_tag = next(tag for tag in tags if not registry.tag_exists(tag))
            except StopIteration:
                pass  # no invalid tags
            else:
                raise CommandError(f'No data check for the "{invalid_tag}" tag.')
        else:
            tags = ["data", "reporting", "expression"]  # default tags

        self.check(
            app_configs=app_configs,
            tags=tags,
            display_num_errors=True,
        )
