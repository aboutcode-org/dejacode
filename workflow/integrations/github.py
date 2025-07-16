#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#


from urllib.parse import urlparse

from django.conf import settings

from github import Github


def handle_integration(request):
    github_token = settings.DEJACODE_GITHUB_INTEGRATION_TOKEN
    if not github_token:
        raise Exception("DEJACODE_GITHUB_INTEGRATION_TOKEN is not set.")

    github_api = Github(github_token)
    repo_id = extract_github_repo_path(request.request_template.issue_tracker_id)
    repo = github_api.get_repo(repo_id)

    labels = []
    if request.priority:
        labels.append(str(request.priority))

    external_issue = request.external_issue

    if external_issue:  # Update existing issue on GitHib
        issue = repo.get_issue(number=int(external_issue.issue_id))
        state = "closed" if request.is_closed else "open"
        issue.edit(
            title=make_issue_title(request),
            body=make_issue_body(request),
            state=state,
        )
    else:
        issue = repo.create_issue(
            title=make_issue_title(request),
            body=make_issue_body(request),
            labels=labels,
        )
        # Create an ExternalIssueLink instance and assign to the Request.
        request.link_external_issue(platform="github", repo=repo_id, issue_id=issue.number)


def make_issue_title(request):
    return f"[DEJACODE] {request.title}"


def make_issue_body(request):
    body = f"""
    - Request template: {request.request_template}
    - Product context: {request.product_context}
    - Applies to: {request.content_object}
    - Submitted by: {request.requester}
    - Assigned to: {request.assignee}
    - Priority: {request.priority}
    """
    return body


def extract_github_repo_path(url):
    """Extract 'username/repo-name' from a GitHub URL."""
    parsed = urlparse(url)
    if "github.com" not in parsed.netloc:
        raise ValueError("Not a GitHub URL")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        raise ValueError("Invalid GitHub repository URL")

    return f"{path_parts[0]}/{path_parts[1]}"
