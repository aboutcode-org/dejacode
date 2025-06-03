.. _reference_1:

=====================================================================
Reference 1 - Declared License Expression and License Clarity Scoring
=====================================================================

When you scan a Package from DejaCode, you can view the Scan Results in a
:guilabel:`Actions` tab on the Package details user view. DejaCode presents a selection of
scan details with an emphasis on license detection. You can also download the
complete :guilabel:`Scan Results` in .json format.

License Summary Fields
======================

In DejaCode, the Scan tab of the Package details user view shows
new license clarity scoring fields and new summary fields.

The new summary fields are:

- :guilabel:`declared_license_expression`
- :guilabel:`declared_holder`
- :guilabel:`primary_language`
- :guilabel:`other_license_expressions`
- :guilabel:`other_holders`
- :guilabel:`other_languages`

You can set the values from :guilabel:`declared_license_expression`,
:guilabel:`declared_holder`, and :guilabel:`primary_language` to the package definition
in DejaCode.

Declared License Expression
===========================

Declared License Expression is the primary license expression as determined from the
declaration(s) of  the authors of the package.

Note that the term declared_license_expression is used equivalently for the concept of
a primary license expression in order to align with community usage, such as SPDX.

Here is how ScanCode determines the value for a declared license expression, holder and
primary language of a package when it scans a codebase:

- Look at the root of a codebase to see if there are any package manifest files
  that have origin information.

- If there is package data available, collect the license expression, holder, and
  package language and use that information as the declared license expression,
  declared holder, and primary language.

- If there are multiple package manifests at the codebase root, then concatenate all
  of the license expressions and holders together and use those concatenated values
  to construct the declared license expression and declared holder

- If there is no package data, then collect license and holder information
  from key files (such as LICENSE, NOTICE, README, COPYING, ADDITIONAL_LICENSE_INFO).
  Try to find the primary license from the licenses referenced by the key files.
  If unable to determine a single license that is the primary, then concatenate
  all of the detected license expressions from key files together and use that as
  a conjunctive declared license expression. Concatenate all of the detected holders
  from key files together as the declared holder.

Note that a count of how many times a license identifier occurs in a codebase
does NOT necessarily identify a license that appears in the declared (primary) license
expression due to the typical inclusion of multiple third-party libraries that may have
varying standards for license declaration. It is possible that the declared license
expression constructed by this process may not appear literally in the codebase.

License Clarity Scoring
=======================

:guilabel:`License Clarity`
License Clarity is a set of criteria that indicate how clearly, comprehensively and
accurately a software project has defined and communicated the licensing that applies
to the project software. Note that this is not an indication of the license clarity of
any software dependencies.

:guilabel:`Score`
The license clarity score is a value from 0-100 calculated by combining the weighted
values determined for each of the scoring elements: Declared license, Identification
precision, License texts, Declared copyright, Ambiguous compound licensing, and
Conflicting license categories.

:guilabel:`Declared license`
When true, indicates that the software package licensing is documented at top-level or
well-known locations (key files) in the software project, typically in a package
manifest, NOTICE, LICENSE, COPYING or README file. Scoring Weight = 40.

:guilabel:`Identification precision`
Identification precision indicates how well the license statement(s) of the software
identify known licenses that can be designated by precise keys (identifiers) as provided
in a publicly available license list, such as the ScanCode LicenseDB, the SPDX license
list, the OSI license list, or a URL pointing to a specific license text in a project
or organization website, Scoring Weight = 40.

:guilabel:`License texts`
License texts are provided to support the declared license expression in files such as
a package manifest, NOTICE, LICENSE, COPYING or README. Scoring Weight = 10.

:guilabel:`Declared copyright`
When true, indicates that the software package copyright is documented at top-level or
well-known locations (key files) in the software project, typically in a package
manifest, NOTICE, LICENSE, COPYING or README file. Scoring Weight = 10.

:guilabel:`Ambiguous compound licensing`
When true, indicates that the software has a license declaration that makes it difficult
to construct a reliable license expression, such as in the case of multiple licenses
where the conjunctive versus disjunctive relationship is not well defined.
Scoring Weight = -10 (note negative weight).

:guilabel:`Conflicting license categories`
When true, indicates the declared license expression of the software is in the
permissive category, but that other potentially conflicting categories, such as
copyleft and proprietary, have been detected in lower level code.
Scoring Weight = -20 (note negative weight).

.. note:: Refer to :ref:`user_tutorial_2` for package creation and maintenance
  procedures.
