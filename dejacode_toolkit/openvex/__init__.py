#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from enum import StrEnum
from typing import Annotated, List, Union

from msgspec import UNSET, Meta, Struct, UnsetType, field


class Status(StrEnum):
    not_affected = "not_affected"
    affected = "affected"
    fixed = "fixed"
    under_investigation = "under_investigation"


class Justification(StrEnum):
    component_not_present = "component_not_present"
    vulnerable_code_not_present = "vulnerable_code_not_present"
    vulnerable_code_not_in_execute_path = "vulnerable_code_not_in_execute_path"
    vulnerable_code_cannot_be_controlled_by_adversary = (
        "vulnerable_code_cannot_be_controlled_by_adversary"
    )
    inline_mitigations_already_exist = "inline_mitigations_already_exist"


class Vulnerability(Struct):
    name: Annotated[
        str,
        Meta(
            description=(
                "A string with the main identifier used to name the vulnerability."
            )
        ),
    ]
    field_id: Union[
        Annotated[
            str,
            Meta(
                description=(
                    "An Internationalized Resource Identifier (IRI) identifying the"
                    " struct."
                )
            ),
        ],
        UnsetType,
    ] = field(name="@id", default=UNSET)
    description: Union[
        Annotated[
            str,
            Meta(description="Optional free form text describing the vulnerability."),
        ],
        UnsetType,
    ] = UNSET
    aliases: Union[
        Annotated[
            List[str],
            Meta(
                description=(
                    "A list of strings enumerating other names under which the"
                    " vulnerability may be known."
                )
            ),
        ],
        UnsetType,
    ] = UNSET


class Identifiers1(Struct):
    purl: Annotated[str, Meta(description="Package URL")]
    cpe22: Union[
        Annotated[str, Meta(description="Common Platform Enumeration v2.2")], UnsetType
    ] = UNSET
    cpe23: Union[
        Annotated[str, Meta(description="Common Platform Enumeration v2.3")], UnsetType
    ] = UNSET


class Identifiers2(Struct):
    cpe22: Annotated[str, Meta(description="Common Platform Enumeration v2.2")]
    purl: Union[Annotated[str, Meta(description="Package URL")], UnsetType] = UNSET
    cpe23: Union[
        Annotated[str, Meta(description="Common Platform Enumeration v2.3")], UnsetType
    ] = UNSET


class Identifiers3(Struct):
    cpe23: Annotated[str, Meta(description="Common Platform Enumeration v2.3")]
    purl: Union[Annotated[str, Meta(description="Package URL")], UnsetType] = UNSET
    cpe22: Union[
        Annotated[str, Meta(description="Common Platform Enumeration v2.2")], UnsetType
    ] = UNSET


type Identifiers = Union[Identifiers1, Identifiers2, Identifiers3]


class Hashes(Struct):
    md5: Union[str, UnsetType] = UNSET
    sha1: Union[str, UnsetType] = UNSET
    sha_256: Union[str, UnsetType] = field(name="sha-256", default=UNSET)
    sha_384: Union[str, UnsetType] = field(name="sha-384", default=UNSET)
    sha_512: Union[str, UnsetType] = field(name="sha-512", default=UNSET)
    sha3_224: Union[str, UnsetType] = field(name="sha3-224", default=UNSET)
    sha3_256: Union[str, UnsetType] = field(name="sha3-256", default=UNSET)
    sha3_384: Union[str, UnsetType] = field(name="sha3-384", default=UNSET)
    sha3_512: Union[str, UnsetType] = field(name="sha3-512", default=UNSET)
    blake2s_256: Union[str, UnsetType] = field(name="blake2s-256", default=UNSET)
    blake2b_256: Union[str, UnsetType] = field(name="blake2b-256", default=UNSET)
    blake2b_512: Union[str, UnsetType] = field(name="blake2b-512", default=UNSET)


class Subcomponent1(Struct):
    field_id: Annotated[
        str,
        Meta(
            description=(
                "Optional IRI identifying the component to make it externally"
                " referenceable."
            )
        ),
    ] = field(name="@id")
    identifiers: Union[
        Annotated[
            Identifiers,
            Meta(
                description=(
                    "Optional IRI identifying the component to make it externally"
                    " referenceable."
                )
            ),
        ],
        UnsetType,
    ] = UNSET
    hashes: Union[
        Annotated[
            Hashes, Meta(description="Map of cryptographic hashes of the component.")
        ],
        UnsetType,
    ] = UNSET


class Subcomponent2(Struct):
    identifiers: Annotated[
        Identifiers,
        Meta(
            description=(
                "Optional IRI identifying the component to make it externally"
                " referenceable."
            )
        ),
    ]
    field_id: Union[
        Annotated[
            str,
            Meta(
                description=(
                    "Optional IRI identifying the component to make it externally"
                    " referenceable."
                )
            ),
        ],
        UnsetType,
    ] = field(name="@id", default=UNSET)
    hashes: Union[
        Annotated[
            Hashes, Meta(description="Map of cryptographic hashes of the component.")
        ],
        UnsetType,
    ] = UNSET


type Subcomponent = Union[Subcomponent1, Subcomponent2]


class Component1(Struct):
    field_id: Annotated[
        str,
        Meta(
            description=(
                "Optional IRI identifying the component to make it externally"
                " referenceable."
            )
        ),
    ] = field(name="@id")
    identifiers: Union[
        Annotated[
            Identifiers,
            Meta(
                description=(
                    "A map of software identifiers where the key is the type and the"
                    " value the identifier."
                )
            ),
        ],
        UnsetType,
    ] = UNSET
    hashes: Union[
        Annotated[
            Hashes, Meta(description="Map of cryptographic hashes of the component.")
        ],
        UnsetType,
    ] = UNSET
    subcomponents: Union[
        Annotated[
            List[Subcomponent],
            Meta(
                description=(
                    "List of subcomponent structs describing the subcomponents subject"
                    " of the VEX statement."
                )
            ),
        ],
        UnsetType,
    ] = UNSET


class Component2(Struct):
    identifiers: Annotated[
        Identifiers,
        Meta(
            description=(
                "A map of software identifiers where the key is the type and the value"
                " the identifier."
            )
        ),
    ]
    field_id: Union[
        Annotated[
            str,
            Meta(
                description=(
                    "Optional IRI identifying the component to make it externally"
                    " referenceable."
                )
            ),
        ],
        UnsetType,
    ] = field(name="@id", default=UNSET)
    hashes: Union[
        Annotated[
            Hashes, Meta(description="Map of cryptographic hashes of the component.")
        ],
        UnsetType,
    ] = UNSET
    subcomponents: Union[
        Annotated[
            List[Subcomponent],
            Meta(
                description=(
                    "List of subcomponent structs describing the subcomponents subject"
                    " of the VEX statement."
                )
            ),
        ],
        UnsetType,
    ] = UNSET


type Component = Union[Component1, Component2]


class Statement(Struct):
    vulnerability: Annotated[
        Vulnerability, Meta(description="A struct identifying the vulnerability.")
    ]
    status: Annotated[
        Status,
        Meta(
            description=(
                "A VEX statement MUST provide the status of the vulnerabilities with"
                " respect to the products and components listed in the statement."
            )
        ),
    ]
    field_id: Union[
        Annotated[
            str,
            Meta(
                description=(
                    "Optional IRI identifying the statement to make it externally"
                    " referenceable."
                )
            ),
        ],
        UnsetType,
    ] = field(name="@id", default=UNSET)
    version: Union[
        Annotated[
            int,
            Meta(
                description=(
                    "Optional integer representing the statement's version number."
                ),
                ge=1,
            ),
        ],
        UnsetType,
    ] = UNSET
    timestamp: Union[
        Annotated[
            str,
            Meta(
                description=(
                    "Timestamp is the time at which the information expressed in the"
                    " statement was known to be true."
                )
            ),
        ],
        UnsetType,
    ] = UNSET
    last_updated: Union[
        Annotated[
            str, Meta(description="Timestamp when the statement was last updated.")
        ],
        UnsetType,
    ] = UNSET
    products: Union[
        Annotated[
            List[Component],
            Meta(description="List of product structs that the statement applies to."),
        ],
        UnsetType,
    ] = UNSET
    supplier: Union[
        Annotated[str, Meta(description="Supplier of the product or subcomponent.")],
        UnsetType,
    ] = UNSET
    status_notes: Union[
        Annotated[
            str,
            Meta(
                description=(
                    "A statement MAY convey information about how status was determined"
                    " and MAY reference other VEX information."
                )
            ),
        ],
        UnsetType,
    ] = UNSET
    justification: Union[
        Annotated[
            Justification,
            Meta(
                description=(
                    "For statements conveying a not_affected status, a VEX statement"
                    " MUST include either a status justification or an impact_statement"
                    " informing why the product is not affected by the vulnerability."
                )
            ),
        ],
        UnsetType,
    ] = UNSET
    impact_statement: Union[
        Annotated[
            str,
            Meta(
                description=(
                    "For statements conveying a not_affected status, a VEX statement"
                    " MUST include either a status justification or an impact_statement"
                    " informing why the product is not affected by the vulnerability."
                )
            ),
        ],
        UnsetType,
    ] = UNSET
    action_statement: Union[
        Annotated[
            str,
            Meta(
                description=(
                    "For a statement with affected status, a VEX statement MUST include"
                    " a statement that SHOULD describe actions to remediate or mitigate"
                    " the vulnerability."
                )
            ),
        ],
        UnsetType,
    ] = UNSET
    action_statement_timestamp: Union[
        Annotated[
            str, Meta(description="The timestamp when the action statement was issued.")
        ],
        UnsetType,
    ] = UNSET


class OpenVEX(Struct):
    field_context: Annotated[
        str, Meta(description="The URL linking to the OpenVEX context definition.")
    ] = field(name="@context")
    field_id: Annotated[
        str, Meta(description="The IRI identifying the VEX document.")
    ] = field(name="@id")
    author: Annotated[
        str,
        Meta(
            description="Author is the identifier for the author of the VEX statement."
        ),
    ]
    timestamp: Annotated[
        str,
        Meta(
            description="Timestamp defines the time at which the document was issued."
        ),
    ]
    version: Annotated[int, Meta(description="Version is the document version.", ge=1)]
    statements: Annotated[
        List[Statement],
        Meta(
            description=(
                "A statement is an assertion made by the document's author about the"
                " impact a vulnerability has on one or more software 'products'."
            )
        ),
    ]
    role: Union[
        Annotated[
            str, Meta(description="Role describes the role of the document author.")
        ],
        UnsetType,
    ] = UNSET
    last_updated: Union[
        Annotated[str, Meta(description="Date of last modification to the document.")],
        UnsetType,
    ] = UNSET
    tooling: Union[
        Annotated[
            str,
            Meta(
                description=(
                    "Tooling expresses how the VEX document and contained VEX"
                    " statements were generated."
                )
            ),
        ],
        UnsetType,
    ] = UNSET
