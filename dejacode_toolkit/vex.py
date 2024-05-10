import json

from cyclonedx.model.vulnerability import BomTarget
from cyclonedx.model.vulnerability import BomTargetVersionRange
from cyclonedx.model.vulnerability import ImpactAnalysisAffectedStatus
from cyclonedx.model.vulnerability import ImpactAnalysisJustification
from cyclonedx.model.vulnerability import ImpactAnalysisResponse
from cyclonedx.model.vulnerability import ImpactAnalysisState
from cyclonedx.model.vulnerability import Vulnerability
from cyclonedx.model.vulnerability import VulnerabilityAnalysis
from cyclonedx.model.vulnerability import VulnerabilityRating
from cyclonedx.model.vulnerability import VulnerabilityReference
from cyclonedx.model.vulnerability import VulnerabilityScoreSource
from cyclonedx.model.vulnerability import VulnerabilitySeverity
from cyclonedx.model.vulnerability import VulnerabilitySource
from cyclonedx.output.json import SchemaVersion1Dot4
from cyclonedx.output.json import SchemaVersion1Dot5
from cyclonedx.output.json import SchemaVersion1Dot6
from packageurl import PackageURL
from serializable import _SerializableJsonEncoder

from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductPackageVEX

# from cyclonedx.model.vulnerability import VulnerabilityCredits
# from cyclonedx.model.vulnerability import VulnerabilityAdvisory

SCORING_SYSTEMS_CYCLONEDX = {
    "cvssv2": VulnerabilityScoreSource.CVSS_V2,
    "cvssv3": VulnerabilityScoreSource.CVSS_V3,
    "cvssv3.1": VulnerabilityScoreSource.CVSS_V3_1,
    "cvssv4": VulnerabilityScoreSource.CVSS_V4,
    "owasp": VulnerabilityScoreSource.OWASP,
    "ssvc": VulnerabilityScoreSource.SSVC,
    "other": VulnerabilityScoreSource.OTHER,
}

GENERIC_SEVERITIES_VALUE_CYCLONEDX = {
    "none": VulnerabilitySeverity.NONE,
    "info": VulnerabilitySeverity.INFO,
    "low": VulnerabilitySeverity.LOW,
    "meduim": VulnerabilitySeverity.MEDIUM,
    "high": VulnerabilitySeverity.HIGH,
    "critical": VulnerabilitySeverity.CRITICAL,
    "unknow": VulnerabilitySeverity.UNKNOWN,
}

STATUS_VEX_CYCLONEDX = {
    True: ImpactAnalysisAffectedStatus.AFFECTED,
    False: ImpactAnalysisAffectedStatus.UNAFFECTED,
    # "unknow": ImpactAnalysisAffectedStatus.UNKNOWN, default
}

STATE_VEX_CYCLONEDX = {
    "R": ImpactAnalysisState.RESOLVED,
    "RWP": ImpactAnalysisState.RESOLVED_WITH_PEDIGREE,
    "E": ImpactAnalysisState.EXPLOITABLE,
    "IT": ImpactAnalysisState.IN_TRIAGE,
    "FP": ImpactAnalysisState.FALSE_POSITIVE,
    "NA": ImpactAnalysisState.NOT_AFFECTED,
}

JUSTIFICATION_VEX_CYCLONEDX = {
    "CNP": ImpactAnalysisJustification.CODE_NOT_PRESENT,
    "CNR": ImpactAnalysisJustification.CODE_NOT_REACHABLE,
    "PP": ImpactAnalysisJustification.PROTECTED_AT_PERIMITER,
    "PR": ImpactAnalysisJustification.PROTECTED_AT_RUNTIME,
    "PC": ImpactAnalysisJustification.PROTECTED_BY_COMPILER,
    "PMC": ImpactAnalysisJustification.PROTECTED_BY_MITIGATING_CONTROL,
    "RC": ImpactAnalysisJustification.REQUIRES_CONFIGURATION,
    "RD": ImpactAnalysisJustification.REQUIRES_DEPENDENCY,
    "RE": ImpactAnalysisJustification.REQUIRES_ENVIRONMENT,
}

RESPONSES_VEX_CYCLONEDX = {
    "CNF": ImpactAnalysisResponse.CAN_NOT_FIX,
    "RB": ImpactAnalysisResponse.ROLLBACK,
    "U": ImpactAnalysisResponse.UPDATE,
    "WNF": ImpactAnalysisResponse.WILL_NOT_FIX,
    "WA": ImpactAnalysisResponse.WORKAROUND_AVAILABLE,
}


def create_auto_vex(package, vulnerabilities):
    # automatically create a VEX for each product package that has a vulnerability
    vex_objects = []
    vulnerability_ids = []
    for entry in vulnerabilities:
        unresolved = entry.get("affected_by_vulnerabilities", [])
        for vulnerability in unresolved:
            vulnerability_id = vulnerability.get("vulnerability_id")
            if vulnerability_id:
                vulnerability_ids.append(vulnerability_id)

    productpackages = ProductPackage.objects.filter(package=package)
    for productpackage in productpackages:
        for vulnerability_id in vulnerability_ids:
            vex_objects.append(
                ProductPackageVEX(
                    dataspace=productpackage.dataspace,
                    productpackage=productpackage,
                    vulnerability_id=vulnerability_id,
                )
            )

    ProductPackageVEX.objects.bulk_create(vex_objects, ignore_conflicts=True)


def vulnerability_format_vcio_to_cyclonedx(vcio_vulnerability, vex: ProductPackageVEX):
    """Change the VCIO format of the vulnerability to CycloneDX and add the vex vulnerability"""
    vulnerability_source = VulnerabilitySource(
        url=vcio_vulnerability.get("url"),
    )

    references = vcio_vulnerability.get("references") or []
    vulnerability_reference, vulnerability_ratings = get_references_and_rating(references)

    state = STATE_VEX_CYCLONEDX.get(vex.state)
    justification = JUSTIFICATION_VEX_CYCLONEDX.get(vex.justification)

    responses = []
    for vex_res in vex.responses or []:
        response = RESPONSES_VEX_CYCLONEDX.get(vex_res)
        if response:
            responses.append(response)

    vulnerability_analysis = VulnerabilityAnalysis(
        state=state,
        responses=responses,
        justification=justification,
        detail=vex.detail,
    )

    # vulnerability_advisory = VulnerabilityAdvisory()  # ignore
    # vulnerability_credits = VulnerabilityCredits()  # ignore

    # property = Property()  # ignore
    # tool = Tool()  # ignore

    bom_targets = []
    versions = []
    for affected_fixed_package in (
        vcio_vulnerability.get("affected_packages") + vcio_vulnerability.get("fixed_packages") or []
    ):
        is_vulnerable = affected_fixed_package.get("is_vulnerable")
        status = STATUS_VEX_CYCLONEDX.get(is_vulnerable, ImpactAnalysisAffectedStatus.UNKNOWN)
        purl_string = affected_fixed_package.get("purl")

        vul_purl = None
        if purl_string:
            vul_purl = PackageURL.from_string(purl_string)
            versions.append(BomTargetVersionRange(version=vul_purl.version, status=status))

    if versions:
        bom_target = BomTarget(ref=vex.productpackage.package.package_url, versions=versions)
        bom_targets.append(bom_target)

    weaknesses = vcio_vulnerability.get("weaknesses") or []
    cwes = get_cwes(weaknesses)

    vulnerability = Vulnerability(
        id=vcio_vulnerability.get("vulnerability_id"),
        source=vulnerability_source,
        references=vulnerability_reference,
        ratings=vulnerability_ratings,
        cwes=cwes,
        description=vcio_vulnerability.get("summary") or "",
        analysis=vulnerability_analysis,
        affects=bom_targets,
        # bom_ref="",
        # detail=detail,
        # recommendation="",
        # advisories=advisories,
        # created=created,
        # published=published,
        # updated=updated,
        # credits=credits,
        # tools=tools,
        # properties=properties,
        # Deprecated Parameters kept for backwards compatibility
        # source_name=source_name,
        # source_url=source_url,
        # recommendations=recommendations,
    )
    return vulnerability


def get_cwes(weaknesses):
    """
    Get the list of cwes number using vulnerability weaknesses
    >>> get_cwes([{"cwe_id": 613,"name": "..."}]})
    [613]
    >>> get_cwes([{"cwe_id": 613,"name": "..."}, {"cwe_id": 79,"name": "..."}])
    [613, 79]
    >>> get_cwes([])
    []
    """
    cwes = []
    for weakness in weaknesses:
        cwe_id = weakness.get("cwe_id")
        if cwe_id:
            cwes.append(cwe_id)
    return cwes


def is_float(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def get_references_and_rating(references):
    cyclonedx_references, cyclonedx_rating = [], []
    for ref in references:
        source = VulnerabilitySource(url=ref.get("url"))
        cyclonedx_references.append(
            VulnerabilityReference(id=ref.get("reference_id"), source=source)
        )

        for score in ref.get("scores") or []:
            vul_source = VulnerabilitySource(url=ref.get("reference_url"))

            value = score.get("value")
            scoring_system = score.get("scoring_system")
            vector = score.get("scoring_elements")

            vul_severity = None
            if scoring_system in SCORING_SYSTEMS_CYCLONEDX:
                vul_method = SCORING_SYSTEMS_CYCLONEDX.get(scoring_system)

            if value.lower() in GENERIC_SEVERITIES_VALUE_CYCLONEDX:
                vul_method = SCORING_SYSTEMS_CYCLONEDX.get(scoring_system)
                vul_severity = GENERIC_SEVERITIES_VALUE_CYCLONEDX.get(value.lower())

            vul_rating = VulnerabilityRating(
                source=vul_source,
                score=float(value) if is_float(value) else None,
                severity=vul_severity,
                method=vul_method,
                vector=vector,
            )
            cyclonedx_rating.append(vul_rating)

    return cyclonedx_references, cyclonedx_rating


def get_vex_document(vcio_vulnerabilities, vexs, spec_version="1.4", version=1):
    schema_version = {
        "1.4": SchemaVersion1Dot4,
        "1.5": SchemaVersion1Dot5,
        "1.6": SchemaVersion1Dot6,
    }.get(spec_version, SchemaVersion1Dot4)

    vulnerabilities = []
    if len(vcio_vulnerabilities) != len(vexs):
        raise KeyError("Invalid number of vulnerabilities or vexs")

    for vcio_vulnerability, vex in zip(vcio_vulnerabilities, vexs):
        if not (vcio_vulnerability and vex):
            continue
        cyclonedx_vulnerability = vulnerability_format_vcio_to_cyclonedx(vcio_vulnerability, vex)
        vulnerabilities.append(
            json.loads(
                json.dumps(
                    cyclonedx_vulnerability,
                    cls=_SerializableJsonEncoder,
                    view_=schema_version,
                )
            )
        )

    return json.dumps(
        {
            "bomFormat": "CycloneDX",
            "specVersion": spec_version,
            "version": version,
            "vulnerabilities": vulnerabilities,
        }
    )
