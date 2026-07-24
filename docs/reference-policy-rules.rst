.. _reference_policy_rules:

Policy Rules Engine
===================

DejaCode includes a **Policy Rules Engine** that continuously evaluates configurable
compliance rules against your products and records violations. It provides a structured
way to detect, track, and resolve compliance issues across usage policies, license
coverage, and vulnerability exposure.

When a rule is triggered, DejaCode records a **policy violation** with a count of the
affected packages and the detection date. Violations are automatically resolved when the
underlying condition is corrected.

All rules are **disabled by default**. Each dataspace activates and configures the
rules that are relevant to its compliance program via the **Dataspace Configuration**
form.

1. Built-in Rules
-----------------

Eight rules are available out of the box, organized into two categories: policy-based
rules and vulnerability-based rules.

**Policy-based rules**

.. list-table::
   :header-rows: 1

   * - Rule type
     - Label
     - Severity
     - Description
   * - ``usage_policy_error``
     - **Usage Policy Error**
     - Error
     - Detects packages assigned a usage policy flagged with an error compliance alert.
   * - ``usage_policy_warning``
     - **Usage Policy Warning**
     - Warning
     - Detects packages assigned a usage policy flagged with a warning compliance alert.
   * - ``license_policy_error``
     - **License Policy Error**
     - Error
     - Detects packages whose licenses are assigned a usage policy flagged with an error
       compliance alert.
   * - ``license_policy_warning``
     - **License Policy Warning**
     - Warning
     - Detects packages whose licenses are assigned a usage policy flagged with a warning
       compliance alert.
   * - ``license_coverage_gap``
     - **License Coverage Gap**
     - Warning
     - Detects packages with no license expression.

**Vulnerability-based rules**

.. list-table::
   :header-rows: 1

   * - Rule type
     - Label
     - Severity
     - Description
   * - ``vulnerability_detected``
     - **Vulnerability Detected**
     - Error
     - Detects packages with at least one known vulnerability. Supports an optional
       ``min_risk_score`` parameter to restrict detection to vulnerabilities above a
       minimum risk score.
   * - ``vulnerability_unresolved``
     - **Vulnerability Unresolved**
     - Warning
     - Detects packages with known vulnerabilities that have no completed triage analysis
       (i.e., no analysis in a terminal state: resolved, resolved_with_pedigree, or
       not_affected).
   * - ``vulnerability_stale``
     - **Vulnerability Stale**
     - Error
     - Detects packages with high-risk vulnerabilities that have remained unaddressed
       beyond a configurable number of days. Supports ``max_days`` and ``min_risk_score``
       parameters.

.. seealso::
    Refer to :ref:`reference_vulnerability_management` for background on vulnerability
    fields such as risk score used by the vulnerability-based rules.

**Severity levels** determine how violations are displayed in the compliance tab:

- **Error** rules are highlighted in red and indicate a critical compliance issue
  requiring immediate attention.
- **Warning** rules are highlighted in yellow and indicate a condition that requires
  attention but does not necessarily block a release.

2. Violation Lifecycle
----------------------

Each policy violation is a record associated with a product and a rule type. Its
lifecycle follows these states:

- **Detected**: the violation is created the first time a rule evaluation finds the
  condition triggered. The ``detected_date`` is set at this point and never changes.
- **Active**: the violation remains active as long as the condition persists across
  subsequent evaluations.
- **Resolved**: when a rule evaluation finds the condition is no longer triggered, the
  violation is marked resolved and a ``resolved_date`` is recorded.
- **Re-activated**: if the condition recurs after being resolved, the existing violation
  record is updated in place (the original ``detected_date`` is preserved).

Only **active (unresolved)** violations are shown in the compliance tab and returned
by the REST API.
