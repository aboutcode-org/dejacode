#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class NotificationQuerySet(models.QuerySet):
    def unread(self):
        return self.filter(unread=True)

    def mark_all_as_read(self):
        return self.unread().update(unread=False)

    def notify(self, recipients, actor, verb, **fields):
        """Create a Notification from the `actor` for each of the `recipients`."""
        notifications = [
            self.model(recipient=recipient, actor=actor, verb=verb, **fields)
            for recipient in recipients
        ]
        return self.bulk_create(notifications)


class Notification(models.Model):
    """An internal notification: `actor` `verb` `action_object`, sent to a `recipient`."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("recipient"),
    )
    unread = models.BooleanField(_("unread"), default=True, db_index=True)
    actor_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="notify_actor",
        verbose_name=_("actor content type"),
    )
    actor_object_id = models.CharField(_("actor object id"), max_length=255)
    actor = GenericForeignKey("actor_content_type", "actor_object_id")
    verb = models.CharField(_("verb"), max_length=255)
    description = models.TextField(_("description"), blank=True, null=True)
    action_object_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="notify_action_object",
        verbose_name=_("action object content type"),
        blank=True,
        null=True,
    )
    action_object_object_id = models.CharField(
        _("action object object id"), max_length=255, blank=True, null=True
    )
    action_object = GenericForeignKey("action_object_content_type", "action_object_object_id")
    timestamp = models.DateTimeField(_("timestamp"), default=timezone.now, db_index=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ("-timestamp",)
        indexes = [
            models.Index(fields=["recipient", "unread"]),
        ]
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")

    def __str__(self):
        return f"{self.actor} {self.verb}"
