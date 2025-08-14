.. _integrations_introduction:

Integrations overview
=====================

DejaCode offers several ways to connect with other tools and services, enabling
**automation**, **synchronization**, and **streamlined workflows**. Depending on your
needs, you can choose from :ref:`platform_specific_integrations`, the
:ref:`rest_api_integration`, or the :ref:`webhook_integration`.

.. _platform_specific_integrations:

Platform-specific integrations
------------------------------

DejaCode provides built-in support for the following platforms:

- :ref:`integrations_github`
- :ref:`integrations_gitlab`
- :ref:`integrations_jira`
- :ref:`integrations_sourcehut`
- :ref:`integrations_forgejo`

These integrations are designed to work **seamlessly** with each platform's features.
They typically allow **requests**, **comments**, and **status changes** in DejaCode to
be linked or synchronized with corresponding items in the external platform, such as
**issues** or **tickets**.

Platform-specific integrations are the best choice when:

- Your team already uses **one of the supported platforms**
- You want **minimal setup**, with features mapped directly between systems
- You prefer a **native, optimized experience** rather than building custom logic

.. _rest_api_integration:

REST API
--------

The :ref:`integrations_rest_api` provides **full programmatic access** to most features
of the platform. This makes it possible to integrate DejaCode with **any script,
application, or automation system**, regardless of the programming language or
framework.

With the REST API, you can:

- **Create, update, and retrieve** requests and related objects
- **Automate** administrative tasks
- Pull data into **reporting** or **analytics tools**
- Build **custom user interfaces** on top of DejaCode data

This approach offers **maximum flexibility**, but requires you to write the logic for
**handling events**, **processing data**, and **authenticating** with the API.

.. _webhook_integration:

Webhook integration
-------------------

:ref:`integrations_webhook` allow DejaCode to **push** information to an **external
system** the moment specific events occur, instead of requiring you to **poll** the
API.

When a configured event happens (such as a **request** being created or updated),
DejaCode sends an HTTP ``POST`` request with a **JSON payload** to your **target URL**.
You can then process this payload to **trigger automation**, **update another system**,
or **log the change**.

Webhooks can be configured for a **variety of events**, and the payload can be
extended with **custom fields** and **headers**. They are especially powerful when
combined with the REST API — **webhooks deliver the trigger**, and **API calls perform
follow-up actions**.

Generic integrations
--------------------

While platform-specific integrations focus on **GitHub**, **GitLab**, **Jira**,
**SourceHut**, and **Forgejo**, both the :ref:`rest_api_integration` and
:ref:`webhook_integration` provide the tools to connect DejaCode to **virtually any
application or service**.

Examples include:

- Pushing updates to a **Slack** channel or **Microsoft Teams**
- Updating **internal dashboards**
- Triggering **security scans** or **CI/CD jobs**
- Synchronizing data with **proprietary in-house systems**

Choosing the right approach
---------------------------

- Use a :ref:`platform_specific_integrations` integration if your workflow centers on
  **one of the supported platforms** and you want the **easiest setup**.
- Use the :ref:`rest_api_integration` for **full control** and **flexibility** over
  how DejaCode interacts with other systems.
- Use :ref:`webhook_integration` to receive **real-time notifications** and act
  immediately on events.
- Combine :ref:`webhook_integration` with the :ref:`rest_api_integration` for
  **event-driven automation** that can **react** and then **fetch or update** related
  data as needed.
