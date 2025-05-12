#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.urls import path

from component_catalog.models import Component
from component_catalog.models import Package
from component_catalog.views import ComponentAddView
from component_catalog.views import ComponentDetailsView
from component_catalog.views import ComponentListView
from component_catalog.views import ComponentUpdateView
from component_catalog.views import PackageAddView
from component_catalog.views import PackageDetailsView
from component_catalog.views import PackageListView
from component_catalog.views import PackageTabPurlDBView
from component_catalog.views import PackageTabScanView
from component_catalog.views import PackageUpdateView
from component_catalog.views import ScanListView
from component_catalog.views import component_create_ajax_view
from component_catalog.views import delete_scan_view
from component_catalog.views import get_scan_progress_htmx_view
from component_catalog.views import package_create_ajax_view
from component_catalog.views import package_scan_view
from component_catalog.views import send_scan_data_as_file_view
from dje.views import DataspacedDeleteView
from dje.views import ExportCycloneDXBOMView
from dje.views import ExportSPDXDocumentView
from dje.views import MultiSendAboutFilesView
from dje.views import SendAboutFilesView

packages_patterns = [
    path(
        "packages/add/",
        PackageAddView.as_view(),
        name="package_add",
    ),
    path(
        "packages/add_urls/",
        package_create_ajax_view,
        name="package_add_urls",
    ),
    path(
        "packages/about_files/",
        MultiSendAboutFilesView.as_view(
            model=Package,
        ),
        name="package_multi_about_files",
    ),
    path(
        "packages/<str:dataspace>/<uuid:uuid>/change/",
        PackageUpdateView.as_view(),
        name="package_change",
    ),
    path(
        "packages/<str:dataspace>/<path:identifier>/<uuid:uuid>/change/",
        PackageUpdateView.as_view(),
        name="package_change",
    ),
    path(
        "packages/<str:dataspace>/<uuid:uuid>/about_files/",
        SendAboutFilesView.as_view(
            model=Package,
            slug_url_kwarg="uuid",
        ),
        name="package_about_files",
    ),
    path(
        "packages/<str:dataspace>/<uuid:uuid>/export_spdx/",
        ExportSPDXDocumentView.as_view(
            model=Package,
            slug_url_kwarg="uuid",
        ),
        name="package_export_spdx",
    ),
    path(
        "packages/<str:dataspace>/<uuid:uuid>/export_cyclonedx/",
        ExportCycloneDXBOMView.as_view(
            model=Package,
            slug_url_kwarg="uuid",
        ),
        name="package_export_cyclonedx",
    ),
    path(
        "packages/<str:dataspace>/<uuid:uuid>/delete/",
        DataspacedDeleteView.as_view(
            model=Package,
            slug_url_kwarg="uuid",
            permission_required="component_catalog.delete_package",
        ),
        name="package_delete",
    ),
    path(
        "packages/<str:dataspace>/<uuid:uuid>/scan/",
        package_scan_view,
        name="package_scan",
    ),
    path(
        "packages/<str:dataspace>/<uuid:uuid>/scan_progress_htmx/",
        get_scan_progress_htmx_view,
        name="scan_progress_htmx",
    ),
    path(
        "packages/<str:dataspace>/<uuid:uuid>/tab_scan/",
        PackageTabScanView.as_view(),
        name="package_tab_scan",
    ),
    path(
        "packages/<str:dataspace>/<uuid:uuid>/tab_purldb/",
        PackageTabPurlDBView.as_view(),
        name="package_tab_purldb",
    ),
    path(
        "packages/<str:dataspace>/<uuid:uuid>/",
        PackageDetailsView.as_view(),
        name="package_details",
    ),
    path(
        "packages/<str:dataspace>/<path:identifier>/<uuid:uuid>/",
        PackageDetailsView.as_view(),
        name="package_details",
    ),
    path(
        "packages/<str:dataspace>/",
        PackageListView.as_view(),
        name="package_list",
    ),
    path(
        "packages/",
        PackageListView.as_view(),
        name="package_list",
    ),
]

scans_patterns = [
    path(
        "scans/<uuid:project_uuid>/<str:filename>/data/",
        send_scan_data_as_file_view,
        name="scan_data_as_file",
    ),
    path(
        "scans/<uuid:project_uuid>/delete/",
        delete_scan_view,
        name="scan_delete",
    ),
    path(
        "scans/",
        ScanListView.as_view(),
        name="scan_list",
    ),
]


# WARNING: we moved the components/ patterns from the include to the following
# since we need the packages/ and scans/ to be registered on the root "/"


def component_path(path_segment, view):
    return [
        path(
            f"components/<str:dataspace>/<str:name>/<str:version>/{path_segment}/",
            view,
            name=f"component_{path_segment}",
        ),
        path(
            f"components/<str:dataspace>/<str:name>/{path_segment}/",
            view,
            name=f"component_{path_segment}",
        ),
    ]


component_patterns = [
    *component_path("change", ComponentUpdateView.as_view()),
    *component_path(
        "delete",
        DataspacedDeleteView.as_view(
            model=Component,
            slug_url_kwarg=("name", "version"),
            permission_required="component_catalog.delete_component",
        ),
    ),
    *component_path(
        "about_files",
        SendAboutFilesView.as_view(
            model=Component,
            slug_url_kwarg=("name", "version"),
        ),
    ),
    *component_path(
        "export_spdx",
        ExportSPDXDocumentView.as_view(
            model=Component,
            slug_url_kwarg=("name", "version"),
        ),
    ),
    *component_path(
        "export_cyclonedx",
        ExportCycloneDXBOMView.as_view(
            model=Component,
            slug_url_kwarg=("name", "version"),
        ),
    ),
    path(
        "components/<str:dataspace>/<str:name>/<str:version>/",
        ComponentDetailsView.as_view(),
        name="component_details",
    ),
    path(
        "components/<str:dataspace>/<str:name>/",
        ComponentDetailsView.as_view(),
        name="component_details",
    ),
    path(
        "components/add/",
        ComponentAddView.as_view(),
        name="component_add",
    ),
    path(
        "components/add_ajax/",
        component_create_ajax_view,
        name="component_add_ajax",
    ),
    path(
        "components/about_files/",
        MultiSendAboutFilesView.as_view(
            model=Component,
        ),
        name="component_multi_about_files",
    ),
    path(
        "components/<str:dataspace>/",
        ComponentListView.as_view(),
        name="component_list",
    ),
    path(
        "components/",
        ComponentListView.as_view(),
        name="component_list",
    ),
]


urlpatterns = packages_patterns + component_patterns + scans_patterns
