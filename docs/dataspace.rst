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
**reference data provided by nexB** from the data utilized in a specific DejaCode
installation.
Essentially, it introduces the notion of a "tenant" within a DejaCode installation,
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
3. **Support for Multi-Tenancy**: Enables the sharing of the same DejaCode instance among
   different organizations, each operating within its distinct Dataspace,
   promoting multi-tenancy while maintaining data segregation.

In summary, the Dataspace concept in DejaCode plays a pivotal role in maintaining data
integrity, enabling efficient updates, accommodating customization, and supporting
multi-tenancy for a diverse range of organizations within a DejaCode installation.

Setting up your License Library
===============================

After you have created your own Dataspace, you should copy the Reference License
Library into it.

To load the License Library data in your Dataspace, use the following command:

.. code-block:: bash

    dejacode clonedataset nexB <YOUR_DATASPACE_NAME> <SUPERUSER_USERNAME> --license_library

This ``clonedataset`` command may take several hours. Once it has completed, you can review
the results by signing on to the application as a superuser in your own Dataspace.

Select :guilabel:`Licenses` from the main menu bar to see the user view of the Licenses.

Select :guilabel:`Admin Dashboard` from the dropdown under your user name, then
:guilabel:`Licenses`, to access the **Browse Licenses** administrator form. In this mode,
you can select a license to review its details and modify it as appropriate for your
organization.

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

- **Data email notification:** Generally you want to leave this field unchecked. When
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
available to each one by clicking on the :guilabel:`(permission details)` link.

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
    You can control the visibility of the tabs of each application object by Permission
    Group from the :guilabel:`Tab permissions` button of your Dataspace definition.

Defining your Usage Policies
============================

Usage Policies express how your organization allows the use of Licenses, Components,
and Packages. The Reference Data provides sample Usage Policies that you can copy to
your Dataspace and customize, since a Usage Policy assignment is specific to your
organizational requirements.

- :ref:`how_to_1` explains how to define your Usage Policies, assign them to your
  Licenses, Components, and Packages, and make them visible to your users.
- :ref:`how_to_2` explains how to copy Usage Policies and other objects from the
  Reference Data to your Dataspace.

Reviewing your Dataspace settings
=================================

The presentation of your data to your user community, and the features available
in your Dataspace, are controlled by a number of options in your Dataspace
definition.

From the :guilabel:`Admin Dashboard`, select :guilabel:`Dataspaces` and open
your Dataspace definition.

There are several options grouped in sections such as:

* **Attribution Package Information** used when generating Product Attribution notices,
* **User Interface Settings** to control some aspects of the user interface,
* **Application Process Settings**, including the AboutCode integrations
  (see :ref:`integrations_aboutcode`).

These are initially set to the recommended default settings when you install.

If you make any changes, be sure to save them by clicking the :guilabel:`Save`
button at the bottom of the form.

.. note:: You can get **additional information** and help for each field on this form
    (and any administrative form in DejaCode) from the help text displayed below the
    field.

Using your Component Catalog
============================

After you have set up the License Library in your own Dataspace, and have defined your
Usage Policies, you are ready to start working with **Components** and **Packages**.

- Copy the Components and Packages that you need from the Reference Data, as explained
  in :ref:`how_to_2`.
- Create Packages from a download URL, a scan, the PurlDB, or a CSV import, as
  explained in :ref:`user_tutorial_2`.
- Set their Usage Policies from their Licenses, as explained in :ref:`how_to_1`.

Enabling integrations
=====================

To scan packages, browse the PurlDB, and track vulnerabilities, enable the AboutCode
integrations in your Dataspace: see :ref:`integrations_aboutcode`.
