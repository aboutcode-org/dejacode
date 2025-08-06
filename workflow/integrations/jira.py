#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import base64
import re
from urllib.parse import urlparse

from workflow.integrations.base import BaseIntegration

JIRA_API_PATH = "/rest/api/3"


class JiraIntegration(BaseIntegration):
    """
    A class for managing Jira issue creation, updates, and comments
    from DejaCode requests.
    """

    issuetype = "DejaCode Request"
    closed_status = "Done"

    def get_headers(self):
        jira_user = self.dataspace.get_configuration("jira_user")
        jira_token = self.dataspace.get_configuration("jira_token")
        if not jira_user or not jira_token:
            raise ValueError("The jira_user or jira_token is not set on the Dataspace.")

        auth = f"{jira_user}:{jira_token}"
        encoded_auth = base64.b64encode(auth.encode()).decode()
        return {
            "Authorization": f"Basic {encoded_auth}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def sync(self, request):
        """Sync the given request with Jira by creating or updating an issue."""
        try:
            base_url, project_key = self.extract_jira_info(
                request.request_template.issue_tracker_id
            )
        except ValueError as error:
            raise ValueError(f"Invalid Jira tracker URL: {error}")

        self.api_url = base_url.rstrip("/") + JIRA_API_PATH

        external_issue = request.external_issue
        if external_issue:
            self.update_issue(
                issue_id=external_issue.issue_id,
                title=self.make_issue_title(request),
                body=self.make_issue_body(request),
                status=self.closed_status if request.is_closed else None,
            )
        else:
            issue = self.create_issue(
                project_key=project_key,
                title=self.make_issue_title(request),
                body=self.make_issue_body(request),
            )
            request.link_external_issue(
                platform="jira",
                repo=base_url,
                issue_id=issue["key"],
            )

    def create_issue(self, project_key, title, body=""):
        """Create a new Jira issue."""
        url = f"{self.api_url}/issue"
        data = {
            "fields": {
                "project": {"key": project_key},
                "summary": title,
                "description": markdown_to_adf(body),
                "issuetype": {"name": self.issuetype},
            }
        }
        return self.post(url, json=data)

    def update_issue(self, issue_id, title=None, body=None, status=None):
        """Update an existing Jira issue."""
        url = f"{self.api_url}/issue/{issue_id}"
        fields = {}
        if title:
            fields["summary"] = title
        if body:
            fields["description"] = markdown_to_adf(body)

        if fields:
            self.put(url, json={"fields": fields})

        # Transition (e.g., close) if status is specified
        if status:
            self.transition_issue(issue_id, status)

        return {"id": issue_id}

    def post_comment(self, repo_id, issue_id, comment_body):
        """Post a comment on an existing Jira issue."""
        api_url = repo_id.rstrip("/") + JIRA_API_PATH
        url = f"{api_url}/issue/{issue_id}/comment"
        data = {"body": markdown_to_adf(comment_body)}
        return self.post(url, json=data)

    def transition_issue(self, issue_id, target_status_name):
        """Transition a Jira issue to a new status by name."""
        transitions_url = f"{self.api_url}/issue/{issue_id}/transitions"
        response_json = self.get(url=transitions_url)
        transitions = response_json.get("transitions", [])

        # Search for a transition name that match the `target_status_name`
        for transition in transitions:
            if transition["to"]["name"].lower() == target_status_name.lower():
                transition_id = transition["id"]
                break
        else:
            raise ValueError(f"No transition found for status '{target_status_name}'")

        data = {"transition": {"id": transition_id}}
        return self.post(transitions_url, json=data)

    @staticmethod
    def extract_jira_info(url):
        """
        Extract the base Jira URL and project key from a Jira Cloud URL.
        Supports:
        - https://<domain>.atlassian.net/projects/PROJECTKEY
        - https://<domain>.atlassian.net/browse/PROJECTKEY
        - https://<domain>.atlassian.net/jira/software/projects/PROJECTKEY/...
        - https://<domain>.atlassian.net/jira/servicedesk/projects/PROJECTKEY/...
        """
        parsed = urlparse(url)
        if not parsed.netloc.endswith("atlassian.net"):
            raise ValueError("Invalid Jira Cloud domain.")

        base_url = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path

        project_key_pattern = r"/(?:[^/]+/)*(?:projects|browse)/([A-Z][A-Z0-9]+)"
        match = re.search(project_key_pattern, path)
        if match:
            return base_url, match.group(1)

        raise ValueError("Unable to extract Jira project key from URL.")


def markdown_to_adf(markdown_text):
    """
    Convert minimal Markdown to Atlassian Document Format (ADF).
    Converts:
    - '### ' headings into ADF heading blocks (level 3)
    - All other non-empty lines into paragraphs
    """
    lines = markdown_text.splitlines()
    content = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("### "):
            content.append(
                {
                    "type": "heading",
                    "attrs": {"level": 3},
                    "content": [{"type": "text", "text": stripped[4:].strip()}],
                }
            )
        elif stripped:
            content.append(
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": stripped}],
                }
            )

    return {
        "version": 1,
        "type": "doc",
        "content": content,
    }
