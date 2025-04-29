#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#


from collections import Counter

from component_catalog.models import Package
from dje.management.commands import DataspacedCommand


class Command(DataspacedCommand):
    help = "Create PackageSet relationships from existing packages."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        # parser.add_argument("username", help="Your username, for History entries.")
        parser.add_argument(
            "--last_modified_date",
            help=(
                "Limit the packages batch to objects created/modified after that date. "
                'Format: "YYYY-MM-DD"'
            ),
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        qs = Package.objects.scope(self.dataspace).has_package_url()
        plain_purl_list = (
            qs.annotate_plain_purl().values_list("plain_purl", flat=True).order_by("plain_purl")
        )
        duplicates = [
            purl for purl, count in Counter(plain_purl_list).items() if count > 1 and purl
        ]
        print(duplicates)
