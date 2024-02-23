.. _installation:

============
Installation
============

Welcome to the **DejaCode** installation guide! This guide explains how to install
DejaCode on various platforms. Please follow the instructions carefully for a smooth
installation experience.

The **recommended DejaCode installation** method is to :ref:`run_with_docker`, which
is the easiest and ensures all features work with minimal configuration.
This installation works on all operating systems.

Alternatively, if you prefer, you can install DejaCode locally as a development server
with some limitations.
In this case, you may refer to the :ref:`local_development_installation` section for
more details.

.. _run_with_docker:

Run with Docker
===============

1. Get Docker
-------------

Start by downloading and **installing Docker on your platform**.
Refer to Docker's documentation for the best installation path for your system:
|get_docker_link|.

.. |get_docker_link| raw:: html

   <a href="https://docs.docker.com/get-docker/" target="_blank" class="external">Get Docker</a>

2. Build the image
------------------

DejaCode comes with the necessary ``Dockerfile`` and ``docker-compose.yml`` files to
create the Docker images and to manage the services (database, cache, webserver).

.. warning:: For **Windows** users, before cloning the repository, ensure that your git
    ``autocrlf`` configuration is set to ``false``::

        git config --global core.autocrlf false

Clone the DejaCode repository
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Open your terminal and clone the `DejaCode repo <https://github.com/nexB/dejacode>`_
with the following command::

    git clone --depth=1 https://github.com/nexB/dejacode.git

Build the Docker image
^^^^^^^^^^^^^^^^^^^^^^

Create an **environment file**, and **build the Docker image** with::

    cd dejacode && make envfile
    docker compose build

3. Run the app
--------------

To **run the DejaCode images as containers**, use the following command::

    docker compose up -d

4. Create an application user
-----------------------------

To create a superuser for the application, use the following command::

    make createsuperuser

Follow the prompt instructions, providing the required information:

- **Username**: Choose a unique username.
- **Email Address**: Provide a valid email address.
- **Strong Password**: Create a password following security guidelines.

Use these credentials to access the application.

.. admonition:: Congratulations!
   :class: tip

   Congratulations, you are now ready to use DejaCode.

   Open a web browser and visit |localhost_link| to **access the web UI**.

   You can sign-in with your user credentials generated above.

   You can move onto the Tutorials section starting with the :ref:`user_tutorial_1`.

.. |localhost_link| raw:: html

   <a href="http://localhost/" target="_blank" class="external">http://localhost/</a>

.. important::
    DejaCode will utilize all available CPUs according to your Docker configuration,
    ensuring faster processing.

    **Make sure to allocate enough memory to support each CPU process.**

    A good rule of thumb is to allocate **1 GB of memory per CPU**.
    For example, with Docker configured for 8 CPUs, allocate a minimum of 8 GB of
    memory.

5. Dataspace setup and AboutCode integrations
---------------------------------------------

Upon the initialization of the DejaCode application, the ``nexB`` reference
:ref:`dataspace` is created with a **default set of data**, including license and
organization libraries.

Additionally, **AboutCode integrations are pre-configured** to connect to
**public instances** of the following AboutCode applications:

- **ScanCode.io**: Facilitates package scanning.
  Refer to :ref:`dejacode_dataspace_scancodeio`.
- **PurlDB**: Provides access to a database of scanned packages.
  Refer to :ref:`dejacode_dataspace_purldb`.
- **VulnerableCodeDB**: Enables access to a database containing information on package
  vulnerabilities.
  Refer to :ref:`dejacode_dataspace_vulnerablecode`.

.. warning::
    In the scenario of **deploying DejaCode as an enterprise service** within your
    organization, it is **strongly recommended to review these configurations**.
    Consideration should be given to **running your own instances** of these
    applications  to ensure that **sensitive or private data** is not inadvertently
    submitted to public services. This strategic approach helps to safeguard
    organizational data and privacy during package scanning and vulnerability
    assessments.

Hardware requirements
=====================

The minimum hardware/system requirements for running DejaCode as an enterprise
server are:

+-----------+------------------------------------------------------------------+
| Item      | Minimum                                                          |
+===========+==================================================================+
| Processor | Modern X86 64 bit Multi Core, with at least **4 physical cores** |
+-----------+------------------------------------------------------------------+
| Memory    | **64 GB** or more (ECC preferred)                                |
+-----------+------------------------------------------------------------------+
| Disk      | 2 * 500GB SDD in RAID mirror setup (enterprise disk preferred)   |
+-----------+------------------------------------------------------------------+
| OS        | **Ubuntu 22.04 LTS 64-bit** server clean installation            |
+-----------+------------------------------------------------------------------+

.. _local_development_installation:

Local development installation
==============================

.. note::
    This section is designed for those interested in actively contributing to the
    development and enhancement of DejaCode. After setting up DejaCode, please refer
    to our Contributing chapter for comprehensive instructions on submitting
    code changes.

Supported Platforms
-------------------

**DejaCode** has been tested and is supported on the following operating systems:

#. **Debian-based** Linux distributions
#. **macOS** 10.14 and up

.. warning::
     On **Windows** DejaCode can **only** be :ref:`run_with_docker`.

Pre-installation Checklist
--------------------------

Before you install DejaCode, make sure you have the following prerequisites:

#. **Python: versions 3.12** found at https://www.python.org/downloads/
#. **Git**: most recent release available at https://git-scm.com/
#. **PostgreSQL**: release 16 or later found at https://www.postgresql.org/ or
   https://postgresapp.com/ on macOS

.. _system_dependencies:

Clone and Configure
-------------------

#. Clone the `DejaCode GitHub repository <https://github.com/nexB/dejacode>`_::

    git clone https://github.com/nexB/dejacode.git && cd dejacode

#. Install the dependencies::

    make dev

#. Create an environment file::

    make envfile

Database
--------

**PostgreSQL** is the preferred database backend.
To set up the database user, database, and table, run::

    make postgresdb

Tests
-----

You can validate your DejaCode installation by running the test suite::

    make test

Run the App
-----------

Start the local web server using::

    make run

Then, open your web browser and visit http://localhost:8000/ to access the web
application.

.. warning::
    This setup is **not suitable for deployments** and is
    **only supported for local development**.
    It is highly recommended to use the :ref:`run_with_docker` setup to ensure the
    availability of all the features.
