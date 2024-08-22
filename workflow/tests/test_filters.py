#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.db.models.fields import BLANK_CHOICE_DASH
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dje.models import Dataspace
from dje.tests import create_superuser
from dje.tests import create_user
from workflow.filters import RequestFilterSet
from workflow.models import Priority
from workflow.models import Request
from workflow.models import RequestTemplate


class RequestFilterTest(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="Other")
        self.nexb_user = create_superuser("nexb_user", self.nexb_dataspace)
        self.basic_user = create_user(
            "basic_user", self.nexb_dataspace, workflow_email_notification=True
        )
        self.other_user = create_superuser("other_user", self.other_dataspace)
        self.requester_user = create_user("requester_user", self.nexb_dataspace)

        self.priority1 = Priority.objects.create(label="Urgent", dataspace=self.nexb_dataspace)
        self.priority2 = Priority.objects.create(label="Low", dataspace=self.nexb_dataspace)
        self.other_priority = Priority.objects.create(label="Top", dataspace=self.other_dataspace)

        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.product_ct = ContentType.objects.get(app_label="product_portfolio", model="product")

        self.request_template1 = RequestTemplate.objects.create(
            name="Template1",
            description="Header Desc1",
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
        )

        self.other_template = RequestTemplate.objects.create(
            name="Template2",
            description="Header Desc1",
            dataspace=self.other_dataspace,
            content_type=self.component_ct,
        )

        self.request1 = Request.objects.create(
            title="Title1",
            request_template=self.request_template1,
            requester=self.nexb_user,
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
            priority=self.priority1,
        )

        self.request2 = Request.objects.create(
            title="SomeTitle",
            request_template=self.request_template1,
            requester=self.basic_user,
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
            priority=self.priority2,
            status=Request.Status.CLOSED,
        )

        self.other_request = Request.objects.create(
            title="OtherTitle",
            request_template=self.other_template,
            requester=self.other_user,
            dataspace=self.other_dataspace,
            content_type=self.component_ct,
        )

    def test_request_filter_no_dataspace(self):
        with self.assertRaises(AttributeError):
            RequestFilterSet()

        self.assertTrue(RequestFilterSet(dataspace=self.nexb_dataspace))

    def test_request_filter_dataspace_scoping(self):
        request_filter = RequestFilterSet(dataspace=self.nexb_dataspace)

        qs = request_filter.filters["request_template"].queryset
        self.assertTrue(self.request_template1 in qs)
        self.assertFalse(self.other_template in qs)

        qs = request_filter.filters["requester"].queryset
        self.assertTrue(self.nexb_user in qs)
        self.assertTrue(self.basic_user in qs)
        self.assertFalse(self.requester_user in qs)
        self.assertFalse(self.other_user in qs)

        qs = request_filter.filters["assignee"].queryset
        self.assertFalse(self.nexb_user in qs)
        # Non-admin cannot be assignee
        self.assertFalse(self.basic_user in qs)
        self.assertFalse(self.requester_user in qs)
        self.assertFalse(self.other_user in qs)

        qs = request_filter.filters["priority"].queryset
        self.assertTrue(self.priority1 in qs)
        self.assertTrue(self.priority2 in qs)
        self.assertFalse(self.other_priority in qs)

        self.client.login(username=self.nexb_user.username, password="secret")
        response = self.client.get(reverse("workflow:request_list"))
        self.assertContains(response, self.nexb_user.username)
        self.assertContains(response, self.basic_user.username)
        self.assertNotContains(response, self.requester_user.username)
        self.assertNotContains(response, self.other_user.username)

        self.assertContains(response, "?requester={}".format(self.nexb_user.username))
        self.assertContains(response, "?requester={}".format(self.basic_user.username))
        self.assertNotContains(response, "?requester={}".format(self.requester_user.username))
        self.assertNotContains(response, "?requester={}".format(self.other_user.username))

    def test_request_filterset_related_only_values_filter(self):
        self.assertEqual(
            ["status", "request_template", "requester", "assignee", "priority"],
            RequestFilterSet.related_only,
        )

        scoped_qs = Request.objects.scope(self.nexb_dataspace)

        filterset = RequestFilterSet(dataspace=self.nexb_dataspace, queryset=scoped_qs)
        self.assertEqual([self.request2, self.request1], list(filterset.qs))
        self.assertEqual(
            [self.basic_user, self.nexb_user], list(filterset.filters["requester"].queryset)
        )
        self.assertEqual([], list(filterset.filters["assignee"].queryset))
        self.assertEqual(
            [self.priority2, self.priority1], list(filterset.filters["priority"].queryset)
        )
        self.assertEqual(
            [BLANK_CHOICE_DASH[0], ("open", "Open"), ("closed", "Closed")],
            list(filterset.filters["status"].field.choices),
        )

        filterset = RequestFilterSet(
            dataspace=self.nexb_dataspace, queryset=scoped_qs, data={"q": "no_match"}
        )
        self.assertEqual([], list(filterset.qs))
        self.assertEqual([], list(filterset.filters["requester"].queryset))
        self.assertEqual([], list(filterset.filters["assignee"].queryset))
        self.assertEqual([], list(filterset.filters["priority"].queryset))
        self.assertEqual(BLANK_CHOICE_DASH, list(filterset.filters["status"].field.choices))

        filterset = RequestFilterSet(
            dataspace=self.nexb_dataspace, queryset=scoped_qs, data={"q": self.request1.title}
        )
        self.assertEqual([self.request1], list(filterset.qs))
        self.assertEqual([self.nexb_user], list(filterset.filters["requester"].queryset))
        self.assertEqual([], list(filterset.filters["assignee"].queryset))
        self.assertEqual([self.priority1], list(filterset.filters["priority"].queryset))
        self.assertEqual(
            [BLANK_CHOICE_DASH[0], ("open", "Open")],
            list(filterset.filters["status"].field.choices),
        )

        # The current filter value does not apply to itself
        filterset = RequestFilterSet(
            dataspace=self.nexb_dataspace, queryset=scoped_qs, data={"status": self.request1.status}
        )
        self.assertEqual([self.request1], list(filterset.qs))
        self.assertEqual([self.nexb_user], list(filterset.filters["requester"].queryset))
        self.assertEqual([], list(filterset.filters["assignee"].queryset))
        self.assertEqual([self.priority1], list(filterset.filters["priority"].queryset))
        self.assertEqual(
            [BLANK_CHOICE_DASH[0], ("open", "Open"), ("closed", "Closed")],
            list(filterset.filters["status"].field.choices),
        )

    def test_request_filter_search(self):
        self.request1.notes = "a bunch a notes"
        self.request1.save()

        request_filter = RequestFilterSet(dataspace=self.nexb_dataspace)
        self.assertEqual(3, len(request_filter.qs))

        data = {"q": ""}
        request_filter = RequestFilterSet(data=data, dataspace=self.nexb_dataspace)
        self.assertEqual(3, len(request_filter.qs))

        data = {"q": self.request1.notes}
        request_filter = RequestFilterSet(data=data, dataspace=self.nexb_dataspace)
        self.assertEqual(1, len(request_filter.qs))

        data = {"q": "wrong value"}
        request_filter = RequestFilterSet(data=data, dataspace=self.nexb_dataspace)
        self.assertEqual(0, len(request_filter.qs))

        product1 = self.product_ct.model_class().objects.create(
            name="Product1", version="2.5", dataspace=self.nexb_dataspace
        )
        self.request1.product_context = product1
        self.request1.save()

        data = {"q": product1.name}
        request_filter = RequestFilterSet(data=data, dataspace=self.nexb_dataspace)
        self.assertEqual(1, len(request_filter.qs))
        data = {"q": product1.version}
        request_filter = RequestFilterSet(data=data, dataspace=self.nexb_dataspace)
        self.assertEqual(1, len(request_filter.qs))
        data = {"q": str(product1)}
        request_filter = RequestFilterSet(data=data, dataspace=self.nexb_dataspace)
        self.assertEqual(1, len(request_filter.qs))

        component1 = self.component_ct.model_class().objects.create(
            name="Component1", version="8.9", dataspace=self.nexb_dataspace
        )
        self.request1.content_object = component1
        self.request1.save()

        data = {"q": component1.name}
        request_filter = RequestFilterSet(data=data, dataspace=self.nexb_dataspace)
        self.assertEqual(1, len(request_filter.qs))
        data = {"q": component1.version}
        request_filter = RequestFilterSet(data=data, dataspace=self.nexb_dataspace)
        self.assertEqual(1, len(request_filter.qs))
        data = {"q": str(component1)}
        request_filter = RequestFilterSet(data=data, dataspace=self.nexb_dataspace)
        self.assertEqual(1, len(request_filter.qs))

    def test_request_filter_sort_default_by_recent_activity(self):
        request_filter = RequestFilterSet(dataspace=self.nexb_dataspace)
        expected = "Recent activity (default)"
        self.assertEqual(expected, request_filter.filters["sort"].extra["empty_label"])
        self.assertEqual(self.other_request, request_filter.qs[0])

        self.request1.save()
        request_filter = RequestFilterSet(dataspace=self.nexb_dataspace)
        self.assertEqual(self.request1, request_filter.qs[0])

        self.other_request.save()
        self.assertEqual(self.other_request, request_filter.qs[0])

    def test_request_filter_sort_by_newest(self):
        request_filter = RequestFilterSet(dataspace=self.nexb_dataspace)
        expected = ("-created_date", "Newest")
        self.assertIn(expected, request_filter.filters["sort"].extra["choices"])
        self.assertEqual(self.other_request, request_filter.qs[0])

        Request.objects.filter(id=self.request1.id).update(created_date=timezone.now())
        data = {"sort": "-created_date"}
        request_filter = RequestFilterSet(data=data, dataspace=self.nexb_dataspace)
        self.assertEqual(self.request1, request_filter.qs[0])

    def test_request_filter_following(self):
        data = {"following": "yes"}
        request_filter = RequestFilterSet(data=data, dataspace=self.nexb_dataspace)
        self.assertEqual(3, len(request_filter.qs))

        mock_request = mock.Mock()
        mock_request.user = self.nexb_user
        request_filter = RequestFilterSet(
            data=data, request=mock_request, dataspace=self.nexb_dataspace
        )
        self.assertEqual(1, len(request_filter.qs))
