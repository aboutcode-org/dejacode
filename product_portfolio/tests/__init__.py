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
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductPackage


def make_product(dataspace, inventory=None, **data):
    """Create a product for test purposes."""
    if "name" not in data:
        data["name"] = f"product-{make_string(10)}"

    product = Product.objects.create(
        dataspace=dataspace,
        **data,
    )

    inventory = inventory or []
    if not isinstance(inventory, list):
        inventory = [inventory]

    for instance in inventory:
        if isinstance(instance, Package):
            ProductPackage.objects.create(product=product, package=instance, dataspace=dataspace)
        if isinstance(instance, Component):
            ProductComponent.objects.create(
                product=product, component=instance, dataspace=dataspace
            )

    return product
