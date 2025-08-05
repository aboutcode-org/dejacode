#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from urllib.parse import urlparse

from workflow.integrations.base import BaseIntegration

GITHUB_API_URL = "https://api.github.com"


class GitHubIntegration(BaseIntegration):
    """
    A class for managing GitHub issue creation, updates, and comments
    from DejaCode requests.
    """

    api_url = GITHUB_API_URL

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
                labels=labels,
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

    def update_issue(self, repo_id, issue_id, title=None, body=None, state=None, labels=None):
        """Update an existing GitHub issue."""
        url = f"{self.api_url}/repos/{repo_id}/issues/{issue_id}"
        data = {}
        if title:
            data["title"] = title
        if body:
            data["body"] = body
        if state:
            data["state"] = state
        if labels:
            data["labels"] = labels

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
