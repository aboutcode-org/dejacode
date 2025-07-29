#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from urllib.parse import urlparse

from django.conf import settings

import requests

GITHUB_API_URL = "https://api.github.com"
DEJACODE_SITE_URL = settings.SITE_URL.rstrip("/")


class GitHubIntegration:
    """
    A class for managing GitHub issue creation, updates, and comments
    from DejaCode requests.
    """

    api_url = GITHUB_API_URL
    default_timeout = 10

    def __init__(self, dataspace):
        if not dataspace:
            raise ValueError("Dataspace must be provided.")
        self.dataspace = dataspace
        self.session = self.get_session()

    def get_session(self):
        session = requests.Session()
        session.headers.update(self.get_headers())
        return session

    def get_headers(self):
        github_token = self.dataspace.get_configuration(field_name="github_token")
        if not github_token:
            raise ValueError("The github_token is not set on the Dataspace.")
        return {"Authorization": f"token {github_token}"}

    def sync(self, request):
        """Sync the given request with GitHub by creating or updating an issue."""
        try:
            repo_id = self.extract_github_repo_path(request.request_template.issue_tracker_id)
        except ValueError as error:
            raise ValueError(f"Invalid GitHub repository URL: {error}")

        labels = []
        if request.priority:
            labels.append(str(request.priority))

        external_issue = request.external_issue
        if external_issue:
            self.update_issue(
                repo_id=repo_id,
                issue_id=external_issue.issue_id,
                title=self.make_issue_title(request),
                body=self.make_issue_body(request),
                state="closed" if request.is_closed else "open",
            )
        else:
            issue = self.create_issue(
                repo_id=repo_id,
                title=self.make_issue_title(request),
                body=self.make_issue_body(request),
                labels=labels,
            )
            request.link_external_issue(
                platform="github",
                repo=repo_id,
                issue_id=issue["number"],
            )

    def create_issue(self, repo_id, title, body="", labels=None):
        """Create a new GitHub issue."""
        url = f"{self.api_url}/repos/{repo_id}/issues"
        data = {
            "title": title,
            "body": body,
        }
        if labels:
            data["labels"] = labels

        response = self.session.post(
            url,
            json=data,
            timeout=self.default_timeout,
        )
        response.raise_for_status()
        return response.json()

    def update_issue(self, repo_id, issue_id, title=None, body=None, state=None):
        """Update an existing GitHub issue."""
        url = f"{self.api_url}/repos/{repo_id}/issues/{issue_id}"
        data = {}
        if title:
            data["title"] = title
        if body:
            data["body"] = body
        if state:
            data["state"] = state

        response = self.session.patch(
            url,
            json=data,
            timeout=self.default_timeout,
        )
        response.raise_for_status()
        return response.json()

    def post_comment(self, repo_id, issue_id, comment_body):
        """Post a comment on an existing GitHub issue."""
        url = f"{self.api_url}/repos/{repo_id}/issues/{issue_id}/comments"
        data = {"body": comment_body}

        response = self.session.post(
            url,
            json=data,
            timeout=self.default_timeout,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def extract_github_repo_path(url):
        """Extract 'username/repo-name' from a GitHub URL."""
        parsed = urlparse(url)
        if "github.com" not in parsed.netloc:
            raise ValueError("URL does not point to GitHub.")

        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 2:
            raise ValueError("Incomplete GitHub repository path.")

        return f"{path_parts[0]}/{path_parts[1]}"

    @staticmethod
    def make_issue_title(request):
        return f"[DEJACODE] {request.title}"

    @staticmethod
    def make_issue_body(request):
        request_url = f"{DEJACODE_SITE_URL}{request.get_absolute_url()}"
        label_fields = [
            ("📝 Request Template", request.request_template),
            ("📦 Product Context", request.product_context),
            ("📌 Applies To", request.content_object),
            ("🙋 Submitted By", request.requester),
            ("👤 Assigned To", request.assignee),
            ("🚨 Priority", request.priority),
            ("🗒️ Notes", request.notes),
            ("🔗️ DejaCode URL", request_url),
        ]

        lines = []
        for label, value in label_fields:
            if value:
                lines.append(f"### {label}\n{value}")

        lines.append("----")

        for question in request.get_serialized_data_as_list():
            label = question.get("label")
            value = question.get("value")
            input_type = question.get("input_type")

            if input_type == "BooleanField":
                value = "Yes" if str(value).lower() in ("1", "true", "yes") else "No"

            lines.append(f"### {label}\n{value}")

        return "\n\n".join(lines)
