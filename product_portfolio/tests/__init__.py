#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import uuid

from component_catalog.models import Component
from component_catalog.models import Package
from component_catalog.tests import make_component
from component_catalog.tests import make_package
from dje.tests import make_string
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductDependency
from product_portfolio.models import ProductItemPurpose
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductStatus


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
            make_product_package(product, package=instance)
        if isinstance(instance, Component):
            make_product_component(product, component=instance)

    return product


def make_product_package(product, package=None, **data):
    dataspace = product.dataspace

    if not package:
        package = make_package(dataspace)

    return ProductPackage.objects.create(
        product=product,
        package=package,
        dataspace=dataspace,
        **data,
    )


def make_product_component(product, component=None):
    dataspace = product.dataspace

    if not component:
        component = make_component(dataspace)

    return ProductComponent.objects.create(
        product=product,
        component=component,
        dataspace=dataspace,
    )


def make_product_item_purpose(dataspace, **data):
    if "label" not in data:
        data["label"] = make_string(10)
    if "text" not in data:
        data["text"] = make_string(10)

    return ProductItemPurpose.objects.create(
        dataspace=dataspace,
        **data,
    )


def make_product_status(dataspace, **data):
    if "label" not in data:
        data["label"] = make_string(10)
    if "text" not in data:
        data["text"] = make_string(10)

    return ProductStatus.objects.create(
        dataspace=dataspace,
        **data,
    )


def make_product_dependency(product, **data):
    if "dependency_uid" not in data:
        data["dependency_uid"] = str(uuid.uuid4())

    return ProductDependency.objects.create(
        product=product,
        dataspace=product.dataspace,
        **data,
    )
