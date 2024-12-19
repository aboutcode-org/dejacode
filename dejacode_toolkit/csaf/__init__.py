#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List
from typing import Optional
from typing import Union

from pydantic import AnyUrl
from pydantic import BaseModel
from pydantic import Field
from pydantic import RootModel
from pydantic import confloat
from pydantic import constr

# from . import cvss_v2
# from . import cvss_v3


class AggregateSeverity(BaseModel):
    """
    Is a vehicle that is provided by the document producer to convey the urgency and criticality with which the one or more vulnerabilities reported should be addressed. It is a document-level metric and applied to the document as a whole — not any specific vulnerability. The range of values in this field is defined according to the document producer's policies and procedures.
    """

    namespace: Optional[AnyUrl] = Field(
        default=None,
        description="Points to the namespace so referenced.",
        title="Namespace of aggregate severity",
    )
    text: constr(min_length=1) = Field(
        ...,
        description="Provides a severity which is independent of - and in addition to - any other standard metric for determining the impact or severity of a given vulnerability (such as CVSS).",
        examples=["Critical", "Important", "Moderate"],
        title="Text of aggregate severity",
    )


class CsafVersion(Enum):
    """
    Gives the version of the CSAF specification which the document was generated for.
    """

    field_2_0 = "2.0"


class Label(Enum):
    """
    Provides the TLP label of the document.
    """

    AMBER = "AMBER"
    GREEN = "GREEN"
    RED = "RED"
    WHITE = "WHITE"


class Tlp(BaseModel):
    """
    Provides details about the TLP classification of the document.
    """

    label: Label = Field(
        ..., description="Provides the TLP label of the document.", title="Label of TLP"
    )
    url: Optional[AnyUrl] = Field(
        default="https://www.first.org/tlp/",
        description="Provides a URL where to find the textual description of the TLP version which is used in this document. Default is the URL to the definition by FIRST.",
        examples=[
            "https://www.us-cert.gov/tlp",
            "https://www.bsi.bund.de/SharedDocs/Downloads/DE/BSI/Kritis/Merkblatt_TLP.pdf",
        ],
        title="URL of TLP version",
    )


class Distribution(BaseModel):
    """
    Describe any constraints on how this document might be shared.
    """

    text: Optional[constr(min_length=1)] = Field(
        default=None,
        description="Provides a textual description of additional constraints.",
        examples=[
            "Copyright 2021, Example Company, All Rights Reserved.",
            "Distribute freely.",
            "Share only on a need-to-know-basis only.",
        ],
        title="Textual description",
    )
    tlp: Optional[Tlp] = Field(
        default=None,
        description="Provides details about the TLP classification of the document.",
        title="Traffic Light Protocol (TLP)",
    )


class Category(Enum):
    """
    Provides information about the category of publisher releasing the document.
    """

    coordinator = "coordinator"
    discoverer = "discoverer"
    other = "other"
    translator = "translator"
    user = "user"
    vendor = "vendor"


class Publisher(BaseModel):
    """
    Provides information about the publisher of the document.
    """

    category: Category = Field(
        ...,
        description="Provides information about the category of publisher releasing the document.",
        title="Category of publisher",
    )
    contact_details: Optional[constr(min_length=1)] = Field(
        default=None,
        description="Information on how to contact the publisher, possibly including details such as web sites, email addresses, phone numbers, and postal mail addresses.",
        examples=[
            "Example Company can be reached at contact_us@example.com, or via our website at https://www.example.com/contact."
        ],
        title="Contact details",
    )
    issuing_authority: Optional[constr(min_length=1)] = Field(
        default=None,
        description="Provides information about the authority of the issuing party to release the document, in particular, the party's constituency and responsibilities or other obligations.",
        title="Issuing authority",
    )
    name: constr(min_length=1) = Field(
        ...,
        description="Contains the name of the issuing party.",
        examples=["BSI", "Cisco PSIRT", "Siemens ProductCERT"],
        title="Name of publisher",
    )
    namespace: AnyUrl = Field(
        ...,
        description="Contains a URL which is under control of the issuing party and can be used as a globally unique identifier for that issuing party.",
        examples=["https://csaf.io", "https://www.example.com"],
        title="Namespace of publisher",
    )


class Alias(RootModel[constr(min_length=1)]):
    root: constr(min_length=1) = Field(
        ...,
        description="Specifies a non-empty string that represents a distinct optional alternative ID used to refer to the document.",
        examples=["CVE-2019-12345"],
        title="Alternate name",
    )


class Engine(BaseModel):
    """
    Contains information about the engine that generated the CSAF document.
    """

    name: constr(min_length=1) = Field(
        ...,
        description="Represents the name of the engine that generated the CSAF document.",
        examples=["Red Hat rhsa-to-cvrf", "Secvisogram", "TVCE"],
        title="Engine name",
    )
    version: Optional[constr(min_length=1)] = Field(
        default=None,
        description="Contains the version of the engine that generated the CSAF document.",
        examples=["0.6.0", "1.0.0-beta+exp.sha.a1c44f85", "2"],
        title="Engine version",
    )


class Generator(BaseModel):
    """
    Is a container to hold all elements related to the generation of the document. These items will reference when the document was actually created, including the date it was generated and the entity that generated it.
    """

    date: Optional[datetime] = Field(
        default=None,
        description="This SHOULD be the current date that the document was generated. Because documents are often generated internally by a document producer and exist for a nonzero amount of time before being released, this field MAY be different from the Initial Release Date and Current Release Date.",
        title="Date of document generation",
    )
    engine: Engine = Field(
        ...,
        description="Contains information about the engine that generated the CSAF document.",
        title="Engine of document generation",
    )


class Status(Enum):
    """
    Defines the draft status of the document.
    """

    draft = "draft"
    final = "final"
    interim = "interim"


class Category1(Enum):
    """
    Defines the category of relationship for the referenced component.
    """

    default_component_of = "default_component_of"
    external_component_of = "external_component_of"
    installed_on = "installed_on"
    installed_with = "installed_with"
    optional_component_of = "optional_component_of"


class Cwe(BaseModel):
    """
    Holds the MITRE standard Common Weakness Enumeration (CWE) for the weakness associated.
    """

    id: constr(pattern=r"^CWE-[1-9]\d{0,5}$") = Field(
        ...,
        description="Holds the ID for the weakness associated.",
        examples=["CWE-22", "CWE-352", "CWE-79"],
        title="Weakness ID",
    )
    name: constr(min_length=1) = Field(
        ...,
        description="Holds the full name of the weakness as given in the CWE specification.",
        examples=[
            "Cross-Site Request Forgery (CSRF)",
            "Improper Limitation of a Pathname to a Restricted Directory ('Path Traversal')",
            "Improper Neutralization of Input During Web Page Generation ('Cross-site Scripting')",
        ],
        title="Weakness name",
    )


class Label1(Enum):
    """
    Specifies the machine readable label.
    """

    component_not_present = "component_not_present"
    inline_mitigations_already_exist = "inline_mitigations_already_exist"
    vulnerable_code_cannot_be_controlled_by_adversary = (
        "vulnerable_code_cannot_be_controlled_by_adversary"
    )
    vulnerable_code_not_in_execute_path = "vulnerable_code_not_in_execute_path"
    vulnerable_code_not_present = "vulnerable_code_not_present"


class Id(BaseModel):
    """
    Contains a single unique label or tracking ID for the vulnerability.
    """

    system_name: constr(min_length=1) = Field(
        ...,
        description="Indicates the name of the vulnerability tracking or numbering system.",
        examples=["Cisco Bug ID", "GitHub Issue"],
        title="System name",
    )
    text: constr(min_length=1) = Field(
        ...,
        description="Is unique label or tracking ID for the vulnerability (if such information exists).",
        examples=["CSCso66472", "oasis-tcs/csaf#210"],
        title="Text",
    )


class Party(Enum):
    """
    Defines the category of the involved party.
    """

    coordinator = "coordinator"
    discoverer = "discoverer"
    other = "other"
    user = "user"
    vendor = "vendor"


class Status1(Enum):
    """
    Defines contact status of the involved party.
    """

    completed = "completed"
    contact_attempted = "contact_attempted"
    disputed = "disputed"
    in_progress = "in_progress"
    not_contacted = "not_contacted"
    open = "open"


class Involvement(BaseModel):
    """
    Is a container, that allows the document producers to comment on the level of involvement (or engagement) of themselves or third parties in the vulnerability identification, scoping, and remediation process.
    """

    date: Optional[datetime] = Field(
        default=None,
        description="Holds the date and time of the involvement entry.",
        title="Date of involvement",
    )
    party: Party = Field(
        ...,
        description="Defines the category of the involved party.",
        title="Party category",
    )
    status: Status1 = Field(
        ...,
        description="Defines contact status of the involved party.",
        title="Party status",
    )
    summary: Optional[constr(min_length=1)] = Field(
        default=None,
        description="Contains additional context regarding what is going on.",
        title="Summary of the involvement",
    )


class Category2(Enum):
    """
    Specifies the category which this remediation belongs to.
    """

    mitigation = "mitigation"
    no_fix_planned = "no_fix_planned"
    none_available = "none_available"
    vendor_fix = "vendor_fix"
    workaround = "workaround"


class Entitlement(RootModel[constr(min_length=1)]):
    root: constr(min_length=1) = Field(
        ...,
        description="Contains any possible vendor-defined constraints for obtaining fixed software or hardware that fully resolves the vulnerability.",
        title="Entitlement of the remediation",
    )


class Category3(Enum):
    """
    Specifies what category of restart is required by this remediation to become effective.
    """

    connected = "connected"
    dependencies = "dependencies"
    machine = "machine"
    none = "none"
    parent = "parent"
    service = "service"
    system = "system"
    vulnerable_component = "vulnerable_component"
    zone = "zone"


class RestartRequired(BaseModel):
    """
    Provides information on category of restart is required by this remediation to become effective.
    """

    category: Category3 = Field(
        ...,
        description="Specifies what category of restart is required by this remediation to become effective.",
        title="Category of restart",
    )
    details: Optional[constr(min_length=1)] = Field(
        default=None,
        description="Provides additional information for the restart. This can include details on procedures, scope or impact.",
        title="Additional restart information",
    )


class Category4(Enum):
    """
    Categorizes the threat according to the rules of the specification.
    """

    exploit_status = "exploit_status"
    impact = "impact"
    target_set = "target_set"


class AccessVectorType(Enum):
    NETWORK = "NETWORK"
    ADJACENT_NETWORK = "ADJACENT_NETWORK"
    LOCAL = "LOCAL"


class AccessComplexityType(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AuthenticationType(Enum):
    MULTIPLE = "MULTIPLE"
    SINGLE = "SINGLE"
    NONE = "NONE"


class CiaType(Enum):
    NONE = "NONE"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"


class ExploitabilityType(Enum):
    UNPROVEN = "UNPROVEN"
    PROOF_OF_CONCEPT = "PROOF_OF_CONCEPT"
    FUNCTIONAL = "FUNCTIONAL"
    HIGH = "HIGH"
    NOT_DEFINED = "NOT_DEFINED"


class RemediationLevelType(Enum):
    OFFICIAL_FIX = "OFFICIAL_FIX"
    TEMPORARY_FIX = "TEMPORARY_FIX"
    WORKAROUND = "WORKAROUND"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_DEFINED = "NOT_DEFINED"


class ReportConfidenceType(Enum):
    UNCONFIRMED = "UNCONFIRMED"
    UNCORROBORATED = "UNCORROBORATED"
    CONFIRMED = "CONFIRMED"
    NOT_DEFINED = "NOT_DEFINED"


class CollateralDamagePotentialType(Enum):
    NONE = "NONE"
    LOW = "LOW"
    LOW_MEDIUM = "LOW_MEDIUM"
    MEDIUM_HIGH = "MEDIUM_HIGH"
    HIGH = "HIGH"
    NOT_DEFINED = "NOT_DEFINED"


class TargetDistributionType(Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    NOT_DEFINED = "NOT_DEFINED"


class CiaRequirementType(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    NOT_DEFINED = "NOT_DEFINED"


class ScoreType(RootModel[confloat(ge=0.0, le=10.0)]):
    root: confloat(ge=0.0, le=10.0)


class AttackVectorType(Enum):
    NETWORK = "NETWORK"
    ADJACENT_NETWORK = "ADJACENT_NETWORK"
    LOCAL = "LOCAL"
    PHYSICAL = "PHYSICAL"


class ModifiedAttackVectorType(Enum):
    NETWORK = "NETWORK"
    ADJACENT_NETWORK = "ADJACENT_NETWORK"
    LOCAL = "LOCAL"
    PHYSICAL = "PHYSICAL"
    NOT_DEFINED = "NOT_DEFINED"


class AttackComplexityType(Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class ModifiedAttackComplexityType(Enum):
    HIGH = "HIGH"
    LOW = "LOW"
    NOT_DEFINED = "NOT_DEFINED"


class PrivilegesRequiredType(Enum):
    HIGH = "HIGH"
    LOW = "LOW"
    NONE = "NONE"


class ModifiedPrivilegesRequiredType(Enum):
    HIGH = "HIGH"
    LOW = "LOW"
    NONE = "NONE"
    NOT_DEFINED = "NOT_DEFINED"


class UserInteractionType(Enum):
    NONE = "NONE"
    REQUIRED = "REQUIRED"


class ModifiedUserInteractionType(Enum):
    NONE = "NONE"
    REQUIRED = "REQUIRED"
    NOT_DEFINED = "NOT_DEFINED"


class ScopeType(Enum):
    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"


class ModifiedScopeType(Enum):
    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"
    NOT_DEFINED = "NOT_DEFINED"


class CiaTypeModel(Enum):
    NONE = "NONE"
    LOW = "LOW"
    HIGH = "HIGH"


class ModifiedCiaType(Enum):
    NONE = "NONE"
    LOW = "LOW"
    HIGH = "HIGH"
    NOT_DEFINED = "NOT_DEFINED"


class ExploitCodeMaturityType(Enum):
    UNPROVEN = "UNPROVEN"
    PROOF_OF_CONCEPT = "PROOF_OF_CONCEPT"
    FUNCTIONAL = "FUNCTIONAL"
    HIGH = "HIGH"
    NOT_DEFINED = "NOT_DEFINED"


class ConfidenceType(Enum):
    UNKNOWN = "UNKNOWN"
    REASONABLE = "REASONABLE"
    CONFIRMED = "CONFIRMED"
    NOT_DEFINED = "NOT_DEFINED"


class SeverityType(Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Name(RootModel[constr(min_length=1)]):
    root: constr(min_length=1) = Field(
        ...,
        description="Contains the name of a single contributor being recognized.",
        examples=["Albert Einstein", "Johann Sebastian Bach"],
        title="Name of the contributor",
    )


class AcknowledgmentsTItem(BaseModel):
    """
    Acknowledges contributions by describing those that contributed.
    """

    names: Optional[List[Name]] = Field(
        default=None,
        description="Contains the names of contributors being recognized.",
        min_length=1,
        title="List of acknowledged names",
    )
    organization: Optional[constr(min_length=1)] = Field(
        default=None,
        description="Contains the name of a contributing organization being recognized.",
        examples=["CISA", "Google Project Zero", "Talos"],
        title="Contributing organization",
    )
    summary: Optional[constr(min_length=1)] = Field(
        default=None,
        description="SHOULD represent any contextual details the document producers wish to make known about the acknowledgment or acknowledged parties.",
        examples=["First analysis of Coordinated Multi-Stream Attack (CMSA)"],
        title="Summary of the acknowledgment",
    )
    urls: Optional[List[AnyUrl]] = Field(
        default=None,
        description="Specifies a list of URLs or location of the reference to be acknowledged.",
        title="List of URLs",
    )


class AcknowledgmentsT(RootModel[List[AcknowledgmentsTItem]]):
    """
    Contains a list of acknowledgment elements.
    """

    root: List[AcknowledgmentsTItem] = Field(
        ...,
        description="Contains a list of acknowledgment elements.",
        min_length=1,
        title="List of acknowledgments",
    )


class Category5(Enum):
    """
    Describes the characteristics of the labeled branch.
    """

    architecture = "architecture"
    host_name = "host_name"
    language = "language"
    legacy = "legacy"
    patch_level = "patch_level"
    product_family = "product_family"
    product_name = "product_name"
    product_version = "product_version"
    product_version_range = "product_version_range"
    service_pack = "service_pack"
    specification = "specification"
    vendor = "vendor"


class FileHash(BaseModel):
    """
    Contains one hash value and algorithm of the file to be identified.
    """

    algorithm: constr(min_length=1) = Field(
        ...,
        description="Contains the name of the cryptographic hash algorithm used to calculate the value.",
        examples=["blake2b512", "sha256", "sha3-512", "sha384", "sha512"],
        title="Algorithm of the cryptographic hash",
    )
    value: constr(pattern=r"^[0-9a-fA-F]{32,}$", min_length=32) = Field(
        ...,
        description="Contains the cryptographic hash value in hexadecimal representation.",
        examples=[
            "37df33cb7464da5c7f077f4d56a32bc84987ec1d85b234537c1c1a4d4fc8d09dc29e2e762cb5203677bf849a2855a0283710f1f5fe1d6ce8d5ac85c645d0fcb3",
            "4775203615d9534a8bfca96a93dc8b461a489f69124a130d786b42204f3341cc",
            "9ea4c8200113d49d26505da0e02e2f49055dc078d1ad7a419b32e291c7afebbb84badfbd46dec42883bea0b2a1fa697c",
        ],
        title="Value of the cryptographic hash",
    )


class Hash(BaseModel):
    """
    Contains all information to identify a file based on its cryptographic hash values.
    """

    file_hashes: List[FileHash] = Field(
        ...,
        description="Contains a list of cryptographic hashes for this file.",
        min_length=1,
        title="List of file hashes",
    )
    filename: constr(min_length=1) = Field(
        ...,
        description="Contains the name of the file which is identified by the hash values.",
        examples=["WINWORD.EXE", "msotadddin.dll", "sudoers.so"],
        title="Filename",
    )


class ModelNumber(RootModel[constr(min_length=1)]):
    root: constr(min_length=1) = Field(
        ...,
        description="Contains a full or abbreviated (partial) model number of the component to identify.",
        title="Model number",
    )


class SerialNumber(RootModel[constr(min_length=1)]):
    root: constr(min_length=1) = Field(
        ...,
        description="Contains a full or abbreviated (partial) serial number of the component to identify.",
        title="Serial number",
    )


class Sku(RootModel[constr(min_length=1)]):
    root: constr(min_length=1) = Field(
        ...,
        description="Contains a full or abbreviated (partial) stock keeping unit (SKU) which is used in the ordering process to identify the component.",
        title="Stock keeping unit",
    )


class XGenericUri(BaseModel):
    """
    Provides a generic extension point for any identifier which is either vendor-specific or derived from a standard not yet supported.
    """

    namespace: AnyUrl = Field(
        ...,
        description="Refers to a URL which provides the name and knowledge about the specification used or is the namespace in which these values are valid.",
        title="Namespace of the generic URI",
    )
    uri: AnyUrl = Field(..., description="Contains the identifier itself.", title="URI")


class ProductIdentificationHelper(BaseModel):
    """
    Provides at least one method which aids in identifying the product in an asset database.
    """

    cpe: Optional[
        constr(
            pattern=r'^(cpe:2\.3:[aho\*\-](:(((\?*|\*?)([a-zA-Z0-9\-\._]|(\\[\\\*\?!"#\$%&\'\(\)\+,/:;<=>@\[\]\^`\{\|\}~]))+(\?*|\*?))|[\*\-])){5}(:(([a-zA-Z]{2,3}(-([a-zA-Z]{2}|[0-9]{3}))?)|[\*\-]))(:(((\?*|\*?)([a-zA-Z0-9\-\._]|(\\[\\\*\?!"#\$%&\'\(\)\+,/:;<=>@\[\]\^`\{\|\}~]))+(\?*|\*?))|[\*\-])){4})|([c][pP][eE]:/[AHOaho]?(:[A-Za-z0-9\._\-~%]*){0,6})$',
            min_length=5,
        )
    ] = Field(
        default=None,
        description="The Common Platform Enumeration (CPE) attribute refers to a method for naming platforms external to this specification.",
        title="Common Platform Enumeration representation",
    )
    hashes: Optional[List[Hash]] = Field(
        default=None,
        description="Contains a list of cryptographic hashes usable to identify files.",
        min_length=1,
        title="List of hashes",
    )
    model_numbers: Optional[List[ModelNumber]] = Field(
        default=None,
        description="Contains a list of full or abbreviated (partial) model numbers.",
        min_length=1,
        title="List of models",
    )
    purl: Optional[AnyUrl] = Field(
        default=None,
        description="The package URL (purl) attribute refers to a method for reliably identifying and locating software packages external to this specification.",
        title="package URL representation",
    )
    sbom_urls: Optional[List[AnyUrl]] = Field(
        default=None,
        description="Contains a list of URLs where SBOMs for this product can be retrieved.",
        title="List of SBOM URLs",
    )
    serial_numbers: Optional[List[SerialNumber]] = Field(
        default=None,
        description="Contains a list of full or abbreviated (partial) serial numbers.",
        min_length=1,
        title="List of serial numbers",
    )
    skus: Optional[List[Sku]] = Field(
        default=None,
        description="Contains a list of full or abbreviated (partial) stock keeping units.",
        min_length=1,
        title="List of stock keeping units",
    )
    x_generic_uris: Optional[List[XGenericUri]] = Field(
        default=None,
        description="Contains a list of identifiers which are either vendor-specific or derived from a standard not yet supported.",
        min_length=1,
        title="List of generic URIs",
    )


class LangT(
    RootModel[
        constr(
            pattern=r"^(([A-Za-z]{2,3}(-[A-Za-z]{3}(-[A-Za-z]{3}){0,2})?|[A-Za-z]{4,8})(-[A-Za-z]{4})?(-([A-Za-z]{2}|[0-9]{3}))?(-([A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3}))*(-[A-WY-Za-wy-z0-9](-[A-Za-z0-9]{2,8})+)*(-[Xx](-[A-Za-z0-9]{1,8})+)?|[Xx](-[A-Za-z0-9]{1,8})+|[Ii]-[Dd][Ee][Ff][Aa][Uu][Ll][Tt]|[Ii]-[Mm][Ii][Nn][Gg][Oo])$"
        )
    ]
):
    root: constr(
        pattern=r"^(([A-Za-z]{2,3}(-[A-Za-z]{3}(-[A-Za-z]{3}){0,2})?|[A-Za-z]{4,8})(-[A-Za-z]{4})?(-([A-Za-z]{2}|[0-9]{3}))?(-([A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3}))*(-[A-WY-Za-wy-z0-9](-[A-Za-z0-9]{2,8})+)*(-[Xx](-[A-Za-z0-9]{1,8})+)?|[Xx](-[A-Za-z0-9]{1,8})+|[Ii]-[Dd][Ee][Ff][Aa][Uu][Ll][Tt]|[Ii]-[Mm][Ii][Nn][Gg][Oo])$"
    ) = Field(
        ...,
        description="Identifies a language, corresponding to IETF BCP 47 / RFC 5646. See IETF language registry: https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry",
        examples=["de", "en", "fr", "frc", "jp"],
        title="Language type",
    )


class Category6(Enum):
    """
    Contains the information of what kind of note this is.
    """

    description = "description"
    details = "details"
    faq = "faq"
    general = "general"
    legal_disclaimer = "legal_disclaimer"
    other = "other"
    summary = "summary"


class NotesTItem(BaseModel):
    """
    Is a place to put all manner of text blobs related to the current context.
    """

    audience: Optional[constr(min_length=1)] = Field(
        default=None,
        description="Indicates who is intended to read it.",
        examples=[
            "all",
            "executives",
            "operational management and system administrators",
            "safety engineers",
        ],
        title="Audience of note",
    )
    category: Category6 = Field(
        ...,
        description="Contains the information of what kind of note this is.",
        title="Note category",
    )
    text: constr(min_length=1) = Field(
        ...,
        description="Holds the content of the note. Content varies depending on type.",
        title="Note content",
    )
    title: Optional[constr(min_length=1)] = Field(
        default=None,
        description="Provides a concise description of what is contained in the text of the note.",
        examples=[
            "Details",
            "Executive summary",
            "Technical summary",
            "Impact on safety systems",
        ],
        title="Title of note",
    )


class NotesT(RootModel[List[NotesTItem]]):
    """
    Contains notes which are specific to the current context.
    """

    root: List[NotesTItem] = Field(
        ...,
        description="Contains notes which are specific to the current context.",
        min_length=1,
        title="List of notes",
    )


class ProductGroupIdT(RootModel[constr(min_length=1)]):
    root: constr(min_length=1) = Field(
        ...,
        description="Token required to identify a group of products so that it can be referred to from other parts in the document. There is no predefined or required format for the product_group_id as long as it uniquely identifies a group in the context of the current document.",
        examples=["CSAFGID-0001", "CSAFGID-0002", "CSAFGID-0020"],
        title="Reference token for product group instance",
    )


class ProductGroupsT(RootModel[List[ProductGroupIdT]]):
    """
    Specifies a list of product_group_ids to give context to the parent item.
    """

    root: List[ProductGroupIdT] = Field(
        ...,
        description="Specifies a list of product_group_ids to give context to the parent item.",
        min_length=1,
        title="List of product_group_ids",
    )


class ProductIdT(RootModel[constr(min_length=1)]):
    root: constr(min_length=1) = Field(
        ...,
        description="Token required to identify a full_product_name so that it can be referred to from other parts in the document. There is no predefined or required format for the product_id as long as it uniquely identifies a product in the context of the current document.",
        examples=["CSAFPID-0004", "CSAFPID-0008"],
        title="Reference token for product instance",
    )


class ProductsT(RootModel[List[ProductIdT]]):
    """
    Specifies a list of product_ids to give context to the parent item.
    """

    root: List[ProductIdT] = Field(
        ...,
        description="Specifies a list of product_ids to give context to the parent item.",
        min_length=1,
        title="List of product_ids",
    )


class Category7(Enum):
    """
    Indicates whether the reference points to the same document or vulnerability in focus (depending on scope) or to an external resource.
    """

    external = "external"
    self = "self"


class ReferencesTItem(BaseModel):
    """
    Holds any reference to conferences, papers, advisories, and other resources that are related and considered related to either a surrounding part of or the entire document and to be of value to the document consumer.
    """

    category: Optional[Category7] = Field(
        default="external",
        description="Indicates whether the reference points to the same document or vulnerability in focus (depending on scope) or to an external resource.",
        title="Category of reference",
    )
    summary: constr(min_length=1) = Field(
        ...,
        description="Indicates what this reference refers to.",
        title="Summary of the reference",
    )
    url: AnyUrl = Field(
        ..., description="Provides the URL for the reference.", title="URL of reference"
    )


class ReferencesT(RootModel[List[ReferencesTItem]]):
    """
    Holds a list of references.
    """

    root: List[ReferencesTItem] = Field(
        ...,
        description="Holds a list of references.",
        min_length=1,
        title="List of references",
    )


class VersionT(
    RootModel[
        constr(
            pattern=r"^(0|[1-9][0-9]*)$|^((0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?)$"
        )
    ]
):
    root: constr(
        pattern=r"^(0|[1-9][0-9]*)$|^((0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?)$"
    ) = Field(
        ...,
        description="Specifies a version string to denote clearly the evolution of the content of the document. Format must be either integer or semantic versioning.",
        examples=["1", "4", "0.9.0", "1.4.3", "2.40.0+21AF26D3"],
        title="Version",
    )


class RevisionHistoryItem(BaseModel):
    """
    Contains all the information elements required to track the evolution of a CSAF document.
    """

    date: datetime = Field(
        ..., description="The date of the revision entry", title="Date of the revision"
    )
    legacy_version: Optional[constr(min_length=1)] = Field(
        default=None,
        description="Contains the version string used in an existing document with the same content.",
        title="Legacy version of the revision",
    )
    number: VersionT
    summary: constr(min_length=1) = Field(
        ...,
        description="Holds a single non-empty string representing a short description of the changes.",
        examples=["Initial version."],
        title="Summary of the revision",
    )


class Tracking(BaseModel):
    """
    Is a container designated to hold all management attributes necessary to track a CSAF document as a whole.
    """

    aliases: Optional[List[Alias]] = Field(
        default=None,
        description="Contains a list of alternate names for the same document.",
        min_length=1,
        title="Aliases",
    )
    current_release_date: datetime = Field(
        ...,
        description="The date when the current revision of this document was released",
        title="Current release date",
    )
    generator: Optional[Generator] = Field(
        default=None,
        description="Is a container to hold all elements related to the generation of the document. These items will reference when the document was actually created, including the date it was generated and the entity that generated it.",
        title="Document generator",
    )
    id: constr(pattern=r"^[\S](.*[\S])?$", min_length=1) = Field(
        ...,
        description="The ID is a simple label that provides for a wide range of numbering values, types, and schemes. Its value SHOULD be assigned and maintained by the original document issuing authority.",
        examples=[
            "Example Company - 2019-YH3234",
            "RHBA-2019:0024",
            "cisco-sa-20190513-secureboot",
        ],
        title="Unique identifier for the document",
    )
    initial_release_date: datetime = Field(
        ...,
        description="The date when this document was first published.",
        title="Initial release date",
    )
    revision_history: List[RevisionHistoryItem] = Field(
        ...,
        description="Holds one revision item for each version of the CSAF document, including the initial one.",
        min_length=1,
        title="Revision history",
    )
    status: Status = Field(
        ...,
        description="Defines the draft status of the document.",
        title="Document status",
    )
    version: VersionT


class Document(BaseModel):
    """
    Captures the meta-data about this document describing a particular set of security advisories.
    """

    acknowledgments: Optional[AcknowledgmentsT] = Field(
        default=None,
        description="Contains a list of acknowledgment elements associated with the whole document.",
        title="Document acknowledgments",
    )
    aggregate_severity: Optional[AggregateSeverity] = Field(
        default=None,
        description="Is a vehicle that is provided by the document producer to convey the urgency and criticality with which the one or more vulnerabilities reported should be addressed. It is a document-level metric and applied to the document as a whole — not any specific vulnerability. The range of values in this field is defined according to the document producer's policies and procedures.",
        title="Aggregate severity",
    )
    category: constr(pattern=r"^[^\s\-_\.](.*[^\s\-_\.])?$", min_length=1) = Field(
        ...,
        description="Defines a short canonical name, chosen by the document producer, which will inform the end user as to the category of document.",
        examples=[
            "csaf_base",
            "csaf_security_advisory",
            "csaf_vex",
            "Example Company Security Notice",
        ],
        title="Document category",
    )
    csaf_version: CsafVersion = Field(
        ...,
        description="Gives the version of the CSAF specification which the document was generated for.",
        title="CSAF version",
    )
    distribution: Optional[Distribution] = Field(
        default=None,
        description="Describe any constraints on how this document might be shared.",
        title="Rules for sharing document",
    )
    lang: Optional[LangT] = Field(
        default=None,
        description="Identifies the language used by this document, corresponding to IETF BCP 47 / RFC 5646.",
        title="Document language",
    )
    notes: Optional[NotesT] = Field(
        default=None,
        description="Holds notes associated with the whole document.",
        title="Document notes",
    )
    publisher: Publisher = Field(
        ...,
        description="Provides information about the publisher of the document.",
        title="Publisher",
    )
    references: Optional[ReferencesT] = Field(
        default=None,
        description="Holds a list of references associated with the whole document.",
        title="Document references",
    )
    source_lang: Optional[LangT] = Field(
        default=None,
        description="If this copy of the document is a translation then the value of this property describes from which language this document was translated.",
        title="Source language",
    )
    title: constr(min_length=1) = Field(
        ...,
        description="This SHOULD be a canonical name for the document, and sufficiently unique to distinguish it from similar documents.",
        examples=[
            "Cisco IPv6 Crafted Packet Denial of Service Vulnerability",
            "Example Company Cross-Site-Scripting Vulnerability in Example Generator",
        ],
        title="Title of this document",
    )
    tracking: Tracking = Field(
        ...,
        description="Is a container designated to hold all management attributes necessary to track a CSAF document as a whole.",
        title="Tracking",
    )


class ProductGroup(BaseModel):
    """
    Defines a new logical group of products that can then be referred to in other parts of the document to address a group of products with a single identifier.
    """

    group_id: ProductGroupIdT
    product_ids: List[ProductIdT] = Field(
        ...,
        description="Lists the product_ids of those products which known as one group in the document.",
        min_length=2,
        title="List of Product IDs",
    )
    summary: Optional[constr(min_length=1)] = Field(
        default=None,
        description="Gives a short, optional description of the group.",
        examples=[
            "Products supporting Modbus.",
            "The x64 versions of the operating system.",
        ],
        title="Summary of the product group",
    )


class Flag(BaseModel):
    """
    Contains product specific information in regard to this vulnerability as a single machine readable flag.
    """

    date: Optional[datetime] = Field(
        default=None,
        description="Contains the date when assessment was done or the flag was assigned.",
        title="Date of the flag",
    )
    group_ids: Optional[ProductGroupsT] = None
    label: Label1 = Field(
        ...,
        description="Specifies the machine readable label.",
        title="Label of the flag",
    )
    product_ids: Optional[ProductsT] = None


class ProductStatus(BaseModel):
    """
    Contains different lists of product_ids which provide details on the status of the referenced product related to the current vulnerability.
    """

    first_affected: Optional[ProductsT] = Field(
        default=None,
        description="These are the first versions of the releases known to be affected by the vulnerability.",
        title="First affected",
    )
    first_fixed: Optional[ProductsT] = Field(
        default=None,
        description="These versions contain the first fix for the vulnerability but may not be the recommended fixed versions.",
        title="First fixed",
    )
    fixed: Optional[ProductsT] = Field(
        default=None,
        description="These versions contain a fix for the vulnerability but may not be the recommended fixed versions.",
        title="Fixed",
    )
    known_affected: Optional[ProductsT] = Field(
        default=None,
        description="These versions are known to be affected by the vulnerability.",
        title="Known affected",
    )
    known_not_affected: Optional[ProductsT] = Field(
        default=None,
        description="These versions are known not to be affected by the vulnerability.",
        title="Known not affected",
    )
    last_affected: Optional[ProductsT] = Field(
        default=None,
        description="These are the last versions in a release train known to be affected by the vulnerability. Subsequently released versions would contain a fix for the vulnerability.",
        title="Last affected",
    )
    recommended: Optional[ProductsT] = Field(
        default=None,
        description="These versions have a fix for the vulnerability and are the vendor-recommended versions for fixing the vulnerability.",
        title="Recommended",
    )
    under_investigation: Optional[ProductsT] = Field(
        default=None,
        description="It is not known yet whether these versions are or are not affected by the vulnerability. However, it is still under investigation - the result will be provided in a later release of the document.",
        title="Under investigation",
    )


class Remediation(BaseModel):
    """
    Specifies details on how to handle (and presumably, fix) a vulnerability.
    """

    category: Category2 = Field(
        ...,
        description="Specifies the category which this remediation belongs to.",
        title="Category of the remediation",
    )
    date: Optional[datetime] = Field(
        default=None,
        description="Contains the date from which the remediation is available.",
        title="Date of the remediation",
    )
    details: constr(min_length=1) = Field(
        ...,
        description="Contains a thorough human-readable discussion of the remediation.",
        title="Details of the remediation",
    )
    entitlements: Optional[List[Entitlement]] = Field(
        default=None,
        description="Contains a list of entitlements.",
        min_length=1,
        title="List of entitlements",
    )
    group_ids: Optional[ProductGroupsT] = None
    product_ids: Optional[ProductsT] = None
    restart_required: Optional[RestartRequired] = Field(
        default=None,
        description="Provides information on category of restart is required by this remediation to become effective.",
        title="Restart required by remediation",
    )
    url: Optional[AnyUrl] = Field(
        default=None,
        description="Contains the URL where to obtain the remediation.",
        title="URL to the remediation",
    )


class Threat(BaseModel):
    """
    Contains the vulnerability kinetic information. This information can change as the vulnerability ages and new information becomes available.
    """

    category: Category4 = Field(
        ...,
        description="Categorizes the threat according to the rules of the specification.",
        title="Category of the threat",
    )
    date: Optional[datetime] = Field(
        default=None,
        description="Contains the date when the assessment was done or the threat appeared.",
        title="Date of the threat",
    )
    details: constr(min_length=1) = Field(
        ...,
        description="Represents a thorough human-readable discussion of the threat.",
        title="Details of the threat",
    )
    group_ids: Optional[ProductGroupsT] = None
    product_ids: Optional[ProductsT] = None


class FullProductNameT(BaseModel):
    """
    Specifies information about the product and assigns the product_id.
    """

    name: constr(min_length=1) = Field(
        ...,
        description="The value should be the product’s full canonical name, including version number and other attributes, as it would be used in a human-friendly document.",
        examples=[
            "Cisco AnyConnect Secure Mobility Client 2.3.185",
            "Microsoft Host Integration Server 2006 Service Pack 1",
        ],
        title="Textual description of the product",
    )
    product_id: ProductIdT
    product_identification_helper: Optional[ProductIdentificationHelper] = Field(
        default=None,
        description="Provides at least one method which aids in identifying the product in an asset database.",
        title="Helper to identify the product",
    )


class Relationship(BaseModel):
    """
    Establishes a link between two existing full_product_name_t elements, allowing the document producer to define a combination of two products that form a new full_product_name entry.
    """

    category: Category1 = Field(
        ...,
        description="Defines the category of relationship for the referenced component.",
        title="Relationship category",
    )
    full_product_name: FullProductNameT
    product_reference: ProductIdT = Field(
        ...,
        description="Holds a Product ID that refers to the Full Product Name element, which is referenced as the first element of the relationship.",
        title="Product reference",
    )
    relates_to_product_reference: ProductIdT = Field(
        ...,
        description="Holds a Product ID that refers to the Full Product Name element, which is referenced as the second element of the relationship.",
        title="Relates to product reference",
    )


class Score(BaseModel):
    """
    Specifies information about (at least one) score of the vulnerability and for which products the given value applies.
    """

    # cvss_v2: Optional[cvss_v2.Field0] = None
    # cvss_v3: Optional[Union[cvss_v3.Field0, cvss_v3.Field1]] = None
    products: ProductsT


class Vulnerability(BaseModel):
    """
    Is a container for the aggregation of all fields that are related to a single vulnerability in the document.
    """

    acknowledgments: Optional[AcknowledgmentsT] = Field(
        default=None,
        description="Contains a list of acknowledgment elements associated with this vulnerability item.",
        title="Vulnerability acknowledgments",
    )
    cve: Optional[constr(pattern=r"^CVE-[0-9]{4}-[0-9]{4,}$")] = Field(
        default=None,
        description="Holds the MITRE standard Common Vulnerabilities and Exposures (CVE) tracking number for the vulnerability.",
        title="CVE",
    )
    cwe: Optional[Cwe] = Field(
        default=None,
        description="Holds the MITRE standard Common Weakness Enumeration (CWE) for the weakness associated.",
        title="CWE",
    )
    discovery_date: Optional[datetime] = Field(
        default=None,
        description="Holds the date and time the vulnerability was originally discovered.",
        title="Discovery date",
    )
    flags: Optional[List[Flag]] = Field(
        default=None,
        description="Contains a list of machine readable flags.",
        min_length=1,
        title="List of flags",
    )
    ids: Optional[List[Id]] = Field(
        default=None,
        description="Represents a list of unique labels or tracking IDs for the vulnerability (if such information exists).",
        min_length=1,
        title="List of IDs",
    )
    involvements: Optional[List[Involvement]] = Field(
        default=None,
        description="Contains a list of involvements.",
        min_length=1,
        title="List of involvements",
    )
    notes: Optional[NotesT] = Field(
        default=None,
        description="Holds notes associated with this vulnerability item.",
        title="Vulnerability notes",
    )
    product_status: Optional[ProductStatus] = Field(
        default=None,
        description="Contains different lists of product_ids which provide details on the status of the referenced product related to the current vulnerability. ",
        title="Product status",
    )
    references: Optional[ReferencesT] = Field(
        default=None,
        description="Holds a list of references associated with this vulnerability item.",
        title="Vulnerability references",
    )
    release_date: Optional[datetime] = Field(
        default=None,
        description="Holds the date and time the vulnerability was originally released into the wild.",
        title="Release date",
    )
    remediations: Optional[List[Remediation]] = Field(
        default=None,
        description="Contains a list of remediations.",
        min_length=1,
        title="List of remediations",
    )
    scores: Optional[List[Score]] = Field(
        default=None,
        description="Contains score objects for the current vulnerability.",
        min_length=1,
        title="List of scores",
    )
    threats: Optional[List[Threat]] = Field(
        default=None,
        description="Contains information about a vulnerability that can change with time.",
        min_length=1,
        title="List of threats",
    )
    title: Optional[constr(min_length=1)] = Field(
        default=None,
        description="Gives the document producer the ability to apply a canonical name or title to the vulnerability.",
        title="Title",
    )


class ProductTree(BaseModel):
    """
    Is a container for all fully qualified product names that can be referenced elsewhere in the document.
    """

    branches: Optional[BranchesT] = None
    full_product_names: Optional[List[FullProductNameT]] = Field(
        default=None,
        description="Contains a list of full product names.",
        min_length=1,
        title="List of full product names",
    )
    product_groups: Optional[List[ProductGroup]] = Field(
        default=None,
        description="Contains a list of product groups.",
        min_length=1,
        title="List of product groups",
    )
    relationships: Optional[List[Relationship]] = Field(
        default=None,
        description="Contains a list of relationships.",
        min_length=1,
        title="List of relationships",
    )


class CommonSecurityAdvisoryFramework(BaseModel):
    """
    Representation of security advisory information as a JSON document.
    """

    document: Document = Field(
        ...,
        description="Captures the meta-data about this document describing a particular set of security advisories.",
        title="Document level meta-data",
    )
    product_tree: Optional[ProductTree] = Field(
        default=None,
        description="Is a container for all fully qualified product names that can be referenced elsewhere in the document.",
        title="Product tree",
    )
    vulnerabilities: Optional[List[Vulnerability]] = Field(
        default=None,
        description="Represents a list of all relevant vulnerability information items.",
        min_length=1,
        title="Vulnerabilities",
    )


class BranchesTItem(BaseModel):
    """
    Is a part of the hierarchical structure of the product tree.
    """

    branches: Optional[BranchesT] = None
    category: Category5 = Field(
        ...,
        description="Describes the characteristics of the labeled branch.",
        title="Category of the branch",
    )
    name: constr(min_length=1) = Field(
        ...,
        description="Contains the canonical descriptor or 'friendly name' of the branch.",
        examples=[
            "10",
            "365",
            "Microsoft",
            "Office",
            "PCS 7",
            "SIMATIC",
            "Siemens",
            "Windows",
        ],
        title="Name of the branch",
    )
    product: Optional[FullProductNameT] = None


class BranchesT(RootModel[List[BranchesTItem]]):
    """
    Contains branch elements as children of the current element.
    """

    root: List[BranchesTItem] = Field(
        ...,
        description="Contains branch elements as children of the current element.",
        min_length=1,
        title="List of branches",
    )


ProductTree.model_rebuild()
BranchesTItem.model_rebuild()
