#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from urllib.parse import quote
from urllib.parse import urlparse

from workflow.integrations.base import BaseIntegration

GITLAB_API_URL = "https://gitlab.com/api/v4"


class GitLabIntegration(BaseIntegration):
    """
    A class for managing GitLab issue creation, updates, and comments
    from DejaCode requests.
    """

    api_url = GITLAB_API_URL

    def get_headers(self):
        gitlab_token = self.dataspace.get_configuration(field_name="gitlab_token")
        if not gitlab_token:
            raise ValueError("The gitlab_token is not set on the Dataspace.")
        return {"PRIVATE-TOKEN": gitlab_token}

    def sync(self, request):
        """Sync the given request with GitLab by creating or updating an issue."""
        try:
            project_path = self.extract_gitlab_project_path(
                request.request_template.issue_tracker_id
            )
        except ValueError as error:
            raise ValueError(f"Invalid GitLab project URL: {error}")

        labels = []
        if request.priority:
            labels.append(str(request.priority))

        external_issue = request.external_issue
        if external_issue:
            self.update_issue(
                repo_id=project_path,
                issue_id=external_issue.issue_id,
                title=self.make_issue_title(request),
                body=self.make_issue_body(request),
                state_event="close" if request.is_closed else "reopen",
                labels=labels,
            )
        else:
            issue = self.create_issue(
                repo_id=project_path,
                title=self.make_issue_title(request),
                body=self.make_issue_body(request),
                labels=labels,
            )
            request.link_external_issue(
                platform="gitlab",
                repo=project_path,
                issue_id=issue["iid"],
            )

    def create_issue(self, repo_id, title, body="", labels=None):
        """Create a new GitLab issue."""
        project_path = quote(repo_id, safe="")
        url = f"{self.api_url}/projects/{project_path}/issues"
        data = {
            "title": title,
            "description": body,
        }
        if labels:
            # GitLab expects a comma-separated string for labels
            data["labels"] = ",".join(labels)

        return self.post(url, json=data)

    def update_issue(self, repo_id, issue_id, title=None, body=None, state_event=None, labels=None):
        """Update an existing GitLab issue."""
        project_path = quote(repo_id, safe="")
        url = f"{self.api_url}/projects/{project_path}/issues/{issue_id}"
        data = {}
        if title:
            data["title"] = title
        if body:
            data["description"] = body
        if state_event:
            data["state_event"] = state_event
        if labels:
            # GitLab expects a comma-separated string for labels
            data["labels"] = ",".join(labels)

        return self.put(url, json=data)

    def post_comment(self, repo_id, issue_id, comment_body, base_url=None):
        """Post a comment on an existing GitLab issue."""
        project_path = quote(repo_id, safe="")
        url = f"{self.api_url}/projects/{project_path}/issues/{issue_id}/notes"
        data = {"body": comment_body}

        return self.post(url, json=data)

    @staticmethod
    def extract_gitlab_project_path(url):
        """Extract 'namespace/project' from a GitLab URL."""
        parsed = urlparse(url)
        if "gitlab.com" not in parsed.netloc:
            raise ValueError("URL does not point to GitLab.")

        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 2:
            raise ValueError("Incomplete GitLab project path.")

        return "/".join(path_parts[:2])
