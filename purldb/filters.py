#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.utils.translation import gettext_lazy as _

import django_filters

from component_catalog.models import Package
from dje.filters import FilterSetUtilsMixin


class PurlDBFilterSet(FilterSetUtilsMixin, django_filters.FilterSet):
    purl = django_filters.CharFilter(label=_("Package URL"))
    q = django_filters.CharFilter(label=_("Search"))
    sort = django_filters.OrderingFilter(
        label=_("Sort"),
        fields=[
            "type",
            "namespace",
            "name",
            "version",
            "download_url",
            "release_date",
        ],
    )

    class Meta:
        model = Package
        fields = [
            "type",
            "namespace",
            "name",
            "version",
            "download_url",
            "filename",
            "sha1",
            "md5",
            "size",
            "release_date",
        ]
