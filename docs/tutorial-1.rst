.. _user_tutorial_1:

===============================
Tutorial 1 - Your first Product
===============================

Prerequisites:
- You’ve created your DejaCode account **(link to Quickstart guide here)**
- You’re `signed in <https://public.dejacode.com/login/>`_ to DejaCode

----------------
Create a Product
----------------

First, we need to create the product:

1. Select `Products <https://public.dejacode.com/products/>`_ from the main menu bar.
2. Click the green `Add Product <https://public.dejacode.com/products/add/>`_ button.
3. Enter a ‘Name’ for your product
4. Enter any other values that you know (you can refer to `Product model <https://dejacode.readthedocs.io/en/latest/reference-data-models.html#data-model-product>`_ for details about each field)
5. Click ‘Add Product’ at the bottom of the page

----------------------------
Load an SBOM to your Product
----------------------------

The next step is to load a SBOM (Software Bill of Material) into your new product. This is essentially a list of all the components, dependencies, and metadata associated with your application.

.. note::
   For this tutorial, you can use one of our example DBOM files from our `GitHub repository <https://github.com/aboutcode-org/dejacode/tree/main/docs/sboms/>`_.

Now let’s import it:

1. On the product details page (you should be there already), select the ‘**Actions**’ dropdown at the top of the page, then select ‘**Import SBOM**’
2. Click ‘Choose File’ then select your SBOM file (.cdx.json or .spdx.json)
3. Check the ‘Update existing packages with discovered packages data’ checkbox
4. *(Optional) You can also check ‘Scan all packages of this product post-import’ to initiate a ScanCode scan of all the packages assigned to your product*
5. Click the '**Import**' button.
6. When the upload is done, you’ll be shown the ‘**Imports**’ tab, with a status by your import.
7. Refresh the page periodically until the status ideally reads ’Completed’

You can now view your import results in the 'Inventory' tab at the top of the page.

-------------------------------
Assign Packages to your Product
-------------------------------

The next step is to assign packages to your product. A package is is a collection of software files and associated metadata that is managed as a single unit for tracking, compliance, and license management purposes.

There are two ways to assign a package to your product.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Option 1: Add Package directly to Product
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The first option entails opening the product, and adding the package to the list.

1. On the product details page, select the ‘**Manage**’ dropdown at the top of the page, then select ‘**Packages**’
2. Click the **'Add Package to Product'** button at the bottom left of the page
3. Start typing the package identifier from the package definition to search for your package (for example, if you wanted to add the package 'diagrams-0.12.0.tar.gz', it should only need to type 'dia' for it to be returned)
4. Select the package
5. Click the '**Save**' button
6. Repeat steps to add more packages

You've now added the new package, and you can see the results by selecting the 'Inventory' tab on the product details page

**(You can also do this by selecting your packages on the 'Packages' page, and clicking 'Add to' then 'Product')**

------------------------------
Add Components to your Product
------------------------------

You can also add `Components <https://public.dejacode.com/components/>`_ to you Product. A Component is an individual open-source or third-party software element (library, framework, tool, etc).

Like packages, there are two ways to add a Component to your Product.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Option 1: Add Component directly to Product
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. On the product details page, select the ‘**Manage**’ dropdown at the top of the page, then select ‘**Components**’
2. Click the **'Add Component to Product'** button.
3. Start typing the name of the Component to search (for example, type 'Apache Log4J')
4. Select your Component from the returned list
5. Click '**Save**'
6. Repeat steps to add more Components

You've now added the new component, and you can see the results by selecting the 'Inventory' tab on the product details page

**(You can also do this by selecting your components on the 'Components' page, and clicking 'Add to' then 'Product')**

--------------------------------------------
Review the Licenses that Impact your Product
--------------------------------------------

Now you've added your product and assigned packages and components, you can now review your licences.

The simplest way to do this is to view your 'Licence summary'.

1. Open the product details page
2. Select the ‘**Manage**’ dropdown at the top of the page, then select ‘**Licence Summary**'

Your full list product licences will now be displayed in a table view. DejaCode displays the **Usage Policy** and all the **Items** for each **License**.

.. note::
   You can export the **License summary** by clicking the **'Export as CSV'** button at the top right of the page.

-----------------------------------------------------------------------------------------------------------------------
Next: `Tutorial 2 - Working with Packages <https://dejacode.readthedocs.io/en/latest/tutorial-2.html#user-tutorial-2>`_
-----------------------------------------------------------------------------------------------------------------------
