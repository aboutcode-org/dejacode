#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import logging
from urllib.parse import urlparse

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.translation import gettext_lazy as _

import requests

logger = logging.getLogger(__name__)


class AbstractWebhookSubscription(models.Model):
    """
    Abstract base for Webhook subscription models.

    Subclasses must implement get_payload(context) and create_delivery(payload, context).
    Override get_slack_payload(context) to support Slack webhook URLs.
    """

    target_url = models.URLField(
        _("Target URL"),
        max_length=1024,
        blank=False,
        help_text=_(
            "The URL to which the POST request will be sent when the Webhook is triggered."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_(
            "Indicates whether the Webhook is currently active and should be triggered."
        ),
    )
    created_date = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        help_text=_("The date and time when the Webhook subscription was created."),
    )

    class Meta:
        abstract = True
        ordering = ["-created_date"]

    def get_payload(self, context):
        raise NotImplementedError

    def get_slack_payload(self, context):
        """Return a Slack-specific payload, or None to fall back to get_payload."""
        return None

    def create_delivery(self, payload, context):
        raise NotImplementedError

    def deliver(self, context, timeout=10):
        """Deliver this Webhook by sending a POST request to the target_url."""
        logger.info(f"Delivering Webhook {self.uuid}")

        if not self.is_active:
            logger.info(f"Webhook {self.uuid} is not active.")
            return False

        parsed = urlparse(self.target_url)
        if parsed.hostname == "hooks.slack.com" and (
            slack_payload := self.get_slack_payload(context)
        ):
            payload = slack_payload
        else:
            payload = self.get_payload(context)

        delivery = self.create_delivery(payload, context)

        try:
            response = requests.post(
                url=self.target_url,
                data=json.dumps(payload, cls=DjangoJSONEncoder),
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
        except requests.exceptions.RequestException as exception:
            logger.error(exception)
            delivery.delivery_error = str(exception)
            delivery.save()
            return delivery

        delivery.response_status_code = response.status_code
        delivery.response_text = response.text
        delivery.save()

        if delivery.success:
            logger.info(f"Webhook {self.uuid} delivered successfully.")
        else:
            logger.info(f"Webhook {self.uuid} returned a {response.status_code}.")

        return delivery


class AbstractWebhookDelivery(models.Model):
    """Abstract base for Webhook delivery history models."""

    target_url = models.URLField(
        _("Target URL"),
        max_length=1024,
        blank=False,
        help_text=_(
            "Stores a copy of the Webhook target URL in case the subscription object "
            "is deleted."
        ),
    )
    sent_date = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        help_text=_("The date and time when the Webhook was sent."),
    )
    payload = models.JSONField(
        blank=True,
        default=dict,
        help_text=_("The JSON payload that was sent to the target URL."),
    )
    response_status_code = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("The HTTP status code received in response to the Webhook request."),
    )
    response_text = models.TextField(
        blank=True,
        help_text=_("The text response received from the target URL."),
    )
    delivery_error = models.TextField(
        blank=True,
        help_text=_("Any error messages encountered during the Webhook delivery."),
    )

    class Meta:
        abstract = True
        verbose_name = _("webhook delivery")
        verbose_name_plural = _("webhook deliveries")
        ordering = ["-sent_date"]

    def __str__(self):
        return f"Webhook uuid={self.uuid} posted at {self.sent_date}"

    @property
    def delivered(self):
        return bool(self.response_status_code)

    @property
    def success(self):
        return self.response_status_code in (200, 201, 202)
