#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import re

from django.http import FileResponse
from django.http import Http404

from cyclonedx import output as cyclonedx_output
from cyclonedx.model import bom as cyclonedx_bom
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator

from dejacode import __version__ as dejacode_version
from dejacode_toolkit import spdx

CYCLONEDX_DEFAULT_SPEC_VERSION = "1.6"


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
            all_licenses.update(
                entry.related_component_or_package.licenses.all())
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
    root_component = instance.as_cyclonedx()

    bom = cyclonedx_bom.Bom()
    bom.metadata = cyclonedx_bom.BomMetaData(
        component=root_component,
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

    cyclonedx_components = []
    if hasattr(instance, "get_cyclonedx_components"):
        cyclonedx_components = [
            component.as_cyclonedx() for component in instance.get_cyclonedx_components()
        ]

    for component in cyclonedx_components:
        bom.components.add(component)
        bom.register_dependency(root_component, [component])

    return bom


def get_cyclonedx_bom_json(cyclonedx_bom, spec_version=None):
    """Generate JSON output for the provided instance in CycloneDX BOM format."""
    if not spec_version:
        spec_version = CYCLONEDX_DEFAULT_SPEC_VERSION
    schema_version = SchemaVersion.from_version(spec_version)

    json_outputter = cyclonedx_output.make_outputter(
        bom=cyclonedx_bom,
        output_format=cyclonedx_output.OutputFormat.JSON,
        schema_version=schema_version,
    )

    # Using the internal API in place of the output_as_string() method to avoid
    # a round of deserialization/serialization while fixing the field ordering.
    json_outputter.generate()
    bom_as_dict = json_outputter._bom_json

    # The default order out of the outputter is not great, the following sorts the
    # bom using the order from the schema.
    sorted_json = sort_bom_with_schema_ordering(bom_as_dict, schema_version)

    return sorted_json


def sort_bom_with_schema_ordering(bom_as_dict, schema_version):
    """Sort the ``bom_as_dict`` using the ordering from the ``schema_version``."""
    schema_file = JsonStrictValidator(schema_version)._schema_file
    with open(schema_file) as sf:
        schema_dict = json.loads(sf.read())

    order_from_schema = list(schema_dict.get("properties", {}).keys())
    ordered_dict = {key: bom_as_dict.get(
        key) for key in order_from_schema if key in bom_as_dict}

    return json.dumps(ordered_dict, indent=2)


def get_cyclonedx_filename(instance):
    base_filename = f"dejacode_{instance.dataspace.name}_{instance._meta.model_name}"
    filename = f"{base_filename}_{instance}.cdx.json"
    return safe_filename(filename)
