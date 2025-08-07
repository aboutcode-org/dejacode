#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from urllib.parse import urlparse

from workflow.integrations.base import BaseIntegration

FORGEJO_API_URL = ""


class ForgejoIntegration(BaseIntegration):
    """
    A class for managing Forgejo issue creation, updates, and comments
    from DejaCode requests.
    """

    api_url = FORGEJO_API_URL

    def get_headers(self):
        forgejo_token = self.dataspace.get_configuration(field_name="forgejo_token")
        if not forgejo_token:
            raise ValueError("The forgejo_token is not set on the Dataspace.")
        return {"Authorization": f"token {forgejo_token}"}

    def sync(self, request):
        """Sync the given request with Forgejo by creating or updating an issue."""
        try:
            repo_id = self.extract_forgejo_repo_path(request.request_template.issue_tracker_id)
        except ValueError as error:
            raise ValueError(f"Invalid Forgejo repository URL: {error}")

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
            )
            request.link_external_issue(
                platform="forgejo",
                repo=repo_id,
                issue_id=issue["number"],
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

    def post_comment(self, repo_id, issue_id, comment_body):
        """Post a comment on an existing Forgejo issue."""
        url = f"{self.api_url}/repos/{repo_id}/issues/{issue_id}/comments"
        data = {"body": comment_body}

        return self.post(url, json=data)

    @staticmethod
    def extract_forgejo_repo_path(url):
        """Extract 'owner/repo-name' from a Forgejo URL."""
        parsed = urlparse(url)
        if not parsed.netloc:
            raise ValueError("URL must include a hostname.")

        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 2:
            raise ValueError("Incomplete Forgejo repository path.")

        return f"{path_parts[0]}/{path_parts[1]}"
