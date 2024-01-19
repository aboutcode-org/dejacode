.. _dataspace:

=========
Dataspace
=========

The Dataspace serves as a pivotal mechanism within DejaCode, facilitating the
segregation of data for each organization while maintaining a unified storage
structure in the same database, schema, or table.
Within a given installation, multiple "Dataspace" organizations can be defined,
but there exists only one reference.

This concept is a crucial element employed across DejaCode to effectively separate
**reference data provided by nexB** from the data utilized in a specific DJE
installation.
Essentially, it introduces the notion of a "tenant" within a DJE installation,
enabling the isolation of organization-specific and/or private records.
This segregation supports both multi-tenancy and the coexistence of nexB-provided
reference data and organization-specific or customized data.

The key purposes of this separation include:

1. **Orderly and Simplified Data Updates**: Facilitates smooth and streamlined updates
   from nexB reference data, ensuring efficient data synchronization and exchange
   across Dataspaces.
2. **Dataspace-Specific Customizations**: Allows for customization of Dataspace-specific
   data, such as configurations for license tags or specific preferences, tailoring
   the installation to the unique needs of each organization.
3. **Support for Multi-Tenancy**: Enables the sharing of the same DJE instance among
   different organizations, each operating within its distinct Dataspace,
   promoting multi-tenancy while maintaining data segregation.

In summary, the Dataspace concept in DejaCode plays a pivotal role in maintaining data
integrity, enabling efficient updates, accommodating customization, and supporting
multi-tenancy for a diverse range of organizations within a DJE installation.

Setting up your License Library
===============================

After you have created your own Dataspace, you should copy the Reference License
Library into it.

To load the License Library data in your Dataspace, use the following command:

.. code-block:: bash

    dejacode clonedataset nexB <YOUR_DATASPACE_NAME> <SUPERUSER_USERNAME> --license_library

This ``clonedataset`` command may take several hours. Once it has completed, you can review
the results by signing on to the application as a superuser in your own Dataspace.

Select the **Licenses** option in the navigation header to see the user view of the Licenses.

Select the **Administration > Licenses** option from the dropdown list under your user name
to access the **Browse Licenses** administrator form. In this mode, you can select
a license to review its details and modify it as appropriate for your organization.

Managing Users in your Dataspace
================================

As part of your DejaCode installation process you should have created a Superuser
in the **nexB Reference Dataspace**; you want to keep that User for DevOps purposes
in your ongoing maintenance of DejaCode.

Most of the Users that you need to define should be assigned to your own Dataspace.
While you are initially setting up your own Dataspace, you can define those user
participants in your project team as Superusers in order to give them access to the
various entities that need to be reviewed and defined to meet the requirements of your
organization.
Please note, as before, that you should also check the Staff status field when you
define a Superuser to enable access to the Administrative part of DejaCode.

When you define a User, take note of specific essential fields:

- **Email notification:** Generally you want to leave this field unchecked. When
  checked, the User will receive an email notification for every update to the
  database in your dataspace, and it is very unlikely that you will want that.
- **Staff status:** Be sure to check this field for any User that needs to add
  and/or update the data in your Dataspace.
- **Superuser status:** Check this field to enable the User to perform all system
  and data administration tasks in DejaCode. This status is especially helpful
  while you are in Dataspace setup mode to ensure that members of the project
  team have the DejaCode access that they need. Note that you will generally
  leave this field unchecked for most of your Users.

User Permission Groups
======================

The **Permission Groups** are defined to support the most likely roles that your
User Community will perform. You can get details about the application tasks
available to each one by clicking on the **(permission details)** link.

Generally, the two most important and useful Permission Groups for you to use
are the following:

- **Legal:** The Legal Users are primarily responsible for setting policy on your
  Licenses and Components, and communicating those details to your overall User
  Community through DejaCode. Be sure to also check **Staff status** when you
  assign the Legal Permission Group to a User. You may also assign this group
  to members of your senior management team.
- **Engineering:** The Engineering Users primarily use DejaCode to read Component
  and License information, including the policies that you have set, and also to
  create new Components and/or copy them from Reference Data. If you want to
  restrict such Users from actually performing data updates in DejaCode, simply
  make sure that **Staff status** is not checked; otherwise, you can give them
  access to creating and updating the Components that they discover as part of
  their ongoing software development process.

.. note::  All Users can see the data in the User Views of the application.
    You can control the **Tab Visibility** of each application object by Permission
    Group from your Dataspace definition.

Defining your Usage Policies
============================

The Reference licenses are intentionally not defined with Usage Policy assignments,
since a Usage Policy assignment is specific to your organization.

To get started:

* Navigate to the **Administration** dashboard and select the **Usage policies** option.

* After your initial installation, the results on your **Browse Usage policies** form
  will probably be empty.

* You can kickstart the process of defining policies by copying Usage Policies
  defined in Reference Data to your Dataspace.

* Click on the **View Reference Data** button, to view the sample Usage Policies
  defined in Reference Data.

* You can copy them one by one with the "Copy to my Dataspace" link, or

* Click on the checkbox at the top of the list to select all of the Reference Data
  Usage Policies, and then select the **Copy the selected objects** option from
  the dropdown menu at the bottom left of the page and click the **Go** button.

* On the following screens, accept all defaults and click the **Copy** button in the
  lower right hand corner of the page.

When you return to the **Browse Usage policies** page, you can see the results of your
copy action. Note that the **Show all** button resets the view all records from your
own Dataspace, and the **View Reference Data** button resets the view to see the
originally installed data.

At this point you can decide to work with the sample Usage Policies that you copied,
or you can modify them to customize them, create new ones and/or delete those that
you do not need.

.. note:: The techniques that you used to **Copy Reference Data** to your own Dataspace
    are the same that you can use from most of the **Browse forms** in DejaCode.

Assigning Usage Policies to licenses
====================================

There are more than **2,000 Licenses** in your License list from Reference Data, so
you will want to develop a strategy that works for your business requirements to
assign Usage Policies efficiently. The two basic techniques are:

1. One at a time: edit a license and assign it a policy from the dropdown field on
   the **Change License** form.
2. Mass update: Select a group of licenses on the **Browse License** form and use Mass
   Update to assign a Usage Policy to that group of licenses.

As an example of the first technique, locate and select the license with the key
of **apache-2.0** in your list. Your organization probably already has a policy
regarding this very common license; you may simply allow engineering to use
components under that license or you may require additional review of how they
are actually using those components or you may have concerns about specific
clauses in that license, depending on your business requirements.
Based on those considerations, you should be able to select a **Usage Policy** from the
dropdown list on that field. At this point you may also choose to enter text
into the **Guidance** field, which is reserved for comments unique to your
organization, as well as the **Guidance URL** field which may point to a web page
(usually one internal to your organization) that provides additional extended guidance.
Both of the Guidance fields are optional, and you can always return to them
at a later time. When you have completed your updates, click the **Save**
button at the bottom right corner of the page to save your changes.

As an example of the second technique, let us assume that your legal group does
not require any review of the usage of components under a **Public Domain license**.
You can set a **Usage Policy** for all of those licenses at once:

* Set a filter on the **Browse Licenses** page, and select the **Public Domain**
  choice under the **Category** filter.

* Use the **Select All** checkbox in the upper left corner of the list  to select
  all the licenses in the **Public Domain** category,

* then select the **Mass update** option from the dropdown list at the bottom
  of the page, and click the **Go** button.

The application will present a form that shows the field updates that you can apply to
all of the selected Licenses.

* Select the **Usage Policy** field using its checkbox, and then select
  a Usage Policy from the dropdown.

* Click the **Update records** button in the lower right hand of the form to
  save this Usage Policy assignment.

.. note:: The techniques that you used to **Mass Update** licenses in your Dataspace
    are the same that you can use from most of the **Browse forms** in DejaCode.

Reviewing your Dataspace settings
=================================

The presentation of your License Usage Policies and selected license attributes
to your user community is controlled by a number of flags in your Dataspace
definition.

From the **Administration dashboard**, select **Dataspaces** and open
your Dataspace definition.

There are several options grouped in sections such as:

* **Attribution Package Information** used when generating Product Attribution notices,
* **User Interface Settings** to control some aspects of the user interface,
* **Application Process Settings**  .

These are initially set to the recommended default settings when you install.

To complete your initial "Usage Policies" configuration, make sure that the
**Show usage policy in license library view** option is checked.

If you make any changes, be sure to save them by clicking the **Save**
button at the bottom of the form.

To see the results of your **Usage Policy assignments**, click the **Licenses** option
at the top of any page to return to the user view of the **License Library**.
The icon of any Usage Policy that you assigned to a License will be displayed in
its own column on the License list.

.. note:: You can get **additional information** and help for each field on this form
    (and any administrative form in DejaCode) by clicking the **Show/Hide help** button
    at the top of the page.

Using your Component Catalog
============================

After you have setup the License Library in your own Dataspace, and have defined your
Usage Policies, you are ready to start working with **Components** and **Packages**.
There are multiple ways to discover and copy the components that interest you from
Reference Data; here are a few ways to do that:

1. Search for a specific component or package in the User View of the Reference Data,
   select the one you want, and copy it to your Dataspace.
2. Search and/or filter Reference Data components or packages using the Administrator's
   Browse Components or Browse Packages pages, select the ones you need, and Copy the
   selected entries to your Dataspace, either one by one or many at once.

As an example of the first technique, click on the **Components** option to see the
User View of the components in your Dataspace. You can use this view to search
your own Dataspace, or you can click on the **View Reference Data** button to search
for new components that you need.

For example, if you enter ``aboutcode`` in the search field near the top of the form,
you will see at least two versions of the component "AboutCode toolkit" in Reference
Data. Click on the **+** sign to expand the list to see all the versions.
You can open version ``3.0.2`` to see if it is the component that you want.

Simply click the **Copy to my Dataspace** button, and on the following screens,
accept all defaults and click the **Make the Copy** button
in the lower right hand corner of the form.

To review and possibly edit the copied component, click on its name on the page
presented by the application, which will take you to the **Change Component form**.
You can scroll down to see the Usage Policy field on that component,
and if you accepted and/or checked the Dataspace option to
**Set usage policy on new component from licenses** the Usage Policy will already
be assigned. In our AboutCode toolkit example, this is based on your Usage Policy
on the ``Apache 2.0 (apache-2.0)`` license.

You can review and optionally modify any of the fields on the component and Save your
changes.
The copied component now appears in the Components User View, ready for your user
community to see.

As an example of the second technique, go to the **Browse Components** form in the
Administrator side of the application, and click the **View Reference Data** button.
Enter the value ``name^angular`` in the search field (which means: find all components
with a name that begins with "angular") and press Return.

DejaCode will show you a list of various components that meet your search criteria.
Identify the ones that you want and check the selection boxes.
From the dropdown list in the lower right corner of the form, select
**Copy the selected objects** and click the Go button.

On the next page, you may see a message if any of the selected components already
exist in your own Dataspace; optionally, you can check any of those to update those
components from Reference Data. Click the **Make the Copy and Update** button to
continue, and DejaCode shows you the results of your action on the next page.

.. note:: The techniques that you used to **Copy Reference Data** to your own Dataspace
    are the same that you can use from most of the **Browse forms** in DejaCode.

Assigning Usage Policies to Components
======================================

As you add new components to your Dataspace, you will want to develop a strategy
that works for you business requirements to assign Usage Policies efficiently.

The basic techniques to use in your own Dataspace are:

1. Edit a component and assign it a policy from the dropdown field on the
   **Change Component** form.
2. Select a group of components on the **Browse License** form and use **Mass Update**
   to assign a policy to that group of components.
3. Select a group of components on the **Browse License** form and use the
   **Set usage policy from licenses** option in the dropdown list in the lower
   right hand corner of the form and follow the prompts to complete that action.

.. _dejacode_dataspace_scancodeio:

Enable package scanning with your ScanCode.io server
====================================================

DejaCode integration with a ScanCode.io server enables you to take
advantage of the detailed Package metadata that ScanCode can provide for
publicly available software.

You can:

* Simply provide a Download URL for the Package to initiate Package creation,
  data collection, and scanning in DejaCode.
* Initiate scanning on an existing Package in your DejaCode database.
* View formatted scan results on the Scan tab of the DejaCode Package user view.
* Move specific results returned from a scan to your Package definition.
* Download the scan results to a JSON-formatted file to integrate with other
  analysis and reporting tools.

Install and configure ScanCode.io
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. warning::
    If you plan to run ScanCode.io **on the same server** (virtual or  physical) as
    the DejaCode instance, **ensure that the host machine has sufficient resources**
    to handle both applications.
    Also, you will have to provide custom network ports for the ScanCode.io application
    as the ports 80 and 443 will be already used by the DejaCode application.
    See https://scancodeio.readthedocs.io/en/latest/installation.html#use-alternative-http-ports

1. Install a ScanCode.io server following instructions at
   https://scancodeio.readthedocs.io/en/latest/installation.html

   For production use, the **minimum system requirements for ScanCode.io** are:

   +-----------+---------------------------------------------------------------------+
   | Item      | Minimum                                                             |
   +===========+=====================================================================+
   | Processor | Modern X86 64 bit Multi Core, with at least **8 physical cores**    |
   +-----------+---------------------------------------------------------------------+
   | Memory    | **64GB** or more (ECC preferred)                                    |
   +-----------+---------------------------------------------------------------------+
   | Disk      | **2x500GB SDD** in RAID mirror setup (enterprise disk preferred).   |
   +-----------+---------------------------------------------------------------------+

2. Enable the ScanCode.io authentication system following:
   https://scancodeio.readthedocs.io/en/latest/application-settings.html#scancodeio-require-authentication

3. Create a user in ScanCode.io and get its API key for authentication by your
   DejaCode instance:
   https://scancodeio.readthedocs.io/en/latest/command-line-interface.html#scanpipe-create-user-username

4. Set the ScanCode.io Server URL and API key in your Dataspace Configuration:

 - Access your DejaCode web application **Administration dashboard**.
 - Navigate to the **Dataspaces** section and select your Dataspace name.
 - Within the **Application Process Settings** section, enable the
   **Enable package scanning** option.
 - Update the values for the **ScanCode.io URL** and **ScanCode.io API key** fields
   located in the **Configuration** panel at the bottom of the form.
 - Click the **Save** button.

You can now access the **Scans** section from the **Tools** menu and request package
scans from this view.

.. _dejacode_dataspace_purldb:

Enable PurlDB service
=====================

DejaCode integration with the **PurlDB** service enables user access to the
PurlDB option from the Tools menu, which presents a list of PurlDB data mined and
scanned automatically from multiple public sources.
Users can view PurlDB details and can create DejaCode Package definitions using
those details, and DejaCode also presents a new PurlDB tab when viewing the details
of a Package with matching key values.
This integration also enhances the **Global Search** feature to extend the search scope
beyond the standard DejaCode objects (Packages, Components, Licenses, Owners)
and perform an asynchronous query of the PurlDB to find relevant data.

You can:

* Browse and search from a list of over **21 millions Packages**.
* Get extra information on your local Packages from the **"PurlDB" tab**.
* **Create local Packages automatically** from entries found in the PurlDB.
* Enhance the **Global search** results with Packages from the PurlDB.
* Check for **new Package versions** from your Products inventory

PurlDB service
^^^^^^^^^^^^^^

A public instance of **PurlDB** is available at
https://public.purldb.io/api/packages/

Alternatively, you have the option to run your instance of PurlDB by
following the documentation provided at https://purldb.readthedocs.io/

Set the PurlDB Server URL and API key in your Dataspace Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

 - Access your DejaCode web application **Administration dashboard**.
 - Navigate to the **Dataspaces** section and select your Dataspace name.
 - Within the **Application Process Settings** section, enable the
   **Enable PurlDB access** option.
 - Update the values for the **PurlDB URL** and **PurlDB API key** fields
   located in the **Configuration** panel at the bottom of the form.
 - Click the **Save** button.

You can now access the **PurlDB** section from the **Tools** menu and browse package
from this view.

.. _dejacode_dataspace_vulnerablecode:

Enable VulnerableCodeDB service
===============================

DejaCode integration with the **VulnerableCodeDB** service authorizes DejaCode to access
the VulnerableCodeDB using a Package URL (purl) to determine if there are any
**reported vulnerabilities for a specific Package** and return the Vulnerability ID
and related URLs to a **Vulnerabilities tab** in the **Package details** user view.

DejaCode displays a Vulnerability icon next to the Package identifier in the user view
list, and also in any Product Inventory list using that Package.

Users can view the VulnerableCodeDB details of an affected Package and use the links to
access publicly available reports (e.g. CVE, CPE, GHSA, DSA), discussions, and status
updates regarding the vulnerabilities.

You can:

* Explore the Vulnerabilities that affect a Package.
* Review and edit your Product Package assignments to record your analysis, the actions
  you have taken, and the current status of your usage of that Package.

VulnerableCodeDB service
^^^^^^^^^^^^^^^^^^^^^^^^

A public instance of **VulnerableCodeDB** is available at
https://public.vulnerablecode.io/api/

Alternatively, you have the option to run your instance of VulnerableCodeDB by
following the documentation provided at https://vulnerablecode.readthedocs.io/

Set the VulnerableCodeDB Server URL and API key in your Dataspace Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

 - Access your DejaCode web application **Administration dashboard**.
 - Navigate to the **Dataspaces** section and select your Dataspace name.
 - Within the **Application Process Settings** section, enable the
   **Enable VulnerableCodeDB access** option.
 - Update the values for the **VulnerableCode URL** and **VulnerableCode API key**
   fields located in the **Configuration** panel at the bottom of the form.
 - Click the **Save** button.

You can now see Vulnerabilities in the Packages user view.
The availability of the services can be checked by clicking on your user name in the
top right corner of the app, then "Status > Integrations Status".
