#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F
from django.http import Http404
from django.utils.translation import gettext_lazy as _

from component_catalog.filters import VulnerabilityFilterSet
from dejacode_toolkit.vulnerablecode import VulnerableCode
from dje.views import DataspacedFilterView
from dje.views import Header
from vulnerabilities.models import Vulnerability


class VulnerabilityListView(
    LoginRequiredMixin,
    DataspacedFilterView,
):
    model = Vulnerability
    filterset_class = VulnerabilityFilterSet
    template_name = "component_catalog/vulnerability_list.html"
    template_list_table = "component_catalog/tables/vulnerability_list_table.html"
    table_headers = (
        Header("vulnerability_id", _("Vulnerability")),
        Header("aliases", _("Aliases")),
        # Keep `max_score` to enable column sorting
        Header("max_score", _("Score"), help_text="Severity score range", filter="max_score"),
        Header("summary", _("Summary")),
        Header("affected_products_count", _("Affected products"), help_text="Affected products"),
        Header("affected_packages_count", _("Affected packages"), help_text="Affected packages"),
        Header("fixed_packages_count", _("Fixed by"), help_text="Fixed by packages"),
    )

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .only(
                "uuid",
                "vulnerability_id",
                "aliases",
                "summary",
                "fixed_packages_count",
                "max_score",
                "min_score",
                "created_date",
                "last_modified_date",
                "dataspace",
            )
            .with_affected_products_count()
            .with_affected_packages_count()
            .order_by(
                F("max_score").desc(nulls_last=True),
                "-min_score",
            )
        )

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        if not self.dataspace.enable_vulnerablecodedb_access:
            raise Http404("VulnerableCode access is not enabled.")

        vulnerablecode = VulnerableCode(self.dataspace)
        context_data["vulnerablecode_url"] = vulnerablecode.service_url
        return context_data
