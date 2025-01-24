#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS
from django.db import connections
from django.db.migrations import operations
from django.db.migrations.executor import MigrationExecutor

SAFE_OPERATIONS = (
    operations.CreateModel,
    operations.DeleteModel,
    operations.RemoveField,
    operations.AlterModelOptions,
)


def is_safe(operation):
    if isinstance(operation, SAFE_OPERATIONS):
        return True
    return False


class Command(BaseCommand):
    help = (
        "Checks the migration plan to determine if a database downtime is required."
        "Exits with a non-zero status if a zero-downtime migration is not possible."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help='Nominates a database to synchronize. Defaults to the "default" database.',
        )

    def handle(self, *args, **options):
        database = options["database"]

        # Get the database we're operating from
        connection = connections[database]

        # Hook for backends needing any database preparation
        connection.prepare_database()

        # Work out which apps have migrations and which do not
        executor = MigrationExecutor(connection)

        # Check on every migration files that could be run, without app_label scope
        targets = executor.loader.graph.leaf_nodes()

        # Build the migration plan
        plan = executor.migration_plan(targets)

        # Analyze all operations of the migrations plan to check if any is not safe
        unsafe_operations = defaultdict(list)
        for migration, backwards in plan:
            for operation in migration.operations:
                if not is_safe(operation):
                    unsafe_operations[migration].append(operation)

        if not unsafe_operations:
            message = "Planned migrations allow for a zero-downtime deployment"
            self.stdout.write(message, self.style.SUCCESS)
            exit(0)

        message = "The following planned migration operations require database downtime"
        self.stdout.write(message, self.style.ERROR)

        for migration, operation_list in unsafe_operations.items():
            self.stdout.write(str(migration), self.style.MIGRATE_HEADING)
            for operation in operation_list:
                self.stdout.write("  - " + str(operation))

        exit(1)
