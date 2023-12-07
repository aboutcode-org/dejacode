#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.urls import path

from dje.views import DataspacedCreateView
from dje.views import DataspacedDeleteView
from dje.views import DataspacedUpdateView
from organization.forms import OwnerForm
from organization.models import Owner
from organization.views import OwnerDetailsView
from organization.views import OwnerListView

urlpatterns = [
    path(
        "<str:dataspace>/<str:name>/change/",
        DataspacedUpdateView.as_view(
            model=Owner,
            form_class=OwnerForm,
            slug_url_kwarg="name",
            permission_required="organization.change_owner",
        ),
        name="owner_change",
    ),
    path(
        "<str:dataspace>/<str:name>/delete/",
        DataspacedDeleteView.as_view(
            model=Owner,
            slug_url_kwarg="name",
            permission_required="organization.delete_owner",
        ),
        name="owner_delete",
    ),
    path(
        "<str:dataspace>/<str:name>/",
        OwnerDetailsView.as_view(),
        name="owner_details",
    ),
    path(
        "add/",
        DataspacedCreateView.as_view(
            model=Owner,
            form_class=OwnerForm,
            permission_required="organization.add_owner",
        ),
        name="owner_add",
    ),
    path(
        "<str:dataspace>/",
        OwnerListView.as_view(),
        name="owner_list",
    ),
    path(
        "",
        OwnerListView.as_view(),
        name="owner_list",
    ),
]
