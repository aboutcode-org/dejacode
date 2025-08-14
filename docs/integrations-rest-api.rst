.. _integrations_rest_api:

REST API Integration
====================

DejaCode offers a REST API to allow integration with external applications in a
generic way. You can use it to fetch, create, and update DejaCode Requests
from your own scripts or applications.

The full REST API documentation is also available in the DejaCode web UI under
**Tools > API Documentation**.

This guide focuses specifically on interacting with **DejaCode Requests**.

.. note::

    Example HTTP requests assume the DejaCode URL is ``https://localhost``.
    Replace with your actual instance URL.

Prerequisites
-------------

- A **DejaCode API Key**, available from your **Profile** settings page.

Authentication
--------------

Include your **API Key** in the "Authorization" HTTP header for every request.
The key must be prefixed by the string literal ``Token`` followed by a space:

    Authorization: Token abcdef123456

.. warning::
    Treat your API key like a password — keep it secret and secure.

Example using cURL::

    curl -X GET \
      https://localhost/api/v2/requests/ \
      -H "Authorization: Token abcdef123456"

Example using Python::

    import requests

    api_url = "https://localhost/api/v2/requests/"
    headers = {"Authorization": "Token abcdef123456"}
    params = {"page": "2"}
    response = requests.get(api_url, headers=headers, params=params)
    print(response.json())

Request List
------------

**Endpoint:** ``GET /api/v2/requests/``

This endpoint lists all requests. Responses include pagination fields ``next``
and ``previous`` to navigate through pages.

You can sort the list using ``?ordering=FIELD``. Prefix a field with ``-`` to
reverse the sort order (descending). Available fields:

- ``title``
- ``request_template``
- ``status``
- ``priority``
- ``assignee``
- ``requester``
- ``created_date``
- ``last_modified_date``

Filtering is supported using ``FIELD=VALUE`` syntax. Available filters include:

- ``request_template``
- ``status``
- ``requester``
- ``assignee``
- ``priority``
- ``content_type``
- ``last_modified_date``

Example: Get closed requests sorted by last modification date::

    api_url = "https://localhost/api/v2/requests/"
    headers = {"Authorization": "Token abcdef123456"}
    params = {"status": "closed", "ordering": "last_modified_date"}
    response = requests.get(api_url, headers=headers, params=params)
    print(response.json())

Request Details
---------------

**Endpoint:** ``GET /api/v2/requests/{uuid}/``

Returns all available information for a specific request. Replace ``{uuid}``
with the UUID of the request you want to retrieve.

Example JSON response snippet::

    {
        "uuid": "adf1835e-4b58-42d0-b1f4-c57791167d19",
        "title": "Issue title",
        "request_template": "https://localhost/api/v2/request_templates/5b106292-d8b6-459c-abda-e6a87527a0db/",
        "status": "open",
        "assignee": "username",
        "notes": "",
        "serialized_data": {"Notes": "This version has a known vulnerability."},
        "created_date": "2025-08-12T17:41:47.424373+04:00",
        "last_modified_date": "2025-08-12T17:42:29.031833+04:00",
        "comments": [
            {
                "uuid": "8ee73eb2-353a-4e84-8536-fe4e25a1abf6",
                "username": "username",
                "text": "Comment content.",
                "created_date": "2025-08-14T09:17:55.397285+04:00"
            }
        ]
    }

Create a Request
----------------

**Endpoint:** ``POST /api/v2/requests/``

Required fields:

- **title** (string): A short, descriptive title of the request.
- **request_template** (string): URI of the template to use.
- **assignee** (string): Username of the person assigned.

Optional fields:

- **status** (string): ``open``, ``closed``, or ``draft``. Default is ``open``.
- **priority** (string|null): Priority level.
- **product_context** (string|null): URI of a product context.
- **notes** (string): Notes related to the request.
- **serialized_data** (string): Additional structured data.
- **is_private** (boolean): True if only visible to requester/reviewers.
- **content_object** (string|null): URI of associated content object.
- **cc_emails** (array of strings): List of emails to notify.

Example of minimal JSON payload::

    {
        "title": "New vulnerability found",
        "request_template": "Address Vulnerabilities in Product Packages",
        "assignee": "username"
    }

Example using cURL::

    api_url="https://localhost/api/v2/requests/"
    headers="Authorization: Token abcdef123456"
    data='{
        "title": "New vulnerability found",
        "request_template": "Address Vulnerabilities in Product Packages",
        "assignee": "username"
    }'

    curl -X POST "$api_url" -H "$headers" -d "$data"

Example using Python::

    import requests
    api_url = "https://localhost/api/v2/requests/"
    headers = {
        "Authorization": "Token abcdef123456",
        "Content-Type": "application/json"
    }
    data = {
        "title": "New vulnerability found",
        "request_template": "Address Vulnerabilities in Product Packages",
        "assignee": "username"
    }
    response = requests.post(api_url, headers=headers, json=data)
    print(response.json())

Update a Request
----------------

**Endpoint:** ``PUT /api/v2/requests/{uuid}/``

Performs a full update. All fields of the request must be provided.

Partial Update
--------------

**Endpoint:** ``PATCH /api/v2/requests/{uuid}/``

Allows updating only specific fields. For example, to close a request::

    import requests
    api_url = "https://localhost/api/v2/requests/{uuid}/"
    headers = {
        "Authorization": "Token abcdef123456",
        "Content-Type": "application/json"
    }
    data = {"status": "closed"}
    response = requests.patch(api_url, headers=headers, json=data)
    print(response.json())

