DejaCode
========

DejaCode is a complete enterprise-level application to automate open source license
compliance and ensure software supply chain integrity, powered by
`ScanCode <https://github.com/nexB/scancode-toolkit>`_,
the industry-leading code scanner.

- Run scans and track all the open source and third-party products and components used
  in your software.
- Apply usage policies at the license or component level, and integrate into
  ScanCode to ensure compliance.
- Capture software inventories (SBOMs), generate compliance artifacts, and keep
  historical data.
- Ensure FOSS compliance with enterprise-grade features and integrations for DevOps and
  software systems.
- Scan a software package, simply by providing its Download URL, to get comprehensive
  details of its composition and create an SBOM.
- Load software package data into DejaCode with the integration for the open source
  ScanCode.io and ScanCode Toolkit projects to create a product’s SBOM.
- Track and report vulnerability tracking and reporting by integrating with the open
  source VulnerableCode project.
- Create, publish and share SBOM documents in DejaCode, including detailed attribution
  documentation and custom reports in multiple file formats and standards, such as
  CycloneDX and SPDX.

Getting started
---------------

The DejaCode documentation is available here: https://dejacode.readthedocs.io/

If you have questions please ask them in
`Discussions <https://github.com/nexB/dejacode/discussions>`_.

If you want to contribute to DejaCode, start with our
`Contributing <https://dejacode.readthedocs.io/en/latest/contributing.html>`_ page.

Build and tests status
----------------------

+------------+-------------------+
| **Tests**  | **Documentation** |
+============+===================+
| |ci-tests| |    |docs-rtd|     |
+------------+-------------------+

DejaCode License Notice
-----------------------

DejaCode is an enterprise-level application to automate open source license
compliance and ensure software supply chain integrity, powered by ScanCode,
the industry-leading code scanner.

SPDX-License-Identifier: AGPL-3.0-only

Copyright (c) nexB Inc.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Commercial License option
-------------------------

DejaCode is offered under a nexB commercial license as an alternative.
You can learn more about this option by contacting us at
https://www.nexb.com/contact-us/


.. |ci-tests| image:: https://github.com/nexB/dejacode/actions/workflows/ci.yml/badge.svg?branch=main
    :target: https://github.com/nexB/dejacode/actions/workflows/ci.yml
    :alt: CI Tests Status

.. |docs-rtd| image:: https://readthedocs.org/projects/dejacode/badge/?version=latest
    :target: https://dejacode.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Build Status
