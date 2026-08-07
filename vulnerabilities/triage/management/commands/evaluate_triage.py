#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import apps
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from dje.models import Dataspace
from vulnerabilities.triage.engine import evaluate_ruleset
from vulnerabilities.triage.models import TriageRecord
from vulnerabilities.triage.models import TriageRuleset

"""
docker compose -f compose.dev.yml exec web ./manage.py evaluate_triage nexB
"""


class Command(BaseCommand):
    help = "Evaluate all enabled triage rulesets against all products in the given dataspace."

    def add_arguments(self, parser):
        parser.add_argument("dataspace", help="Name of the target Dataspace.")

    def handle(self, *args, **options):
        dataspace_name = options["dataspace"]

        try:
            dataspace = Dataspace.objects.get(name=dataspace_name)
        except Dataspace.DoesNotExist:
            raise CommandError(f'Dataspace "{dataspace_name}" does not exist.')

        Product = apps.get_model("product_portfolio", "product")
        products = Product.unsecured_objects.scope(dataspace)
        rulesets = TriageRuleset.objects.filter(dataspace=dataspace, enabled=True)

        product_count = products.count()
        ruleset_count = rulesets.count()

        self.stdout.write(f"Products: {product_count}, rulesets: {ruleset_count}")

        if not ruleset_count:
            self.stdout.write("No enabled rulesets found.")
            return

        if not product_count:
            self.stdout.write("No products found.")
            return

        for product in products:
            self.stdout.write(f"  {product}")
            for ruleset in rulesets:
                evaluate_ruleset(ruleset=ruleset, product=product)

        total = TriageRecord.objects.filter(dataspace=dataspace).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {total} package triage record(s) active in dataspace '{dataspace_name}'."
            )
        )
