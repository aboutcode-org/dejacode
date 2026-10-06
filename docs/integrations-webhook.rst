.. _integrations_webhook:

Webhook integration
===================

Webhooks provide a way for DejaCode to automatically send data to external systems
when certain events occur. This allows you to trigger workflows, update other tools,
or synchronize data in real time, without the need for polling the API.

When an event is fired in DejaCode, the associated webhook sends an HTTP ``POST``
request to the configured target URL. The request contains a JSON payload describing
the event and relevant data.

Use cases
---------

Webhooks can be used to:

- Notify a project management tool when a request is created or updated
- Push updates to a monitoring or reporting dashboard
- Synchronize status changes with an external ticketing system
- Trigger automation in CI/CD pipelines
- Alert a Slack channel when new policy violations are detected or resolved
- Notify security teams when new vulnerability data is available

Available events
----------------

The following events can be configured as webhook triggers.

**Request events**

- ``request.added`` — A new request is created
- ``request.updated`` — An existing request is modified
- ``request_comment.added`` — A comment is added to a request

**Vulnerability events**

- ``vulnerability.data_update`` — Vulnerability data is updated (daily refresh or
  package import)

**Policy events**

- ``policy.violation_detected`` — One or more new policy violations are detected
  during a rule evaluation run
- ``policy.violation_resolved`` — One or more policy violations are resolved during
  a rule evaluation run

.. seealso::
    :ref:`how_to_6` for instructions on enabling policy rules in your Dataspace.

**User events**

- ``user.locked_out`` — A user account is locked out following failed login attempts
- ``user.added_or_updated`` — A user account is created or modified

.. note::

    The list of available events may vary based on your DejaCode configuration.
    Check the Admin UI for the current list.

Webhook configuration
---------------------

Webhooks are managed from the **Admin UI**.

1. Go to the **Administration dashboard**.
2. Navigate to **Webhooks**.
3. Click **Add webhook** to create a new one.
4. Fill in the following fields:

   - **Target URL** — The endpoint that will receive the POST requests.
   - **Event** — The event name that will trigger the webhook.
   - **Is active** — Enable or disable the webhook.
   - **Extra payload** — Additional JSON data to include in the request body.
   - **Extra headers** — Additional HTTP headers to include in the request.

5. Save the webhook.

When the selected event occurs, DejaCode will send a POST request to the target URL
with the event payload.

Payload structure
-----------------

DejaCode uses two payload formats depending on the event type.

**Structured payload** (request events)

Request events use a structured JSON format containing a ``hook`` object with webhook
metadata and a ``data`` object with the full serialized resource.

Example payload for ``request.added``::

    {
      "hook": {
        "uuid": "22c9203f-e90b-4135-a142-583ef4f41e72",
        "event": "request.added",
        "target": "https://target.com/path/"
      },
      "data": {
        "api_url": "/api/v2/requests/fbc77986-06ff-4dbb-81c3-95cd36dbed66/",
        "absolute_url": "/requests/fbc77986-06ff-4dbb-81c3-95cd36dbed66/",
        "uuid": "fbc77986-06ff-4dbb-81c3-95cd36dbed66",
        "title": "New vulnerability detected",
        "request_template": "/api/v2/request_templates/f28a034f-d6df-4fa7-9283-a93730858616/",
        "request_template_name": "Address Vulnerabilities in Product Packages",
        "status": "open",
        "priority": "Urgent",
        "assignee": "username",
        "product_context": null,
        "notes": "",
        "serialized_data": {
          "Product Team Contact": "contact email",
          "Need By Date": "",
          "Notes": ""
        },
        "is_private": false,
        "requester": "username",
        "content_type": "product",
        "content_object": null,
        "content_object_display_name": null,
        "cc_emails": [],
        "last_modified_by": null,
        "created_date": "2025-08-14T13:48:26.909014+04:00",
        "last_modified_date": "2025-08-14T13:48:26.909035+04:00",
        "comments": [],
        "dataspace": "Dataspace"
      }
    }

**Text payload** (vulnerability and policy events)

Vulnerability and policy events use a simpler format with a single ``text`` field
containing a human-readable summary of the event.

Example payload for ``vulnerability.data_update``::

    {
      "text": "[DejaCode] New vulnerabilities detected!\n42 vulnerabilities affecting 7 packages"
    }

Example payload for ``policy.violation_detected``::

    {
      "text": "[DejaCode] Policy violations detected for MyApp 2.0\n- Vulnerability Detected: 3 violation(s)\n- Vulnerability Stale: 1 violation(s)"
    }

Example payload for ``policy.violation_resolved``::

    {
      "text": "[DejaCode] 2 policy violation(s) resolved for MyApp 2.0"
    }

If **extra payload** is defined on the webhook, it is merged into the JSON body.
If **extra headers** are defined, they are added to the HTTP request.

Security considerations
-----------------------

- Always validate incoming webhook requests on your server.
- If possible, restrict the target URL to accept requests only from trusted IP ranges.
- Consider adding a signature header in **extra headers** to verify authenticity.
