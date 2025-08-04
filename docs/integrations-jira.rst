.. _integrations_jira:

Jira Cloud Integration
======================

DejaCode's integration with Jira allows you to automatically forward
**Workflow Requests** to Jira **Issues**.
This behavior can be selectively applied to any **Request Template** of your choice.

Prerequisites
-------------

- A **Jira Cloud project** that you want to integrate with DejaCode.
- A **Jira user account** with sufficient permissions
  (at least *Create Issues* and *Edit Issues*) in that project.

Jira API Token
--------------

To enable integration, you need a Jira Cloud **API token** and the associated
**user email**.

1. **Generate a Jira API Token**:

   - Go to: https://id.atlassian.com/manage-profile/security/api-tokens
   - Click **"Create API token"**
   - Enter a descriptive label (e.g., ``DejaCode Integration``)
   - Click **Create** and then **Copy** the token

2. **Store Your Credentials Securely**:

   - You will need both:

     - Your **Jira user email** (the one used to log into Jira)
     - The **API token** you just generated

.. note::

   The API token is required for authenticating to the Jira Cloud REST API.
   If your Jira instance is hosted on-prem (Jira Server/Data Center), the integration
   may not be supported without further customization.

DejaCode Dataspace Configuration
--------------------------------

To use your Jira credentials in DejaCode:

1. Go to the **Administration dashboard**
2. Navigate to **Dataspaces**, and select your Dataspace
3. Scroll to the **Jira Integration** section under **Configuration**
4. Enter:

   - Your **Jira user email**
   - The **API token** you generated

5. Save the form

Activate Jira Integration on Request Templates
----------------------------------------------

1. Go to the **Administration dashboard**
2. Navigate to **Workflow** > **Request templates**
3. Create or edit a Request Template in your Dataspace
4. Set the **Issue Tracker ID** field to your Jira base URL with project key, e.g.::

       https://YOUR-DOMAIN.atlassian.net/projects/PROJECTKEY
       https://YOUR-DOMAIN.atlassian.net/jira/software/projects/PROJECTKEY/summary

   - This URL must point to your Jira Cloud instance

Once the integration is configured:

- New **Requests** using this template will be automatically pushed to Jira
- Field updates (like title or priority) and **status changes** (e.g. closed) will be
  synced
- New **Comments** on a DejaCode Request will be propagated to the Jira Issue
