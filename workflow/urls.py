#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.urls import path

from workflow.views import RequestListView
from workflow.views import request_add_view
from workflow.views import request_details_view
from workflow.views import request_edit_view
from workflow.views import send_attachment_view

urlpatterns = [
    path("", RequestListView.as_view(), name="request_list"),
    path("<uuid:request_uuid>/", request_details_view, name="request_details"),
    path("form/<uuid:template_uuid>/", request_add_view, name="request_add"),
    path("<uuid:request_uuid>/edit/", request_edit_view, name="request_edit"),
    path("attachment/(<uuid:attachment_uuid>/", send_attachment_view, name="send_attachment"),
]
