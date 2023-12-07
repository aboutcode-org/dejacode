#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.urls import path

from purldb.views import PurlDBDetailsView
from purldb.views import PurlDBListView
from purldb.views import PurlDBSearchTableView

urlpatterns = [
    path(
        "search_table/",
        PurlDBSearchTableView.as_view(),
        name="purldb_search_table",
    ),
    path(
        "<uuid:uuid>/",
        PurlDBDetailsView.as_view(),
        name="purldb_details",
    ),
    path(
        "",
        PurlDBListView.as_view(),
        name="purldb_list",
    ),
]
