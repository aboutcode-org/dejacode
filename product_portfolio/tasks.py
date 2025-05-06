#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging

from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist

from django_rq import job
from guardian.shortcuts import get_perms as guardian_get_perms

logger = logging.getLogger(__name__)


@job("default", timeout=1200)
def improve_packages_from_purldb_task(product_uuid, user_uuid):
    logger.info(
        f"Entering improve_packages_from_purldb task with "
        f"product_uuid={product_uuid} user_uuid={user_uuid}"
    )

    DejacodeUser = apps.get_model("dje", "DejacodeUser")
    History = apps.get_model("dje", "History")
    Product = apps.get_model("product_portfolio", "product")
    ScanCodeProject = apps.get_model("product_portfolio", "scancodeproject")

    try:
        user = DejacodeUser.objects.get(uuid=user_uuid)
    except ObjectDoesNotExist:
        logger.error(f"[improve_packages_from_purldb]: User uuid={user_uuid} does not exists.")
        return

    try:
        product = Product.objects.get_queryset(user).get(uuid=product_uuid)
    except ObjectDoesNotExist:
        logger.error(
            f"[improve_packages_from_purldb]: Product uuid={product_uuid} does not exists."
        )
        return

    perms = guardian_get_perms(user, product)
    has_change_permission = "change_product" in perms
    if not has_change_permission:
        logger.error("[improve_packages_from_purldb]: Permission denied.")
        return

    scancode_project = ScanCodeProject.objects.create(
        product=product,
        dataspace=product.dataspace,
        type=ScanCodeProject.ProjectType.IMPROVE_FROM_PURLDB,
        status=ScanCodeProject.Status.IMPORT_STARTED,
        created_by=user,
    )

    try:
        updated_packages = product.improve_packages_from_purldb(user)
    except Exception as e:
        logger.error(f"[improve_packages_from_purldb]: {e}.")
        scancode_project.update(
            status=ScanCodeProject.Status.FAILURE,
            import_log=["Error:", str(e)],
        )
        return

    logger.info(f"[improve_packages_from_purldb]: {len(updated_packages)} updated from PurlDB.")
    verb = "Improved packages from PurlDB:"
    if updated_packages:
        description = ", ".join([str(package) for package in updated_packages])
        History.log_change(user, product, message=f"{verb} {description}")
    else:
        description = "No packages updated from PurlDB data."

    scancode_project.update(
        status=ScanCodeProject.Status.SUCCESS,
        import_log=[verb, description],
    )

    user.send_internal_notification(
        verb=verb,
        action_object=product,
        description=description,
    )
