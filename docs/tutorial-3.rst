.. _user_tutorial_3:

Tutorial 3 - Working with Reports
=================================

.. note::
    **Before you start**:

    - A staff account with access to the :guilabel:`Admin Dashboard`.

Sign in to DejaCode.

Create a Query, a Column Template, and a Report
-----------------------------------------------

A DejaCode Report combines a **Query**, which selects the objects, and a
**Column Template**, which defines the fields to display. Follow
:ref:`user_tutorial_6_vuln_report` for the step-by-step creation of all three.

.. tip::
    - For date fields, DejaCode recognizes the special values ``today``,
      ``past_7_days``, ``past_30_days``, and ``past_90_days`` in Query filters.
    - After saving a Query, click the ``See the nnn ... in changelist`` link of the
      message to preview the selected objects.
    - On the Browse forms of the Admin interface, the **Reporting query** filter
      restricts the list to the objects selected by a Query.

Run your Reports
----------------

- Select :guilabel:`Reports` from the :guilabel:`Tools` section of the side menu.
- Select a Report to run it.
- Modify the value of any Field Parameter and click the :guilabel:`Rerun Report` button.
- Export the Report results, for example to an ``xlsx`` formatted file.

Manage Your Report Collection
-----------------------------

- Select :guilabel:`Admin Dashboard` from the dropdown under your user name.
- Select the :guilabel:`Reports` option in the :guilabel:`Reporting` panel.
- In the search field on the right, enter ``name:vulnerabilities`` and press Return.
- Use the checkbox in the first column to select one or more reports, including
  the Report that you created.
- Select :guilabel:`Mass update` from the dropdown in the lower left section of the form
  and click the :guilabel:`Go` button.
- Check **Update** on the ``Group`` row.
- Enter ``Vulnerabilities`` in the **New value** field.
- Click the :guilabel:`Update records` button in the lower right section of the form.
- Review the results of your updates on the ``Browse Reports`` form.
- Select :guilabel:`Reports` from the :guilabel:`Tools` section of the side menu.

.. note:: The selected reports are now grouped together under your ``Group`` label.

You can return to the ``Browse Reports`` form at any time to review and update the ``Group``
assignments to meet your requirements.

- Select :guilabel:`Admin Dashboard` from the dropdown under your user name.
- Select the :guilabel:`Reports` option in the :guilabel:`Reporting` panel.
- On the ``Browse Reports`` form, click the :guilabel:`View Reference Data` button
  in the upper left section of the form.
- Use the checkbox in the first column to select one or more reports that interest you.
- Select :guilabel:`Copy the selected objects` from the dropdown in the lower left section
  of the form and click the :guilabel:`Go` button.
- Follow the prompts on the following forms to complete your Copy action.
- Review and edit the copied reports in your own Dataspace.

Continue refining and reviewing your reports.

In :ref:`user_tutorial_4_vulnerabilities`, we'll go further!
