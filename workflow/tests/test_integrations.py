#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dje.models import Dataspace
from dje.tests import create_superuser
from workflow.integrations.github import GitHubIntegration
from workflow.models import Question
from workflow.models import RequestTemplate


class GitHubIntegrationTestCase(TestCase):
    def setUp(self):
        patcher = mock.patch("workflow.models.Request.handle_integrations", return_value=None)
        self.mock_handle_integrations = patcher.start()
        self.addCleanup(patcher.stop)

        self.dataspace = Dataspace.objects.create(name="nexB")
        self.dataspace.set_configuration("github_token", "fake-token")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.request_template = RequestTemplate.objects.create(
            name="GitHub Template",
            description="Integration test template",
            content_type=self.component_ct,
            dataspace=self.dataspace,
            issue_tracker_id="https://github.com/nexB/repo",
        )
        self.question = Question.objects.create(
            template=self.request_template,
            label="Example Question",
            input_type="TextField",
            position=0,
            dataspace=self.dataspace,
        )
        self.request = self.request_template.create_request(
            title="Example Request",
            requester=self.super_user,
            serialized_data='{"Example Question": "Some value"}',
        )
        self.github = GitHubIntegration(dataspace=self.dataspace)

    def test_extract_github_repo_path_valid_url(self):
        url = "https://github.com/user/repo"
        result = GitHubIntegration.extract_github_repo_path(url)
        self.assertEqual(result, "user/repo")

    def test_extract_github_repo_path_invalid_url(self):
        with self.assertRaises(ValueError):
            GitHubIntegration.extract_github_repo_path("https://example.com/user/repo")

    def test_get_headers_returns_auth_header(self):
        headers = self.github.get_headers()
        self.assertEqual(headers, {"Authorization": "token fake-token"})

    def test_make_issue_title(self):
        title = GitHubIntegration.make_issue_title(self.request)
        self.assertEqual(title, "[DEJACODE] Example Request")

    def test_make_issue_body_contains_question(self):
        body = GitHubIntegration.make_issue_body(self.request)
        self.assertIn("### Example Question", body)
        self.assertIn("Some value", body)

    @mock.patch("requests.Session.post")
    def test_create_issue_calls_post(self, mock_session_post):
        mock_session_post.return_value.json.return_value = {"number": 10}
        mock_session_post.return_value.raise_for_status.return_value = None

        issue = self.github.create_issue(
            repo_id="user/repo",
            title="Issue Title",
            body="Issue Body",
            labels=["High"],
        )

        self.assertEqual(issue["number"], 10)
        mock_session_post.assert_called_once()

    @mock.patch("requests.Session.patch")
    def test_update_issue_calls_patch(self, mock_session_patch):
        mock_session_patch.return_value.json.return_value = {"state": "closed"}
        mock_session_patch.return_value.raise_for_status.return_value = None

        response = self.github.update_issue(
            repo_id="user/repo",
            issue_id=123,
            title="Updated title",
            body="Updated body",
            state="closed",
        )

        self.assertEqual(response["state"], "closed")
        mock_session_patch.assert_called_once()
