#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import requests

"""
Script to fetch DejaCode license for expression testing.
"""


def licenses_key_and_names(api_base_url, api_key):
    """
    Return a list of (key, name, short_name) for all the licenses
    from a DejaCode instance using API calls.
    """
    api_url = "/".join([api_base_url.rstrip("/"), "licenses/"])

    for licenses in call_api(api_url, api_key, paginate=100):
        for lic in licenses:
            yield lic.get("key"), lic.get("name"), lic.get("short_name")


def get_response(api_url, headers, params):
    """Return the JSON response from calling `api_url` with `headers` and `params`."""
    response = requests.get(api_url, headers=headers, params=params)
    if response.status_code != requests.codes.ok:
        raise Exception(
            "Failed API call HTTP request: {}".format(response.status_code))
    return response.json()


def call_api(api_url, api_key, paginate=0, headers=None, params=None):
    """
    Call the API at `api_url` with `api_key` and yield JSON results from
    the reponses. Raise an exception on failure.

    Pass `headers` and `params` mappings to the underlying request if
    provided. If `paginate` is a non-zero attempt to paginate with
    `paginate` number of pages and return all the results.
    """
    headers = headers or {
        "Authorization": "Token {}".format(api_key),
        "Accept": "application/json; indent=2",
    }

    params = params or {}

    def _get_results(response):
        return response.json()

    if paginate:
        assert isinstance(paginate, int)
        params["page_size"] = paginate

        first = True
        while True:
            if first:
                first = False
            response = get_response(api_url, headers, params)
            yield response.get("results", [])

            api_url = response.get("next")
            if not api_url:
                break
    else:
        response = get_response(api_url, headers, params)
        yield response.get("results", [])


if __name__ == "__main__":
    import json
    import os
    import sys

    api_base_url = os.environ.get("DEJACODE_API_URL", None)
    api_key = os.environ.get("DEJACODE_API_KEY", None)
    if not (api_base_url and api_key):
        print(
            "You must set the DEJACODE_API_KEY and DEJACODE_API_URL "
            "environment variables before running this script."
        )
        sys.exit(0)
    licenses = licenses_key_and_names(api_base_url, api_key)

    with open("all_licenses.json", "w") as o:
        o.write(json.dumps(sorted(licenses), indent=2))
