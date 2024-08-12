#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.humanize.templatetags.humanize import naturaltime
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from grappelli.dashboard import Dashboard
from grappelli.dashboard import modules


class DejaCodeDashboard(Dashboard):
    def init_with_context(self, context):
        user = context["request"].user
        dataspace = user.dataspace

        self.children.append(
            modules.ModelList(
                "",
                column=1,
                collapsible=True,
                models=[
                    "*.Product",
                    "*.Component",
                    "*.Package",
                    "*.License",
                    "*.Owner",
                ],
            )
        )

        administration_models = ["dje.*"]
        if dataspace.is_reference:
            administration_models.extend(
                [
                    "django.contrib.*",
                ]
            )
            if user.is_superuser:
                administration_models.extend(
                    [
                        "axes.*",
                    ]
                )

        # Append an app list module for "Administration"
        self.children.append(
            modules.ModelList(
                _("Administration"),
                column=1,
                collapsible=True,
                models=administration_models,
            )
        )

        # Append a recent actions module
        self.children.append(
            modules.RecentActions(
                _("My Recent Actions"),
                collapsible=False,
                column=1,
                limit=10,
            )
        )

        shortcuts = [
            {
                "title": _("Documentation"),
                "url": "https://dejacode.readthedocs.io/en/latest/",
            },
            {
                "title": _("Models documentation"),
                "url": reverse("admin:docs_models"),
            },
            {
                "title": _("API documentation"),
                "url": reverse("api-docs:docs-index"),
            },
        ]

        if user.is_superuser:
            shortcuts.append(
                {
                    "title": _("Download License Policies"),
                    "url": reverse("admin:policy_usagepolicy_license_dump"),
                }
            )

        if user.is_staff:
            shortcuts.append(
                {
                    "title": _("Integrations status"),
                    "url": reverse("integrations_status"),
                }
            )

        shortcuts.append(
            {
                "title": _("Sign out"),
                "url": reverse("logout"),
            }
        )

        # Append an app list module for "Applications"
        self.children.append(
            modules.AppList(
                _("Applications"),
                column=2,
                collapsible=True,
                exclude=(
                    "django.contrib.*",
                    "dje.*",
                    "axes.*",
                ),
            )
        )

        # Append another link list module for "Shortcuts"
        self.children.append(
            modules.LinkList(
                _("Shortcuts"),
                collapsible=False,
                column=3,
                children=shortcuts,
            )
        )

        imports = []

        if user.has_perm("component_catalog.add_component"):
            imports.append(
                {
                    "title": _("Component import"),
                    "url": reverse("admin:component_catalog_component_import"),
                }
            )
        if user.has_perm("component_catalog.add_package"):
            imports.append(
                {
                    "title": _("Package import"),
                    "url": reverse("admin:component_catalog_package_import"),
                }
            )
        if user.has_perm("component_catalog.add_subcomponent"):
            imports.append(
                {
                    "title": _("Subcomponent import"),
                    "url": reverse("admin:component_catalog_subcomponent_import"),
                }
            )
        if user.has_perm("organization.add_owner"):
            imports.append(
                {
                    "title": _("Owner import"),
                    "url": reverse("admin:organization_owner_import"),
                }
            )
        if user.has_perm("product_portfolio.add_productcomponent"):
            imports.append(
                {
                    "title": _("Product component import"),
                    "url": reverse("admin:product_portfolio_productcomponent_import"),
                }
            )
        if user.has_perm("product_portfolio.add_productpackage"):
            imports.append(
                {
                    "title": _("Product package import"),
                    "url": reverse("admin:product_portfolio_productpackage_import"),
                }
            )
        if user.has_perm("product_portfolio.add_codebaseresource"):
            imports.append(
                {
                    "title": _("Codebase resource import"),
                    "url": reverse("admin:product_portfolio_codebaseresource_import"),
                }
            )

        if imports:
            self.children.append(
                modules.LinkList(
                    _("Imports"),
                    collapsible=True,
                    column=3,
                    children=imports,
                )
            )

        data_updates = []
        if dataspace.enable_vulnerablecodedb_access:
            updated_at = dataspace.vulnerabilities_updated_at
            data_updates.append(
                {
                    "title": _(f"Vulnerabilities: {naturaltime(updated_at)}"),
                    "description": updated_at,
                }
            )

        if data_updates:
            self.children.append(
                modules.LinkList(
                    _("Data updates"),
                    collapsible=True,
                    column=3,
                    children=data_updates,
                )
            )
