#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging

from django.apps import apps

from django_rq import job

from notification.models import WebhookSubscription

logger = logging.getLogger("dje")


@job
def deliver_webhook_task(
    webhook_subscription_uuid,
    payload_override=None,
    instance_app_label=None,
    instance_model_name=None,
    instance_pk=None,
):
    """Deliver a webhook payload to the target URL of the given WebhookSubscription."""
    try:
        webhook_subscription = WebhookSubscription.objects.get(uuid=webhook_subscription_uuid)
    except WebhookSubscription.DoesNotExist:
        logger.error(f"WebhookSubscription uuid={webhook_subscription_uuid} not found.")
        return

    instance = None
    if instance_app_label and instance_model_name and instance_pk:
        try:
            model_class = apps.get_model(instance_app_label, instance_model_name)
            instance = model_class.objects.get(pk=instance_pk)
        except Exception:
            logger.error(
                f"Instance {instance_app_label}.{instance_model_name} pk={instance_pk} not found."
            )
            return

    webhook_subscription.deliver(instance, payload_override=payload_override)
