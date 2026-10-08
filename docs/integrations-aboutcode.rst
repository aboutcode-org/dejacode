.. _integrations_aboutcode:

AboutCode Integrations
======================

DejaCode relies on three services of the AboutCode stack to collect package data:

- **ScanCode.io**: scan packages to detect their licenses, copyrights, and other
  metadata.
- **PurlDB**: browse a database of packages mined and scanned from public sources.
- **VulnerableCode**: get the known vulnerabilities affecting your packages.

Each service is enabled per Dataspace. Its URL and API key are taken from the
Dataspace configuration when defined, otherwise from the application settings
(see :ref:`dejacode_settings_aboutcode_integrations`).

Configure a service in your Dataspace
-------------------------------------

1. Select :guilabel:`Admin Dashboard` from the dropdown under your user name.
2. Navigate to the :guilabel:`Dataspaces` section and select your Dataspace name.
3. In the **Application Process Settings** section, check the option of the service.
4. In the **Configuration** panel at the bottom of the form, set the URL and API key
   of the service.
5. Click the :guilabel:`Save` button.

.. list-table::
   :header-rows: 1

   * - Service
     - Option
     - URL field
     - API key field
   * - ScanCode.io
     - **Enable package scanning**
     - **ScanCode.io URL**
     - **ScanCode.io API key**
   * - PurlDB
     - **Enable PurlDB access**
     - **PurlDB URL**
     - **PurlDB API key**
   * - VulnerableCode
     - **Enable VulnerableCodeDB access**
     - **VulnerableCode URL**
     - **VulnerableCode API key**

.. tip:: To validate the setup, select :guilabel:`Integrations Status` from the
  dropdown under your user name.

.. _dejacode_dataspace_scancodeio:

ScanCode.io
-----------

With ScanCode.io, you can:

* Provide a Download URL to create a Package, collect its data, and scan it.
* Scan an existing Package from its :guilabel:`Scan` tab.
* Review the scan results on the :guilabel:`Scan` tab and apply them to the Package
  definition.
* Download the scan results as JSON to use them in other analysis and reporting tools.

Scans are listed from :guilabel:`Scans` in the :guilabel:`Integrations` section of the
side menu.

Install your own ScanCode.io server
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Follow the instructions at https://scancodeio.readthedocs.io/en/latest/installation.html

For production use, the **minimum system requirements for ScanCode.io** are:

+-----------+---------------------------------------------------------------------+
| Item      | Minimum                                                             |
+===========+=====================================================================+
| Processor | Modern X86 64 bit Multi Core, with at least **8 physical cores**    |
+-----------+---------------------------------------------------------------------+
| Memory    | **64GB** or more (ECC preferred)                                    |
+-----------+---------------------------------------------------------------------+
| Disk      | **2x500GB SDD** in RAID mirror setup (enterprise disk preferred).   |
+-----------+---------------------------------------------------------------------+

.. warning::
    If you run ScanCode.io **on the same server** (virtual or physical) as DejaCode:

    - **Ensure that the host machine has sufficient resources** for both applications.
    - **Use custom network ports for ScanCode.io**, as ports 80 and 443 are used by
      DejaCode. See
      https://scancodeio.readthedocs.io/en/latest/installation.html#use-alternative-http-ports
    - Set the **ScanCode.io URL** to ``http://host.docker.internal:[port]`` on macOS
      and Windows, or ``http://172.17.0.1:[port]`` on Linux, instead of
      ``http://localhost:[port]``.

Secure ScanCode.io with authentication
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For an enterprise deployment, enable authentication on ScanCode.io and give DejaCode
an API key:

1. Enable the ScanCode.io authentication system, see
   `ScanCode.io Application Settings <https://scancodeio.readthedocs.io/en/latest/application-settings.html#scancodeio-settings-require-authentication>`_.
2. Restart the ScanCode.io services::

    docker compose restart web worker

3. Generate an API key for DejaCode, see
   `CLI Create User <https://scancodeio.readthedocs.io/en/latest/command-line-interface.html#cli-create-user>`_.
4. Set this key in the **ScanCode.io API key** field of your Dataspace configuration.

.. _dejacode_dataspace_purldb:

PurlDB
------

With PurlDB, you can:

* Browse and search over **21 million Packages** from :guilabel:`PurlDB` in the
  :guilabel:`Integrations` section of the side menu.
* Create local Packages from PurlDB entries.
* Get extra information on your local Packages from their :guilabel:`PurlDB` tab.
* Extend the **Global search** results with Packages from the PurlDB.
* Check for **new Package versions** in your Products inventory.

A public instance is available at https://public.purldb.io/api/packages/.
To run your own instance, see https://purldb.readthedocs.io/.

.. _dejacode_dataspace_vulnerablecode:

VulnerableCode
--------------

DejaCode uses the Package URL (purl) of each Package to get its known vulnerabilities
from VulnerableCode. With VulnerableCode, you can:

* See a vulnerability icon next to affected Packages, in the Package list and in
  Product inventories.
* Explore the vulnerabilities of a Package on its :guilabel:`Vulnerabilities` tab,
  with links to public reports (e.g. CVE, GHSA, DSA).
* Analyze the vulnerabilities affecting your Products, see :ref:`how_to_4`.

A public instance is available at https://public.vulnerablecode.io/api/.
To run your own instance, see https://vulnerablecode.readthedocs.io/.

.. seealso::
    :ref:`reference_vulnerability_management` for how vulnerability data is collected
    and used.
