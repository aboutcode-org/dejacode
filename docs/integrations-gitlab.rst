.. _integrations_gitlab:

GitLab Integration
==================

DejaCode's integration with GitLab allows you to automatically forward
**Workflow Requests** to GitLab project **Issues**.
This behavior can be selectively applied to any **Request Template** of your choice.

Prerequisites
-------------

- A **GitLab project** that you want to integrate with DejaCode.
- A **GitLab user account** with sufficient permissions to create and manage issues in
  the target project.

GitLab Personal Access Token
----------------------------

To enable integration, you need a GitLab **personal access token (PAT)** with
appropriate permissions.

1. **Access GitLab Personal Access Tokens**:

   - Go to: https://gitlab.com/-/user_settings/personal_access_tokens
   - Click the **"Add new token"** button
   - Provide a **name** (e.g., ``DejaCode Integration``) and **expiration date**
     (recommended)

2. **Permissions**:

   Under **Scopes**, select:

   - ``api`` — Full access to create, update, and comment on issues

.. note::

   It is recommended to **create a dedicated GitLab user** with a clear, descriptive
   name such as ``dejacode-integration``. This ensures that all GitLab issues managed by
   the integration are clearly attributed to that user, improving traceability and
   auditability.

3. **Generate the Token**:

   - Click **Create token**
   - Copy the token and store it securely — you’ll need it for the next step

DejaCode Dataspace Configuration
--------------------------------

To use your GitLab token in DejaCode:

1. Go to the **Administration dashboard**
2. Navigate to **Dataspaces**, and select your Dataspace
3. Scroll to the **GitLab Integration** section under **Configuration**
4. Paste your GitLab token in the **GitLab token** field
5. Save the form

Activate GitLab Integration on Request Templates
------------------------------------------------

1. Go to the **Administration dashboard**
2. Navigate to **Workflow** > **Request templates**
3. Create or edit a Request Template in your Dataspace
4. Set the **Issue Tracker ID** field to your GitLab project URL, e.g.::

       https://gitlab.com/group/project_name

Once the integration is configured:

- New **Requests** using this template will be automatically pushed to GitLab
- Field updates (like title or priority) and **status changes** (e.g. closed) will be
  synced
- New **Comments** on a DejaCode Request will be propagated to the GitLab Issue.
