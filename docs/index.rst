====================================
Welcome to DejaCode's documentation!
====================================

DejaCode is an open source application to manage the license compliance and the
security of the software that you use and distribute. It records what is in your
products, the licenses and vulnerabilities that apply to that content, and your
organization's policies for using it.

DejaCode includes the following modules:

* **Product Portfolio**: Record and maintain software inventories for your products,
  import and export SBOMs.
* **Component and Packages Catalog**: Identify the origin, licensing terms and
  relationships of open source and other software components by consulting the catalog.
  Communicate your company usage policy for components to your users, and provide
  them with detailed guidance.
* **License Library**: Understand software licensing terms with the nexB library
  of open source and proprietary licenses. Communicate your company usage policy
  for licenses to your users, and provide them with detailed guidance.
* **Vulnerability Management**: Track the known vulnerabilities affecting your
  packages, analyze their impact on your products, and export VEX documents. See
  :ref:`reference_vulnerability_management`.
* **Compliance**: Monitor the license and security compliance of your products with
  policy rules and vulnerability triage. See :ref:`reference_policy_rules` and
  :ref:`reference_vulnerability_triage`.
* **Reporting**: Create your own reports, from your queries and column templates,
  to explore, analyze and export your DejaCode application data.
* **Workflow Requests**: Create your own request templates to enable your users
  to submit requests regarding your products, components, licenses and their
  policies, and to track the progress of each request.
* **API**: Use the DejaCode API to integrate with your other data sources and
  applications.

New to DejaCode? Start with the :ref:`quickstart`.

.. toctree::
    :maxdepth: 2
    :caption: Getting Started

    quickstart
    installation
    dataspace
    application-settings
    faq

.. toctree::
    :maxdepth: 1
    :caption: Tutorial

    tutorial-1
    tutorial-2
    tutorial-3
    tutorial-4-vulnerabilities
    tutorial-5-sboms
    tutorial-6-vuln-report
    tutorial-7-policy-rules
    tutorial-8-vulnerability-triage

.. toctree::
    :maxdepth: 1
    :caption: How-To

    howto-1
    howto-2
    howto-3
    howto-4-product-vulnerability-analysis
    howto-5-product-object-permissions
    howto-6-policy-rules-configuration
    howto-7-vulnerability-triage-configuration

.. toctree::
    :maxdepth: 1
    :caption: Reference

    reference-data-models
    reference-vulnerability-management
    reference-policy-rules
    reference-vulnerability-triage
    reference-1
    reference-2
    reference-3-cravex

.. toctree::
    :maxdepth: 1
    :caption: Integrations

    integrations-introduction
    integrations-aboutcode
    integrations-forgejo
    integrations-github
    integrations-gitlab
    integrations-jira
    integrations-sourcehut
    integrations-rest-api
    integrations-webhook

.. toctree::
   :maxdepth: 1
   :caption: Miscellaneous

   contributing
   changelog
   doc_maintenance
