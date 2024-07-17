#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from guardian.shortcuts import assign_perm
from guardian.shortcuts import remove_perm

from component_catalog.models import Component
from dje.copier import copy_object
from dje.models import Dataspace
from dje.models import secure_queryset_relational_fields
from dje.tests import create_superuser
from dje.tests import create_user
from product_portfolio.tests.test_admin_guardian import refresh_product
from workflow.models import Question
from workflow.models import Request
from workflow.models import RequestAttachment
from workflow.models import RequestComment
from workflow.models import RequestEvent
from workflow.models import RequestTemplate


class WorkflowModelsTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.alt_dataspace = Dataspace.objects.create(name="Alternate")
        self.super_user = create_superuser("nexb_user", self.nexb_dataspace)
        self.basic_user = create_user("basic_user", self.nexb_dataspace)
        self.alt_user = create_superuser("alter_user", self.alt_dataspace)

        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.product_ct = ContentType.objects.get(app_label="product_portfolio", model="product")

        self.request_template1 = RequestTemplate.objects.create(
            name="Template1",
            description="Header Desc1",
            dataspace=self.super_user.dataspace,
            content_type=self.component_ct,
        )

        self.question1 = Question.objects.create(
            template=self.request_template1,
            label="Organization",
            help_text="Your Organization (Department) name",
            input_type="TextField",
            is_required=False,
            position=0,
            dataspace=self.super_user.dataspace,
        )

        self.question2 = Question.objects.create(
            template=self.request_template1,
            label="Project",
            help_text="Product/Project Name",
            input_type="TextField",
            is_required=True,
            position=1,
            dataspace=self.super_user.dataspace,
        )

        self.question3 = Question.objects.create(
            template=self.request_template1,
            label="YesNo",
            help_text="Help?",
            input_type="BooleanField",
            is_required=True,
            position=2,
            dataspace=self.super_user.dataspace,
        )

        self.request1 = self.request_template1.create_request(
            title="Title1", requester=self.super_user
        )

        self.request_template2 = RequestTemplate.objects.create(
            name="Template2",
            description="Header Desc2",
            dataspace=self.super_user.dataspace,
            content_type=self.product_ct,
        )

        self.product1 = self.product_ct.model_class().objects.create(
            name="p1", dataspace=self.nexb_dataspace
        )

        self.request2 = self.request_template2.create_request(
            title="Title2", requester=self.super_user
        )

        self.example_serialized_data = {
            self.question1.label: "Owner1",
            self.question2.label: "Project1",
            self.question3.label: "1",
        }

    def test_request_model_get_serialized_data_as_list(self):
        self.assertIsInstance(self.request1.serialized_data, str)

        old_as_list = [{"input_type": "CharField", "value": "a", "label": "Project"}]
        self.request1.serialized_data = json.dumps(old_as_list)
        self.request1.save()
        self.request1.refresh_from_db()
        self.assertEqual({}, self.request1.get_serialized_data())
        self.assertEqual([], self.request1.get_serialized_data_as_list())

        self.request1.serialized_data = json.dumps(self.example_serialized_data)
        self.request1.save()
        self.request1.refresh_from_db()
        expected = [
            {"input_type": "TextField", "value": "Owner1", "label": "Organization"},
            {"input_type": "TextField", "value": "Project1", "label": "Project"},
            {"input_type": "BooleanField", "value": "1", "label": "YesNo"},
        ]
        self.assertEqual(expected, self.request1.get_serialized_data_as_list())

        # ValueError: No JSON object could be decoded
        self.request1.serialized_data = str(self.example_serialized_data)[10:30]
        self.request1.save()
        self.request1.refresh_from_db()
        self.assertEqual([], self.request1.get_serialized_data_as_list())

    def test_request_model_get_serialized_data_as_html(self):
        self.assertEqual("", self.request1.serialized_data)
        self.assertEqual("", self.request1.get_serialized_data_as_html())

        self.request1.serialized_data = json.dumps(self.example_serialized_data)
        self.request1.save()
        self.request1.refresh_from_db()

        expected = "Organization: Owner1<br>Project: Project1<br>YesNo: Yes"
        self.assertEqual(expected, self.request1.get_serialized_data_as_html())

    def test_request_model_get_serialized_data_as_html_unicode_content(self):
        self.request1.serialized_data = json.dumps({self.question1.label: "\u2013"})
        self.request1.save()
        self.request1.refresh_from_db()

        expected = "Organization: \u2013<br>Project: None<br>YesNo: No"
        self.assertEqual(expected, self.request1.get_serialized_data_as_html())

        # Forcing a non-unicode string for the template
        self.assertEqual(
            "\u2013<br>None<br>No",
            self.request1.get_serialized_data_as_html(html_template="{value}"),
        )

    def test_request_model_get_involved_users(self):
        self.assertIsNone(self.request1.assignee)
        expected = {self.request1.requester}
        self.assertEqual(expected, self.request1.get_involved_users())

        self.request1.assignee = self.basic_user
        self.request1.save()
        expected = {
            self.request1.requester,
            self.request1.assignee,
        }
        self.assertEqual(expected, self.request1.get_involved_users())

        comment_user = create_user("comment_user", self.nexb_dataspace)
        self.request1.comments.create(user=comment_user, text="Com", dataspace=self.nexb_dataspace)
        expected = {
            self.request1.requester,
            self.request1.assignee,
            comment_user,
        }
        self.assertEqual(expected, self.request1.get_involved_users())

        edit_user = create_user("edit_user", self.nexb_dataspace)
        closed_user = create_user("closed_user", self.nexb_dataspace)
        attachment_user = create_user("attachment_user", self.nexb_dataspace)
        self.request1.events.create(
            user=edit_user, text="Edit", event_type=RequestEvent.EDIT, dataspace=self.nexb_dataspace
        )
        self.request1.events.create(
            user=closed_user,
            text="Closed",
            event_type=RequestEvent.CLOSED,
            dataspace=self.nexb_dataspace,
        )
        self.request1.events.create(
            user=attachment_user,
            text="Attach",
            event_type=RequestEvent.ATTACHMENT,
            dataspace=self.nexb_dataspace,
        )

        expected = {
            self.request1.requester,
            self.request1.assignee,
            comment_user,
            edit_user,
            closed_user,
            attachment_user,
        }
        self.assertEqual(expected, self.request1.get_involved_users())

    def test_request_template_manager_actives(self):
        # No RequestTemplate active
        RequestTemplate.objects.update(is_active=False)
        self.assertQuerySetEqual([], RequestTemplate.objects.actives())

        # 1 RequestTemplate active
        self.request_template1.is_active = True
        self.request_template1.save()
        self.assertEqual(1, RequestTemplate.objects.actives().count())

        # 2 RequestTemplate active
        self.request_template2.is_active = True
        self.request_template2.save()
        self.assertEqual(2, RequestTemplate.objects.actives().count())

    def test_request_template_manager_for_content_type(self):
        qs = RequestTemplate.objects.for_content_type(self.component_ct)
        self.assertEqual(1, qs.count())
        qs = RequestTemplate.objects.for_content_type(self.product_ct)
        self.assertEqual(1, qs.count())

    def test_request_template_manager_get_by_natural_key(self):
        request_template = RequestTemplate.objects.get_by_natural_key(
            self.request_template1.dataspace.name, self.request_template1.uuid
        )
        self.assertEqual(self.request_template1, request_template)

    def test_request_template_model_natural_key(self):
        dataspace_name = self.request_template1.dataspace.name
        self.assertEqual(
            (dataspace_name, self.request_template1.uuid), self.request_template1.natural_key()
        )

    def test_request_template_model_get_absolute_url(self):
        self.assertEqual(
            self.request_template1.get_absolute_url(),
            "/requests/form/{}/".format(self.request_template1.uuid),
        )

    def test_request_template_model_create_request(self):
        request = self.request_template1.create_request(
            requester=self.super_user,
        )
        self.assertEqual(self.request_template1, request.request_template)
        self.assertEqual(self.request_template1.content_type, request.content_type)
        self.assertEqual(self.request_template1.dataspace, request.dataspace)
        self.assertEqual(self.request_template1.dataspace, request.dataspace)
        self.assertEqual(self.super_user, request.requester)
        self.assertEqual(Request.Status.OPEN, request.status)
        self.assertIsNone(request.assignee)
        self.assertFalse(request.is_private)
        self.assertIsNone(request.priority)
        self.assertIsNone(request.cc_emails)

        self.request_template1.default_assignee = self.super_user
        self.request_template1.save()
        request = self.request_template1.create_request(
            requester=self.super_user,
            title="Title",
            status=Request.Status.OPEN,
        )
        self.assertEqual("Title", request.title)
        self.assertEqual(Request.Status.OPEN, request.status)
        self.assertEqual(self.super_user, request.assignee)

    def test_copy_request_template(self):
        copied_object = copy_object(self.request_template1, self.alt_dataspace, self.super_user)

        self.assertEqual(self.alt_dataspace, copied_object.dataspace)
        self.assertEqual(self.request_template1.uuid, copied_object.uuid)
        self.assertEqual(self.request_template1.name, copied_object.name)
        self.assertEqual(self.request_template1.description, copied_object.description)
        # Check the many2many copy
        self.assertEqual(self.request_template1.questions.count(), copied_object.questions.count())

    def test_request_manager_unassigned(self):
        self.assertIsNone(self.request1.assignee)
        self.assertEqual(
            [self.request1, self.request2], list(Request.objects.unassigned().order_by("id"))
        )

    def test_request_manager_assigned_to(self):
        self.request1.assignee = self.super_user
        self.request1.save()
        self.assertEqual([self.request1], list(Request.objects.assigned_to(self.super_user)))

    def test_request_manager_followed_by(self):
        self.assertEqual([], list(Request.objects.followed_by(self.basic_user)))

        comment1 = RequestComment.objects.create(
            request=self.request1,
            user=self.basic_user,
            text="Comment1",
            dataspace=self.nexb_dataspace,
        )
        self.assertEqual([self.request1], list(Request.objects.followed_by(self.basic_user)))

        comment1.delete()
        self.assertEqual([], list(Request.objects.followed_by(self.basic_user)))
        attachment1 = RequestAttachment.objects.create(
            request=self.request1,
            uploader=self.basic_user,
            file="filename.ext",
            dataspace=self.nexb_dataspace,
        )
        self.assertEqual([self.request1], list(Request.objects.followed_by(self.basic_user)))

        attachment1.delete()
        self.assertEqual([], list(Request.objects.followed_by(self.basic_user)))
        self.request1.assignee = self.basic_user
        self.request1.save()
        self.assertEqual([self.request1], list(Request.objects.followed_by(self.basic_user)))

    def test_request_queryset_status_methods(self):
        self.request1.status = Request.Status.OPEN
        self.request1.save()
        self.request2.status = Request.Status.CLOSED
        self.request2.save()
        request3 = self.request_template2.create_request(
            title="Title3",
            requester=self.super_user,
            status=Request.Status.DRAFT,
        )

        qs = Request.objects.open()
        self.assertIn(self.request1, qs)
        self.assertNotIn(self.request2, qs)
        self.assertNotIn(request3, qs)

        qs = Request.objects.closed()
        self.assertNotIn(self.request1, qs)
        self.assertIn(self.request2, qs)
        self.assertNotIn(request3, qs)

    def test_request_model_is_draft_property(self):
        self.request1.status = Request.Status.OPEN
        self.assertFalse(self.request1.is_draft)

        self.request1.status = Request.Status.DRAFT
        self.assertTrue(self.request1.is_draft)

    def _base_test_request_manager_product_secured(self, method_name):
        remove_perm("view_product", self.basic_user, self.product1)
        self.request2.product_context = None
        self.request2.object_id = None
        self.request2.save()
        manager_method = getattr(Request.objects, method_name)
        self.assertEqual(2, manager_method(user=self.basic_user).count())
        self.assertEqual(2, manager_method(user=self.super_user).count())

        self.request2.product_context = self.product1
        self.request2.save()
        self.assertEqual(2, manager_method(user=self.super_user).count())
        self.assertEqual(1, manager_method(user=self.basic_user).count())
        self.assertIn(self.request1, manager_method(user=self.basic_user))
        assign_perm("view_product", self.basic_user, self.product1)
        self.assertEqual(2, manager_method(user=self.basic_user).count())

        remove_perm("view_product", self.basic_user, self.product1)
        self.request2.product_context = None
        self.request2.object_id = self.product1.id
        self.request2.save()
        self.assertEqual(2, manager_method(user=self.super_user).count())
        self.assertEqual(1, manager_method(user=self.basic_user).count())
        self.assertIn(self.request1, manager_method(user=self.basic_user))
        assign_perm("view_product", self.basic_user, self.product1)
        self.assertEqual(2, manager_method(user=self.basic_user).count())

    def test_request_manager_product_secured_all_methods(self):
        methods = [
            "product_secured",
            "for_list_view",
            "for_details_view",
            "for_edit_view",
        ]

        for method_name in methods:
            self._base_test_request_manager_product_secured(method_name)

    def test_request_manager_product_secured_for_content_object(self):
        manager = Request.objects.for_content_object

        self.request2.object_id = self.product1.id
        self.request2.save()

        self.assertIn(self.request2, manager(self.product1))
        self.assertIn(self.request2, manager(self.product1, self.super_user))
        self.assertNotIn(self.request2, manager(self.product1, self.basic_user))

        assign_perm("view_product", self.basic_user, self.product1)
        self.assertIn(self.request2, manager(self.product1, self.basic_user))

    def test_request_manager_product_secured_for_activity_tab(self):
        manager = Request.objects.for_activity_tab

        self.request2.object_id = self.product1.id
        self.request2.save()

        self.assertIn(self.request2, manager(self.product1, self.super_user))
        self.assertNotIn(self.request2, manager(self.product1, self.basic_user))

        assign_perm("view_product", self.basic_user, self.product1)
        self.assertIn(self.request2, manager(self.product1, self.basic_user))

    def test_secure_queryset_relational_fields(self):
        alt_rt = copy_object(self.request_template1, self.alt_dataspace, self.super_user)
        alt_request = Request.objects.create(
            title="Alternate",
            request_template=alt_rt,
            requester=self.alt_user,
            dataspace=self.alt_dataspace,
            content_type=self.product_ct,
        )

        self.assertEqual(3, Request.objects.count())
        queryset = Request.objects.all()

        qs = secure_queryset_relational_fields(queryset, self.alt_user)
        self.assertEqual(1, qs.count())
        self.assertNotIn(self.request1, qs)
        self.assertNotIn(self.request2, qs)
        self.assertIn(alt_request, qs)

        qs = secure_queryset_relational_fields(queryset, self.basic_user)
        self.assertEqual(2, qs.count())
        self.assertIn(self.request1, qs)
        self.assertIn(self.request2, qs)
        self.assertNotIn(alt_request, qs)

        qs = secure_queryset_relational_fields(queryset, self.super_user)
        self.assertEqual(2, qs.count())
        self.assertIn(self.request1, qs)
        self.assertIn(self.request2, qs)
        self.assertNotIn(alt_request, qs)

        # Adding a Product on the product_context FK
        self.request1.product_context = self.product1
        self.request1.save()

        qs = secure_queryset_relational_fields(queryset, self.alt_user)
        self.assertEqual(1, qs.count())
        self.assertNotIn(self.request1, qs)
        self.assertNotIn(self.request2, qs)
        self.assertIn(alt_request, qs)

        qs = secure_queryset_relational_fields(queryset, self.basic_user)
        self.assertEqual(1, qs.count())
        self.assertNotIn(self.request1, qs)
        self.assertIn(self.request2, qs)
        self.assertNotIn(alt_request, qs)

        assign_perm("view_product", self.basic_user, self.product1)
        qs = secure_queryset_relational_fields(queryset, self.basic_user)
        self.assertEqual(2, qs.count())
        self.assertIn(self.request1, qs)
        self.assertIn(self.request2, qs)
        self.assertNotIn(alt_request, qs)

        qs = secure_queryset_relational_fields(queryset, self.super_user)
        self.assertEqual(2, qs.count())
        self.assertIn(self.request1, qs)
        self.assertIn(self.request2, qs)
        self.assertNotIn(alt_request, qs)

    def test_request_mixin_methods_request_count(self):
        self.assertIsNone(self.product1.request_count)
        self.assertEqual(0, self.product1.count_requests())

        self.request2.object_id = self.product1.id
        self.request2.save()

        self.request2 = Request.objects.get(pk=self.request2.pk)
        self.assertEqual(self.product1, self.request2.content_object)
        self.assertEqual(str(self.product1), self.request2.content_object_repr)

        self.assertEqual(1, self.product1.count_requests())
        self.product1 = refresh_product(self.product1)
        self.assertEqual(1, self.product1.request_count)

        self.assertIn(self.request2, self.product1.get_requests(self.super_user))
        self.assertNotIn(self.request2, self.product1.get_requests(self.basic_user))
        assign_perm("view_product", self.basic_user, self.product1)
        self.assertIn(self.request2, self.product1.get_requests(self.basic_user))

        Request.objects.all().delete()
        self.assertEqual(0, self.product1.count_requests())
        self.product1 = refresh_product(self.product1)
        self.assertEqual(0, self.product1.request_count)

        component1 = Component.objects.create(name="c1", dataspace=self.nexb_dataspace)
        self.assertIsNone(component1.request_count)
        self.assertEqual(0, component1.count_requests())
        request1 = Request.objects.create(
            title="Title1",
            request_template=self.request_template1,
            requester=self.super_user,
            dataspace=self.super_user.dataspace,
            content_object=component1,
        )
        self.assertEqual(1, component1.count_requests())
        component1.refresh_from_db()
        self.assertEqual(1, component1.request_count)

        # The content_object is deleted and the request saved again.
        component1.delete()
        request1.save()

        # Updating the content_object where the current one does not exist anymore
        component2 = Component.objects.create(name="c2", dataspace=self.nexb_dataspace)
        request1.content_object = component2
        request1.save()

    def test_request_comment_model_as_html(self):
        cases = [
            ("comment1", "<p>comment1</p>"),
            (
                "https://nexb.com",
                '<p><a href="https://nexb.com" rel="nofollow">https://nexb.com</a></p>',
            ),
            ("> quote", "<blockquote>\n<p>quote</p>\n</blockquote>"),
            ("<script>", "&lt;script&gt;"),
            ('<a href="ok" target="_blank">', '<p><a href="ok" rel="nofollow"></a></p>'),
            ('<a onclick="evil()">', "<p><a></a></p>"),
            (
                "<<script>script>evil()<</script>/script>",
                "<p>&lt;&lt;script&gt;script&gt;evil()&lt;&lt;/script&gt;/script&gt;</p>",
            ),
        ]

        for text, expected in cases:
            self.assertEqual(expected, RequestComment(text=text).as_html())

    def test_request_content_object_update_request_count_on_delete(self):
        component1 = Component.objects.create(name="c1", dataspace=self.nexb_dataspace)
        request1 = Request.objects.create(
            title="Title1",
            request_template=self.request_template1,
            requester=self.super_user,
            dataspace=self.super_user.dataspace,
            content_object=component1,
        )

        component1.refresh_from_db()
        self.assertEqual(1, component1.count_requests())
        self.assertEqual(1, component1.request_count)

        component1.delete()
        request1.delete()
