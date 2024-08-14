#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from dje.importers import BaseImporter
from dje.importers import BaseImportModelForm
from organization.models import Owner


class OwnerImportForm(BaseImportModelForm):
    class Meta:
        model = Owner
        exclude = ("children",)  # Explicitly exclude ManyToManyField


class OwnerImporter(BaseImporter):
    model_form = OwnerImportForm
