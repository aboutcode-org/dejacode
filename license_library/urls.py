#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.urls import path

from dje.views import DataspacedDeleteView
from license_library.models import License
from license_library.views import LicenseDetailsView
from license_library.views import LicenseDownloadTextView
from license_library.views import LicenseListView

urlpatterns = [
    path(
        "<str:dataspace>/<str:key>/delete/",
        DataspacedDeleteView.as_view(
            model=License,
            slug_url_kwarg="key",
            permission_required="license_library.delete_license",
        ),
        name="license_delete",
    ),
    path(
        "<str:dataspace>/<str:key>/download_text/",
        LicenseDownloadTextView.as_view(),
        name="license_download_text",
    ),
    path(
        "<str:dataspace>/<str:key>/",
        LicenseDetailsView.as_view(),
        name="license_details",
    ),
    path(
        "<str:dataspace>/",
        LicenseListView.as_view(),
        name="license_list",
    ),
    path(
        "",
        LicenseListView.as_view(),
        name="license_list",
    ),
]
