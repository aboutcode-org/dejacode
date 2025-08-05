#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from workflow.integrations.base import BaseIntegration
from workflow.integrations.github import GitHubIntegration
from workflow.integrations.gitlab import GitLabIntegration
from workflow.integrations.jira import JiraIntegration

__all__ = [
    "BaseIntegration",
    "GitHubIntegration",
    "GitLabIntegration",
    "JiraIntegration",
]


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
