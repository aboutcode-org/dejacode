#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.urls import reverse

from axes.handlers.database import AxesDatabaseHandler
from axes.helpers import get_credentials
from axes.helpers import get_failure_limit

from dje.models import Dataspace
from dje.models import DejacodeUser
from dje.models import History
from dje.tasks import send_mail_task
from dje.tasks import send_mail_to_admins_task
from notification.models import find_and_fire_hook

ADDITION = History.ADDITION
CHANGE = History.CHANGE
DELETION = History.DELETION


VERBOSE_ACTION = {ADDITION: "Added", CHANGE: "Updated", DELETION: "Removed"}


def has_email_settings():
    """
    Set the EMAIL_BACKEND settings to None to disable the notification feature.
    The user and password are not required for the SMTP settings.
    """
    backend = settings.EMAIL_BACKEND
    host = settings.EMAIL_HOST
    port = settings.EMAIL_PORT
    from_email = settings.DEFAULT_FROM_EMAIL

    if backend and host and port and from_email:
        return True
    return False


def send_notification_email(user, instance, action, message=""):
    if not has_email_settings():
        return

    if not hasattr(instance, "dataspace"):
        return

    recipients = get_user_model().objects.get_data_update_recipients(instance.dataspace)
    if not recipients:
        return

    verbose_name = instance._meta.verbose_name.capitalize()
    verbose_action = VERBOSE_ACTION[action]
    subject = f'{verbose_action} {verbose_name}: "{instance}"'
    body = (
        f'{verbose_name} "{instance}" in dataspace "{instance.dataspace.name}" '
        f"{verbose_action.lower()} by: {user.first_name} {user.last_name} ({user.username})"
    )

    if action is History.CHANGE and message:
        if message == "No fields changed.":
            return
        body += f"\n\n{message}"

    if action is not History.DELETION:
        site_url = settings.SITE_URL.rstrip("/")
        body += f"\n\n{site_url}{instance.get_admin_url()}"

    send_mail_task.delay(subject, body, settings.DEFAULT_FROM_EMAIL, recipients)


def send_notification_email_on_queryset(user, queryset, action, message=""):
    if not has_email_settings():
        return

    if not queryset:
        return

    if len(queryset) == 1:
        return send_notification_email(user, queryset[0], action, message)

    first = queryset[0]
    if not hasattr(first, "dataspace"):
        return

    recipients = get_user_model().objects.get_data_update_recipients(first.dataspace)
    if not recipients:
        return

    verbose_name_plural = first._meta.verbose_name_plural.capitalize()
    verbose_action = VERBOSE_ACTION[action]

    subject = f"Multiple {verbose_name_plural} {verbose_action.lower()}"
    body = (
        f'{verbose_name_plural} in dataspace "{first.dataspace.name}" '
        f"{verbose_action.lower()} by {user.first_name} {user.last_name} ({user.username}):"
    )

    for instance in queryset:
        body += f"\n- {instance}"

        if action is not History.DELETIONL:
            site_url = settings.SITE_URL.rstrip("/")
            body += f" {site_url}{instance.get_admin_url()}"

    if message:
        body += f"\n\n{message}"

    send_mail_task.delay(subject, body, settings.DEFAULT_FROM_EMAIL, recipients)


def successful_mass_update(sender, action, request, queryset, modeladmin, form, **kwargs):
    """
    Wrap the email notification and History creation for mass update
    using the action_end Signal.
    As the Signal may be sent from various functions of adminaction we are
    limiting the notification to the 'mass_update' action only.
    """
    if action != "mass_update":
        return

    # Crafting a details message of the changes using the form
    changes = []
    for field_name, value in form.cleaned_data.items():
        # Ignoring private fields like '_validate'
        if field_name.startswith("_"):
            continue
        changes.append((field_name, value))

    if len(changes) < 1:  # No modification applied.
        return

    field_names = ", ".join(field for field, _ in changes)
    message = f"Mass update applied on {field_names}."

    # Disabling the default notification from log_change() as we sent a custom
    # one right after.
    request._disable_notification = True

    Component = apps.get_model("component_catalog", "Component")

    for instance in queryset:  # Create 1 History entry per object in the QS.
        modeladmin.log_change(request, instance, message)

        # Update the completion_level if Mass Updating Components.
        if instance.__class__ == Component:
            instance.update_completion_level()

    # Send 1 email notification including all the modified objects.
    message = "Changes details:\n\n"
    message += "\n\n".join(f"* {field}\nNew value: {value}" for field, value in changes)

    send_notification_email_on_queryset(request.user, queryset, History.CHANGE, message)


def send_password_changed_email(user):
    subject = "Your DejaCode password has been changed."
    data = {
        "user": user,
        "site_url": settings.SITE_URL.rstrip("/"),
        "password_reset_url": reverse("password_reset"),
    }
    body = render_to_string("registration/password_change_email.txt", data)
    send_mail_task.delay(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])


def notify_on_user_locked_out(request, username, **kwargs):
    """
    Email system administrator and triggers 'user.locked_out'
    Webhook defined in the reference Dataspace when the `user_locked_out`
    signal is triggered.
    """
    access_attempt_url = reverse("admin:axes_accessattempt_changelist")
    access_attempt_absolute_url = request.build_absolute_uri(location=access_attempt_url)
    access_attempt_link = f"{access_attempt_absolute_url}?q={username}"
    user = DejacodeUser.objects.get_or_none(username=username)

    subject = "[DejaCode] Login attempt on locked account requires review!"
    message = f'Review access entry for username "{username}" at {access_attempt_link}\n'

    # In case the `username` is not found in the database,
    # we limit the notification to 1 per each `failure_limit` (default=5).
    if not user:
        credentials = get_credentials(username)
        failure_limit = get_failure_limit(request, credentials)
        failures = AxesDatabaseHandler().get_failures(request, credentials)
        skip_notify = bool(failures % failure_limit)
        if skip_notify:
            return

    if user:
        user_list_url = reverse("admin:dje_dejacodeuser_changelist")
        user_list_absolute_url = request.build_absolute_uri(location=user_list_url)
        user_list_link = f"{user_list_absolute_url}?q={username}"
        message += (
            f'"{username}" is an existing DejaCode user in Dataspace '
            f'"{user.dataspace.name}": {user_list_link}\n'
        )
        hint = (
            'The user forgot his password. Delete the "Attempted Access" entry '
            "from the admin view and tell the user to reset its password using "
            'the "Forgot password?" link.'
        )
    elif DejacodeUser.objects.filter(email=username).exists():
        hint = (
            f'The provided "{username}" exists as the email of a user account. '
            f"You can let the user know that the username should be used instead."
        )
    else:
        message += f'"{username}" is NOT an existing DejaCode user.\n'
        hint = "This looks like a malicious login attempt."

    message += f"Suggestion: {hint}"

    send_mail_to_admins_task.delay(subject, message)

    reference_dataspace = Dataspace.objects.get_reference()
    if not reference_dataspace:
        return

    find_and_fire_hook(
        "user.locked_out",
        instance=None,
        dataspace=reference_dataspace,
        payload_override={"text": f"{subject}\n{message}"},
    )


def notify_on_user_added_or_updated(instance, **kwargs):
    """
    Webhook defined in the reference Dataspace when the `post_save`
    signal is triggered a DejacodeUser.
    Not using the built-in 'user.added' nor 'user.updated' event as
    we want to trigger this for all users but only triggering the Webhooks of the
    reference Dataspace.
    """
    reference_dataspace = Dataspace.objects.get_reference()
    if not reference_dataspace:
        return

    find_and_fire_hook(
        "user.added_or_updated",
        instance=instance,
        dataspace=reference_dataspace,
    )
