.. _user_tutorial_3:

=================================
Tutorial 3 - Working with Reports
=================================

Sign into DejaCode.

Create a Reporting Query
========================

- Select the :guilabel:`Dashboard` option from the dropdown beneath your User name.
- Select the :guilabel:`Queries` option in the :guilabel:`Reporting` panel.
- Click the :guilabel:`Add query` button in the upper right section of the form.
- Enter a **Name**. For this example, enter ``Quarterly License Activity``.
- Enter a **Description**. For this example, enter
  ``Licenses Created in the 'past_90_days' OR Licenses Modified in the 'past_90_days'.``
- Select an **Object type**. For this example, choose ``license_library | license``.
- Select an **Operator**. For this example, choose ``or``.
- Click the :guilabel:`Add another filter` option in the :guilabel:`Filters` panel.

**First Filter**:

- Select ``created_date`` for the **Field Name**.
- Select ``Greater than or equal to`` for the **Lookup**.
- Enter ``past_90_days`` for the **Value**.
- Check **Runtime Parameter** to enable it.

**Second Filter**:

- Select ``last_modified_date`` for the **Field Name**.
- Select ``Greater than or equal to`` for the **Lookup**.
- Enter ``past_90_days`` for the **Value**.
- Check **Runtime Parameter** to enable it.

.. note:: In addition to specific date values,
  DejaCode recognizes special values for date field lookups:
  ``today``, ``past_7_days``, ``past_30_days``, ``past_90_days``

Click the :guilabel:`Add another order field` option in the
:guilabel:`Order Fields` panel.

**First Order Field**:

- Select ``last_modified_date`` for the **Field Name**.
- Select ``descending`` for **Sort**.

**Second Order Field**:

- Select ``key`` for the **Field Name**.
- Select ``ascending`` for **Sort**.

Click the :guilabel:`Save and continue editing` button in the lower right section of the form.

- Click the blue link in the message ``See the nnn licenses in changelist``.
- DejaCode presents the selected data on the ``Browse Licenses`` form.
- Select any license to access the ``Change license`` form.
- Click the :guilabel:`History` button in the upper right section of the form.
- Review the license history.
- Click the License Name in the upper part of the form to return to the main License form.

- Click the :guilabel:`Return to list` button in the lower left section of the form.
- On the ``Browse Licenses`` form, click the :guilabel:`Show all` button in the upper left.
- Click the :guilabel:`Filter` dropdown in the upper right and click the ``All`` value in
  the ``Reporting query`` field, and select any Query, noting that the Query you just
  created is in the list of Queries. Review the results.

Create a Column Template
========================

- Select the :guilabel:`Administration` in the upper right section of the form.
- Select the :guilabel:`Column templates` option in the :guilabel:`Reporting` panel.
- Click the :guilabel:`Add column template` button in the upper right section of the form.
- Enter a **Name**. For this example, enter ``Quarterly License Activity``.
- Enter a **Description**. For this example, enter
  ``License fields that pertain to analysis of recently created or modified licenses.``
- Select an **Object type**. For this example, choose ``license_library | license``.

- Click the :guilabel:`Add another column template assigned field` option
  in the :guilabel:`Column Template Assigned Fields` panel.

First Column Template Assigned Field:

- Select ``key`` for the **Field Name**.
- Enter ``License Key`` for the **Display name**.

Add additional Assigned Fields as follows:

 - ``short_name``: ``License Short Name``
 - ``category > label``: ``Category``
 - ``last_modified_by > username``: ``Modified by``
 - ``last_modified_date``: ``Date modified``
 - ``where_used``: ``Where used``
 - any additional fields that interest you.

- Click the :guilabel:`Save and continue editing` button in the lower right section of the form.
- You can optionally change the order of the fields using the ``Move item`` icon.
  in the right hand section of each Assigned Field.
- Click the :guilabel:`Save` button in the lower right section of the form.

.. note:: You are now ready to use your Column Template in a DejaCode Report.

Create a DejaCode Report
========================

- Select the :guilabel:`Administration` in the upper right section of the form.
- Select the :guilabel:`Reports` option in the :guilabel:`Reporting` panel.
- Click the :guilabel:`Add report` button in the upper right section of the form.
- Enter a **Name**. For this example, enter ``Quarterly License Activity``.
- Enter a **Description**. For this example, enter
  ``Licenses Created in the 'past_90_days' OR Licenses Modified in the 'past_90_days'.``
- Select ``Quarterly License Activity`` from the **Query** dropdown.
- Select ``Quarterly License Activity`` from the **Column template** dropdown.
- Check **User available** to enable it.
- Accept the defaulted text in the **Report context** field.
- Click the :guilabel:`Save and continue editing` button in the lower right section of the form.
- Click the :guilabel:`View` button in the upper right section of the form.

Review the Report results:

- Click the link icon to the left of a License Key to view that License.
- Export the Report results to an ``xlsx`` formatted file.
- Modify the value of any Field Parameter and click the **Rerun Report** button.
- Experiment with various Export formats and Field Parameter values.

Select the :guilabel:`Reports` option from the main menu bar :guilabel:`Tools` dropdown.

Select other Reports to run and review.

Manage Your Report Collection
=============================

- Select the :guilabel:`Dashboard` option from the dropdown beneath your User name.
- Select the :guilabel:`Reports` option in the :guilabel:`Reporting` panel.
- In the search field on the right, enter ``name:activity`` and press Return.
- Use the checkbox in the first column to select one or more reports, including
  your new report.
- Select ``Mass update`` from the dropdown in the lower left section of the form
  and click the **Go** button.
- Check **Update** on the ``Group`` row.
- Enter ``Activity`` in the **New value** field.
- Click the :guilabel:`Update records` button in the lower right section of the form.
- Review the results of your updates on the ``Browse Reports`` form.
- Select the :guilabel:`Reports` option from the main menu bar :guilabel:`Tools` dropdown.

.. note:: The selected reports are now grouped together under your ``Group`` label.

You can return to the ``Browse Reports`` form at any time to review and update the ``Group``
assignments to meet your requirements.

- Select the :guilabel:`Dashboard` option from the dropdown beneath your User name.
- Select the :guilabel:`Reports` option in the :guilabel:`Reporting` panel.
- On the ``Browse Reports`` form, click the :guilabel:`View Reference Data` button
  in the upper left section of the form.
- Use the checkbox in the first column to select one or more reports that interest you.
- Select ``Copy the selected objects`` from the dropdown in the lower left section
  of the form and click the :guilabel:`Go` button.
- Follow the prompts on the following forms to complete your Copy action.
- Review and edit the copied reports in your own Dataspace.

Continue refining and reviewing your reports.

In Tutorial 4, we'll go further!
