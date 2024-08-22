#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model

from dje.management import ALL_MODELS
from dje.management import REPORTING_MODELS
from dje.management import WORKFLOW_MODELS
from dje.management import AssociatedPolicy
from dje.management import UsagePolicy
from dje.management.commands import DataspacedCommand
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.models import get_unsecured_manager
from notification.models import Webhook


class Command(DataspacedCommand):
    help = (
        "Removes all the data related to a given Dataspace from "
        "the database. "
        "Use the option --keep-users to keep the Users."
    )

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--keep-users",
            action="store_true",
            dest="keep_users",
            default=False,
            help="Keeps the Users and the Dataspace.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        dataspace = self.dataspace

        models = ALL_MODELS[:]  # Making a copy to not impact the original list
        models += WORKFLOW_MODELS
        models += REPORTING_MODELS
        models.reverse()  # The order matters, see the protected FK

        models.extend(
            [
                # WARNING: The following Policy models order matters and needs to be after
                # main models.
                AssociatedPolicy,
                UsagePolicy,
                ExternalReference,
                ExternalSource,
                Webhook,
            ]
        )

        # Clear the associated_product_relation_status FK values so the
        # ProductRelationStatus model can be flushed before the UsagePolicy model.
        usage_policies = UsagePolicy.objects.filter(dataspace=dataspace)
        usage_policies.update(associated_product_relation_status=None)

        for model_class in models:
            qs = get_unsecured_manager(model_class).filter(dataspace=dataspace)
            if options["verbosity"] > 1:
                self.stdout.write(f"Deleting {qs.count()} {model_class.__name__}...")
            qs.delete()

        # This is the case where --keep-users is NOT given
        if not options["keep_users"]:
            get_user_model().objects.scope(dataspace).delete()
            dataspace.delete()

        msg = f'All the "{dataspace}" Dataspace data have been removed.'
        self.stdout.write(self.style.SUCCESS(msg))
