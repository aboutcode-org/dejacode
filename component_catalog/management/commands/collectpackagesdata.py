#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.db.models import Q

from component_catalog.models import Package
from dje.management.commands import DataspacedCommand


class Command(DataspacedCommand):
    help = ('Collects and saves md5, sha1, and size values where one of those '
            'are missing in the given Dataspace on Package instances.')

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '--save',
            action='store_true',
            dest='save',
            default=False,
            help='Use save() in place of update() (default) to trigger all '
                 'associated logic and signals. Fields such as last_modified_date '
                 'will be updated.',
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        packages = (
            Package.objects.scope(self.dataspace)
            .exclude(download_url='')
            .filter(Q(md5='') | Q(sha1='') | Q(size__isnull=True))
        )

        self.stdout.write(f'{packages.count()} Packages in the queue.')

        update_count = 0
        for package in packages:
            self.stdout.write(f'Collecting: {package.download_url}')
            update_fields = package.collect_data(save=False)
            if not update_fields:
                continue

            if options['save']:
                package.save()
            else:
                Package.objects.filter(pk=package.pk).update(
                    **{field: getattr(package, field) for field in update_fields}
                )

            self.stdout.write(f"{', '.join(update_fields)} updated")
            update_count += 1

        msg = f'{update_count} Package(s) updated.'
        self.stdout.write(self.style.SUCCESS(msg))
