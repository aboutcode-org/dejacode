#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from urllib.parse import urlparse

import requests

GITHUB_API_URL = "https://api.github.com"


class GitHubIntegration:
    dataspace = None
    api_url = GITHUB_API_URL
    default_timeout = 10

    def __init__(self, dataspace):
        if not dataspace:
            raise ValueError("Dataspace must be provided.")
        self.dataspace = dataspace

    def get_headers(self):
        github_token = self.dataspace.get_configuration(field_name="github_token")
        if not github_token:
            raise ValueError("The github_token is not set on the Dataspace.")
        return {"Authorization": f"token {github_token}"}

    def sync(self, request):
        repo_id = extract_github_repo_path(request.request_template.issue_tracker_id)

        labels = []
        if request.priority:
            labels.append(str(request.priority))

        external_issue = request.external_issue

        if external_issue:  # Update existing issue on GitHib
            self.update_issue(
                repo_id=repo_id,
                issue_number=external_issue.issue_id,
                title=make_issue_title(request),
                body=make_issue_body(request),
                state="closed" if request.is_closed else "open",
            )
        else:
            issue = self.create_issue(
                repo_id=repo_id,
                title=make_issue_title(request),
                body=make_issue_body(request),
                labels=labels,
            )
            # Create an ExternalIssueLink instance and assign to the Request.
            request.link_external_issue(
                platform="github",
                repo=repo_id,
                issue_id=issue["number"],
            )

    def create_issue(self, repo_id, title, body=None, labels=None):
        url = f"{self.api_url}/repos/{repo_id}/issues"
        data = {"title": title}
        if body:
            data["body"] = body
        if labels:
            data["labels"] = labels

        response = requests.post(
            url,
            json=data,
            headers=self.get_headers(),
            timeout=self.default_timeout,
        )
        return response.json()

    def update_issue(self, repo_id, issue_number, title=None, body=None, state=None):
        url = f"{self.api_url}/repos/{repo_id}/issues/{issue_number}"
        data = {}
        if title:
            data["title"] = title
        if body:
            data["body"] = body
        if state:
            data["state"] = state

        response = requests.patch(
            url,
            json=data,
            headers=self.get_headers(),
            timeout=self.default_timeout,
        )
        return response.json()


def make_issue_title(request):
    return f"[DEJACODE] {request.title}"


def make_issue_body(request):
    label_fields = [
        ("📝 Request Template", request.request_template),
        ("📦 Product Context", request.product_context),
        ("📌 Applies To", request.content_object),
        ("🙋 Submitted By", request.requester),
        ("👤 Assigned To", request.assignee),
        ("🚨 Priority", request.priority),
        ("🗒️ Notes", request.notes),
    ]

    lines = []
    for label, value in label_fields:
        if value:
            lines.append(f"### {label}\n{value}")

    lines.append("----")

    for question in request.get_serialized_data_as_list():
        value = question.get("value")
        if question.get("input_type") == "BooleanField":
            value = "Yes" if value in [1, "1"] else "No"
        lines.append(f"### {question.get('label')}\n{value}")

    return "\n\n".join(lines)


def extract_github_repo_path(url):
    """Extract 'username/repo-name' from a GitHub URL."""
    parsed = urlparse(url)
    if "github.com" not in parsed.netloc:
        raise ValueError("Not a GitHub URL")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        raise ValueError("Invalid GitHub repository URL")

    return f"{path_parts[0]}/{path_parts[1]}"
