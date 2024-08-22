#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import apps
from django.db.models import Case
from django.db.models import Count
from django.db.models import IntegerField
from django.db.models import Prefetch
from django.db.models import Value
from django.db.models import When
from django.utils.translation import gettext_lazy as _

from dje.templatetags.dje_tags import urlize_target_blank
from dje.urn_resolver import URN_HELP_TEXT
from dje.views import AcceptAnonymousMixin
from dje.views import DataspacedFilterView
from dje.views import Header
from dje.views import ObjectDetailsView
from dje.views import TabField
from organization.filters import OwnerFilterSet
from organization.models import Owner

License = apps.get_model("license_library", "License")
Component = apps.get_model("component_catalog", "Component")


OWNER_LICENSES_HELP = _(
    "Licenses where the owner is the original author or custodian of that license and/or is "
    "currently responsible for the text of that license."
)

OWNER_COMPONENTS_HELP = _(
    "Components where the owner is the original author or custodian of that component and/or "
    "is currently responsible for the maintenance of that component."
)


class OwnerListView(
    AcceptAnonymousMixin,
    DataspacedFilterView,
):
    model = Owner
    filterset_class = OwnerFilterSet
    template_list_table = "organization/includes/owner_list_table.html"
    include_reference_dataspace = True
    put_results_in_session = True
    table_headers = (
        Header("name", "Owner name"),
        Header("licenses", "Licenses", OWNER_LICENSES_HELP, "license"),
        Header("components", "Components", OWNER_COMPONENTS_HELP, "component"),
        Header("homepage_url"),
        Header("type", "Type", filter="type"),
    )

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .only(
                "name",
                "alias",
                "homepage_url",
                "type",
                "dataspace",
            )
            .prefetch_related(
                "license_set__usage_policy",
                "component_set__usage_policy",
            )
            .annotate(
                license_count=Count("license"),
                component_count=Count("component"),
                has_license_and_component=Case(
                    When(license_count__gt=0, component_count__gt=0, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                ),
            )
            .order_by("has_license_and_component", "name")
        )


class OwnerDetailsView(
    AcceptAnonymousMixin,
    ObjectDetailsView,
):
    model = Owner
    slug_url_kwarg = "name"
    template_name = "organization/owner_details.html"
    include_reference_dataspace = True
    show_previous_and_next_object_links = True
    tabset = {
        "essentials": {
            "fields": [
                "name",
                "homepage_url",
                "type",
                "contact_info",
                "alias",
                "notes",
                "urn",
                "dataspace",
            ],
        },
        "licenses": {
            "fields": [
                "licenses",
            ],
        },
        "components": {
            "fields": [
                "components",
            ],
        },
        "hierarchy": {},
        "external_references": {
            "fields": [
                "external_references",
            ],
        },
        "history": {
            "fields": [
                "created_date",
                "created_by",
                "last_modified_date",
                "last_modified_by",
            ],
        },
    }

    def get_queryset(self):
        license_qs = License.objects.select_related("license_profile", "category", "usage_policy")

        return (
            super()
            .get_queryset()
            .prefetch_related(
                "component_set__packages",
                "component_set__licenses__usage_policy",
                "external_references",
                Prefetch("license_set", queryset=license_qs),
            )
        )

    def tab_essentials(self):
        tab_fields = [
            TabField("name"),
            TabField("homepage_url", value_func=urlize_target_blank),
            TabField("type"),
            TabField("contact_info", value_func=urlize_target_blank),
            TabField("alias"),
            TabField("notes"),
            (_("URN"), self.object.urn_link, URN_HELP_TEXT, None),
            TabField("dataspace"),
        ]

        return {"fields": self.get_tab_fields(tab_fields)}

    def tab_licenses(self):
        license_qs = self.object.license_set.all()
        if license_qs:
            return {
                "fields": [
                    (None, license_qs, None, "organization/tabs/tab_license.html"),
                ]
            }

    def tab_hierarchy(self):
        hierarchy = self.get_owner_hierarchy(self.object)
        if hierarchy:
            return {"fields": [], "extra": hierarchy}
