#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.conf import settings
from django.template.loader import render_to_string

from notifications.signals import notify as internal_notification

from dje.tasks import send_mail_task

# WARNING: Using the name `req` in place of `request` for Request instance,
# to avoid any conflict, especially in template contexts,
# with the HTTP `request` used everywhere in Django.


def get_recipient_emails(recipients, cc_emails):
    emails = {user.email for user in recipients if user.workflow_email_notification}

    if cc_emails:
        emails = set(cc_emails).union(emails)

    return list(emails)


def send_request_notification(http_request, req, created, extra=None):
    """
    Send an email notification following a Request creation or edition.
    An email is sent to the users involved in the Request, based on their
    `workflow_email_notification` flag.
    """
    content_object_verbose = f" for {req.content_object}" if req.content_object else ""
    action_user = req.requester if created else req.last_modified_by

    data = {
        "req": req,
        "content_object_verbose": content_object_verbose,
        "action": "submitted" if created else "updated",
        "action_user": action_user,
        "site_url": http_request.build_absolute_uri(location="/").rstrip("/"),
    }

    subject = (
        "Request {req}{content_object_verbose} {action} by {action_user} in {req.dataspace}"
    ).format(**data)

    template = "request_created_email.txt" if created else "request_updated_email.txt"
    body = render_to_string(f"workflow/{template}", data)

    recipients = req.get_involved_users()

    emails = get_recipient_emails(recipients, req.cc_emails)
    send_mail_task.delay(subject, body, settings.DEFAULT_FROM_EMAIL, emails)

    # Remove the `action_user` from the internal notification recipients
    recipients.discard(action_user)

    internal_notification.send(
        sender=action_user,
        verb="{} Request".format("submitted" if created else "updated"),
        action_object=req,
        recipient=list(recipients),
        description=extra.get("description") if extra else "",
    )


def send_request_comment_notification(http_request, comment, closed=False):
    """
    Send an email notification following the addition of a comment on a Request.
    An email is sent to the users involved in the Request except for the
    user responsible for this action, regardless of their email_notification flag.
    """
    req = comment.request

    content_object_verbose = ""
    if req.content_object:
        content_object_verbose = f" for {req.content_object}"

    data = {
        "comment": comment,
        "req": req,
        "action": "closed" if closed else "commented",
        "content_object_verbose": content_object_verbose,
        "site_url": http_request.build_absolute_uri(location="/").rstrip("/"),
    }

    subject = (
        "Request {req}{content_object_verbose} {action} by {comment.user} in {req.dataspace}"
    ).format(**data)

    body = render_to_string("workflow/comment_created_email.txt", data)

    recipients = req.get_involved_users()

    emails = get_recipient_emails(recipients, req.cc_emails)
    send_mail_task.delay(subject, body, settings.DEFAULT_FROM_EMAIL, emails)

    # Remove the `comment.user` from the internal notification recipients
    recipients.discard(comment.user)

    internal_notification.send(
        sender=comment.user,
        verb="commented on Request",
        action_object=req,
        recipient=list(recipients),
        description=comment.text,
    )


def request_slack_payload(req, created):
    color = "#5bb75b" if created else "#ff9d2e"
    action = "created" if created else "updated"
    user = req.requester if created else req.last_modified_by
    site_url = settings.SITE_URL.rstrip("/")

    def make_field_dict(title, value):
        return {"title": title, "value": value, "short": True}

    fields = [
        make_field_dict("Assigned to", f"{req.assignee}"),
        make_field_dict("Status", f"{req.get_status_display()}"),
    ]
    if req.priority:
        fields.append(make_field_dict("Priority", f"{req.priority}"))
    if req.product_context:
        fields.append(make_field_dict("Product context", f"{req.product_context}"))
    if req.content_object:
        content_object_link = (
            f"<{site_url}{req.content_object.get_absolute_url()}|{req.content_object}>"
        )
        fields.append(make_field_dict("Applies to", content_object_link))

    # https://api.slack.com/docs/messages/builder
    return {
        "attachments": [
            {
                "fallback": f"#{req.id} {req.title} {action} by {user}",
                "pretext": f"[DejaCode/{req.dataspace.name}] Request {action} by {user}",
                "color": color,
                "title": f"#{req.id} {req.title}",
                "title_link": f"{site_url}{req.get_absolute_url()}",
                "text": f"{req.request_template.name}",
                "fields": fields,
                "ts": f"{req.last_modified_date.timestamp()}",
            }
        ]
    }


def request_comment_slack_payload(comment):
    req = comment.request
    site_url = settings.SITE_URL.rstrip("/")

    pretext = (
        f"[DejaCode/{req.dataspace.name}] New comment by {comment.user} on Request "
        f"<{site_url}{req.get_absolute_url()}|#{req.id} {req.title}> "
        f"(assigned to {req.assignee})"
    )

    # https://api.slack.com/docs/messages/builder
    return {
        "attachments": [
            {
                "fallback": pretext,
                "pretext": pretext,
                "color": "#ff9d2e",
                "text": comment.text,
                "ts": f"{comment.last_modified_date.timestamp()}",
            }
        ]
    }
