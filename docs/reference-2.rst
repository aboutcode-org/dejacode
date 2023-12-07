.. _reference_2:

===========================================================
Reference 2 - Understand the Package URL (purl) in DejaCode
===========================================================

A Package URL (purl) provides an exact, unique identification of a software object
that also includes information about its origin.

The Package URL is an open source community specification defined here:
https://github.com/package-url/purl-spec

The Package URL is now a widely accepted standard for identifying software objects,
critical to the usefulness of SBOMs (Software Bills of Materials) and for
integration with vulnerability tracking services.

Package URL Elements
====================

:guilabel:`Package URL (purl)`
DejaCode dynamically derives a Package URL (purl) value as a string that combines all
of the Package URL elements. The Package URL is displayed in multiple contexts in the
DejaCode UI, and is also available as a Column Template field in DejaCode Reports.

Package URL elements are:

- :guilabel:`Type`
- :guilabel:`Namespace`
- :guilabel:`Name`
- :guilabel:`Version`
- :guilabel:`Qualifiers`
- :guilabel:`Subpath`

:guilabel:`Type`
The Package URL Type is a short code to identify the type of this package.
For example: gem for a Rubygem, docker for a container, pypi for a Python Wheel or Egg,
maven for a Maven Jar, deb for a Debian package, etc.

:guilabel:`Namespace`
The Package URL Namespace is a Package name prefix, such as Maven groupid,
Docker image owner, GitHub user or organization, etc.

:guilabel:`Name`
The Package URL Name is the Name of the package.

:guilabel:`Version`
The Package URL Version is the Version of the package.

:guilabel:`Qualifiers`
Package URL Qualifiers provide extra qualifying data for a package such as the
name of an OS, architecture, distro, etc.

:guilabel:`Subpath`
The Package URL Subpath is an extra subpath within a package,
relative to the package root.

DejaCode automatically combines the various Package URL elements to display the
complete Package URL string. You can also reference that in a Package-based
Column Template in your DejaCode reports.

Setting the Package URL in DejaCode
===================================

When you create a new Package in DejaCode, the application automatically derives the
Package URL elements when you save it from the data your provide, primarily from the
Download URL value.

For existing Packages in DejaCode that do not have the Package URL set, you can use
the Administrative Browse Packages form to select those Packages and use the
:guilabel:`Set Package URL "purl" from the Download URL command` to prompt DejaCode
to calculate and set a Package URL using the available Package data.

Package Vulnerability Tracking
==============================

In DejaCode, there is a Dataspace option to "Enable VulnerableCodeDB access"
that authorizes DejaCode to access the VulnerableCodeDB using a Package URL (purl) to
determine if there are any reported vulnerabilities for a specific Package and return
the Vulnerability ID and related URLs to a Vulnerabilities tab in the Package details
user view. DejaCode displays a Vulnerability icon next to the Package identifier in
the user view list, and also in any Product Inventory list using that Package.

You can view the VulnerableCodeDB details of an affected Package and use the links to
access publicly available reports (e.g. CVE, CPE, GHSA, DSA), discussions, and status
updates regarding the vulnerabilities.

Your system administrator can configure DejaCode to provide the necessary credentials
to access a VulnerableCodeDB.

For more information about the open source VulnerableCode project, see
https://github.com/nexB/vulnerablecode

.. note:: Refer to :ref:`user_tutorial_2` for package creation and maintenance
  procedures.
