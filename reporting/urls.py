#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.urls import path

from reporting.views import ReportDetailsView
from reporting.views import ReportListView

urlpatterns = [
    path("<uuid:uuid>/", ReportDetailsView.as_view(), name="report_details"),
    path("", ReportListView.as_view(), name="report_list"),
]
