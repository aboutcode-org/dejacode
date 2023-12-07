#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from dje.models import Dataspace


class DataspacedCommand(BaseCommand):
    dataspace = None

    def add_arguments(self, parser):
        parser.add_argument("dataspace", help="Name of the Dataspace.")

    def handle(self, *args, **options):
        dataspace_name = options["dataspace"]
        try:
            self.dataspace = Dataspace.objects.get(name=dataspace_name)
        except Dataspace.DoesNotExist:
            raise CommandError(f'The Dataspace "{dataspace_name}" does not exit.')
