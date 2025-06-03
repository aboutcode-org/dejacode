.. _reference_3_cravex:

========================================
Reference 3 - CRAVEX support in DejaCode
========================================

This essay describes DejaCode features that support CRA compliance activities.

The EU's Cyber Resilience Act (CRA) aims to enhance the cybersecurity of products
with digital elements, ensuring that hardware and software sold in the EU are
designed with strong security measures, and manufacturers remain responsible for
cybersecurity throughout the product lifecycle.

A VEX (Vulnerability Exploitability eXchange) document is a standardized format, part
of the Cybersecurity and Infrastructure Security Agency (CISA) initiative, that provides
a machine-readable way to share information about the exploitability of vulnerabilities
in software products, helping organizations prioritize cybersecurity efforts.

Key Objectives of the CRA
-------------------------

* **Enhanced Cybersecurity**: The CRA aims to improve the cybersecurity of products
  with digital elements, including both hardware and software.
* **Manufacturer Responsibility**:  The CRA places responsibility on manufacturers to
  ensure the cybersecurity of their products throughout the entire lifecycle, from design
  to end-of-life.
* **EU-Wide Standardization**: The CRA aims to establish common cybersecurity rules and
  standards across the EU, facilitating compliance for manufacturers and developers.
* **Consumer Protection**: The CRA aims to protect consumers and businesses from the
  risks posed by inadequate cybersecurity measures in digital products.
* **Transparency**: The CRA aims to improve transparency about the cybersecurity
  properties of products, enabling users to make informed choices.

Key Provisions of the CRA
-------------------------

* **Cybersecurity Requirements**: Manufacturers must ensure that products with digital
  elements meet essential cybersecurity requirements, including risk assessments,
  security-by-design practices, and vulnerability management.
* **Vulnerability Reporting**: Manufacturers are required to report any actively
  exploited vulnerabilities to the European Union Agency for Cybersecurity (ENISA)
  within 24 hours.
* **Security Updates**: Manufacturers must provide timely and effective security updates
  to address vulnerabilities.
* **Documentation and Certification**: Manufacturers must provide adequate documentation
  and certification to demonstrate compliance with the CRA's requirements.
* **Enforcement**: The CRA includes provisions for enforcement, including penalties
  for non-compliance.

Key Cybersecurity Features of DejaCode
--------------------------------------

* **Create SBOMs for your products**: Use DejaCode to generate SBOMs (Software Bills of
  Materials) in CycloneDX or SPDX format directly from your Product definitions. This
  ensures that you identify exactly what is in your product in a machine-readable format
  since DejaCode uses the Package URL (PURL) industry standard to identify each software
  item (and its origin) in your product.
* **Import SBOMs into your products**: Use DejaCode to import SBOMs in CycloneDX or
  SPDX format that you receive from your suppliers or from code that you have scanned
  using tools such as ScanCode.io. DejaCode interprets the SBOM details to create packages,
  enrich the package metadata, and assign them to your product.
* **Get timely automatic updates from VulnerableCode**: Using the PURL as a reliable and
  accurate identifier, DejaCode routinely updates your data to identify known
  vulnerabilities, including a calculated Risk factor, and notifies you of new updates.
* **Respond to vulnerabilities in your products**: Leverage the Vulnerability Risk factor
  to prioritize your cybersecurity reviews of the software in your products, as supported
  by the extensive details that DejaCode has gathered. Enter your status and comments
  regarding the reachability and exploitability of specific software vulnerabilities in
  the context of your product usage, as well as any actions that you are taking to address
  them. Generate VEX documents in a variety of industry-standard formats to communicate
  those conclusions to your organization, to your customers, and to ENISA.
* **Track your vulnerability remediations in your products**: As you upgrade or patch
  the software in your products, track those updates in DejaCode to support accurate,
  up-to-date SBOM revisions that you can provide to interested parties.

Additional Resources
--------------------

Official texts and commentary for the Cyber Resilience Act:

* Text: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202402847

* Commentary: https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act

Community discussions:

* https://github.com/orcwg/cra-hub/blob/main/faq.md

* https://orcwg.org/
