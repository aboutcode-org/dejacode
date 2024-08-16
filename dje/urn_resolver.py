#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

"""Resolve URNS to model instances."""

from django.contrib.contenttypes.models import ContentType

from dje.urn import parse as urn_parse

# Describe the URN objects relation to DejaCode apps and models
URN_MODEL_APPS = {
    "license": {
        "app_label": "license_library",
        "model": "license",
    },
    "owner": {
        "app_label": "organization",
        "model": "owner",
    },
    "component": {
        "app_label": "component_catalog",
        "model": "component",
    },
    "product": {
        "app_label": "product_portfolio",
        "model": "product",
    },
}


URN_HELP_TEXT = "URN is a globally unique and universal way to reference data."


def resolve(urn, dataspace):
    """
    Parse and resolve a URN against the database and return the corresponding
    database object.
    Raise URNValidationError on errors.
    """
    model_name, parsed_fields = urn_parse(urn)
    filters = {"dataspace": dataspace}
    filters.update(parsed_fields)

    # Always re-get the actual real model name through the DESCRIPTION
    # and not directly from the URN to avoid hacking
    model_data = URN_MODEL_APPS[model_name]
    app_label = model_data["app_label"]
    model = model_data["model"]

    # Using ContentType to get the corresponding Model
    model_class = ContentType.objects.get_by_natural_key(
        app_label, model).model_class()

    return model_class.objects.get(**filters)
