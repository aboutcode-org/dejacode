#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import re
from datetime import UTC
from datetime import datetime

from django.http import FileResponse
from django.http import Http404

from cyclonedx import output as cyclonedx_output
from cyclonedx.model import bom as cyclonedx_bom
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator

from dejacode import __version__ as dejacode_version
from dejacode_toolkit import csaf
from dejacode_toolkit import openvex
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


def get_cyclonedx_bom(instance, user, include_components=True, include_vex=False):
    """
    https://cyclonedx.org/use-cases/#dependency-graph
    https://cyclonedx.org/use-cases/#vulnerability-exploitability
    """
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

    if include_components:
        for component in cyclonedx_components:
            bom.components.add(component)
            bom.register_dependency(root_component, [component])

    if include_vex:
        vulnerability_qs = instance.get_vulnerability_qs(prefetch_related_packages=True)
        vulnerabilities = []
        for vulnerability in vulnerability_qs:
            analysis = None
            vulnerability_analyses = vulnerability.vulnerability_analyses.all()
            if len(vulnerability_analyses) == 1:
                analysis = vulnerability_analyses[0]

            vulnerabilities.append(
                vulnerability.as_cyclonedx(
                    affected_instances=vulnerability.affected_packages.all(),
                    analysis=analysis,
                )
            )

        bom.vulnerabilities = vulnerabilities

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
    ordered_dict = {key: bom_as_dict.get(key) for key in order_from_schema if key in bom_as_dict}

    return json.dumps(ordered_dict, indent=2)


def get_filename(instance, extension):
    base_filename = f"dejacode_{instance.dataspace.name}_{instance._meta.model_name}"
    filename = f"{base_filename}_{instance}.{extension}.json"
    return safe_filename(filename)


CDX_STATE_TO_CSAF_STATUS = {
    "resolved": "fixed",
    "resolved_with_pedigree": "fixed",
    "exploitable": "known_affected",
    "in_triage": "under_investigation",
    "false_positive": "known_not_affected",
    "not_affected": "known_not_affected",
}

CDX_RESPONSE_TO_CSAF_REMEDIATION = {
    "can_not_fix": "no_fix_planned",
    "rollback": "vendor_fix",
    "update": "vendor_fix",
    "will_not_fix": "no_fix_planned",
    "workaround_available": "workaround",
}

ALIAS_PREFIX_TO_CSAF_SYSTEM_NAME = {
    "CVE": "Common Vulnerabilities and Exposures",
    "GHSA": "GitHub Security Advisory",
    "PYSEC": "Python Packaging Advisory",
    "USN": "Ubuntu Security Notice",
}


def get_csaf_document(product):
    """Return a csaf.Document object using the provided `product` context."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    publisher = csaf.Publisher(
        category="vendor",
        name=product.dataspace.name,
        namespace=product.dataspace.homepage_url or "https://url.not.available",
    )
    revision_history = csaf.RevisionHistoryItem(
        date=now,
        number="1",
        summary="Initial version",
    )
    tracking = csaf.Tracking(
        current_release_date=now,
        id=f"CSAF-Document-{str(product.uuid)}",
        initial_release_date=now,
        revision_history=[revision_history],
        status="final",
        version="1",
    )
    document = csaf.Document(
        category="csaf_vex",
        csaf_version="2.0",
        publisher=publisher,
        title=f"CSAF VEX document for {product}",
        tracking=tracking,
    )
    return document


def get_csaf_product_tree(product):
    name = product.name
    version = product.version or "Unknown"
    vendor = product.owner.name if product.owner else "Unknown"

    product_version_branch = csaf.BranchesTItem(
        category="product_version",
        name=version,
        product=csaf.FullProductNameT(
            name=f"{vendor} {name} {version}",
            product_id="CSAFPID-0001",
        ),
    )
    product_name_branch = csaf.BranchesTItem(
        category="product_name",
        name=name,
        branches=[product_version_branch],
    )
    product_vendor_branch = csaf.BranchesTItem(
        category="vendor",
        name=vendor,
        branches=[product_name_branch],
    )
    product_tree = csaf.ProductTree(
        branches=csaf.BranchesT(root=[product_vendor_branch]),
    )
    return product_tree


def get_csaf_vulnerability_ids(vulnerability):
    ids = [csaf.Id(system_name="VulnerableCode", text=vulnerability.vulnerability_id)]

    for alias in vulnerability.aliases:
        prefix = alias.split("-")[0]
        system_name = ALIAS_PREFIX_TO_CSAF_SYSTEM_NAME.get(prefix, prefix)
        ids.append(csaf.Id(system_name=system_name, text=alias))

    return ids


def get_csaf_vulnerability_product_status(vulnerability):
    product_id = "CSAFPID-0001"
    products = csaf.ProductsT([csaf.ProductIdT(product_id)])
    status = default_status = "under_investigation"
    remediations = None
    threats = None

    vulnerability_analyses = vulnerability.vulnerability_analyses.all()
    if len(vulnerability_analyses) == 1:
        analysis = vulnerability_analyses[0]
        status = CDX_STATE_TO_CSAF_STATUS.get(analysis.state, default_status)

        if status == "known_affected":
            category = "none_available"
            if analysis.responses:
                response = analysis.responses[0]
                category = CDX_RESPONSE_TO_CSAF_REMEDIATION.get(response, category)
            details = analysis.detail or "Not available"
            remediations = [
                csaf.Remediation(category=category, details=details, product_ids=products)
            ]

        elif status == "known_not_affected":
            details = analysis.detail or "Not available"
            threats = [csaf.Threat(category="impact", details=details, product_ids=products)]

    product_status = csaf.ProductStatus(**{status: products})

    return product_status, remediations, threats


def get_csaf_vulnerability(vulnerability):
    summary = vulnerability.summary or "Not available"
    note = csaf.NotesTItem(category="summary", text=summary)
    product_status, remediations, threats = get_csaf_vulnerability_product_status(vulnerability)

    csaf_vulnerability = csaf.Vulnerability(
        cve=vulnerability.cve,
        ids=get_csaf_vulnerability_ids(vulnerability),
        notes=csaf.NotesT(root=[note]),
        product_status=product_status,
        remediations=remediations,
        threats=threats,
    )
    return csaf_vulnerability


def get_csaf_vulnerabilities(product):
    vulnerability_qs = product.get_vulnerability_qs(prefetch_related_packages=True)
    vulnerabilities = [get_csaf_vulnerability(vulnerability) for vulnerability in vulnerability_qs]
    return vulnerabilities


def get_csaf_security_advisory(product):
    security_advisory = csaf.CommonSecurityAdvisoryFramework(
        document=get_csaf_document(product),
        product_tree=get_csaf_product_tree(product),
        vulnerabilities=get_csaf_vulnerabilities(product),
    )
    return security_advisory


def get_openvex_timestamp():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")


def get_openvex_vulnerability(vulnerability):
    return openvex.Vulnerability(
        field_id=vulnerability.resource_url,
        name=vulnerability.vulnerability_id,
        description=vulnerability.summary,
        aliases=vulnerability.aliases,
    )


def get_openvex_statement(vulnerability):
    products = [
        openvex.Component1(field_id=package.package_url)
        for package in vulnerability.affected_packages.all()
    ]

    status = openvex.Status.under_investigation
    vulnerability_analyses = vulnerability.vulnerability_analyses.all()
    if len(vulnerability_analyses) == 1:
        analysis = vulnerability_analyses[0]
        print(analysis)

    return openvex.Statement(
        vulnerability=get_openvex_vulnerability(vulnerability),
        timestamp=get_openvex_timestamp(),
        products=products,
        status=status,
        # status_notes: analysis.detail
        # justification: analysis.justification
    )


def get_openvex_statements(product):
    vulnerability_qs = product.get_vulnerability_qs(prefetch_related_packages=True)
    statements = [get_openvex_statement(vulnerability) for vulnerability in vulnerability_qs]
    return statements


def get_openvex_document(product):
    return openvex.OpenVEX(
        field_context="https://openvex.dev/ns/v0.2.0",
        field_id=f"OpenVEX-Document-{str(product.uuid)}",
        author=product.dataspace.name,
        timestamp=get_openvex_timestamp(),
        version=1,
        tooling=f"DejaCode-{dejacode_version}",
        statements=get_openvex_statements(product),
    )
