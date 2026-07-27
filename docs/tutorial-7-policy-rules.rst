.. _user_tutorial_7_policy_rules:

Tutorial 7 - Managing Policy Violations
=======================================

Your DejaCode administrator has configured policy rules for your Dataspace. This
tutorial walks you through discovering policy violations on a product, understanding
what they mean, drilling into the affected packages, and resolving them.

.. seealso::
    Refer to :ref:`reference_policy_rules` for a complete description of all available
    rules and their violation lifecycle. If you are an administrator and need to enable
    or configure rules, refer to :ref:`how_to_6`.

Sign into DejaCode.

1. Open the Compliance Dashboard
--------------------------------

1. From the main menu, navigate to the :guilabel:`Compliance Dashboard`.

2. The dashboard lists all your products with their compliance metrics. Look at the
   **Policy violations** column to see which products have active violations.

3. Click the policy violations count on a product row to open its
   :guilabel:`Compliance` tab directly.

2. Review Policy Violations
---------------------------

The **Policy violations** panel shows the active violations for the product.

For each triggered rule, the table shows:

- The rule label and severity, color-coded as red (error) or yellow (warning).
- A short description of what the rule detects.
- The number of packages **in violation**.
- The date the violation was first **detected**.

The badge in the panel header shows the total number of triggered rules. Its color
reflects the highest severity: red if at least one error rule is triggered, yellow
if only warning rules are triggered.

.. tip::
    Click the info icon next to the panel title to open a modal listing all active
    rules with their current status: **Triggered** or **OK**. This gives you a full
    picture of your compliance posture at a glance.
