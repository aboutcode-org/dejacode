#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from dje.models import Dataspace
from vulnerabilities.triage.engine import evaluate_assignments
from vulnerabilities.triage.models import ProductTriageRuleset
from vulnerabilities.triage.models import TriageRecord


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

        assignments = (
            ProductTriageRuleset.objects.filter(
                dataspace=dataspace,
                ruleset__enabled=True,
            )
            .select_related("product", "ruleset")
            .order_by("product__name", "product__version", "-ruleset__precedence")
        )

        assignment_count = assignments.count()
        self.stdout.write(f"Active assignments: {assignment_count}")

        if not assignment_count:
            self.stdout.write("No active ruleset assignments found.")
            return

        evaluated_count = evaluate_assignments(assignments)
        self.stdout.write(f"Evaluated: {evaluated_count}/{assignment_count}")

        total = TriageRecord.objects.filter(dataspace=dataspace).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {total} vulnerability triage record(s) active in '{dataspace_name}'."
            )
        )
