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


def get_headers():
    github_token = settings.DEJACODE_GITHUB_INTEGRATION_TOKEN
    if not github_token:
        raise Exception("DEJACODE_GITHUB_INTEGRATION_TOKEN is not set.")

    return {
        "Authorization": f"token {github_token}",
    }


def handle_integration(request):
    repo_id = extract_github_repo_path(request.request_template.issue_tracker_id)

    labels = []
    if request.priority:
        labels.append(str(request.priority))

    external_issue = request.external_issue

    if external_issue:  # Update existing issue on GitHib
        update_issue(
            repo_id=repo_id,
            issue_number=external_issue.issue_id,
            title=make_issue_title(request),
            body=make_issue_body(request),
            state="closed" if request.is_closed else "open",
        )
    else:
        issue = create_issue(
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


def create_issue(repo_id, title, body=None, labels=None):
    url = f"{GITHUB_API_URL}/repos/{repo_id}/issues"
    data = {"title": title}
    if body:
        data["body"] = body
    if labels:
        data["labels"] = labels

    response = requests.post(url, json=data, headers=get_headers(), timeout=10)
    return response.json()


def update_issue(repo_id, issue_number, title=None, body=None, state=None):
    url = f"{GITHUB_API_URL}/repos/{repo_id}/issues/{issue_number}"
    data = {}
    if title:
        data["title"] = title
    if body:
        data["body"] = body
    if state:
        data["state"] = state

    response = requests.patch(url, json=data, headers=get_headers(), timeout=10)
    return response.json()


def make_issue_title(request):
    return f"[DEJACODE] {request.title}"


def make_issue_body(request):
    lines = [
        f"### 📝 Request Template\n{request.request_template}",
        f"### 📦 Product Context\n{request.product_context}",
        f"### 📌 Applies To\n{request.content_object}",
        f"### 🙋 Submitted By\n{request.requester}",
        f"### 👤 Assigned To\n{request.assignee}",
        f"### 🚨 Priority\n{request.priority}",
        f"### 🗒️ Notes\n{request.notes}",
        "----",
    ]

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
