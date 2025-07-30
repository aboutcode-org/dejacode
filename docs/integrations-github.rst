.. _integrations_github:

GitHub Integration
==================

DejaCode's integration with GitHub allows you to automatically forward
**Workflow Requests** to GitHub repository **Issues**.
This behavior can be selectively applied to any **Request Template** of your choice.

GitHub Account and Personal Access Token
----------------------------------------

To enable integration, you need a GitHub **fine-grained personal access token (PAT)**.

1. **Access GitHub Developer Settings**:

   - Go to: https://github.com/settings/personal-access-tokens
   - Click **"Generate new token"** under *Fine-grained personal access tokens*

2. **Configure the Token**:

   - **Name**: Give it a clear name (e.g., ``DejaCode Integration``)
   - **Expiration**: Set an expiration date (recommended)
   - **Resource owner**: Choose your personal GitHub account or organization

.. note::

   It is recommended to **create a dedicated GitHub user** with a clear, descriptive
   name such as ``dejacode-integration``. This ensures that all GitHub issues managed by
   the integration are clearly attributed to that user, improving traceability and
   auditability.

3. **Repository Access**:

   - Under *Repository access*, select **Only select repositories**
   - Choose the repository where you want issues to be created and updated

4. **Permissions**:

   - Under *Repository permissions*, enable::

        Issues: Read and write

5. **Save and Copy the Token**:

   - Click **Generate token**
   - Copy the token and store it securely — you’ll need it for the next step

DejaCode Dataspace Configuration
--------------------------------

To use your GitHub token in DejaCode:

1. Go to the **Administration dashboard**
2. Navigate to **Dataspaces**, and select your Dataspace
3. Scroll to the **GitHub Integration** section under **Configuration**
4. Paste your GitHub token in the **GitHub token** field
5. Save the form

Activate GitHub Integration on Request Templates
------------------------------------------------

1. Go to the **Administration dashboard**
2. Navigate to **Workflow** > **Request templates**
3. Create or edit a Request Template in your Dataspace
4. Set the **Issue Tracker ID** field to your GitHub repository URL, e.g.::

       https://github.com/org/repo_name

Once the integration is configured:

- New **Requests** using this template will be automatically pushed to GitHub
- Field updates (like title or priority) and **status changes** (e.g. closed) will be
  synced
- New **Comments** on a DejaCode Request will be propagated to the GitHub Issue.
