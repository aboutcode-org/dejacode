.. _how_to_1:

=====================================
How To 1 - Manage your Usage Policies
=====================================

Sign into DejaCode.

.. note:: Sign in as a User with full administrative permissions.

Review and Maintain your Usage Policies
=======================================

- Select the :guilabel:`Dashboard` option from the dropdown beneath your User name.
- Select the :guilabel:`Usage Policies` option in the :guilabel:`Policy` panel.
- Review the Usage Policies currently defined for your dataspace.
- Optionally click the :guilabel:`View Reference Data` button in the upper left section
  of the form. Review the Reference Data Usage Policies. Optionally, you can
  click the :guilabel:`Copy to my Dataspace` button to the left of any entry in order to
  add or update a Usage Policy to your own Dataspace from Reference Data. You can click
  the :guilabel:`View My Data` button to return to your own Usage Policies.

**Examine the Details**:

- Open a Usage Policy or add a new one.
- The **Field Name** should concisely express a Usage Policy defined by your
  organization.
- The **Object type** identifies the kind of object governed by the Usage Policy.
  Consider, for example, that your Usage Policy list may vary somewhat for Licenses as
  opposed to specific Components.
- The **Guidelines** are intended to explain your organization's definition of a Usage
  Policy and can also provide detailed requirements and instructions for compliance.
- The **Icon** associated with a Usage Policy should be one from the
  available icons at https://fontawesome.com/icons?d=gallery&m=free
- The **Color** should be a valid HTML color code (e.g. #FFFFFF) to apply to your icon.
- The **Compliance Alert** indicates how the usage of a DejaCode object (license,
  component, package, etc.) complies with your organization's policies. Value choices
  are:
  "Pass" (or empty, the default value),
  "Warning" (should be reviewed), and
  "Error" (fails compliance policy guidelines).
- The **Associated product relation status** enables you to specify the product relation
  status to use automatically when a component or package with an assigned usage policy
  is added to a product, overriding the general default defined in the product relation
  status table, which supports the list of values that you can select. By defining this
  association, you can save a lot of time and effort when you are reviewing a product
  inventory by concentrating your attention on the exceptions.
- In the :guilabel:`Associated Policies` section, you can define a default value for
  DejaCode to apply automatically on an associated object. This is especially pertinent
  for automatically applying a Usage Policy to a Component or Package when you assign a
  License to one of those objects.

Click the :guilabel:`Save` button in the lower right section of the form.
Review your progress in the Usage Policies list.

Assign your Usage Policies to Licenses
======================================

- Select the :guilabel:`Licenses` option from the dropdown beneath your User name.

**Filter Licenses as Needed**

- Use the **Filter** dropdown in the upper right to restrict the amount of data that you
  process to a manageable list. For example, you can:
- Filter to see all Licenses where **Usage Policy** is empty.
- Filter to see Licenses in a **Category** , **License profile** , or **License style** .
- Select a **Reporting query** to perform more complex filtering.

**Perform Mass Updates to Set License Usage Policies**

- Use the checkboxes on the left side of the form to select Licenses for update.
- Select the **Mass update** option from the dropdown in the lower left and
  click the **Go** button.
- Check the **Usage policy** field and choose the Policy to apply to the selected
  Licenses.
- Click the :guilabel:`Update records` button in the lower right.

Continue this process to assign Usage Policies to all of your Licenses.
You can also assign a Usage Policy to a single License on the Change License form.

Assign your Usage Policies to Components
========================================

- Select the :guilabel:`Components` option from the dropdown beneath your User name.

**Filter Components as Needed**

- Use the **Filter** dropdown in the upper right to restrict the amount of data that you
  process to a manageable list. For example, you can:
- Filter to see all Components where **Usage Policy** is empty.
- Select a **Reporting query** to perform more complex filtering.

**Set Component Usage Policies from Licenses**

- Use the checkboxes on the left side of the form to select Components for update.
- Select the **Set usage policy from licenses** option from the dropdown in the lower
  left and click the **Go** button.
- Use the checkboxes on the right to select Components to update.
- Click the **Set policies** button in the lower right to apply updates.
- Continue this proess to assign Usage Policies to all of your Components.
- Note that you can also edit any Component to specify a Usage Policy different from
  its primary License.

Use the same process to set Package Usage Policies from Licenses.

The Importance of Package and Component Usage Policy Assignments
================================================================

Note that when you are familiar with the way that product teams actually use a
package or component, you may want to set the usage policy on those items to reflect
that usage. For example, if you know that a copyleft-licensed item is always used
unmodified, or as a library, or only as a non-deployed/non-distributed tool, you can
avoid the effort of reviewing each product assignment of that item by setting the
usage policy to indicate that it is approved for product usage. A similar logic
applies to packages or components with complex license expressions; you can confirm
that your usage of that item is only going to execute the code in a certain way and
set the item usage policy to reflect that.

Make Usage Policies Visible to your Users
=========================================

- Select the :guilabel:`Dashboard` option from the dropdown beneath your User name.
- Select the :guilabel:`Dataspaces` option in the :guilabel:`Administration` panel.
- Select your Dataspace to open it and edit the details.
- In the :guilabel:`User Interface Settings` section,
  check the **Show usage policy in user views** in order to
  include the usage policy in user views that show licenses, components or packages.
- Save your work.

Review Usage Policy Impact
==========================

- Open the User View List of Licenses, Components, or Packages to see the Usage Policy
  Icon associated with objects that have Usage Policy assigned. If you open one of these
  objects to see the details view, there is also a Usage Policy tab that shows more
  extensive information about the Policy, including your Guidelines.
- Open a Product and select the Inventory tab. In addition to the Usage Policy Icons,
  you will also see that Items with a Compliance Alert are highlighted with yellow for
  a warning and red for an error, as you defined on the associated Usage Policies.
- You can add the Usage Policy Label as a field to your Column Templates in order to
  see them on your Reports, and to include those values when you export the Report
  Results to your preferred output file format for distribution to your team.

Continue refining and reviewing your Usage Policies.

Export License Policy Definitions
=================================

You can export a list of your License Keys along with associated Usage Policy details
to a YAML-formatted file. This file can be used by other tools such as the open source
ScanCode Toolkit (scancode-toolkit).

- Select the :guilabel:`Dashboard` option from the dropdown beneath your User name.
- Select the :guilabel:`Usage Policies` option in the :guilabel:`Policy` panel.
- Click the :guilabel:`Export License Policies as YAML` button in the upper right
  section of the form.
- View or edit the exported **license_policies.yml** file in your preferred text editor.
- Use the file as an input option to ScanCode Toolkit to enhance the output results.
