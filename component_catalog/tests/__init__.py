#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from component_catalog.models import Component
from component_catalog.models import Package


def make_package(dataspace, package_url=None, **data):
    package = Package(dataspace=dataspace, **data)
    if package_url:
        package.set_package_url(package_url)
    package.save()
    return package


def make_component(dataspace, **data):
    return Component.objects.create(
        dataspace=dataspace,
        **data,
    )
