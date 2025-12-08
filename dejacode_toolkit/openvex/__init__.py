#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from dataclasses import dataclass
from enum import StrEnum


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


@dataclass
class Vulnerability:
    name: str
    field_id: str | None = None
    description: str | None = None
    aliases: list[str] | None = None


@dataclass
class Identifiers1:
    purl: str
    cpe22: str | None = None
    cpe23: str | None = None


@dataclass
class Identifiers2:
    cpe22: str
    purl: str | None = None
    cpe23: str | None = None


@dataclass
class Identifiers3:
    cpe23: str
    purl: str | None = None
    cpe22: str | None = None


type Identifiers = Identifiers1 | Identifiers2 | Identifiers3


@dataclass
class Hashes:
    md5: str | None = None
    sha1: str | None = None
    sha_256: str | None = None
    sha_384: str | None = None
    sha_512: str | None = None
    sha3_224: str | None = None
    sha3_256: str | None = None
    sha3_384: str | None = None
    sha3_512: str | None = None
    blake2s_256: str | None = None
    blake2b_256: str | None = None
    blake2b_512: str | None = None


@dataclass
class Subcomponent1:
    field_id: str
    identifiers: Identifiers | None = None
    hashes: Hashes | None = None


@dataclass
class Subcomponent2:
    identifiers: Identifiers
    field_id: str | None = None
    hashes: Hashes | None = None


type Subcomponent = Subcomponent1 | Subcomponent2


@dataclass
class Component1:
    field_id: str
    identifiers: Identifiers | None = None
    hashes: Hashes | None = None
    subcomponents: list[Subcomponent] | None = None


@dataclass
class Component2:
    identifiers: Identifiers
    field_id: str | None = None
    hashes: Hashes | None = None
    subcomponents: list[Subcomponent] | None = None


type Component = Component1 | Component2


@dataclass
class Statement:
    vulnerability: Vulnerability
    status: Status
    field_id: str | None = None
    version: int | None = None
    timestamp: str | None = None
    last_updated: str | None = None
    products: list[Component] | None = None
    supplier: str | None = None
    status_notes: str | None = None
    justification: Justification | None = None
    impact_statement: str | None = None
    action_statement: str | None = None
    action_statement_timestamp: str | None = None


@dataclass
class OpenVEX:
    field_context: str
    field_id: str
    author: str
    timestamp: str
    version: int
    statements: list[Statement]
    role: str | None = None
    last_updated: str | None = None
    tooling: str | None = None
