#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.test import TestCase

from dje.models import Dataspace
from dje.tests import create_user
from notifications.models import Notification


class NotificationModelTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.actor = create_user("actor", self.dataspace)
        self.recipient1 = create_user("recipient1", self.dataspace)
        self.recipient2 = create_user("recipient2", self.dataspace)

    def test_notification_model_str(self):
        notification = Notification.objects.create(
            recipient=self.recipient1, actor=self.actor, verb="commented"
        )
        self.assertEqual("actor commented", str(notification))

    def test_notification_queryset_unread_and_mark_all_as_read(self):
        unread = Notification.objects.create(
            recipient=self.recipient1, actor=self.actor, verb="unread"
        )
        Notification.objects.create(
            recipient=self.recipient1, actor=self.actor, verb="read", unread=False
        )
        other_recipient = Notification.objects.create(
            recipient=self.recipient2, actor=self.actor, verb="other"
        )

        self.assertEqual([unread], list(self.recipient1.notifications.unread()))

        self.assertEqual(1, self.recipient1.notifications.mark_all_as_read())
        self.assertEqual(0, self.recipient1.notifications.unread().count())
        other_recipient.refresh_from_db()
        self.assertTrue(other_recipient.unread)

    def test_notification_queryset_notify(self):
        notifications = Notification.objects.notify(
            recipients=[self.recipient1, self.recipient2],
            actor=self.actor,
            verb="updated",
            action_object=self.dataspace,
            description="details",
        )
        self.assertEqual(2, len(notifications))

        for recipient in [self.recipient1, self.recipient2]:
            notification = recipient.notifications.get()
            self.assertEqual(self.actor, notification.actor)
            self.assertEqual("updated", notification.verb)
            self.assertEqual(self.dataspace, notification.action_object)
            self.assertEqual("details", notification.description)
            self.assertTrue(notification.unread)

        self.assertEqual([], Notification.objects.notify(recipients=[], actor=self.actor, verb="x"))
