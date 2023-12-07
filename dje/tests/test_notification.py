# -*- coding: utf-8 -*-
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest.mock import MagicMock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from dje import notification
from dje.models import Dataspace
from dje.notification import send_notification_email
from dje.notification import send_notification_email_on_queryset
from dje.tasks import send_mail_to_admins_task
from organization.models import Owner
from organization.models import Subowner


@override_settings(
    EMAIL_HOST_USER="user",
    EMAIL_HOST_PASSWORD="password",
    EMAIL_HOST="localhost",
    EMAIL_PORT=25,
    DEFAULT_FROM_EMAIL="webmaster@localhost",
    ADMINS=[
        ("Admin1", "admin1@localhost.com"),
        ("Admin2", "admin2@localhost.com"),
    ],
)
class EmailNotificationTest(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Dataspace")
        self.user = get_user_model().objects.create_superuser(
            "test", "test@test.com", "t3st", self.dataspace, data_email_notification=True
        )
        self.owner = Owner.objects.create(name="Test Organization", dataspace=self.dataspace)

    @override_settings(
        EMAIL_HOST_USER=None,
        EMAIL_HOST_PASSWORD=None,
        EMAIL_HOST=None,
        EMAIL_PORT=None,
        DEFAULT_FROM_EMAIL=None,
    )
    def test_has_email_settings(self):
        self.assertFalse(notification.has_email_settings())
        settings.EMAIL_HOST_USER = "user"
        self.assertFalse(notification.has_email_settings())
        settings.EMAIL_HOST = "localhost"
        self.assertFalse(notification.has_email_settings())
        settings.EMAIL_PORT = 25
        self.assertFalse(notification.has_email_settings())
        settings.DEFAULT_FROM_EMAIL = "webmaster@localhost"
        self.assertTrue(notification.has_email_settings())
        # The password is not required when the server is non-secured
        settings.EMAIL_HOST_PASSWORD = "password"
        self.assertTrue(notification.has_email_settings())

    def test_get_data_update_recipients(self):
        email_list = [self.user.email]
        self.assertEqual(
            email_list, get_user_model().objects.get_data_update_recipients(self.dataspace)
        )

    def test_send_notification_email(self):
        # No recipient, no mail
        self.user.data_email_notification = False
        self.user.save()
        send_notification_email(self.user, self.owner, notification.ADDITION)
        self.assertEqual(len(mail.outbox), 0)

        # Proper object and user, notification is sent
        self.user.data_email_notification = True
        self.user.save()
        send_notification_email(self.user, self.owner, notification.ADDITION)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, f'Added Owner: "{self.owner}"')

        # Sending a notification on a empty string object
        # Nothing is sent as it's not dataspace related
        send_notification_email(self.user, "", notification.ADDITION)
        self.assertEqual(len(mail.outbox), 1)

        # Sending a change notification with the 'No fields changed.' message
        # Nothing is sent
        send_notification_email(self.user, self.owner, notification.CHANGE, "No fields changed.")
        self.assertEqual(len(mail.outbox), 1)

        # Sending a change notification with a change message
        send_notification_email(self.user, self.owner, notification.CHANGE, "Some changes...")

        self.assertEqual(len(mail.outbox), 2)

    def test_send_notification_email_on_queryset(self):
        self.assertEqual(len(mail.outbox), 0)
        queryset = Owner.objects.all()

        # No recipient, no mail
        self.user.data_email_notification = False
        self.user.save()
        send_notification_email_on_queryset(self.user, queryset, notification.CHANGE)
        self.assertEqual(len(mail.outbox), 0)

        # Proper object and user, notification is sent
        self.user.data_email_notification = True
        self.user.save()
        send_notification_email_on_queryset(self.user, queryset, notification.CHANGE)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(queryset), 1)
        self.assertEqual(mail.outbox[0].subject, f'Updated Owner: "{self.owner}"')

        # Using an empty queryset, nothing is sent
        send_notification_email_on_queryset(self.user, [], notification.CHANGE)
        self.assertEqual(len(mail.outbox), 1)

        # Using a queryset of non-dataspace related object (empty strings)
        send_notification_email_on_queryset(self.user, ["", ""], notification.CHANGE)
        self.assertEqual(len(mail.outbox), 1)

        Owner.objects.create(name="Organization2", dataspace=self.dataspace)
        queryset = Owner.objects.all()

        self.assertEqual(len(queryset), 2)
        send_notification_email_on_queryset(self.user, queryset, notification.CHANGE)
        self.assertEqual(mail.outbox[1].subject, "Multiple Owners updated")
        self.assertIn(str(self.owner), mail.outbox[1].body)

    def test_notification_with_body_containing_unicode_chars(self):
        line = "Ã™â€ž"
        self.assertEqual(len(mail.outbox), 0)
        Owner.objects.create(name="Test2 Organization", dataspace=self.dataspace)
        queryset = Owner.objects.all()

        # Proper object and user, notification is sent
        self.user.data_email_notification = True
        self.user.save()
        send_notification_email_on_queryset(self.user, queryset, notification.CHANGE, line)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(queryset), 2)
        self.assertEqual(mail.outbox[0].subject, "Multiple Owners updated")
        self.assertTrue(str(mail.outbox[0].body).find("\u2122") > 0)

    def test_notification_multiline_subject(self):
        # Use a mock object to test that the subject does not have linebreaks
        # and is not over 255 chars.
        multiline_name = """* zstream.h - C++ interface to the
        'zlib' general purpose compression library\r\n * $Id: zstream.h 1.
        [Filing text to test the length, Filing text to test the length,
        Filing text to test the length, Filing text to test the length,
        Filing text to test the length, Filing text to test the length,
        Filing text to test the length, Filing text to test the length]
        """
        instance = MagicMock()
        instance._meta.verbose_name = multiline_name
        instance.dataspace = self.dataspace

        send_notification_email(self.user, instance, notification.DELETION)
        self.assertEqual(len(mail.outbox), 1)
        subject = mail.outbox[0].subject
        self.assertTrue("zstream.h" in multiline_name)
        self.assertTrue("zstream.h" in subject)

        # We want to make sure the subject do not contain newlines
        self.assertFalse("\r" in subject)
        self.assertFalse("\n" in subject)
        # Also, the subject need to be shorter than 255 chars
        self.assertTrue(len(subject) <= 255)

    def test_notification_changes_details(self):
        # Make sure the changes details of the instance are present in the
        # notification
        self.client.login(username="test", password="t3st")
        owner = Owner.objects.create(
            name="Org", homepage_url="http://www.org.com/", dataspace=self.dataspace
        )

        url = owner.get_admin_url()
        params = {
            "key": str(owner.pk),
            "name": "Name",
            "type": "Organization",
            "homepage_url": "",
            "contact_info": "Contact information",
            "notes": "Notes",
            "related_children-TOTAL_FORMS": 0,
            "related_children-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        self.client.post(url, params)
        notification_body = mail.outbox[0].body

        details = [
            'Changes details for Owner "Name"',
            "* name\nOld value: Org\nNew value: Name",
            "* homepage_url\nOld value: http://www.org.com/\nNew value: ",
            "* contact_info\nOld value: \nNew value: Contact information",
            "* notes\nOld value: \nNew value: Notes",
        ]

        for line in details:
            self.assertTrue(line in notification_body)

    def test_notification_changes_details_related(self):
        # Make sure the changes details of the instance and the related are
        # present in the notification
        self.client.login(username="test", password="t3st")
        owner = Owner.objects.create(name="Org", dataspace=self.dataspace)
        person = Owner.objects.create(name="person", type="Person", dataspace=self.dataspace)
        person2 = Owner.objects.create(name="person2", type="Person", dataspace=self.dataspace)
        subowner = Subowner.objects.create(
            parent=owner,
            child=person,
            start_date="2011-12-06",
            end_date="2011-12-08",
            dataspace=owner.dataspace,
        )

        url = owner.get_admin_url()
        params = {
            "key": str(owner.pk),
            "name": "New Name",
            "type": "Organization",
            "related_children-TOTAL_FORMS": 1,
            "related_children-INITIAL_FORMS": 1,
            "related_children-0-id": str(subowner.id),
            "related_children-0-parent": str(owner.pk),
            "related_children-0-child": str(person2.pk),
            "related_children-0-start_date": "",
            "related_children-0-end_date": "",
            "related_children-0-notes": "Notes",
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        self.client.post(url, params)
        notification_body = mail.outbox[0].body

        details = [
            'Changes details for Owner "New Name"',
            "* name\nOld value: Org\nNew value: New Name",
            'Changes details for Subowner "Parent: New Name ; Child: person2"',
            "* child\nOld value: person\nNew value: person2",
            "* notes\nOld value: \nNew value: Notes",
            "* start_date\nOld value: 2011-12-06\nNew value: None",
            "* end_date\nOld value: 2011-12-08\nNew value: None",
        ]

        for line in details:
            self.assertTrue(line in notification_body)

    def test_notification_changes_details_related_addition(self):
        # The change is an ADDITION of a related (inlines)
        # We do not give details on the related ADDITION
        self.client.login(username="test", password="t3st")

        owner = Owner.objects.create(name="Org", type="Organization", dataspace=self.dataspace)
        person = Owner.objects.create(name="person", type="Person", dataspace=self.dataspace)

        url = owner.get_admin_url()
        params = {
            "key": str(owner.pk),
            "name": owner.name,
            "type": "Organization",
            "related_children-TOTAL_FORMS": 1,
            "related_children-INITIAL_FORMS": 0,
            "related_children-0-parent": str(owner.pk),
            "related_children-0-child": str(person.pk),
            "related_children-0-start_date": "",
            "related_children-0-end_date": "",
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        self.client.post(url, params)
        notification_body = mail.outbox[0].body
        self.assertTrue("Added subowner “Parent: Org ; Child: person”." in notification_body)

    def test_notification_delete_selected_action(self):
        org = Owner.objects.create(name="Owner2", dataspace=self.dataspace)
        self.assertEqual(2, Owner.objects.count())
        self.client.login(username="test", password="t3st")
        url = reverse("admin:organization_owner_changelist")

        data = {
            "_selected_action": [org.id, self.owner.id],
            "action": "delete_selected",
            "post": "yes",
        }

        response = self.client.post(url, data, follow=True)
        self.assertEqual(0, Owner.objects.count())
        msg = '<li class="grp-success">Successfully deleted 2 owners.</li>'
        self.assertContains(response, msg)

        self.assertTrue("Multiple Owners removed" in mail.outbox[0].subject)

    def test_notification_delete_selected_action_select_across(self):
        # Same as test_notification_delete_selected_action with select_across
        org = Owner.objects.create(name="Owner2", dataspace=self.dataspace)
        self.assertEqual(2, Owner.objects.count())
        self.client.login(username="test", password="t3st")
        url = reverse("admin:organization_owner_changelist")

        # '_selected_action' should not matter as 'select_across' is True.
        data = {
            "_selected_action": org.id,
            "action": "delete_selected",
            "post": "yes",
            "select_across": 1,
        }

        response = self.client.post(url, data, follow=True)
        self.assertEqual(0, Owner.objects.count())
        msg = '<li class="grp-success">Successfully deleted 2 owners.</li>'
        self.assertContains(response, msg)

        self.assertTrue("Multiple Owners removed" in mail.outbox[0].subject)

    def test_send_mail_to_admins_task(self):
        send_mail_to_admins_task("subject", "message")
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.subject, "subject")
        self.assertEqual(email.body, "message")
        self.assertEqual(email.from_email, "webmaster@localhost")
        self.assertEqual(
            email.to,
            [
                ("Admin1", "admin1@localhost.com"),
                ("Admin2", "admin2@localhost.com"),
            ],
        )
