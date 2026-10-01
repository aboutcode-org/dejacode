#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import re

from workflow.integrations.base import BaseIntegration
from workflow.integrations.forgejo import ForgejoIntegration
from workflow.integrations.github import GitHubIntegration
from workflow.integrations.gitlab import GitLabIntegration
from workflow.integrations.jira import JiraIntegration
from workflow.integrations.sourcehut import SourceHutIntegration

__all__ = [
    "BaseIntegration",
    "ForgejoIntegration",
    "GitHubIntegration",
    "GitLabIntegration",
    "JiraIntegration",
    "SourceHutIntegration",
    "is_valid_issue_tracker_id",
    "get_class_for_tracker",
    "get_class_for_platform",
]

FORGEJO_PATTERN = re.compile(r"^https://(?:[a-zA-Z0-9.-]*forgejo[a-zA-Z0-9.-]*)/[^/]+/[^/]+/?$")

GITHUB_PATTERN = re.compile(r"^https://github\.com/[^/]+/[^/]+/?$")

GITLAB_PATTERN = re.compile(r"^https://gitlab\.com/[^/]+/[^/]+/?$")

JIRA_PATTERN = re.compile(
    r"^https://[a-zA-Z0-9.-]+\.atlassian\.net(?:/[^/]+)*"
    r"/(?:projects|browse)/[A-Z][A-Z0-9]+(?:/[^/]*)*/*$"
)

SOURCEHUT_PATTERN = re.compile(r"^https://todo\.sr\.ht/~[^/]+/[^/]+/?$")

ISSUE_TRACKER_INTEGRATIONS = {
    GITHUB_PATTERN: GitHubIntegration,
    GITLAB_PATTERN: GitLabIntegration,
    JIRA_PATTERN: JiraIntegration,
    FORGEJO_PATTERN: ForgejoIntegration,
    SOURCEHUT_PATTERN: SourceHutIntegration,
}


def is_valid_issue_tracker_id(issue_tracker_id):
    return get_class_for_tracker(issue_tracker_id) is not None


def get_class_for_tracker(issue_tracker_id):
    for pattern, integration_class in ISSUE_TRACKER_INTEGRATIONS.items():
        if pattern.match(issue_tracker_id):
            return integration_class


def get_class_for_platform(platform):
    return {
        "forgejo": ForgejoIntegration,
        "github": GitHubIntegration,
        "gitlab": GitLabIntegration,
        "jira": JiraIntegration,
        "sourcehut": SourceHutIntegration,
    }.get(platform)
