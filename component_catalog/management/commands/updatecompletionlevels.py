#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from component_catalog.models import Component
from dje.management.commands import DataspacedCommand


class Command(DataspacedCommand):
    help = (
        "Updates the completion level value of all Component objects. "
        "This will not trigger a save if the computed value is identical "
        "to the stored value."
    )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        components = Component.objects.scope(self.dataspace)
        updated_count = sum(1 for component in components if component.update_completion_level())

        msg = f"{updated_count} Component(s) updated."
        self.stdout.write(self.style.SUCCESS(msg))
