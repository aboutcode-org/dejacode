.. _user_tutorial_1:

===============================
Tutorial 1 - Your first Product
===============================

Sign into DejaCode.

Create a Product
================

1. Select :guilabel:`Products` from the main menu bar.

2. Click the green :guilabel:`Add Product` button. Enter the values that you know,
you can refer to :ref:`data_model_product` for details about each fields.

3. Set a **name**, and click the :guilabel:`Add Product` button at the bottom of the
   form.

.. note:: You are ready to assign Inventory objects to your Product!

Import a Software Bill of Materials (SBOM) to your Product
==========================================================

You have the flexibility to employ either your CycloneDX or SPDX
Software Bill of Materials (SBOMs).

Alternatively, you can conveniently download one of the provided examples from
the following
`GitHub repository <https://github.com/nexB/dejacode/tree/main/docs/sboms/>`_.

On the Product details page, from the :guilabel:`Scan` dropdown, select
:guilabel:`Import Packages from manifest`:

* Click the :guilabel:`Choose file/Browse` button on the **Manifest file** field.
* Select your SBOM (.cdx.json or .spdx.json) and click the :guilabel:`Open` button.
* Check the :guilabel:`Update existing packages with discovered packages data` option.
* Click the :guilabel:`Import Packages` button.

DejaCode presents the :guilabel:`Imports` tab. Refresh your screen from the browser
to see the status of your import.

View your import results in the :guilabel:`Inventory tab`.

.. note:: Continue assigning packages to your Product as required.

Assign Packages to your Product
===============================

From the :guilabel:`Manage` dropdown, select :guilabel:`Packages`:

* Click the :guilabel:`Add Package to Product` button.
* Enter the start of a **package identifier**, for example ``diagrams`` and select
  package ``diagrams-0.12.0.tar.gz``.
  DejaCode gets the license ``mit`` from the package definition.
* Click the :guilabel:`Save` button.

You can see the results by selecting the :guilabel:`Inventory tab`.

Select :guilabel:`Packages` from the main menu bar.

* Locate one or more packages to be used in your Product.
* Use the checkbox on the left to select your package(s).
* Select the ``Product`` option from the :guilabel:`Add to` dropdown.
* Select your product from the dropdown list.
* Click the :guilabel:`Add to Product` button.

View your results in the :guilabel:`Inventory tab`.

.. note:: Continue assigning packages to your Product as required.

Review your progress
====================

Click the :guilabel:`Attribution` button:

* Accept all the default attribution configuration settings.
* Scroll down and click the :guilabel:`Generate Attribution`.
* Explore the attribution document that DejaCode presents to you.
* Save the document to your local file system using your browser File Save command.

Select :guilabel:`Reports` from the :guilabel:`Tools` dropdown:

* Select an appropriate report such as ``2-Product Package Analysis``.
* Enter your product Name and Version and click :guilabel:`Rerun Report`.
* Explore the results that DejaCode presents to you.
* Export the report to your local file system using the :guilabel:`Export` button.

Check for New Versions of your Product Packages
===============================================

Select :guilabel:`Products` from the main menu bar.

Click the **Product name** of the Product you are defining to open it.

From the :guilabel:`Manage` dropdown, select :guilabel:`Check for new Package versions`:
New Package Versions are displayed on the :guilabel:`Inventory` tab.
You can click on new versions and add them to DejaCode from the PurlDB.

Assign Catalog Components to your Product
=========================================

Select :guilabel:`Products` from the main menu bar.

Click the **Product name** of the Product you are defining to open it.

From the :guilabel:`Manage` dropdown, select :guilabel:`Components`:

* Click the :guilabel:`Add Component to Product` button.
* Enter the start of a **Component**, for example ``log`` and select
  a version of component ``Apache Log4J``.
  DejaCode gets the license ``apache-2.0`` from the component definition.
* Click the :guilabel:`Save` button.

You can see the results by selecting the :guilabel:`Inventory tab`.

Select :guilabel:`Components` from the main menu bar.

* Locate one or more components to be used in your Product.
* Use the checkbox on the left to select your package(s).
* Select the ``Product`` option from the :guilabel:`Add to` dropdown.
* Select your product from the dropdown list.
* Click the :guilabel:`Add to Product` button.

View your results in the :guilabel:`Inventory tab`.

.. note:: Continue assigning components to your Product as required.

Review your impact
==================

Click the :guilabel:`Attribution` button:

* Accept all the default attribution configuration settings.
* Scroll down and click the :guilabel:`Generate Attribution`.
* Explore the attribution document that DejaCode presents to you.
* Save the document to your local file system using your browser File Save command.

Select :guilabel:`Reports` from the :guilabel:`Tools` dropdown:

* Select an appropriate report such as ``2-Product Component Analysis``.
* Enter your product Name and Version and click :guilabel:`Rerun Report`.
* Explore the results that DejaCode presents to you.
* Export the report to your local file system using the :guilabel:`Export` button.

Assign Custom Components to your Product
========================================

Select :guilabel:`Products` from the main menu bar.

Click the **Product name** of the Product you are defining to open it.

From the :guilabel:`Manage` dropdown, select :guilabel:`Add custom Component`:
Enter the data fields that define your custom Component.
* Click the :guilabel:`Save` button.
Your results are displayed on the :guilabel:`Inventory tab`.

Click the :guilabel:`Attribution` button:

* Accept all the default attribution configuration settings.
* Scroll down and click the :guilabel:`Generate Attribution`.
* Explore the attribution document that DejaCode presents to you.
* Save the document to your local file system using your browser File Save command.

Select :guilabel:`Reports` from the :guilabel:`Tools` dropdown:

* Select an appropriate report such as ``2-Product Custom Component Analysis``.
* Enter your product Name and Version and click :guilabel:`Rerun Report`.
* Explore the results that DejaCode presents to you.
* Export the report to your local file system using the :guilabel:`Export` button.

Review the Licenses that Impact your Product
============================================

Select :guilabel:`Products` from the main menu bar.

Click the **Product name** of the Product you are defining to open it.

From the :guilabel:`Manage` dropdown, select :guilabel:`License Summary`:
Your Product Licenses are displayed on the :guilabel:`License summary form`.
DejaCode displays the **Usage Policy** and all the **Items** for each **License**.
Export the **License summary** by clicking the button :guilabel:`Export as CSV`.

Assign Everything Else to your Product
======================================

Continue refining and reviewing your product.

In :ref:`user_tutorial_2`, we'll explore Packages in greater detail!
