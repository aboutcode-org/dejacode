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
from vulnerabilities.triage.models import TriageDecision
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

        created_count = 0
        updated_count = 0
        no_match_count = 0

        for product in products:
            for ruleset in rulesets:
                result = evaluate_ruleset(ruleset=ruleset, product=product)
                if not result:
                    no_match_count += 1
                    continue

                _, created = TriageDecision.objects.update_or_create(
                    dataspace=dataspace,
                    product=product,
                    ruleset=ruleset,
                    defaults={
                        "action": result["action"],
                        "matched_rules": result["matched_rules"],
                    },
                )

                label = f"{product} -> {ruleset}"
                if created:
                    created_count += 1
                    self.stdout.write(f"  [new]     {label}: {result['action']}")
                else:
                    updated_count += 1
                    self.stdout.write(f"  [updated] {label}: {result['action']}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {created_count} created, {updated_count} updated,"
                f" {no_match_count} no match."
            )
        )
