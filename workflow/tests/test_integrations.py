#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import base64
from unittest import mock
from urllib.parse import quote

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dje.models import Dataspace
from dje.tests import create_superuser
from workflow.integrations import ForgejoIntegration
from workflow.integrations import GitHubIntegration
from workflow.integrations import GitLabIntegration
from workflow.integrations import JiraIntegration
from workflow.integrations import get_class_for_platform
from workflow.integrations import get_class_for_tracker
from workflow.integrations import is_valid_issue_tracker_id
from workflow.models import Question
from workflow.models import RequestTemplate


class WorkflowIntegrationsTestCase(TestCase):
    def test_integrations_is_valid_issue_tracker_id(self):
        valid_urls = [
            # GitHub
            "https://github.com/org/repo",
            # GitLab
            "https://gitlab.com/group/project",
            # Jira
            "https://example.atlassian.net/browse/PROJ",
            "https://example.atlassian.net/projects/PROJ",
            "https://example.atlassian.net/projects/PROJ/",
            "https://example.atlassian.net/projects/PROJ/summary",
            "https://example.atlassian.net/jira/software/projects/PROJ",
            "https://example.atlassian.net/jira/software/projects/PROJ/",
            "https://example.atlassian.net/jira/software/projects/PROJ/summary",
            "https://example.atlassian.net/jira/servicedesk/projects/PROJ",
            # Forgejo
            "https://code.forgejo.org/user/repo",
            "https://git.forgejo.dev/org/project/",
            "https://forgejo.example.org/team/repo",
        ]
        for url in valid_urls:
            self.assertTrue(is_valid_issue_tracker_id(url), msg=url)

        invalid_urls = [
            "https://bitbucket.org/team/repo",
            "https://github.com/",
            "https://gitlab.com/",
            "https://atlassian.net/projects/",
            "https://example.com",
            "https://example.org/user/repo",
        ]
        for url in invalid_urls:
            self.assertFalse(is_valid_issue_tracker_id(url), msg=url)

    def test_integrations_get_class_for_tracker(self):
        self.assertIs(get_class_for_tracker("https://github.com/org/repo"), GitHubIntegration)
        self.assertIs(get_class_for_tracker("https://gitlab.com/group/project"), GitLabIntegration)
        self.assertIs(
            get_class_for_tracker("https://example.atlassian.net/projects/PROJ"), JiraIntegration
        )
        self.assertIs(
            get_class_for_tracker("https://code.forgejo.org/user/repo"), ForgejoIntegration
        )
        self.assertIsNone(get_class_for_tracker("https://example.com"))

    def test_integrations_get_class_for_platform(self):
        self.assertIs(get_class_for_platform("github"), GitHubIntegration)
        self.assertIs(get_class_for_platform("gitlab"), GitLabIntegration)
        self.assertIs(get_class_for_platform("jira"), JiraIntegration)
        self.assertIs(get_class_for_platform("forgejo"), ForgejoIntegration)
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

    @mock.patch("requests.Session.request")
    def test_github_create_issue_calls_post(self, mock_request):
        mock_request.return_value.json.return_value = {"number": 10}
        mock_request.return_value.raise_for_status.return_value = None

        issue = self.github.create_issue(
            repo_id="user/repo",
            title="Issue Title",
            body="Issue Body",
            labels=["High"],
        )

        self.assertEqual(issue["number"], 10)
        mock_request.assert_called_once()

    @mock.patch("requests.Session.request")
    def test_github_update_issue_calls_patch(self, mock_request):
        mock_request.return_value.json.return_value = {"state": "closed"}
        mock_request.return_value.raise_for_status.return_value = None

        response = self.github.update_issue(
            repo_id="user/repo",
            issue_id=123,
            title="Updated title",
            body="Updated body",
            state="closed",
        )

        self.assertEqual(response["state"], "closed")
        mock_request.assert_called_once()

    @mock.patch("requests.Session.request")
    def test_github_post_comment_calls_post(self, mock_request):
        mock_request.return_value.json.return_value = {"id": 77, "body": "Test comment"}
        mock_request.return_value.raise_for_status.return_value = None

        response = self.github.post_comment(
            repo_id="user/repo",
            issue_id=10,
            comment_body="Test comment",
        )

        self.assertEqual(response["body"], "Test comment")
        mock_request.assert_called_once_with(
            method="POST",
            url="https://api.github.com/repos/user/repo/issues/10/comments",
            json={"body": "Test comment"},
            params=None,
            data=None,
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

    @mock.patch("requests.Session.request")
    def test_gitlab_create_issue_calls_post(self, mock_request):
        mock_request.return_value.json.return_value = {"iid": 10}
        mock_request.return_value.raise_for_status.return_value = None

        issue = self.gitlab.create_issue(
            repo_id="user/project",
            title="Issue Title",
            body="Issue Body",
            labels=["High"],
        )

        self.assertEqual(issue["iid"], 10)
        mock_request.assert_called_once_with(
            method="POST",
            url=f"https://gitlab.com/api/v4/projects/{quote('user/project', safe='')}/issues",
            params=None,
            data=None,
            json={
                "title": "Issue Title",
                "description": "Issue Body",
                "labels": "High",
            },
            timeout=self.gitlab.default_timeout,
        )

    @mock.patch("requests.Session.request")
    def test_gitlab_update_issue_calls_put(self, mock_request):
        mock_request.return_value.json.return_value = {"state": "closed"}
        mock_request.return_value.raise_for_status.return_value = None

        response = self.gitlab.update_issue(
            repo_id="user/project",
            issue_id=123,
            title="Updated title",
            body="Updated body",
            state_event="close",
            labels=["Urgent"],
        )

        self.assertEqual(response["state"], "closed")

        project_path = quote("user/project", safe="")
        mock_request.assert_called_once_with(
            method="PUT",
            url=f"https://gitlab.com/api/v4/projects/{project_path}/issues/123",
            params=None,
            data=None,
            json={
                "title": "Updated title",
                "description": "Updated body",
                "state_event": "close",
                "labels": "Urgent",
            },
            timeout=self.gitlab.default_timeout,
        )

    @mock.patch("requests.Session.request")
    def test_gitlab_post_comment_calls_post(self, mock_request):
        mock_request.return_value.json.return_value = {"id": 77, "body": "Test comment"}
        mock_request.return_value.raise_for_status.return_value = None

        response = self.gitlab.post_comment(
            repo_id="user/project",
            issue_id=10,
            comment_body="Test comment",
        )

        self.assertEqual(response["body"], "Test comment")

        project_path = quote("user/project", safe="")
        mock_request.assert_called_once_with(
            method="POST",
            url=f"https://gitlab.com/api/v4/projects/{project_path}/issues/10/notes",
            params=None,
            data=None,
            json={"body": "Test comment"},
            timeout=self.gitlab.default_timeout,
        )


class JiraIntegrationTestCase(TestCase):
    def setUp(self):
        patcher = mock.patch("workflow.models.Request.handle_integrations", return_value=None)
        self.mock_handle_integrations = patcher.start()
        self.addCleanup(patcher.stop)

        self.dataspace = Dataspace.objects.create(name="nexB")
        self.dataspace.set_configuration("jira_user", "fake-user")
        self.dataspace.set_configuration("jira_token", "fake-token")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.request_template = RequestTemplate.objects.create(
            name="Jira Template",
            description="Integration test template",
            content_type=self.component_ct,
            dataspace=self.dataspace,
            issue_tracker_id="https://example.atlassian.net/browse/PROJ",
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
        self.jira = JiraIntegration(dataspace=self.dataspace)

    def test_jira_extract_jira_info_valid_urls(self):
        urls = [
            "https://example.atlassian.net/browse/PROJ",
            "https://example.atlassian.net/projects/PROJ",
            "https://example.atlassian.net/projects/PROJ/",
            "https://example.atlassian.net/projects/PROJ/summary",
            "https://example.atlassian.net/jira/software/projects/PROJ",
            "https://example.atlassian.net/jira/software/projects/PROJ/",
            "https://example.atlassian.net/jira/software/projects/PROJ/summary",
            "https://example.atlassian.net/jira/servicedesk/projects/PROJ",
        ]
        for url in urls:
            base_url, project_key = JiraIntegration.extract_jira_info(url)
            self.assertEqual(base_url, "https://example.atlassian.net")
            self.assertEqual(project_key, "PROJ")

    def test_jira_extract_jira_info_invalid_url(self):
        with self.assertRaises(ValueError):
            JiraIntegration.extract_jira_info("https://example.com/browse/PROJ")

    def test_jira_get_headers_returns_auth_header(self):
        headers = self.jira.get_headers()
        expected_auth = base64.b64encode(b"fake-user:fake-token").decode()
        self.assertEqual(
            headers,
            {
                "Authorization": f"Basic {expected_auth}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    def test_jira_make_issue_title(self):
        title = self.jira.make_issue_title(self.request)
        self.assertEqual(title, "[DEJACODE] Example Request")

    def test_jira_make_issue_body_contains_question(self):
        body = self.jira.make_issue_body(self.request)
        self.assertIn("### Example Question", body)
        self.assertIn("Some value", body)

    @mock.patch("requests.Session.request")
    def test_jira_create_issue_calls_post(self, mock_request):
        mock_request.return_value.json.return_value = {"key": "PROJ-123"}
        mock_request.return_value.raise_for_status.return_value = None

        self.jira.api_url = "https://example.atlassian.net/rest/api/3"
        issue = self.jira.create_issue(
            project_key="PROJ",
            title="Issue Title",
            body="Issue Body",
        )

        self.assertEqual(issue["key"], "PROJ-123")
        mock_request.assert_called_once()

    @mock.patch("requests.Session.request")
    def test_jira_update_issue_calls_put(self, mock_request):
        mock_request.return_value.raise_for_status.return_value = None
        self.jira.api_url = "https://example.atlassian.net/rest/api/3"

        response = self.jira.update_issue(
            issue_id="PROJ-123",
            title="Updated title",
            body="Updated body",
        )

        self.assertEqual(response["id"], "PROJ-123")
        mock_request.assert_called_once()

    @mock.patch("requests.Session.request")
    def test_jira_post_comment_calls_post(self, mock_request):
        mock_request.return_value.json.return_value = {"id": "1001"}
        mock_request.return_value.raise_for_status.return_value = None

        response = self.jira.post_comment(
            repo_id="https://example.atlassian.net",
            issue_id="PROJ-123",
            comment_body="Test comment",
        )

        self.assertEqual(response["id"], "1001")
        mock_request.assert_called_once()


class ForgejoIntegrationTestCase(TestCase):
    def setUp(self):
        patcher = mock.patch("workflow.models.Request.handle_integrations", return_value=None)
        self.mock_handle_integrations = patcher.start()
        self.addCleanup(patcher.stop)

        self.dataspace = Dataspace.objects.create(name="nexB")
        self.dataspace.set_configuration("forgejo_token", "fake-token")
        self.super_user = create_superuser("nexb_user", self.dataspace)
        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.request_template = RequestTemplate.objects.create(
            name="Forgejo Template",
            description="Integration test template",
            content_type=self.component_ct,
            dataspace=self.dataspace,
            issue_tracker_id="https://code.forgejo.org/nexB/repo",
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
        self.forgejo = ForgejoIntegration(dataspace=self.dataspace)

    def test_forgejo_extract_forgejo_info_valid_url(self):
        url = "https://code.forgejo.org/user/repo"
        base_url, repo_path = ForgejoIntegration.extract_forgejo_info(url)
        self.assertEqual(base_url, "https://code.forgejo.org")
        self.assertEqual(repo_path, "user/repo")

    def test_forgejo_extract_forgejo_info_invalid_url_missing_host(self):
        with self.assertRaises(ValueError):
            ForgejoIntegration.extract_forgejo_info("invalid-url")

    def test_forgejo_extract_forgejo_info_invalid_url_missing_repo_path(self):
        with self.assertRaises(ValueError):
            ForgejoIntegration.extract_forgejo_info("https://code.forgejo.org/user")

    def test_forgejo_get_headers_returns_auth_header(self):
        headers = self.forgejo.get_headers()
        self.assertEqual(headers, {"Authorization": "token fake-token"})

    def test_forgejo_make_issue_title(self):
        title = self.forgejo.make_issue_title(self.request)
        self.assertEqual(title, "[DEJACODE] Example Request")

    def test_forgejo_make_issue_body_contains_question(self):
        body = self.forgejo.make_issue_body(self.request)
        self.assertIn("### Example Question", body)
        self.assertIn("Some value", body)

    @mock.patch("requests.Session.request")
    def test_forgejo_create_issue_calls_post(self, mock_request):
        mock_request.return_value.json.return_value = {"number": 42}
        mock_request.return_value.raise_for_status.return_value = None

        self.forgejo.api_url = "https://code.forgejo.org/api/v1"
        issue = self.forgejo.create_issue(
            repo_id="user/repo",
            title="Issue Title",
            body="Issue Body",
        )
        self.assertEqual(issue["number"], 42)
        mock_request.assert_called_once()

    @mock.patch("requests.Session.request")
    def test_forgejo_update_issue_calls_patch(self, mock_request):
        mock_request.return_value.json.return_value = {"state": "closed"}
        mock_request.return_value.raise_for_status.return_value = None

        self.forgejo.api_url = "https://code.forgejo.org/api/v1"
        response = self.forgejo.update_issue(
            repo_id="user/repo",
            issue_id=123,
            title="Updated title",
            body="Updated body",
            state="closed",
        )
        self.assertEqual(response["state"], "closed")
        mock_request.assert_called_once()

    @mock.patch("requests.Session.request")
    def test_forgejo_post_comment_calls_post(self, mock_request):
        mock_request.return_value.json.return_value = {"id": 99, "body": "Test comment"}
        mock_request.return_value.raise_for_status.return_value = None

        response = self.forgejo.post_comment(
            repo_id="user/repo",
            issue_id=123,
            comment_body="Test comment",
            base_url="https://code.forgejo.org",
        )
        self.assertEqual(response["body"], "Test comment")
        mock_request.assert_called_once_with(
            method="POST",
            url="https://code.forgejo.org/api/v1/repos/user/repo/issues/123/comments",
            params=None,
            data=None,
            json={"body": "Test comment"},
            timeout=self.forgejo.default_timeout,
        )
