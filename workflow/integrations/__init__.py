#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import re

from workflow.integrations.base import BaseIntegration
from workflow.integrations.github import GitHubIntegration
from workflow.integrations.gitlab import GitLabIntegration
from workflow.integrations.jira import JiraIntegration

__all__ = [
    "BaseIntegration",
    "GitHubIntegration",
    "GitLabIntegration",
    "JiraIntegration",
    "is_valid_issue_tracker_id",
    "get_class_for_tracker",
    "get_class_for_platform",
]


GITHUB_PATTERN = re.compile(r"^https://github\.com/[^/]+/[^/]+/?$")

GITLAB_PATTERN = re.compile(r"^https://gitlab\.com/[^/]+/[^/]+/?$")

JIRA_PATTERN = re.compile(
    r"^https://[a-zA-Z0-9.-]+\.atlassian\.net/(?:projects|jira/software/projects)/[A-Z][A-Z0-9]+"
)

ISSUE_TRACKER_PATTERNS = [
    GITHUB_PATTERN,
    GITLAB_PATTERN,
    JIRA_PATTERN,
]


def is_valid_issue_tracker_id(issue_tracker_id):
    return any(pattern.match(issue_tracker_id) for pattern in ISSUE_TRACKER_PATTERNS)


def get_class_for_tracker(issue_tracker_id):
    if "github.com" in issue_tracker_id:
        return GitHubIntegration
    elif "gitlab.com" in issue_tracker_id:
        return GitLabIntegration
    elif "atlassian.net" in issue_tracker_id:
        return JiraIntegration


def get_class_for_platform(platform):
    return {
        "github": GitHubIntegration,
        "gitlab": GitLabIntegration,
        "jira": JiraIntegration,
    }.get(platform)
