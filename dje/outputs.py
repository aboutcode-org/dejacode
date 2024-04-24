#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import re

from django.http import FileResponse
from django.http import Http404

from cyclonedx import output as cyclonedx_output
from cyclonedx.model import bom as cyclonedx_bom

from dejacode import __version__ as dejacode_version
from dejacode_toolkit import spdx


def safe_filename(filename):
    """Convert the provided `filename` to a safe filename."""
    return re.sub("[^A-Za-z0-9.-]+", "_", filename).lower()


def get_attachment_response(file_content, filename, content_type):
    if not file_content or not filename:
        raise Http404

    response = FileResponse(
        file_content,
        filename=filename,
        content_type=content_type,
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


def get_spdx_extracted_licenses(spdx_packages):
    """
    Return all the licenses to be included in the SPDX extracted_licenses.
    Those include the `LicenseRef-` licenses, ie: licenses not available in the
    SPDX list.

    In the case of Product relationships, ProductComponent and ProductPackage,
    the set of licenses of the related object, Component or Package, is used
    as the licenses of the relationship is always a subset of the ones of the
    related object.
    This ensures that we have all the license required for a valid SPDX document.
    """
    from product_portfolio.models import ProductRelationshipMixin

    all_licenses = set()
    for entry in spdx_packages:
        if isinstance(entry, ProductRelationshipMixin):
            all_licenses.update(entry.related_component_or_package.licenses.all())
        else:
            all_licenses.update(entry.licenses.all())

    return [
        license.as_spdx() for license in all_licenses if license.spdx_id.startswith("LicenseRef")
    ]


def get_spdx_document(instance, user):
    spdx_packages = instance.get_spdx_packages()

    creation_info = spdx.CreationInfo(
        person_name=f"{user.first_name} {user.last_name}",
        person_email=user.email,
        organization_name=user.dataspace.name,
        tool=f"DejaCode-{dejacode_version}",
    )

    document = spdx.Document(
        name=f"dejacode_{instance.dataspace.name}_{instance._meta.model_name}_{instance}",
        namespace=f"https://dejacode.com/spdxdocs/{instance.uuid}",
        creation_info=creation_info,
        packages=[package.as_spdx() for package in spdx_packages],
        extracted_licenses=get_spdx_extracted_licenses(spdx_packages),
    )

    return document


def get_spdx_filename(spdx_document):
    document_name = spdx_document.as_dict()["name"]
    filename = f"{document_name}.spdx.json"
    return safe_filename(filename)


def get_cyclonedx_bom(instance, user):
    """https://cyclonedx.org/use-cases/#dependency-graph"""
    cyclonedx_components = []

    if hasattr(instance, "get_cyclonedx_components"):
        cyclonedx_components = [
            component.as_cyclonedx() for component in instance.get_cyclonedx_components()
        ]

    bom = cyclonedx_bom.Bom(components=cyclonedx_components)

    cdx_component = instance.as_cyclonedx()
    cdx_component.dependencies.update([component.bom_ref for component in cyclonedx_components])

    bom.metadata = cyclonedx_bom.BomMetaData(
        component=cdx_component,
        tools=[
            cyclonedx_bom.Tool(
                vendor="nexB",
                name="DejaCode",
                version=dejacode_version,
            )
        ],
        authors=[
            cyclonedx_bom.OrganizationalContact(
                name=f"{user.first_name} {user.last_name}",
            )
        ],
    )

    return bom


def get_cyclonedx_bom_json(cyclonedx_bom):
    outputter = cyclonedx_output.get_instance(
        bom=cyclonedx_bom,
        output_format=cyclonedx_output.OutputFormat.JSON,
    )
    return outputter.output_as_string()


def get_cyclonedx_filename(instance):
    base_filename = f"dejacode_{instance.dataspace.name}_{instance._meta.model_name}"
    filename = f"{base_filename}_{instance}.cdx.json"
    return safe_filename(filename)