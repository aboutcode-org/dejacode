#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging
from datetime import datetime
from io import StringIO

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import management
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import send_mail
from django.db import transaction
from django.template.defaultfilters import pluralize

from django_rq import job
from guardian.shortcuts import get_perms as guardian_get_perms

from dejacode_toolkit.scancodeio import ScanCodeIO
from dejacode_toolkit.scancodeio import check_for_existing_scan_workaround
from dje.utils import is_available

logger = logging.getLogger(__name__)


@job
def send_mail_task(subject, message, from_email, recipient_list, fail_silently=True):
    """
    Send an email as an asynchronous task.

    `fail_silently` is True by default as the errors are logged on the Task
    object.

    The subject is cleaned from newlines and limited to 255 characters.
    """
    subject = "".join(subject.splitlines())[:255]
    send_mail(subject, message, from_email, recipient_list, fail_silently)


@job
def send_mail_to_admins_task(subject, message, from_email=None, fail_silently=True):
    """Send an email to system administrators as an asynchronous task."""
    if not from_email:
        from_email = settings.DEFAULT_FROM_EMAIL

    recipient_list = settings.ADMINS
    if not recipient_list:
        return

    send_mail_task(subject, message, from_email, recipient_list, fail_silently)


@job("default", timeout=7200)
def call_management_command(name, *args, **options):
    """Run a management command as an asynchronous task."""
    logger.info(
        f"Entering call_management_command task with name={name} args={args} options={options}"
    )

    options["stdout"] = StringIO()
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    user_id = options.pop("user_id")
    management.call_command(name, *args, **options)
    end_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    if user_id:
        subject = "[DejaCode] Dataspace cloning completed"
        msg = "Cloning process initiated at {} and completed at {}.\n\n{}".format(
            start_time, end_time, options["stdout"].getvalue()
        )
        user = get_user_model().objects.get(pk=user_id)
        user.email_user(subject, msg)


@job
def package_collect_data(instance_id):
    """Run Package.collect_data() as an asynchronous task."""
    Package = apps.get_model("component_catalog", "package")
    logger.info(f"Entering package_collect_data task for Package.id={instance_id}")
    package = Package.objects.get(id=instance_id)
    logger.info(f"Package Download URL: {package.download_url}")
    package.collect_data()


@job
def scancodeio_submit_scan(uris, user_uuid, dataspace_uuid):
    """
    Submit the provided `uris` to ScanCode.io as an asynchronous task.
    Only publicly available URLs are sent to ScanCode.io.
    """
    logger.info(
        f"Entering scancodeio_submit_scan task with "
        f"uris={uris} user_uuid={user_uuid} dataspace_uuid={dataspace_uuid}"
    )

    DejacodeUser = apps.get_model("dje", "DejacodeUser")

    try:
        user = DejacodeUser.objects.get(uuid=user_uuid, dataspace__uuid=dataspace_uuid)
    except ObjectDoesNotExist:
        logger.error(f"[scancodeio_submit_scan]: User uuid={user_uuid} does not exists.")
        return

    if not isinstance(uris, list):
        uris = [uris]

    scancodeio = ScanCodeIO(user.dataspace)
    for uri in uris:
        if is_available(uri):
            response_json = scancodeio.submit_scan(uri, user_uuid, dataspace_uuid)
            check_for_existing_scan_workaround(response_json, uri, user)
        else:
            logger.info(f'uri="{uri}" is not reachable.')


@job
def scancodeio_submit_project(scancodeproject_uuid, user_uuid, pipeline_name):
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
def pull_project_data_from_scancodeio(scancodeproject_uuid):
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
        msg = (
            f"- {len(values)} {object_type}{pluralize(values)} already available in the Dataspace."
        )
        scancode_project.append_to_log(msg)

    for object_type, values in errors.items():
        msg = f"- {len(values)} {object_type} error{pluralize(values)} occurred during import."
        scancode_project.append_to_log(msg)

    scancode_project.save()
    description = "\n".join(scancode_project.import_log)
    scancode_project.notify(verb=notification_verb, description=description)


@job("default", timeout=1200)
def improve_packages_from_purldb(product_uuid, user_uuid):
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
        scancode_project.update(
            status=ScanCodeProject.Status.FAILURE,
            import_log=str(e),
        )

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


@job("default", timeout="3h")
def update_vulnerabilities():
    """Fetch vulnerabilities for all Dataspaces that enable vulnerablecodedb access."""
    from vulnerabilities.fetch import fetch_from_vulnerablecode

    logger.info("Entering update_vulnerabilities task")
    Dataspace = apps.get_model("dje", "Dataspace")
    dataspace_qs = Dataspace.objects.filter(enable_vulnerablecodedb_access=True)

    for dataspace in dataspace_qs:
        logger.info(f"fetch_vulnerabilities for datapsace={dataspace}")
        fetch_from_vulnerablecode(dataspace, batch_size=50, update=True, timeout=60)
