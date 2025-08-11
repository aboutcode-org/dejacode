.. _integrations_sourcehut:

SourceHut Integration
=====================

DejaCode's integration with SourceHut allows you to automatically forward
**Workflow Requests** to SourceHut **tickets**.
This behavior can be selectively applied to any **Request Template** of your choice.

Prerequisites
-------------

- A **SourceHut project** hosted on https://todo.sr.ht that you want to integrate with
  DejaCode.
- A **SourceHut account** with API access and permission to create/edit tickets.

SourceHut API Token
-------------------

To enable integration, you need a SourceHut **API token**.

1. **Create a Token**:

   - Go to https://meta.sr.ht/oauth2
   - Under **Personal Access Tokens**, click **"Generate new token"**
   - Set a clear description like ``DejaCode Integration`` in the "Comment" field
   - Select only the ``todo.sr.ht`` > ``TICKETS`` scope
   - **Generate token** and copy the token

.. note::

   It is recommended to **create a dedicated SourceHut user** with a clear, descriptive
   name such as ``dejacode-integration``. This ensures that all SourceHut issues
   managed by integration are clearly attributed to that user, improving traceability
   and auditability.

DejaCode Dataspace Configuration
--------------------------------

To use your SourceHut token in DejaCode:

1. Go to the **Administration dashboard**
2. Navigate to **Dataspaces**, and select your Dataspace
3. Scroll to the **SourceHut Integration** section under **Configuration**
4. Paste your SourceHut token in the **SourceHut token** field
5. Save the form

Activate SourceHut Integration on Request Templates
---------------------------------------------------

1. Go to the **Administration dashboard**
2. Navigate to **Workflow** > **Request templates**
3. Create or edit a Request Template in your Dataspace
4. Set the **Issue Tracker ID** field to your SourceHut project URL, e.g.::

       https://todo.sr.ht/~USERNAME/PROJECT_NAME

Once the integration is configured:

- New **Requests** using this template will be automatically pushed to SourceHut
- Field updates (like title or priority) and **status changes** (e.g. closed) will be
  synced
- New **Comments** on a DejaCode Request will be propagated to the SourceHut ticket
