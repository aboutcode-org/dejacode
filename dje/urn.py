#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

"""
URN: Uniform Resource Name
==========================

A URN module for DejaCode data.

The URN syntax is specified in:
 * RFC2141 http://tools.ietf.org/html/rfc2141
 * RFC2396 http://tools.ietf.org/html/rfc2396

In DejaCode, a URN is a universal way to reference DejaCode data externally.

A DejaCode URN follows the URN syntax and is generally case sensitive.
It does support UTF-8 characters that are then URL-encoded (using the quote+
encoding)


Syntax and Examples
-------------------

The generic syntax of a DJE URN is::
    urn:<namespace>:<object>:<segments>
where:
 * <namespace> is always "dje"
 * <object> is a DejaCode object identifier. Not all objects of DejaCode are
 supported. Current support includes owner, license and component.
 * <segments> is object-defined and object-specific

The syntax for an Owner is::
    urn:dje:owner:<owner.name>
where owner.name is the name of the owner.

    urn:dje:owner:Apache+Software+Foundation

The syntax for a License is::
    urn:dje:license:<license.key>
where license.key is the key of the license.

    urn:dje:nexB:license:apache-2.0

The syntax for a Component or Product is::
    urn:dje:component:<component.name>:<component.version>
where:
 * component.name is the name of the component
 * component.version is the version of the component. Note that the trailing
 colon representing an empty value/undefined version is required.

 * with version::
     urn:dje:component:log4j:1.0
 * without a defined version::
     urn:dje:component:log4j:
"""

from urllib.parse import quote_plus
from urllib.parse import unquote_plus


class URNValidationError(Exception):
    """The URN format is not valid."""


# Describes each supported URN syntax and their relation to DejaCode objects
# the format is : object_name: [list of field names]
URN_SCHEMAS = {
    "license": ["key"],
    "owner": ["name"],
    "component": ["name", "version"],
}

# max number of urn segments
MAX_SEGMENTS = 4


def build(object_name, **fields):
    """
    Build and encode a URN based on the provided input.
    This is a string and local operation only: the URN is not resolved and
    therefore validity of the data for the URN as a whole and for each segment
    is not checked. The arguments include the object name and all the object
    specific required fields in a dictionary.
    """
    object_name = object_name.strip().lower()
    object_fields = URN_SCHEMAS[object_name]

    # leading and trailing white spaces are not considered significant
    fields = [fields[f].strip() for f in object_fields]
    # each URN field is encoded individually before assembling the URN
    fields = ":".join([quote_plus(f) for f in fields])

    return f"urn:dje:{object_name}:{fields}"


def parse(urn):
    """
    Parse and decode a URN returning the object name and a dictionary with
    each URN fields of a given object.
    Raise URNValidationError on errors.
    """
    urn_parts = [unquote_plus(p) for p in urn.split(":")]

    if len(urn_parts) < MAX_SEGMENTS:
        raise URNValidationError(
            f'Invalid URN format: "{urn}". Expected format is: '
            f'"urn:<namespace>:<object>:<segments>".'
        )

    namespace = ":".join(urn_parts[0:2])
    if namespace != "urn:dje":
        raise URNValidationError(
            f"Invalid URN prefix or namespace. "
            f'Expected "urn:dje" and not "{namespace}" in URN: "{urn}".'
        )

    # object name is always lowercased
    object_name = urn_parts[2].lower()
    if object_name not in URN_SCHEMAS:
        valid_names = ",".join(URN_SCHEMAS)
        raise URNValidationError(
            f'Unsupported URN object: {object_name} in URN: "{urn}". '
            f"Expected one of: {valid_names}."
        )

    segments = urn_parts[3:]
    keys = URN_SCHEMAS[object_name]
    if len(keys) != len(segments):
        raise URNValidationError(
            f'Invalid number of segments in URN: "{urn}".')

    fields = dict(zip(keys, segments))
    return object_name, fields
