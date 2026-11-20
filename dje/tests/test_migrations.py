#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from importlib import import_module

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dje.models import Dataspace
from dje.models import DataspaceConfiguration
from workflow.models import RequestTemplate

integration_urls_migration = import_module(
    "dje.migrations.0017_dataspaceconfiguration_forgejo_url_jira_url"
)


class DataMigrationsTestCase(TestCase):
    def make_request_template(self, dataspace, issue_tracker_id):
        return RequestTemplate.objects.create(
            name=issue_tracker_id,
            content_type=ContentType.objects.get(app_label="component_catalog", model="component"),
            dataspace=dataspace,
            issue_tracker_id=issue_tracker_id,
        )

    def test_data_migrations_set_integration_urls_from_request_templates(self):
        single_host = Dataspace.objects.create(name="single_host")
        single_host.set_configuration("forgejo_token", "token")
        single_host.set_configuration("jira_token", "token")
        self.make_request_template(single_host, "https://forgejo.example.com/org/repo1")
        self.make_request_template(single_host, "https://forgejo.example.com/org/repo2")
        self.make_request_template(single_host, "https://example.atlassian.net/browse/PROJ")

        multiple_hosts = Dataspace.objects.create(name="multiple_hosts")
        multiple_hosts.set_configuration("forgejo_token", "token")
        self.make_request_template(multiple_hosts, "https://forgejo.example.com/org/repo")
        self.make_request_template(multiple_hosts, "https://forgejo.other.example/org/repo")

        integration_urls_migration.set_integration_urls_from_request_templates(apps, None)

        single_host_configuration = DataspaceConfiguration.objects.get(dataspace=single_host)
        self.assertEqual("https://forgejo.example.com", single_host_configuration.forgejo_url)
        self.assertEqual("https://example.atlassian.net", single_host_configuration.jira_url)
        multiple_hosts_configuration = DataspaceConfiguration.objects.get(dataspace=multiple_hosts)
        self.assertEqual("", multiple_hosts_configuration.forgejo_url)
