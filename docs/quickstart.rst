.. _quickstart:

===========
Quick Start
===========

This page takes you from zero to your first Product, with its inventory,
vulnerabilities, and compliance status, in a few minutes.

Choose your path
================

- :ref:`quickstart_public_instance`: **evaluate DejaCode** without installing
  anything.
- :ref:`quickstart_local_install`: **run DejaCode on your machine** with Docker, keeping
  your data private.
- **Deploy DejaCode for your organization**: follow the :ref:`installation` guide,
  including the :ref:`enterprise_deployment` section.

Both of the first two paths continue with the same :ref:`quickstart_first_steps`.

.. _quickstart_public_instance:

Evaluate on the public instance
===============================

1. Open https://public.dejacode.com/ and click :guilabel:`Sign Up`.
2. Fill in the form and click :guilabel:`Create account`.
3. Click the link in the activation email to activate your account.
4. Sign in to DejaCode.

.. warning::
    The public instance is shared and hosted by AboutCode. Do not upload private or
    sensitive data, such as the SBOM of an unreleased product.

Continue with :ref:`quickstart_first_steps`.

.. _quickstart_local_install:

Install on your machine
=======================

You only need `Docker <https://docs.docker.com/get-docker/>`_.

1. Run the installer::

    curl -sSL https://raw.githubusercontent.com/aboutcode-org/dejacode/main/install.sh | bash

2. Create your user::

    dejacode exec web ./manage.py createsuperuser

3. Open http://localhost/ and sign in to DejaCode.

.. seealso::
    :ref:`run_with_docker` for details on the installer and the ``dejacode`` command.

Continue with :ref:`quickstart_first_steps`.

.. _quickstart_first_steps:

First steps
===========

1. Select :guilabel:`Products` from the main menu bar, click the green
   :guilabel:`Add Product` button, set a **name**, and click :guilabel:`Add Product`.

2. Download and unzip the
   `storm-core-1.0.1 SBOM example <https://github.com/aboutcode-org/dejacode/raw/refs/heads/main/docs/sboms/storm-core-1.0.1.cdx.json.zip>`_.

3. On the Product details page, from the :guilabel:`Actions` dropdown, select
   :guilabel:`Import SBOM`, choose the **storm-core-1.0.1.cdx.json** file, and click
   the :guilabel:`Import` button.

4. Follow the progress on the :guilabel:`Imports` tab, then review:

   - The :guilabel:`Inventory` tab: the packages found in the SBOM, with their licenses.
   - The :guilabel:`Vulnerabilities` tab: the known vulnerabilities affecting those
     packages, when vulnerability data is enabled for your Dataspace.
   - The :guilabel:`Compliance` tab: the license and security compliance overview.

5. From the :guilabel:`Share` dropdown, download the Product SBOM as
   :guilabel:`SPDX document` or CycloneDX :guilabel:`SBOM`.

Next steps
==========

- :ref:`user_tutorial_1` and the following tutorials walk through each feature in
  detail.
- :ref:`dataspace` explains how to set up your own Dataspace, users, and usage
  policies.
- :ref:`integrations_introduction` connects DejaCode with your other tools.
