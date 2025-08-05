#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from unittest import mock
from urllib.parse import quote

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dje.models import Dataspace
from dje.tests import create_superuser
from workflow.integrations import JiraIntegration
from workflow.integrations import get_class_for_platform
from workflow.integrations import get_class_for_tracker
from workflow.integrations import is_valid_issue_tracker_id
from workflow.integrations.github import GitHubIntegration
from workflow.integrations.gitlab import GitLabIntegration
from workflow.models import Question
from workflow.models import RequestTemplate


class WorkflowIntegrationsTestCase(TestCase):
    def test_is_valid_issue_tracker_id(self):
        valid_urls = [
            "https://github.com/org/repo",
            "https://gitlab.com/group/project",
            "https://aboutcode.atlassian.net/projects/PROJ",
            "https://aboutcode.atlassian.net/jira/software/projects/PROJ",
        ]
        for url in valid_urls:
            with self.subTest(url=url):
                self.assertTrue(is_valid_issue_tracker_id(url))

        invalid_urls = [
            "https://bitbucket.org/team/repo",
            "https://github.com/",
            "https://gitlab.com/",
            "https://atlassian.net/projects/",
            "https://example.com",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertFalse(is_valid_issue_tracker_id(url))

    def test_get_class_for_tracker(self):
        self.assertIs(get_class_for_tracker("https://github.com/org/repo"), GitHubIntegration)
        self.assertIs(get_class_for_tracker("https://gitlab.com/group/project"), GitLabIntegration)
        self.assertIs(
            get_class_for_tracker("https://aboutcode.atlassian.net/projects/PROJ"), JiraIntegration
        )
        self.assertIsNone(get_class_for_tracker("https://example.com"))

    def test_get_class_for_platform(self):
        self.assertIs(get_class_for_platform("github"), GitHubIntegration)
        self.assertIs(get_class_for_platform("gitlab"), GitLabIntegration)
        self.assertIs(get_class_for_platform("jira"), JiraIntegration)
        self.assertIsNone(get_class_for_platform("example"))


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

    def test_github_extract_github_repo_path_valid_url(self):
        url = "https://github.com/user/repo"
        result = GitHubIntegration.extract_github_repo_path(url)
        self.assertEqual(result, "user/repo")

    def test_github_extract_github_repo_path_invalid_url(self):
        with self.assertRaises(ValueError):
            GitHubIntegration.extract_github_repo_path("https://example.com/user/repo")

    def test_github_get_headers_returns_auth_header(self):
        headers = self.github.get_headers()
        self.assertEqual(headers, {"Authorization": "token fake-token"})

    def test_github_make_issue_title(self):
        title = GitHubIntegration.make_issue_title(self.request)
        self.assertEqual(title, "[DEJACODE] Example Request")

    def test_github_make_issue_body_contains_question(self):
        body = GitHubIntegration.make_issue_body(self.request)
        self.assertIn("### Example Question", body)
        self.assertIn("Some value", body)

    @mock.patch("requests.Session.post")
    def test_github_create_issue_calls_post(self, mock_session_post):
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
    def test_github_update_issue_calls_patch(self, mock_session_patch):
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

    @mock.patch("requests.Session.post")
    def test_github_post_comment_calls_post(self, mock_session_post):
        mock_session_post.return_value.json.return_value = {"id": 77, "body": "Test comment"}
        mock_session_post.return_value.raise_for_status.return_value = None

        response = self.github.post_comment(
            repo_id="user/repo",
            issue_id=10,
            comment_body="Test comment",
        )

        self.assertEqual(response["body"], "Test comment")
        mock_session_post.assert_called_once_with(
            "https://api.github.com/repos/user/repo/issues/10/comments",
            json={"body": "Test comment"},
            timeout=self.github.default_timeout,
        )


class GitLabIntegrationTestCase(TestCase):
    def setUp(self):
        patcher = mock.patch("workflow.models.Request.handle_integrations", return_value=None)
        self.mock_handle_integrations = patcher.start()
        self.addCleanup(patcher.stop)

        self.dataspace = Dataspace.objects.create(name="nexB")
        self.dataspace.set_configuration("gitlab_token", "fake-token")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.request_template = RequestTemplate.objects.create(
            name="GitLab Template",
            description="Integration test template",
            content_type=self.component_ct,
            dataspace=self.dataspace,
            issue_tracker_id="https://gitlab.com/nexB/repo",
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
        self.gitlab = GitLabIntegration(dataspace=self.dataspace)

    def test_gitlab_extract_gitlab_project_path_valid_url(self):
        url = "https://gitlab.com/user/project"
        result = GitLabIntegration.extract_gitlab_project_path(url)
        self.assertEqual(result, "user/project")

    def test_gitlab_extract_gitlab_project_path_invalid_url(self):
        with self.assertRaises(ValueError):
            GitLabIntegration.extract_gitlab_project_path("https://example.com/user/project")

    def test_gitlab_get_headers_returns_auth_header(self):
        headers = self.gitlab.get_headers()
        self.assertEqual(headers, {"PRIVATE-TOKEN": "fake-token"})

    def test_gitlab_make_issue_title(self):
        title = self.gitlab.make_issue_title(self.request)
        self.assertEqual(title, "[DEJACODE] Example Request")

    def test_gitlab_make_issue_body_contains_question(self):
        body = self.gitlab.make_issue_body(self.request)
        self.assertIn("### Example Question", body)
        self.assertIn("Some value", body)

    @mock.patch("requests.Session.post")
    def test_gitlab_create_issue_calls_post(self, mock_session_post):
        mock_session_post.return_value.json.return_value = {"iid": 10}
        mock_session_post.return_value.raise_for_status.return_value = None

        issue = self.gitlab.create_issue(
            repo_id="user/project",
            title="Issue Title",
            body="Issue Body",
            labels=["High"],
        )

        self.assertEqual(issue["iid"], 10)
        mock_session_post.assert_called_once_with(
            f"https://gitlab.com/api/v4/projects/{quote('user/project', safe='')}/issues",
            json={
                "title": "Issue Title",
                "description": "Issue Body",
                "labels": "High",
            },
            timeout=self.gitlab.default_timeout,
        )

    @mock.patch("requests.Session.put")
    def test_gitlab_update_issue_calls_put(self, mock_session_put):
        mock_session_put.return_value.json.return_value = {"state": "closed"}
        mock_session_put.return_value.raise_for_status.return_value = None

        response = self.gitlab.update_issue(
            repo_id="user/project",
            issue_id=123,
            title="Updated title",
            body="Updated body",
            state_event="close",
            labels=["Urgent"],
        )

        self.assertEqual(response["state"], "closed")
        mock_session_put.assert_called_once_with(
            f"https://gitlab.com/api/v4/projects/{quote('user/project', safe='')}/issues/123",
            json={
                "title": "Updated title",
                "description": "Updated body",
                "state_event": "close",
                "labels": "Urgent",
            },
            timeout=self.gitlab.default_timeout,
        )

    @mock.patch("requests.Session.post")
    def test_gitlab_post_comment_calls_post(self, mock_session_post):
        mock_session_post.return_value.json.return_value = {"id": 77, "body": "Test comment"}
        mock_session_post.return_value.raise_for_status.return_value = None

        response = self.gitlab.post_comment(
            repo_id="user/project",
            issue_id=10,
            comment_body="Test comment",
        )

        self.assertEqual(response["body"], "Test comment")
        mock_session_post.assert_called_once_with(
            f"https://gitlab.com/api/v4/projects/{quote('user/project', safe='')}/issues/10/notes",
            json={"body": "Test comment"},
            timeout=self.gitlab.default_timeout,
        )
