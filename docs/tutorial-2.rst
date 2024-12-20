.. _user_tutorial_2:

==================================
Tutorial 2 - Working with Packages
==================================

Sign into DejaCode.

Add a Package from a Download URL
=================================

Select :guilabel:`Packages` from the main menu bar.

Get the download URL of a publicly available package; for example,
select one of the releases at https://github.com/cli/cli/tags
and copy its download URL.

Click the green :guilabel:`Add Package` button and
paste the download URL that you copied into the text box.
Click the green :guilabel:`Add` button.

DejaCode presents the new Package.

- Refresh your browser page to see the :guilabel:`Action` tab.
- Explore the scan results.
- Select values to apply to the new Package definition, such as one or more licenses,
  a Copyright statement, and a Primary langauge.
- Click the :guilabel:`Set values to Package` button.
- Review, and optionally modify, the values in the modal dialog.
- Click the :guilabel:`Set values` button.
- Review the updated Package definition.
- Click the :guilabel:`Edit icon` (the pencil) near the top of the form.
- Make suitable changes to the Package definition; for example,
  enter text in the **Description** field.
- Click the :guilabel:`Update Package` button.
- Review the updated Package definition.

Create a Package using the data entry form
==========================================

Select :guilabel:`Packages` from the main menu bar.

Select the :guilabel:`Add Package form` option from the
green :guilabel:`Add Package` dropdown.
Enter the values that you know, you can refer to :ref:`data_model_package` for details
about each fields.

.. note:: A Filename or a Package URL (type + name) is required.
  The other fields are optional.

Keep the checked default to "Automatically collect the SHA1, MD5, and Size
using the Download URL and apply them to the package definition."

Click the :guilabel:`Add Package` button.

.. note:: DejaCode validates your entry, creates the package, applies automatic
  updates, and submits the a scan request to ScanCode.io if you have that enabled.

Review and edit your new package.

Import a Package to DejaCode from the PurlDB
============================================

Select the :guilabel:`PurlDB` option from the main menu bar :guilabel:`Tools` dropdown.

Use the :guilabel:`Filters` button to enter filtering or sorting criteria.
For example, select ``Release date (descending)`` to see recent data.
Click on the **Identifier** of an interesting package.

Review the data defined for the package.
Click the green :guilabel:`Create Package` button.

Review and edit the new DejaCode Package definition.
Click the :guilabel:`Add Package` button.
DejaCode validates the entry, creates the package, and applies automatic updates.

Review and edit your new package.

Import Package Definitions from a CSV
=====================================

Select :guilabel:`Packages` from the main menu bar.

Select the :guilabel:`Import packages` option from the green :guilabel:`Add Package` dropdown.

Click the :guilabel:`Download immport template` button.
DejaCode uses your browser to download a file named ``pakcage_import_template.csv``.
Open that file in a spreadsheet editor (such as Excel) and save it with a meaningful
name that describes the data you intend to import.

Enter the values for one or more packages into the CSV.  You can get additional help
for each field by clicking the :guilabel:`Show/hide Supported Columns` option on the
Import form in DejaCode.
Save your package import CSV.

Use the :guilabel:`Browse...` button near the bottom of the Import form to select your CSV and
click the blue :guilabel:`Upload` button to import the data to DejaCode.

DejaCode validates your data. Review the results and correct your CSV as needed.
Click the blue :guilabel:`Import` button to create the new packages in DejaCode.

Review the results of the Import presented by DejaCode.
Optionally edit and update the new package(s).
Optionally add the new package(s) to a Product using the :guilabel:`Add to Product` button.

Improve Package Data by Scanning
================================

Select :guilabel:`Packages` from the main menu bar.

Identify and select a Package that needs to be improved.
Click the :guilabel:`Action` button on the Package details form.

Optionally follow the progress of the Scan by selecting the :guilabel:`Scans`
option from the :guilabel:`Tools` dropdown on the main menu bar.

Open or refresh the Package form when the Scan is completed.
Review the results on the Scan tab, select data to apply to the Package definition,
modify that data as needed, and click the :guilabel:`Set values` button to save the updates.

Optionally click the :guilabel:`Download Scan data` button at the bottom of the `Scan` tab
to export a JSON-formatted file with the detailed scan results. You can view that file
in a readable format using a browser such as Firefox.

Continue refining and reviewing your packages.

In :ref:`user_tutorial_3`, we'll go further!
