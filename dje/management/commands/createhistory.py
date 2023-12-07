#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from dje.management import ALL_MODELS_NO_PP
from dje.models import History


class Command(BaseCommand):
    help = (
        'Create the missing "ADDITION" History entries for objects '
        "related to a Dataspace."
        "An existing user is required to be linked to the new History."
    )

    def add_arguments(self, parser):
        parser.add_argument("username", help="Your username.")

    def handle(self, *args, **options):
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=options.get("username"))
        except user_model.DoesNotExist:
            raise CommandError("This username does not exist.")

        verbosity = int(options.get("verbosity", 1))
        history_total_count = 0
        # PP objects should never be loaded/created using the fixture system
        # Therefore, this command does not include PP models.
        models = ALL_MODELS_NO_PP[:]

        # First, adding an History entry for each object
        for model in models:
            history_count = 0

            for obj in model.objects.all():
                history = History.objects.get_for_object(obj, action_flag=History.ADDITION)

                if not history.exists():
                    History.log_addition(user, obj)
                    history_count += 1

            if verbosity >= 2:
                msg = f"Created {history_count} History entries for model '{model.__name__}'"
                self.stdout.write(msg)

            history_total_count += history_count

        self.stdout.write(f"Created {history_total_count} History entries\n")
