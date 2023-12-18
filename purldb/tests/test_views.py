#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import uuid
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from dje.models import Dataspace
from dje.tests import create_superuser
from dje.tests import create_user
from license_library.models import License
from organization.models import Owner

purldb_list = json.loads(
    """
{
    "count": 1,
    "next": null,
    "previous": null,
    "results": [
        {
            "url": "https://purldb/api/packages/2928d61d-b113-46ba-aa11-d23976ee495d/",
            "uuid": "2928d61d-b113-46ba-aa11-d23976ee495d",
            "filename": "abbot-1.4.0.jar",
            "package_sets": [],
            "package_content": "binary",
            "purl": "pkg:maven/abbot/abbot@1.4.0",
            "type": "maven",
            "namespace": "abbot",
            "name": "abbot",
            "version": "1.4.0",
            "qualifiers": "",
            "subpath": "",
            "primary_language": "Java",
            "description": "Abbot Java GUI Test Library",
            "release_date": "2015-09-22T00:00:00Z",
            "parties": [
                {
                    "type": "person",
                    "role": "developper",
                    "name": "Gerard Davisonr",
                    "email": "gerard.davison@oracle.com",
                    "url": null
                }
            ],
            "keywords": [],
            "homepage_url": "http://abbot.sf.net/",
            "download_url": "https://repo1.maven.org/maven2/abbot/abbot/1.4.0/abbot-1.4.0.jar",
            "bug_tracking_url": null,
            "code_view_url": null,
            "vcs_url": null,
            "repository_homepage_url": null,
            "repository_download_url": null,
            "api_data_url": null,
            "size": 687192,
            "md5": null,
            "sha1": "a2363646a9dd05955633b450010b59a21af8a423",
            "sha256": null,
            "sha512": null,
            "copyright": null,
            "holder": null,
            "declared_license_expression": "(bsd-new OR epl-1.0 OR apache-2.0 OR mit)",
            "declared_license_expression_spdx": "(BSD-3-Clause OR EPL-1.0 OR Apache-2.0 OR MIT)",
            "license_detections": [],
            "other_license_expression": null,
            "other_license_expression_spdx": null,
            "other_license_detections": [],
            "extracted_license_statement": "https://www.eclipse.org/legal/epl-v10.html",
            "notice_text": null,
            "source_packages": [
                "pkg:maven/abbot/abbot@1.4.0?classifier=sources"
            ],
            "extra_data": {},
            "package_uid": "pkg:maven/abbot/abbot@1.4.0?uuid=2928d61d-b113-46ba-aa11-d23976ee495d",
            "datasource_id": null,
            "file_references": [],
            "dependencies": [
                {
                    "purl": "pkg:maven/junit/junit",
                    "extracted_requirement": "4.8.2",
                    "scope": "compile",
                    "is_runtime": true,
                    "is_optional": false,
                    "is_resolved": false
                }
            ],
            "resources": "https://purldb/api/packages/2928d61d-b113-46ba-aa11/resources/"
        }
    ]
}
"""
)

purldb_entry = purldb_list.get("results")[0]


def mock_get_package_list(*args, **kwargs):
    return purldb_list


def mock_get_package(*args, **kwargs):
    return purldb_entry


@mock.patch("dejacode_toolkit.purldb.PurlDB.get_package_list", mock_get_package_list)
@mock.patch("dejacode_toolkit.purldb.PurlDB.get_package", mock_get_package)
class PurlDBViewsTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="Alternate")
        self.nexb_user = create_superuser("nexb_user", self.nexb_dataspace)
        self.basic_user = create_user("basic_user", self.nexb_dataspace)
        self.alternate_user = create_superuser("alternate_user", self.alternate_dataspace)
        self.license1 = License.objects.create(
            key="mit",
            name="MIT",
            short_name="MIT",
            dataspace=self.nexb_dataspace,
            owner=Owner.objects.create(name="Owner1", dataspace=self.nexb_dataspace),
        )

    def test_purldb_views_availability(self):
        purldb_uuid = uuid.uuid4()
        list_url = reverse("purldb:purldb_list")
        details_url = reverse("purldb:purldb_details", args=[purldb_uuid])

        response = self.client.get(list_url)
        self.assertRedirects(response, "/login/?next=/purldb/")
        response = self.client.get(details_url)
        self.assertRedirects(response, "/login/?next=/purldb/{}/".format(purldb_uuid))

        self.client.login(username=self.alternate_user.username, password="secret")
        response = self.client.get(list_url)
        self.assertContains(response, "<h1>403 Forbidden</h1>", status_code=403)
        response = self.client.get(details_url)
        self.assertContains(response, "<h1>403 Forbidden</h1>", status_code=403)

        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(list_url)
        self.assertEqual(403, response.status_code)
        response = self.client.get(details_url)
        self.assertEqual(403, response.status_code)

        self.basic_user.dataspace.enable_purldb_access = True
        self.basic_user.dataspace.save()
        response = self.client.get(list_url)
        self.assertEqual(200, response.status_code)
        response = self.client.get(details_url)
        self.assertEqual(200, response.status_code)

        self.nexb_user.dataspace.enable_purldb_access = True
        self.nexb_user.dataspace.save()
        self.client.login(username=self.nexb_user.username, password="secret")
        response = self.client.get(list_url)
        self.assertEqual(200, response.status_code)
        response = self.client.get(details_url)
        self.assertEqual(200, response.status_code)

    def test_purldb_list_view_content(self):
        list_url = reverse("purldb:purldb_list")
        self.client.login(username=self.nexb_user.username, password="secret")

        response = self.client.get(list_url)
        self.assertEqual(403, response.status_code)

        self.nexb_user.dataspace.enable_purldb_access = True
        self.nexb_user.dataspace.save()

        response = self.client.get(list_url)
        self.assertContains(
            response, '<a class="nav-link active" href="/purldb/?all=true">All</a>', html=True
        )
        self.assertContains(response, "1 results", html=True)

        expected = (
            '<a href="/purldb/2928d61d-b113-46ba-aa11-d23976ee495d/">'
            "  pkg:maven/abbot/abbot@1.4.0"
            "</a>"
        )
        self.assertContains(response, expected, html=True)

        expected = (
            'bsd-new OR epl-1.0 OR apache-2.0 OR <a href="/licenses/nexB/mit/" title="MIT">mit</a>'
        )
        self.assertContains(response, expected, html=True)

    def test_purldb_list_view_filters(self):
        list_url = reverse("purldb:purldb_list")
        self.nexb_user.dataspace.enable_purldb_access = True
        self.nexb_user.dataspace.save()
        self.client.login(username=self.nexb_user.username, password="secret")

        response = self.client.get(list_url + "?sort=-name&type__iexact=pypi")
        self.assertContains(response, 'data-bs-target="#purldb-filterset-modal"')
        self.assertContains(response, 'id="purldb-filterset-modal"')
        self.assertContains(
            response, '<option value="-name" selected>Name (descending)</option>', html=True
        )
        self.assertContains(response, '<input type="text" name="type__iexact"')
        self.assertContains(
            response, '<option value="-name" selected>Name (descending)</option>', html=True
        )
        self.assertContains(
            response,
            '<span class="badge text-bg-dark rounded-pill">Type: "pypi" '
            '  <i class="fas fa-times-circle"></i>'
            "</span>",
            html=True,
        )
        self.assertContains(
            response,
            '<a href="?type__iexact=pypi&sort=version" class="sort" aria-label="Sort">'
            '<i class="fas fa-sort"></i>'
            "</a>",
            html=True,
        )
        self.assertContains(response, '<input type="text" name="purl"')

    def test_purldb_details_view_content(self):
        details_url = reverse("purldb:purldb_details", args=[purldb_entry["uuid"]])
        self.client.login(username=self.nexb_user.username, password="secret")

        response = self.client.get(details_url)
        self.assertEqual(403, response.status_code)

        self.nexb_user.dataspace.enable_purldb_access = True
        self.nexb_user.dataspace.save()

        response = self.client.get(details_url)
        expected = "<title>PurlDB: pkg:maven/abbot/abbot@1.4.0</title>"
        self.assertContains(response, expected, html=True)

        expected = """
        <div class="col">
          <div class="header-pretitle">
            <a class="me-1" href="/purldb/" title="Return to  list" data-bs-toggle="tooltip"
               data-bs-placement="bottom">Purldb</a>
          </div>
          <h1 class="header-title text-break">
            pkg:maven/abbot/abbot@1.4.0
          </h1>
        </div>
        """
        self.assertContains(response, expected, html=True)

        expected = """
        <a class="btn btn-success"
           href="/packages/add/?purldb_uuid=2928d61d-b113-46ba-aa11-d23976ee495d"
           target="_blank">
          Create Package
        </a>
        """
        self.assertContains(response, expected, html=True)

        expected = (
            '<button class="nav-link active" id="tab_purldb-tab"'
            ' data-bs-toggle="tab" data-bs-target="#tab_purldb" type="button"'
            ' role="tab" aria-controls="tab_purldb" aria-selected="true">'
        )
        self.assertContains(response, expected)

        expected = 'id="tab_purldb"'
        self.assertContains(response, expected)

    def test_purldb_search_table_view(self):
        search_table_url = reverse("purldb:purldb_search_table")

        response = self.client.get(search_table_url)
        self.assertEqual(302, response.status_code)

        self.client.login(username=self.alternate_user.username, password="secret")
        response = self.client.get(search_table_url)
        self.assertEqual(403, response.status_code)

        self.nexb_user.dataspace.enable_purldb_access = True
        self.nexb_user.dataspace.save()
        self.client.login(username=self.nexb_user.username, password="secret")

        response = self.client.get(search_table_url)
        expected = """
        <h3>
        <span class="badge text-bg-purldb">PurlDB</span>
        <small class="text-muted">
          <span id="purldb-count">1</span> package result for this search.
           Click <a href="/purldb/?q=None">here</a> to see the full list.
        </small>
        </h3>
        """
        self.assertContains(response, expected, html=True)

        expected = """
        <table class="table table-bordered table-striped table-md text-break">
        <thead>
          <tr>
            <th>Identifier</th>
            <th>Type</th>
            <th>Name</th>
            <th>Version</th>
            <th>License</th>
            <th>Download URL</th>
          </tr>
        </thead>
        <tbody>
            <tr>
              <td>
                <strong>
                  <a href="/purldb/2928d61d-b113-46ba-aa11-d23976ee495d/">
                    pkg:maven/abbot/abbot@1.4.0
                  </a>
                </strong>
              </td>
              <td>maven</td>
              <td>abbot</td>
              <td>1.4.0</td>
              <td class="license-expression" style="max-width: 200px;">
                bsd-new OR epl-1.0 OR apache-2.0 OR
                <a href="/licenses/nexB/mit/" title="MIT">mit</a>
              </td>
              <td class="text-truncate" style="max-width: 200px;">
                <a target="_blank"
                   href="https://repo1.maven.org/maven2/abbot/abbot/1.4.0/abbot-1.4.0.jar"
                   rel="nofollow">
                  https://repo1.maven.org/maven2/abbot/abbot/1.4.0/abbot-1.4.0.jar
                </a>
              </td>
            </tr>
          </tbody>
        </table>
        """
        self.assertContains(response, expected, html=True)
