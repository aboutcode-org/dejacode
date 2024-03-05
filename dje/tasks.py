#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
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

from dejacode_toolkit.scancodeio import ScanCodeIO
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
    from dje.models import DejacodeUser

    logger.info(
        f"Entering scancodeio_submit_scan task with "
        f"uris={uris} user_uuid={user_uuid} dataspace_uuid={dataspace_uuid}"
    )

    try:
        user = DejacodeUser.objects.get(uuid=user_uuid, dataspace__uuid=dataspace_uuid)
    except ObjectDoesNotExist:
        return

    if not isinstance(uris, list):
        uris = [uris]

    for uri in uris:
        if is_available(uri):
            ScanCodeIO(user).submit_scan(uri, user_uuid, dataspace_uuid)
        else:
            logger.info(f'uri="{uri}" is not reachable.')


@job
def scancodeio_submit_load_sbom(scancodeproject_uuid, user_uuid):
    """Submit the provided SBOM file to ScanCode.io as an asynchronous task."""
    from dje.models import DejacodeUser

    logger.info(
        f"Entering scancodeio_submit_load_sbom task with "
        f"scancodeproject_uuid={scancodeproject_uuid} user_uuid={user_uuid}"
    )

    ScanCodeProject = apps.get_model("product_portfolio", "scancodeproject")
    scancode_project = ScanCodeProject.objects.get(uuid=scancodeproject_uuid)

    try:
        user = DejacodeUser.objects.get(uuid=user_uuid)
    except ObjectDoesNotExist:
        return

    scancodeio = ScanCodeIO(user)

    # Create a Project instance on ScanCode.io without immediate execution of the
    # pipeline. This allows to get instant feedback from ScanCode.io about the Project
    # creation status and its related data, even in SYNC mode.
    response = scancodeio.submit_load_sbom(
        project_name=scancodeproject_uuid,
        file_location=scancode_project.input_file.path,
        user_uuid=user_uuid,
        execute_now=False,
    )

    if not response:
        logger.info("Error submitting the SBOM file to ScanCode.io server")
        scancode_project.status = ScanCodeProject.Status.FAILURE
        msg = "- Error: SBOM could not be submitted to ScanCode.io"
        scancode_project.append_to_log(msg, save=True)
        return

    logger.info("Update the ScanCodeProject instance")
    scancode_project.status = ScanCodeProject.Status.SUBMITTED
    scancode_project.project_uuid = response.get("uuid")
    msg = "- SBOM file submitted to ScanCode.io for inspection"
    scancode_project.append_to_log(msg, save=True)

    # Delay the execution of the pipeline after the ScancodeProject instance was
    # properly saved and committed in order to avoid any race conditions.
    if runs := response.get("runs"):
        logger.info("Start the pipeline run")
        transaction.on_commit(lambda: scancodeio.start_pipeline(run_url=runs[0]["url"]))


@job
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
        notification_verb = "Load Packages from SBOMs"
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
    msg = f"- Imported {len(created)} package{pluralize(created)}."
    scancode_project.append_to_log(msg)

    if existing:
        msg = f"- {len(existing)} package(s) was/were already available in the Dataspace."
        scancode_project.append_to_log(msg)

    if errors:
        scancode_project.append_to_log(f"- {len(errors)} errors occurred during import.")

    scancode_project.save()
    description = "\n".join(scancode_project.import_log)
    scancode_project.notify(verb=notification_verb, description=description)
