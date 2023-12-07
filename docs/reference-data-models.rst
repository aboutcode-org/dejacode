.. _data_model:

================
Models reference
================

DejaCode Modules
================

DejaCode includes the following modules:

* **Product Portfolio**: Record and maintain software inventories for your products.
* **Component and Packages Catalog**: Identify the origin, licensing terms and
  relationships of open source and other software components by consulting the catalog.
  Communicate your company usage policy for components to your users, and provide
  them with detailed guidance.
* **License Library**: Understand software licensing terms with the nexB library
  of open source and proprietary licenses. Communicate your company usage policy
  for licenses to your users, and provide them with detailed guidance.
* **Reporting**: Create your own reports, from your queries and column templates,
  to explore, analyze and export your DejaCode application data.
* **Workflow Requests**: Create your own request templates to enable your users
  to submit requests regarding your products, components, licenses and their
  policies, and to track the progress of each request.
* **API**: Use the DejaCode API to integrate with your other data sources and
  applications.

.. _data_model_product:

Product model
=============

* **Name** - Your product name. Required field (the only required field).

* **Version** - Your product version. Recommended field.
  For example, ``4.1.3``

* **Owner** - Your owner name. Recommended field.
  If you have defined an Owner for your organization, enter it here.
  You can enter ``Unspecified`` and update it later.

* **License expression** - The license that applies to your product.
  If you have defined a license for your organization products, enter it here.
  You can enter ``commercial-license`` or ``proprietary-license`` and update it later.

* **Copyright** - Your product copyright statement. Recommended field.
  For example, ``Copyright (c) Starship LLC``

* **Notice text** - Your product notice.
  For example, ``Licensed by Starship LLC``

* **Description** - A concise description of your product.

* **Keywords** - Use the autocomplete feature to enter and select keywords.
  For example, ``Framework, Web Service``

* **Primary language** - Use the autocomplete feature to enter and select a
  primary language. For example, ``Python``

* **Homepage URL** - The URL of the home page for your product.
  This must be a valid URL.

* **Contact** - Contact name for your product.

* **Active** - Leave this checked (True) for an Active product.

* **Configuration status** - Keep the ``New`` default value.

* **Release date** - Use the date picker to specify your product release date.

.. _data_model_package:

Package model
=============

* **Filename** - The exact filename of the package.

* **Download URL** - The download URL for obtaining the package.

* **Package URL Type** - A short code to identify the type of this package.
  For example: gem for a Rubygem, docker for a container, pypi for a Python Wheel or Egg,
  maven for a Maven Jar, deb for a Debian package, etc.

* **Package URL Namespace** - Package name prefix, such as Maven groupid,
  Docker image owner, GitHub user or organization, etc.

* **Package URL Name** - Name of the package.

* **Package URL Version** - Version of the package.

* **Package URL Qualifiers** - Extra qualifying data.

* **Package URL Subpath** - Extra subpath within a package, relative to the package root.

* **License expression** - The license expression that applies to the package.
  You can enter a placeholder such as ``other-permissive`` and update it later.

* **Copyright** - The package copyright statement. Recommended field.
  For example, ``Copyright (c) Starship LLC``

* **Notice text** - The notice provided by the package authors.
  For (a very simple) example, ``Licensed by Starship LLC under Apache 2.0``

* **Holder** - The name(s) of the copyright holder(s) of a package,
  as documented in the code

* **Author** - The name(s) of the author(s) of a package as documented in the code.

* **Description** - Free form description, preferably as provided by the author(s).

* **Homepage URL** - The homepage URL of the project responsible for the package.
  This must be a valid URL.

* **Primary language** - Use the autocomplete feature to enter and select a
  a primary language. For example, ``Python``
