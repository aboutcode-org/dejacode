#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from urllib.parse import urlparse

from workflow.integrations.base import BaseIntegration

SOURCEHUT_GRAPHQL_API_URL = "https://todo.sr.ht/query"


class SourceHutIntegration(BaseIntegration):
    """A SourceHut integration using GraphQL for issue creation and updates."""

    api_url = SOURCEHUT_GRAPHQL_API_URL

    def get_headers(self):
        token = self.dataspace.get_configuration(field_name="sourcehut_token")
        if not token:
            raise ValueError("The sourcehut_token is not set on the Dataspace.")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def sync(self, request):
        """Sync the given request with SourceHut by creating or updating a ticket."""
        try:
            project = self.extract_sourcehut_project(request.request_template.issue_tracker_id)
        except ValueError as error:
            raise ValueError(f"Invalid SourceHut project URL: {error}")

        external_issue = request.external_issue

        if external_issue:
            self.update_issue(
                repo_id=external_issue.repo,
                issue_id=external_issue.issue_id,
                title=self.make_issue_title(request),
                body=self.make_issue_body(request),
                state=self.get_status(request),
            )
        else:
            issue = self.create_issue(
                repo_id=project,
                title=self.make_issue_title(request),
                body=self.make_issue_body(request),
            )
            request.link_external_issue(
                platform="sourcehut",
                repo=project,
                issue_id=issue["id"],
            )

    def get_tracker_id(self, project):
        """Return the tracker ID for a SourceHut project name (e.g., "my-project")."""
        query = """
        query {
            trackers {
                results {
                    id
                    name
                }
            }
        }
        """
        response = self.post(self.api_url, json={"query": query})

        try:
            trackers = response["data"]["trackers"]["results"]
            for tracker in trackers:
                if tracker["name"] == project.split("/")[-1]:
                    return tracker["id"]
            raise ValueError(f"No tracker found with name: {project}")
        except (KeyError, TypeError):
            raise ValueError("Could not retrieve tracker list from SourceHut.")

    def create_issue(self, repo_id, title, body=""):
        """Create a new SourceHut ticket via GraphQL."""
        mutation = """
        mutation SubmitTicket($trackerId: Int!, $input: SubmitTicketInput!) {
            submitTicket(trackerId: $trackerId, input: $input) {
                id
                subject
            }
        }
        """
        variables = {
            "trackerId": self.get_tracker_id(repo_id),
            "input": {"subject": title, "body": body},
        }
        response = self.post(
            self.api_url,
            json={"query": mutation, "variables": variables},
        )
        return response.get("data", {}).get("submitTicket")

    def update_issue(self, repo_id, issue_id, title=None, body=None, state=None, labels=None):
        """Update an existing SourceHut ticket via GraphQL."""
        mutation = """
        mutation UpdateTicket($trackerId: Int!, $ticketId: Int!, $input: UpdateTicketInput!) {
            updateTicket(trackerId: $trackerId, ticketId: $ticketId, input: $input) {
                id
                subject
                body
            }
        }
        """
        input_data = {}
        if title:
            input_data["subject"] = title
        if body:
            input_data["body"] = body

        if not input_data:
            raise ValueError("At least one of 'title' or 'body' must be provided.")

        variables = {
            "trackerId": self.get_tracker_id(repo_id),
            "ticketId": int(issue_id),
            "input": input_data,
        }

        response = self.post(
            self.api_url,
            json={"query": mutation, "variables": variables},
        )
        return response.get("data", {}).get("updateTicket")

    def post_comment(self, repo_id, issue_id, comment_body, base_url=None):
        """Post a comment on an existing SourceHut ticket."""
        mutation = """
        mutation SubmitComment($trackerId: Int!, $ticketId: Int!, $input: SubmitCommentInput!) {
            submitComment(trackerId: $trackerId, ticketId: $ticketId, input: $input) {
                id
                created
                ticket {
                    id
                    subject
                }
            }
        }
        """
        variables = {
            "trackerId": self.get_tracker_id(repo_id),
            "ticketId": int(issue_id),
            "input": {"text": comment_body},
        }

        response = self.post(
            self.api_url,
            json={"query": mutation, "variables": variables},
        )
        return response.get("data", {}).get("submitComment")

    @staticmethod
    def extract_sourcehut_project(url):
        """Extract the project slug (e.g., ~user/project-name) from a SourceHut URL."""
        parsed = urlparse(url)
        if "todo.sr.ht" not in parsed.netloc:
            raise ValueError("URL does not point to SourceHut's todo system.")

        path_parts = [p for p in parsed.path.split("/") if p]
        if len(path_parts) < 2 or not path_parts[0].startswith("~"):
            raise ValueError("Invalid SourceHut path format. Expected: ~user/project")

        return f"{path_parts[0]}/{path_parts[1]}"
