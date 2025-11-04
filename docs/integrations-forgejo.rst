.. _integrations_forgejo:

Forgejo Integration
===================

DejaCode's integration with Forgejo allows you to automatically forward
**Workflow Requests** to Forgejo repository **Issues**.
This behavior can be selectively applied to any **Request Template** of your choice.

Prerequisites
-------------

- A **Forgejo repository** that you want to integrate with DejaCode.
- A **Forgejo user account** with sufficient permissions (at least write access) to
  create and manage issues in that repository.

Forgejo Access Token
--------------------

To enable integration, you need a **personal access token** from Forgejo.

1. **Generate a Token**:

   - Log into your Forgejo instance
   - Go to your **User settings** → **Applications** → **Generate New Token**
   - Set a clear name like ``DejaCode Integration``
   - Select **permissions**:

     - ``issue: Read and write``: Create and update issues

   - Generate the token and copy it securely

.. note::

   It is recommended to **create a dedicated Forgejo user** such as
   ``dejacode-integration`` to manage automated activity for better traceability.

DejaCode Dataspace Configuration
--------------------------------

To use your Forgejo token in DejaCode:

1. Go to the **Administration dashboard**
2. Navigate to **Dataspaces**, and select your Dataspace
3. Scroll to the **Forgejo Integration** section under **Configuration**
4. Paste your Forgejo token in the **Forgejo token** field
5. Save the form

Activate Forgejo Integration on Request Templates
-------------------------------------------------

1. Go to the **Administration dashboard**
2. Navigate to **Workflow** > **Request templates**
3. Create or edit a Request Template in your Dataspace
4. Set the **Issue Tracker ID** field to your Forgejo repository URL, e.g.::

       https://forgejo.example.org/org/repo_name

Once the integration is configured:

- New **Requests** using this template will be automatically pushed to Forgejo
- Field updates (like title or priority) and **status changes** (e.g. closed) will be
  synced
- New **Comments** on a DejaCode Request will be propagated to the Forgejo Issue.
