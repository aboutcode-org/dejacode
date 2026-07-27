.. _how_to_6:

How To 6 - Configure Policy Rules
==================================

This chapter explains how to activate and configure the **Policy Rules Engine** for
your Dataspace. Policy rules evaluate compliance conditions against your products
automatically and record violations when thresholds are exceeded.

All rules are disabled by default. You must explicitly enable the rules that are
relevant to your compliance program and, optionally, adjust their parameters and
thresholds.

.. seealso::
    Refer to :ref:`reference_policy_rules` for a complete description of all available
    rules, configuration options, and violation lifecycle.

1. Access the Policy Rules Configuration
----------------------------------------

1. From the DejaCode **Administration dashboard**, navigate to :guilabel:`Dataspaces`.
2. Open your Dataspace by clicking on its name.
3. Scroll down to the **Policy Rules Configuration** section.

Each built-in rule is listed as a collapsible fieldset with its label and description.

2. Enable a Rule
----------------

To activate a rule, expand its fieldset and check the :guilabel:`Enable this rule`
checkbox.

Click :guilabel:`Save` at the bottom of the Dataspace form. DejaCode will immediately
schedule a background re-evaluation of all products in the Dataspace.

.. note::
    Rules that are not enabled are skipped during evaluation and any previously open
    violations for those rules are automatically resolved.
