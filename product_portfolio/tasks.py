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
from django.db import transaction
from django.template.defaultfilters import pluralize

from django_rq import job
from guardian.shortcuts import get_perms as guardian_get_perms

from dejacode_toolkit.scancodeio import ScanCodeIO

logger = logging.getLogger(__name__)


@job
def scancodeio_submit_project_task(scancodeproject_uuid, user_uuid, pipeline_name):
    """Submit the provided SBOM file to ScanCode.io as an asynchronous task."""
    logger.info(
        f"Entering scancodeio_submit_project task with "
        f"scancodeproject_uuid={scancodeproject_uuid} user_uuid={user_uuid} "
        f"pipeline_name={pipeline_name}"
    )

    DejacodeUser = apps.get_model("dje", "DejacodeUser")
    ScanCodeProject = apps.get_model("product_portfolio", "scancodeproject")
    scancode_project = ScanCodeProject.objects.get(uuid=scancodeproject_uuid)

    try:
        user = DejacodeUser.objects.get(uuid=user_uuid)
    except ObjectDoesNotExist:
        logger.error(f"[scancodeio_submit_project]: User uuid={user_uuid} does not exists.")
        return

    scancodeio = ScanCodeIO(user.dataspace)

    # Create a Project instance on ScanCode.io without immediate execution of the
    # pipeline. This allows to get instant feedback from ScanCode.io about the Project
    # creation status and its related data, even in SYNC mode.
    response = scancodeio.submit_project(
        project_name=scancodeproject_uuid,
        pipeline_name=pipeline_name,
        file_location=scancode_project.input_file.path,
        user_uuid=user_uuid,
        execute_now=False,
    )

    if not response:
        logger.info("Error submitting the file to ScanCode.io server")
        scancode_project.status = ScanCodeProject.Status.FAILURE
        msg = "- Error: File could not be submitted to ScanCode.io"
        scancode_project.append_to_log(msg, save=True)
        return

    logger.info("Update the ScanCodeProject instance")
    scancode_project.status = ScanCodeProject.Status.SUBMITTED
    scancode_project.project_uuid = response.get("uuid")
    msg = "- File submitted to ScanCode.io for inspection"
    scancode_project.append_to_log(msg, save=True)

    # Delay the execution of the pipeline after the ScancodeProject instance was
    # properly saved and committed in order to avoid any race conditions.
    if runs := response.get("runs"):
        logger.info("Start the pipeline run")
        transaction.on_commit(lambda: scancodeio.start_pipeline(run_url=runs[0]["url"]))


@job("default", timeout=1200)
def pull_project_data_from_scancodeio_task(scancodeproject_uuid):
    """
    Pull Project data from ScanCode.io as an asynchronous task for the provided
    `scancodeproject_uuid`.
    """
    logger.info(
        f"Entering pull_project_data_from_scancodeio task with "
        f"scancodeproject_uuid={scancodeproject_uuid}"
    )

    ScanCodeProject = apps.get_model("product_portfolio", "scancodeproject")
    scancode_project = ScanCodeProject.objects.get(uuid=scancodeproject_uuid)

    # Make sure the import is not already in progress,
    # or that the import has not completed yet.
    if not scancode_project.can_start_import:
        logger.error("Cannot start import")
        return

    # Update the status to prevent from starting the task again
    ScanCodeProject.objects.filter(uuid=scancode_project.uuid).update(
        status=ScanCodeProject.Status.IMPORT_STARTED
    )

    if scancode_project.type == scancode_project.ProjectType.LOAD_SBOMS:
        notification_verb = "Import SBOM"
    else:
        notification_verb = "Import packages from ScanCode.io"

    try:
        created, existing, errors = scancode_project.import_data_from_scancodeio()
    except Exception as e:
        scancode_project.status = ScanCodeProject.Status.FAILURE
        scancode_project.append_to_log(message=str(e), save=True)
        scancode_project.notify(verb=notification_verb, description="Import failed.")
        return

    scancode_project.status = ScanCodeProject.Status.SUCCESS

    for object_type, values in created.items():
        object_type_plural = f"{object_type}{pluralize(values)}"
        object_type_plural = object_type_plural.replace("dependencys", "dependencies")
        msg = f"- Imported {len(values)} {object_type_plural}."
        scancode_project.append_to_log(msg)

    for object_type, values in existing.items():
        object_type_plural = f"{object_type}{pluralize(values)}"
        object_type_plural = object_type_plural.replace("dependencys", "dependencies")
        reason = "already available in the dataspace"
        if object_type == "dependency":
            reason = "already defined on the product"
        msg = f"- {len(values)} {object_type_plural} skipped: {reason}."
        scancode_project.append_to_log(msg)

    for object_type, values in errors.items():
        msg = f"- {len(values)} {object_type} error{pluralize(values)} occurred during import."
        scancode_project.append_to_log(msg)

    scancode_project.save()
    description = "\n".join(scancode_project.import_log)
    scancode_project.notify(verb=notification_verb, description=description)


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
