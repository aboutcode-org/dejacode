#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging

from django import template
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from aboutcode.notifications import AbstractWebhookDelivery
from aboutcode.notifications import AbstractWebhookSubscription
from aboutcode.notifications import WebhookSubscriptionQuerySetMixin
from dje.models import DataspacedModel
from dje.models import DataspacedQuerySet

logger = logging.getLogger("dje")

WEBHOOK_EVENTS = [
    "request.added",
    "request.updated",
    "request_comment.added",
    "user.added_or_updated",
    "user.locked_out",
    "vulnerability.data_update",
]


class WebhookSubscriptionQuerySet(WebhookSubscriptionQuerySetMixin, DataspacedQuerySet):
    pass


class WebhookSubscription(DataspacedModel, AbstractWebhookSubscription):
    """
    A model to define Webhook subscriptions.

    This model captures the necessary details to configure a Webhook, including the
    target URL and the specific events that trigger the Webhook.
    """

    extra_payload = models.JSONField(
        blank=True,
        default=dict,
        help_text=_("Extra data as JSON to be included in the payload"),
    )
    extra_headers = models.JSONField(
        blank=True,
        default=dict,
        help_text=_("Extra headers as JSON to be included in the request"),
    )

    objects = WebhookSubscriptionQuerySet.as_manager()

    class Meta:
        unique_together = ("dataspace", "uuid")
        ordering = ["-created_date"]

    def __str__(self):
        return f"{self.event} => {self.target_url}"

    def dict(self):
        return {"uuid": str(self.uuid), "event": self.event, "target": self.target_url}

    def get_extra_headers(self):
        """Inject `hook_env` context in headers template values."""
        if hook_env := settings.DEJACODE_WEBHOOK_ENV:
            hook_env_context = template.Context(hook_env)
            return {
                key: self.render_template(value, hook_env_context)
                for key, value in self.extra_headers.items()
            }
        return self.extra_headers

    @staticmethod
    def render_template(value, hook_env_context):
        if "{{" in value and "}}" in value:
            return template.Template(value).render(hook_env_context)
        return value

    def get_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.extra_headers:
            headers.update(self.get_extra_headers())
        return headers

    def deliver(self, context, timeout=10, payload_override=None):
        if payload_override and self.extra_payload:
            payload_override = {**payload_override}
            payload_override.update(self.extra_payload)
        return super().deliver(context, timeout=timeout, payload_override=payload_override)

    def get_payload(self, instance):
        payload = instance.serialize_hook(hook=self)
        if self.extra_payload:
            payload["data"].update(self.extra_payload)
        return payload

    def create_delivery(self, payload, instance):
        return WebhookDelivery(
            dataspace=self.dataspace,
            webhook_subscription=self,
            target_url=self.target_url,
            payload=payload,
        )


class WebhookDelivery(DataspacedModel, AbstractWebhookDelivery):
    """
    Stores historical data for Webhook deliveries.

    This model keeps track of each delivery attempt made by a Webhook subscription,
    including the payload sent, the response received, and any errors that occurred
    during the delivery process.
    """

    webhook_subscription = models.ForeignKey(
        WebhookSubscription,
        related_name="deliveries",
        editable=False,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        help_text=_("The Webhook subscription associated with this delivery."),
    )

    class Meta(AbstractWebhookDelivery.Meta):
        unique_together = [("dataspace", "uuid")]
        ordering = ["-sent_date"]


def fire_webhooks(
    event_name,
    instance,
    dataspace=None,
    payload_override=None,
):
    """
    Enqueue async delivery for each active WebhookSubscription in `dataspace` matching `event_name`.
    If `dataspace` is not provided, uses the Dataspace of the `instance`.
    """
    from notification.tasks import deliver_webhook_task

    if not dataspace and instance:
        dataspace = instance.dataspace
    if not dataspace:
        raise AttributeError("Provide one of `dataspace` or `instance` argument.")

    filters = {
        "event": event_name,
        "is_active": True,
    }

    webhooks = WebhookSubscription.objects.scope(dataspace).filter(**filters)

    for webhook in webhooks:
        task_kwargs = {"webhook_subscription_pk": webhook.pk}
        if payload_override is not None:
            task_kwargs["payload_override"] = payload_override
        if instance is not None:
            task_kwargs["instance_app_label"] = instance._meta.app_label
            task_kwargs["instance_model_name"] = instance._meta.model_name
            task_kwargs["instance_pk"] = instance.pk
        deliver_webhook_task.delay(**task_kwargs)
