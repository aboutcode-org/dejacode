#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from component_catalog.models import Component
from component_catalog.models import Package
from dje.tests import make_string
from vulnerabilities.models import Vulnerability


def make_package(dataspace, package_url=None, is_vulnerable=False, **data):
    """Create a package for test purposes."""
    if not package_url and "filename" not in data:
        data["filename"] = f"package-{make_string(10)}"

    package = Package(dataspace=dataspace, **data)
    if package_url:
        package.set_package_url(package_url)
    package.save()

    if is_vulnerable:
        make_vulnerability(dataspace, affecting=package)

    return package


def make_component(dataspace, is_vulnerable=False, **data):
    """Create a component for test purposes."""
    if "name" not in data:
        data["name"] = f"component-{make_string(10)}"

    component = Component.objects.create(
        dataspace=dataspace,
        **data,
    )

    if is_vulnerable:
        make_vulnerability(dataspace, affecting=component)

    return component


def make_vulnerability(dataspace, affecting=None, **data):
    """Create a vulnerability for test purposes."""
    if "vulnerability_id" not in data:
        data["vulnerability_id"] = f"VCID-0000-{make_string(4)}"

    vulnerability = Vulnerability.objects.create(
        dataspace=dataspace,
        **data,
    )

    if affecting:
        vulnerability.add_affected(affecting)

    return vulnerability
