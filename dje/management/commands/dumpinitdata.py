#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from component_catalog.models import ComponentKeyword
from component_catalog.models import ComponentStatus
from dje.management import LICENSE_LIBRARY_MODELS
from dje.management import POLICY_MODELS
from dje.management import REPORTING_MODELS
from dje.management.commands.dumpdataset import ExcludeFieldsSerializer
from dje.models import Dataspace
from license_library.models import License
from organization.models import Owner
from product_portfolio.models import ProductItemPurpose
from product_portfolio.models import ProductRelationStatus
from product_portfolio.models import ProductStatus
from workflow.models import Priority
from workflow.models import Question
from workflow.models import RequestTemplate


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('dataspace_name', help='Name of the Dataspace.')

    def handle(self, *args, **options):
        dataspace_name = options.get('dataspace_name')
        try:
            dataspace = Dataspace.objects.get(name=dataspace_name)
        except Dataspace.DoesNotExist:
            raise CommandError(f'The Dataspace {dataspace_name} does not exit.')

        models = []
        data = [
            dataspace,
            *Group.objects.all(),
        ]

        # Owners
        license_ids = License.objects.scope(dataspace).values_list("id", flat=True)
        data += list(Owner.objects.scope(dataspace).filter(license__id__in=license_ids))
        # Licenses
        models.extend(LICENSE_LIBRARY_MODELS)
        # Components
        models.extend([ComponentKeyword, ComponentStatus])
        # Products
        models.extend([ProductStatus, ProductRelationStatus, ProductItemPurpose])
        # Workflow
        models.extend([RequestTemplate, Question, Priority])
        # Reporting
        models.extend(REPORTING_MODELS)
        # Policies
        models.extend(POLICY_MODELS)

        for model_class in models:
            qs = model_class.objects.scope(dataspace).select_related()
            data += list(qs)

        return ExcludeFieldsSerializer().serialize(
            queryset=data,
            indent=2,
            use_natural_foreign_keys=True,
            use_natural_primary_keys=True,
        )
