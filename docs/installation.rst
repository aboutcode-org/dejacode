.. _installation:

============
Installation
============

Welcome to the **DejaCode** installation guide! This guide explains how to install
DejaCode on various platforms. Please follow the instructions carefully for a smooth
installation experience.

There are three ways to run DejaCode:

- :ref:`run_with_docker` — **simplest option**, no repository checkout or build step
  required. Uses the pre-built Docker image published on GitHub.
- :ref:`enterprise_deployment` — same pre-built image with custom nginx configuration,
  domain settings, and hardware recommendations for production servers.
- :ref:`local_development_installation` — Docker-based setup for contributors.

.. _run_with_docker:

Run with Docker
===============

This is the simplest way to get DejaCode running. You only need **Docker** —
no repository checkout, no build step required.

1. Get Docker
-------------

Download and **install Docker** on your platform:
|get_docker_link|.

.. |get_docker_link| raw:: html

   <a href="https://docs.docker.com/get-docker/" target="_blank" class="external">Get Docker</a>

2. Run the installer
--------------------

Run the one-liner installer::

    curl -sSL https://raw.githubusercontent.com/aboutcode-org/dejacode/main/install.sh | bash

This script will:

- Create ``~/.dejacode/`` as the installation directory
- Download ``compose.yml``, ``docker.env``, the nginx configuration, and the database seed data
- Generate ``.env`` with a secure secret key
- Install the ``dejacode`` command in ``~/.local/bin/``
- Start all services and wait until the application is ready

.. note::
    Override the default installation directory with:
    ``DEJACODE_HOME=/path/to/dir bash install.sh``

3. Create an application user
-----------------------------

::

    dejacode exec web ./manage.py createsuperuser

Follow the prompt instructions, providing the required information:

- **Username**: Choose a unique username.
- **Email Address**: Provide a valid email address.
- **Strong Password**: Create a password following security guidelines.

4. Access the application
-------------------------

.. admonition:: Congratulations!
   :class: tip

   Open a web browser and visit |localhost_link| to **access the web UI**.

   You can sign-in with the credentials you created above.

   You can move onto the Tutorials section starting with the :ref:`user_tutorial_1`.

.. |localhost_link| raw:: html

   <a href="http://localhost/" target="_blank" class="external">http://localhost/</a>

.. note::
    The pre-built image always corresponds to the most recent release and is tagged
    ``latest``.

.. _dejacode_command:

Managing your installation
--------------------------

The ``dejacode`` command is a thin wrapper around ``docker compose``. All standard
``docker compose`` subcommands work directly::

    dejacode up -d          # start all services in the background
    dejacode down           # stop and remove containers
    dejacode restart        # restart all services
    dejacode ps             # show service status
    dejacode logs -f        # follow all logs
    dejacode logs -f web    # follow logs for a specific service
    dejacode pull           # pull the latest image
    dejacode exec web ./manage.py createsuperuser

To update DejaCode to the latest release::

    dejacode pull && dejacode up -d

To completely remove DejaCode and all its data::

    dejacode uninstall

.. _enterprise_deployment:

Enterprise deployment
=====================

Enterprise deployments use the same pre-built image as the standard install,
with additional configuration for your domain, a custom nginx setup, and
dedicated server hardware.

1. Install
----------

Follow the :ref:`run_with_docker` steps. Once the stack is running, continue
below to adapt it for production.

2. Configure your domain
------------------------

Edit ``~/.dejacode/.env`` and update the following settings to match your
server's hostname or IP::

    ALLOWED_HOSTS=dejacode.example.com
    CSRF_TRUSTED_ORIGINS=https://dejacode.example.com

Restart the stack to apply::

    dejacode restart

3. Configure nginx
------------------

The default nginx configuration embedded in ``compose.yml`` is suitable for
local use. For production, replace it with your own configuration file.

The installer downloads a default nginx configuration to
``~/.dejacode/etc/nginx/conf.d/default.conf``. Replace it with your own
configuration (TLS termination, custom headers, upstream settings, etc.)
and restart::

    dejacode down && dejacode up -d

4. AboutCode integrations
--------------------------

Upon initialization, the ``nexB`` reference :ref:`dataspace` is created with a
default set of data, including license and organization libraries.

**AboutCode integrations are pre-configured** to connect to public instances of:

- **ScanCode.io** — package scanning. See :ref:`dejacode_dataspace_scancodeio`.
- **PurlDB** — database of scanned packages. See :ref:`dejacode_dataspace_purldb`.
- **VulnerableCode** — package vulnerability data. See :ref:`dejacode_dataspace_vulnerablecode`.

.. warning::
    For enterprise deployments it is **strongly recommended to run your own
    instances** of these services to ensure that sensitive or private data is
    not submitted to public endpoints.

Hardware requirements
---------------------

+-----------+------------------------------------------------------------------+
| Item      | Minimum                                                          |
+===========+==================================================================+
| OS        | **Ubuntu 24.04 LTS 64-bit** server                               |
+-----------+------------------------------------------------------------------+
| Processor | Modern x86-64 multi-core, at least **4 physical cores**          |
+-----------+------------------------------------------------------------------+
| Memory    | **64 GB** or more (ECC preferred)                                |
+-----------+------------------------------------------------------------------+
| Disk      | 2 x 500 GB SSD in RAID mirror (enterprise disk preferred)        |
+-----------+------------------------------------------------------------------+

.. important::
    DejaCode uses all available CPUs for worker processes.
    Allocate at least **1 GB of memory per CPU core**.

.. _local_development_installation:

Local development installation
==============================

.. note::
    This section is for contributors to DejaCode. The development environment
    runs entirely in Docker — no local Python or PostgreSQL installation required.
    Please refer to the Contributing guide for instructions on submitting changes.

Clone and configure
-------------------

#. Clone the `DejaCode repository <https://github.com/aboutcode-org/dejacode>`_::

    git clone https://github.com/aboutcode-org/dejacode.git && cd dejacode

#. Create an environment file::

    make envfile_dev

Run the app
-----------

Build the development image and start all services::

    make run

The application is available at http://localhost:8000/.
Source code changes are reflected immediately without restarting the container.

.. note::
    ``make run`` is a shortcut for ``docker compose -f compose.dev.yml up``.
    All standard ``docker compose`` subcommands are available directly::

        docker compose -f compose.dev.yml logs -f
        docker compose -f compose.dev.yml exec web ./manage.py shell
        docker compose -f compose.dev.yml down

Create an application user
--------------------------

::

    make superuser

Tests
-----

::

    make test

.. warning::
    This setup is **not suitable for deployments** and is **only supported for local development**.
