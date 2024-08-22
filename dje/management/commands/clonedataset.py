#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import IntegrityError

from dje.copier import copy_object
from dje.management import ALL_MODELS_NO_PP
from dje.management import LICENSE_LIBRARY_MODELS
from dje.management import POLICY_MODELS
from dje.management import REPORTING_MODELS
from dje.management import get_component_limited_qs
from dje.models import Dataspace
from dje.models import ExternalSource
from product_portfolio.models import ProductRelationStatus
from product_portfolio.models import ProductStatus
from workflow.models import Priority
from workflow.models import Question
from workflow.models import RequestTemplate


class Command(BaseCommand):
    help = "Copy all the data for the reference dataspace into the target one."

    def add_arguments(self, parser):
        parser.add_argument("reference", help="Name of the reference Dataspace.")
        parser.add_argument("target", help="Name of the target Dataspace.")
        parser.add_argument("username", help="Your username.")
        parser.add_argument(
            "--license_library",
            action="store_true",
            dest="license_library",
            default=False,
            help="Limit the clone to License Library objects.",
        )
        parser.add_argument(
            "--product_portfolio",
            action="store_true",
            dest="product_portfolio",
            default=False,
            help="Include Product Portfolio models."
            "WARNING: This should only be used when cloning a Template "
            "Dataspace",
        )

    def handle(self, *args, **options):
        try:
            reference = Dataspace.objects.get(name=options.get("reference"))
            target = Dataspace.objects.get(name=options.get("target"))
        except ObjectDoesNotExist:
            raise CommandError("One of the Dataspace does not exist.")

        if reference == target:
            raise CommandError("reference and target must be different.")

        try:
            user = get_user_model().objects.get(username=options.get("username"))
        except ObjectDoesNotExist:
            raise CommandError("The given username does not exist.")

        if options.get("license_library"):
            models = LICENSE_LIBRARY_MODELS[:]
        else:
            models = ALL_MODELS_NO_PP[:]

        models.extend(REPORTING_MODELS)
        models.extend(POLICY_MODELS)
        models.extend(
            [
                ExternalSource,
                Priority,
                RequestTemplate,
                Question,
            ]
        )

        # The following models cannot be added until the copy supports secured manager.
        # ProductComponent, ProductAssignedLicense, ProductComponentAssignedLicense
        # Also, Product.objects always Return None if no user is provided.
        if options.get("product_portfolio"):
            models.extend(
                [
                    ProductStatus,
                    ProductRelationStatus,
                ]
            )

        # Explicit empty exclude dict for each Models to enforce an exact copy
        copy_kwargs = {"exclude": {}}
        for model in models:
            copy_kwargs["exclude"][model] = []

        # Do not trigger m2m or o2m copy cascade, respect the copy order from
        # the `models` list.
        copy_kwargs["skip_m2m_and_o2m"] = True

        errors = []

        for model in models:
            if model.__name__ == "Component":
                reference_qs = get_component_limited_qs(dataspace=reference)
            else:
                reference_qs = model.objects.scope(reference)

            msg = "{}: copying {} objects...".format(model.__name__, reference_qs.count())
            self.stdout.write(msg)

            for instance in reference_qs:
                try:
                    copy_object(instance, target, user, **copy_kwargs)
                except IntegrityError as e:
                    errors.append(f'{instance.__class__.__name__} pk={instance.pk} error="{e}"')

            # Verification
            target_qs = model.objects.scope(target)
            if len(reference_qs) == target_qs.count():
                self.stdout.write("Copy completed.")
            else:
                self.stdout.write("Errors!")

        self.stdout.write("Data copy completed.")

        if errors:
            self.stderr.write("\n\n".join(errors))
