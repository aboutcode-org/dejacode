#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NotificationConfig(AppConfig):
    name = "notification"
    verbose_name = _("Notification")

    def ready(self):
        from django.db.models.signals import post_save

        from notification.models import fire_webhooks
        from workflow.models import Request
        from workflow.models import RequestComment

        def fire_request_webhook(sender, instance, created, **kwargs):
            event = "request.added" if created else "request.updated"
            fire_webhooks(event, instance)

        def fire_request_comment_webhook(sender, instance, created, **kwargs):
            if created:
                fire_webhooks("request_comment.added", instance)

        post_save.connect(fire_request_webhook, sender=Request, weak=False)
        post_save.connect(fire_request_comment_webhook, sender=RequestComment, weak=False)
