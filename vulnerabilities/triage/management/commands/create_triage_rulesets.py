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
from vulnerabilities.triage.models import TriageAction
from vulnerabilities.triage.models import TriageRuleset

"""
docker compose -f compose.dev.yml exec web ./manage.py create_triage_rulesets nexB
"""

REFERENCE_RULESETS = [
    {
        "name": "Critical Exploited Vulnerability",
        "description": (
            "Vulnerabilities with a critical risk score and a known active exploit"
            " affecting the product."
        ),
        "action": TriageAction.UPGRADE,
        "precedence": 700,
        "rules_config": {
            "risk_score": {"is_active": True, "min_risk_score": 8.0},
            "exploited_vulnerability": {"is_active": True},
        },
    },
    {
        "name": "Active Exploit",
        "description": (
            "Vulnerabilities with a known active exploit affecting the product,"
            " regardless of severity."
        ),
        "action": TriageAction.UPGRADE,
        "precedence": 600,
        "rules_config": {
            "exploited_vulnerability": {"is_active": True},
        },
    },
    {
        "name": "Reachable Vulnerability",
        "description": "Vulnerabilities confirmed as reachable within the product context.",
        "action": TriageAction.APPLY_PATCH,
        "precedence": 500,
        "rules_config": {
            "reachable_vulnerability": {"is_active": True},
        },
    },
    {
        "name": "Critical Vulnerability",
        "description": (
            "Vulnerabilities with a critical risk score and no known active exploit"
            " affecting the product."
        ),
        "action": TriageAction.APPLY_PATCH,
        "precedence": 400,
        "rules_config": {
            "risk_score": {"is_active": True, "min_risk_score": 8.0},
        },
    },
    {
        "name": "Stale Vulnerability",
        "description": (
            "Vulnerabilities with a critical risk score left unaddressed"
            " for more than 30 days in the product."
        ),
        "action": TriageAction.APPLY_PATCH,
        "precedence": 300,
        "rules_config": {
            "stale_vulnerability": {"is_active": True, "min_risk_score": 8.0, "max_days": 30},
        },
    },
    {
        "name": "Dev-Only Vulnerable Package",
        "description": "Vulnerabilities affecting only non-deployed packages in the product.",
        "action": TriageAction.NOTIFY,
        "precedence": 200,
        "rules_config": {
            "dev_only_vulnerable_package": {"is_active": True},
        },
    },
    {
        "name": "Unresolved Vulnerability",
        "description": (
            "Vulnerabilities affecting the product where at least one package"
            " has no completed triage analysis."
        ),
        "action": TriageAction.FORENSIC_ANALYSIS,
        "precedence": 100,
        "rules_config": {
            "unresolved_vulnerability": {"is_active": True},
        },
    },
]


class Command(BaseCommand):
    help = "Create reference triage rulesets in the given dataspace."

    def add_arguments(self, parser):
        parser.add_argument("dataspace", help="Name of the target Dataspace.")
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "Delete all existing triage rulesets in the dataspace before recreating them."
                " This also removes all associated product assignments and triage records."
            ),
        )

    def handle(self, *args, **options):
        dataspace_name = options["dataspace"]

        try:
            dataspace = Dataspace.objects.get(name=dataspace_name)
        except Dataspace.DoesNotExist:
            raise CommandError(f'Dataspace "{dataspace_name}" does not exist.')

        if options["reset"]:
            deleted_count, _ = TriageRuleset.objects.filter(dataspace=dataspace).delete()
            self.stdout.write(f"  Deleted {deleted_count} existing ruleset(s).")

        created_count = 0
        for ruleset_data in REFERENCE_RULESETS:
            _, created = TriageRuleset.objects.get_or_create(
                dataspace=dataspace,
                name=ruleset_data["name"],
                defaults={
                    "description": ruleset_data["description"],
                    "action": ruleset_data["action"],
                    "precedence": ruleset_data["precedence"],
                    "rules_config": ruleset_data["rules_config"],
                    "enabled": True,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f"  Created: {ruleset_data['name']}")
            else:
                self.stdout.write(f"  Already exists: {ruleset_data['name']}")

        self.stdout.write(
            self.style.SUCCESS(
                f"{created_count} ruleset(s) created in dataspace '{dataspace_name}'."
            )
        )
