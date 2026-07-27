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

Overview
--------

Policy rules are configured via the ``policy_rules_config`` JSON field in the
**Dataspace Configuration** form. Each rule is identified by its rule type and supports
three options: ``is_active``, ``threshold``, and ``parameters``.

1. Access the Dataspace Configuration
--------------------------------------

1. From the DejaCode **Administration dashboard**, navigate to
   :guilabel:`Dataspaces > Dataspace configurations`.
2. Open the configuration for your Dataspace.
3. Locate the **Policy rules config** field.

The field accepts a JSON object. If it is empty, no rules are active.
