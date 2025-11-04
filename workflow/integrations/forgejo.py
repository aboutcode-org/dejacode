#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from urllib.parse import urlparse

from workflow.integrations.base import BaseIntegration

FORGEJO_API_PATH = "/api/v1"


class ForgejoIntegration(BaseIntegration):
    """
    A class for managing Forgejo issue creation, updates, and comments
    from DejaCode requests.
    """

    def get_headers(self):
        forgejo_token = self.dataspace.get_configuration("forgejo_token")
        if not forgejo_token:
            raise ValueError("The forgejo_token is not set on the Dataspace.")
        return {"Authorization": f"token {forgejo_token}"}

    def sync(self, request):
        """Sync the given request with Forgejo by creating or updating an issue."""
        try:
            base_url, repo_path = self.extract_forgejo_info(
                request.request_template.issue_tracker_id
            )
        except ValueError as error:
            raise ValueError(f"Invalid Forgejo tracker URL: {error}")

        self.api_url = base_url.rstrip("/") + FORGEJO_API_PATH

        external_issue = request.external_issue
        if external_issue:
            self.update_issue(
                repo_id=repo_path,
                issue_id=external_issue.issue_id,
                title=self.make_issue_title(request),
                body=self.make_issue_body(request),
                state=self.get_status(request),
            )
        else:
            issue = self.create_issue(
                repo_id=repo_path,
                title=self.make_issue_title(request),
                body=self.make_issue_body(request),
            )
            request.link_external_issue(
                platform="forgejo",
                repo=repo_path,
                issue_id=issue["number"],
                base_url=base_url,
            )

    def create_issue(self, repo_id, title, body=""):
        """Create a new Forgejo issue."""
        url = f"{self.api_url}/repos/{repo_id}/issues"
        data = {
            "title": title,
            "body": body,
        }

        return self.post(url, json=data)

    def update_issue(self, repo_id, issue_id, title=None, body=None, state=None):
        """Update an existing Forgejo issue."""
        url = f"{self.api_url}/repos/{repo_id}/issues/{issue_id}"
        data = {}
        if title:
            data["title"] = title
        if body:
            data["body"] = body
        if state:
            data["state"] = state

        return self.patch(url, json=data)

    def post_comment(self, repo_id, issue_id, comment_body, base_url=None):
        """Post a comment on an existing Forgejo issue."""
        url = f"{base_url}{FORGEJO_API_PATH}/repos/{repo_id}/issues/{issue_id}/comments"
        return self.post(url, json={"body": comment_body})

    @staticmethod
    def extract_forgejo_info(url):
        """
        Extract the Forgejo base domain and repo path (org/repo) from a repo URL.

        Example:
        - https://forgejo.example.org/org/repo → ("https://forgejo.example.org", "org/repo")

        """
        parsed = urlparse(url)
        if not parsed.netloc:
            raise ValueError("Missing hostname in Forgejo URL.")

        base_url = f"{parsed.scheme}://{parsed.netloc}"
        path_parts = [p for p in parsed.path.split("/") if p]
        if len(path_parts) < 2:
            raise ValueError("Incomplete Forgejo repository path.")

        repo_path = f"{path_parts[0]}/{path_parts[1]}"
        return base_url, repo_path
