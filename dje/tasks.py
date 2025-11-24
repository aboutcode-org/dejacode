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

from django_rq import job

from dejacode_toolkit.scancodeio import ScanCodeIO
from dejacode_toolkit.scancodeio import update_package_from_existing_scan_data
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
        if not is_available(uri):
            logger.info(f'uri="{uri}" is not reachable.')
            continue

        # Check if a Scan is already available in ScanCode.io for this URI.
        existing_project = scancodeio.get_project_info(download_url=uri)
        if existing_project:
            logger.info(f'Update the local uri="{uri}" package from available Scan data.')
            update_package_from_existing_scan_data(uri, user)
        else:
            scancodeio.submit_scan(uri, user_uuid, dataspace_uuid)


@job("default", timeout=3600)
def update_vulnerabilities():
    """Fetch vulnerabilities for all Dataspaces that enable vulnerablecodedb access."""
    from vulnerabilities.fetch import fetch_from_vulnerablecode

    logger.info("Entering update_vulnerabilities task")
    Dataspace = apps.get_model("dje", "Dataspace")
    dataspace_qs = Dataspace.objects.filter(enable_vulnerablecodedb_access=True)

    for dataspace in dataspace_qs:
        logger.info(f"fetch_vulnerabilities for datapsace={dataspace}")
        fetch_from_vulnerablecode(dataspace, batch_size=50, update=True, timeout=60)
