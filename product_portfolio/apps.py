#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import AppConfig
from django.conf import settings
from django.db import connection
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


def run_unmanaged_models_raw_sql(app_config, **kwargs):
    """Run the `raw_sql` attribute of the unmanaged models within the provided `app_config`."""
    unmanaged_models = [model for model in app_config.get_models() if not model._meta.managed]
    for model in unmanaged_models:
        if raw_sql := getattr(model, "raw_sql", None):
            with connection.cursor() as cursor:
                cursor.execute(raw_sql)


class ProductPortfolioConfig(AppConfig):
    name = "product_portfolio"
    verbose_name = _("Product Portfolio")

    def ready(self):
        if settings.IS_TESTS:
            post_migrate.connect(run_unmanaged_models_raw_sql, sender=self)
