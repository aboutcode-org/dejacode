====================
Application Settings
====================

Settings file
=============

DejaCode is configured with environment variables stored in a ``.env`` file.

The ``.env`` file is created at the root of the DejaCode codebase during its
installation.
You can configure your preferences using the following settings in the ``.env``
file.

.. note::
    DejaCode is based on the Django web framework and its settings system.
    The list of settings available in Django is documented at
    `Django Settings <https://docs.djangoproject.com/en/dev/ref/settings/>`_.

.. tip::
    Settings specific to DejaCode are all prefixed with ``DEJACODE_``.

**Restarting the services is required following any changes to .env:**

.. code-block:: bash

    docker compose restart web worker

DATABASE
--------

The database can be configured using the following settings::

    DEJACODE_DB_HOST=localhost
    DEJACODE_DB_NAME=dejacode_db
    DEJACODE_DB_USER=user
    DEJACODE_DB_PASSWORD=password
    DEJACODE_DB_PORT=5432

ALLOWED_HOSTS
-------------

A list of strings representing the host/domain names that this application can serve.

To enable this setting you need to have a proper host and domain name configured
for your DejaCode installation.

This setting is a security measure to prevent an attacker from poisoning caches
and password reset emails with links to malicious hosts by submitting requests
with a fake HTTP Host header, which is possible even under many seemingly-safe
webserver configurations.

Values in this list can be fully qualified names (e.g. 'www.example.com'), in
which case they will be matched against the request's Host header exactly
(case-insensitive, not including port).

A value beginning with a period can be used as a subdomain wildcard:
'.example.com' will match example.com, www.example.com, and any other subdomain
of example.com. A value of '*' will match anything; in this case you are
responsible to provide your own validation of the Host header.

.. code-block:: python

    ALLOWED_HOSTS=*

EMAIL
-----

This settings enables the email notification feature in DejaCode.
If set, the provided username, password and email/SMTP server details are used
to send email notifications to your DejaCode users.

.. code-block:: python

    # The SMTP user used for authentication on your SMTP server.
    EMAIL_HOST_USER=''
    # Password to use for the SMTP server defined in EMAIL_HOST.
    # Can be empty on non-secured, test servers.
    EMAIL_HOST_PASSWORD=''
    # The SMTP server host to use to send emails.
    EMAIL_HOST=''
    # Port to use for the SMTP server defined in EMAIL_HOST.
    EMAIL_PORT=587
    # Default "FROM" email address to use when sending email notifications
    DEFAULT_FROM_EMAIL=''
    # Whether to use a TLS (secure) connection when talking to the SMTP server
    # You should always use a secure connection.
    EMAIL_USE_TLS=True

SITE_URL
--------

The base URL of this DejaCode installation. This setting is required to build URLs that
reference objects in the application. It is also used when including URLs in email
notifications.

.. code-block:: python

    SITE_URL=http://www.yourdomain.com/

DEJACODE_SUPPORT_EMAIL
----------------------

An optional email address to reach the support team of this instance.
When defined, it will be displayed in various views and emails related to account
registration, activation, and password reset.

.. code-block:: python

    DEJACODE_SUPPORT_EMAIL=support@dejacode.com

ANONYMOUS_USERS_DATASPACE
-------------------------

One Dataspace can be designed as accessible to anyone in a view-only mode.
Set this with an existing Dataspace name to enable view-only access to anonymous, no
logged-in users.

.. code-block:: python

    ANONYMOUS_USERS_DATASPACE=DATASPACE_NAME

REFERENCE_DATASPACE
-------------------

An administrative User in the Reference Dataspace can see and copy data from every
Dataspace; otherwise, the User can only see data from his/her assigned Dataspace
and copy from the Reference Dataspace. An administrative User in the Reference
Dataspace can also maintain User definitions for all Dataspaces.

The default Reference Dataspace is always 'nexB' unless the following setting is
set to another existing Dataspace. If set to an empty value or a non-existent
Dataspace, 'nexB' will be considered the Reference Dataspace.

Caution: be careful when changing this setting as you may no longer have access
to nexB-provided reference data.

.. code-block:: python

    REFERENCE_DATASPACE=nexB

SESSION
-------

You can control whether the DejaCode session framework uses web browser-lifetime
sessions vs. persistent sessions with the ``SESSION_EXPIRE_AT_BROWSER_CLOSE`` setting.
If ``SESSION_EXPIRE_AT_BROWSER_CLOSE`` is set to True, DejaCode cookies will expire as
soon as a user closes his or her web browser.
Use this if you want the user to have to log-in every time they open a browser.

.. code-block:: python

    SESSION_EXPIRE_AT_BROWSER_CLOSE=True

The ``SESSION_COOKIE_AGE`` setting is the maximum age of DejaCode session cookies, in
seconds.
The DejaCode user session will expire if the user is "inactive" in the application for
longer than this value.

.. code-block:: python

    # 1 hour, in seconds.
    SESSION_COOKIE_AGE=3600

DEJACODE_LOG_LEVEL
------------------

By default, only a minimum of logging messages is displayed in the console, mostly
to provide some progress about pipeline run execution.

Default: ``INFO``

The ``DEBUG`` value can be provided to this setting to see all DejaCode debug
messages to help track down configuration issues for example.
This mode can be enabled globally through the ``.env`` file::

    DEJACODE_LOG_LEVEL=DEBUG

.. _clamd-settings:

CLAMD_ENABLED
-------------

When enabled, DejaCode will perform virus scanning on any and all files that a
user attempts to import in the various places where data imports are supported.
A file with a detected virus will be blocked from upload, and DejaCode will
present a pertinent error message to the user when this occurs.

To enable anti-virus scan on file upload, set the ``CLAMD_ENABLED`` setting to
True.

.. code-block:: python

    CLAMD_ENABLED=True

TIME_ZONE
---------

A string representing the time zone for the current ScanCode.io installation. By
default the ``US/Pacific`` time zone is used::

    TIME_ZONE=US/Pacific

.. note::
    You can view a detailed list of time zones `here.
    <https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>`_

.. _dejacode_settings_aboutcode_integrations:

AboutCode integrations
======================

To **integrate DejaCode with other applications within the AboutCode stack**,
you have the flexibility to configure and set up integrations using the following
application settings.

It's important to understand that employing application settings will make these
integrations **globally accessible across all Dataspaces** within your DejaCode
instance.

Alternatively, if you wish to tailor the availability of these features to a specific
Dataspace, you can define and set those values directly within the :ref:`dataspace`
configuration. This can be done through the Dataspace admin UI, allowing you to scope
the availability of these integrations exclusively to the designated Dataspace.

.. _dejacode_settings_scancodeio:

SCANCODEIO
----------

Provide the URL and API key of your `ScanCode.io <https://github.com/nexB/scancode.io>`_
instance.

.. code-block:: python

    SCANCODEIO_URL=https://your_scancodeio.url/
    SCANCODEIO_API_KEY=insert_your_api_key_here

.. note::
    You have the option to define and set those settings directly on your Dataspace.
    For detailed instructions, refer to :ref:`dejacode_dataspace_scancodeio`.

.. _dejacode_settings_purldb:

PURLDB
------

Provide the URL and API key of your `PurlDB <https://github.com/nexB/purldb>`_ instance.

.. code-block:: python

    PURLDB_URL=https://your-purldb.url/
    PURLDB_API_KEY=insert_your_api_key_here

.. note::
    You have the option to define and set those settings directly on your Dataspace.
    For detailed instructions, refer to :ref:`dejacode_dataspace_purldb`.

.. _dejacode_settings_vulnerablecode:

VULNERABLECODE
--------------

You can either run your own instance of
`VulnerableCode <https://github.com/nexB/vulnerablecode>`_
or connect to the public one https://public.vulnerablecode.io/.

.. note:: Providing an API key is optional when using the public VulnerableCode instance.

.. code-block:: python

    VULNERABLECODE_URL=https://public.vulnerablecode.io/
    VULNERABLECODE_API_KEY=insert_your_api_key_here

.. note::
    You have the option to define and set those settings directly on your Dataspace.
    For detailed instructions, refer to :ref:`dejacode_dataspace_vulnerablecode`.

LDAP Integration
================

AUTHENTICATION_BACKEND
----------------------

This setting enables users to authenticate against an LDAP server.

To enable the LDAP authentication, set the following value for the
``AUTHENTICATION_BACKENDS`` setting.

.. code-block:: python

    AUTHENTICATION_BACKENDS=dje.ldap_backend.DejaCodeLDAPBackend

An alternative setup is to allow the authentication in the system first using
LDAP, and then using a DejaCode user account if the authentication through LDAP
was not successful.
For example, this can be useful if the LDAP server is down.

.. code-block:: python

    AUTHENTICATION_BACKENDS=dje.ldap_backend.DejaCodeLDAPBackend,django.contrib.auth.backends.ModelBackend

SERVER_URI
----------

The URI of the LDAP server.

.. code-block:: python

    AUTH_LDAP_SERVER_URI=ldap://ldap.server.com:389

START_TLS
---------

By default, LDAP connections are unencrypted.
If you need a secure connection to the LDAP server, you can either use an
``ldaps://`` URI or enable the StartTLS extension.

To enable StartTLS, set ``AUTH_LDAP_START_TLS`` to True.

.. code-block:: python

    AUTH_LDAP_START_TLS=True

BIND
----

``AUTH_LDAP_BIND_DN`` and ``AUTH_LDAP_BIND_PASSWORD`` should be set with the
distinguished name, and password to use when binding to the LDAP server.

.. note:: Use empty strings (the default) for an anonymous bind.

.. code-block:: python

    AUTH_LDAP_BIND_DN=""
    AUTH_LDAP_BIND_PASSWORD=""

USER_DN
-------

The following setting is required to locate a user in the LDAP directory.
The filter parameter should contain the placeholder %(user)s for the username.
It must return exactly one result for authentication to succeed.

.. code-block:: python

    AUTH_LDAP_USER_DN="ou=users,dc=example,dc=com"
    AUTH_LDAP_USER_FILTERSTR="(uid=%(user)s)"

AUTOCREATE_USER
---------------

When ``AUTH_LDAP_AUTOCREATE_USER`` is True (default), a new DejaCode user will
be created in the database with the minimum permission (a read-only user).

Enabling this setting also requires a valid dataspace name for the
``AUTH_LDAP_DATASPACE`` setting.
New DejaCode users created on the first LDAP authentication will be located in
this Dataspace.

.. code-block:: python

    AUTH_LDAP_AUTOCREATE_USER=True
    AUTH_LDAP_DATASPACE=your_dataspace

.. note:: Set ``AUTH_LDAP_AUTOCREATE_USER`` to False in order to limit
 authentication to users that already exist in the database only, in which case
 new users must be manually created by a DejaCode administrator using the
 application.

.. code-block:: python

    AUTH_LDAP_AUTOCREATE_USER=False

USER_ATTR_MAP
-------------

``AUTH_LDAP_USER_ATTR_MAP`` is used to copy LDAP directory information into
DejaCode user objects, at creation time (see ``AUTH_LDAP_AUTOCREATE_USER``) or
during updates (see ``AUTH_LDAP_ALWAYS_UPDATE_USER``).
This dictionary maps DejaCode user fields to (case-insensitive) LDAP attribute
names.

.. code-block:: python

    AUTH_LDAP_USER_ATTR_MAP=first_name=givenName,last_name=sn,email=mail

ALWAYS_UPDATE_USER
------------------

By default, all mapped user fields will be updated each time the user logs in.
To disable this, set ``AUTH_LDAP_ALWAYS_UPDATE_USER`` to False.

.. code-block:: python

    AUTH_LDAP_ALWAYS_UPDATE_USER=False

Group permissions
-----------------

User's LDAP group memberships can be used with the DejaCode group permissions system.

The LDAP groups that a user belongs to will be mapped with existing DejaCode groups
using the Group ``name`` attribute.
The permissions defined for each of the mapped DejaCode groups will be loaded for the
LDAP user.

To enable and configure DejaCode to use LDAP groups you need to enable LDAP as
explained above and also do these additional tasks:

* In the reference nexB Dataspace, create the DejaCode groups and associated
  permissions through
  the DejaCode admin interface. From the Admin dashboard: ``Administration`` >
  ``Groups``.
* Configure DejaCode settings to enable LDAP groups retrieval by adding these lines to
  your DejaCode settings file.
  Set the proper ``AUTH_LDAP_GROUP_SEARCH`` values matching for your LDAP
  configuration.

.. code-block:: python

    AUTH_LDAP_FIND_GROUP_PERMS=True
    AUTH_LDAP_GROUP_DN="ou=groups,dc=example,dc=com"
    AUTH_LDAP_GROUP_FILTERSTR="(objectClass=groupOfNames)"

Configuration examples
======================

Configuration 1
---------------

* LDAP as the only way to log-in DejaCode.
* Unencrypted connections with the LDAP server.
* Anonymous bind to the LDAP server.
* Users need to be manually created in DejaCode by an administrator first.
* No mapping for users attributes is defined
* Users field values in the database are not updated at authentication time.
* Users are located using the ``uid`` attribute with the
  ``ou=users,dc=example,dc=com`` distinguished name.

.. code-block:: python

    AUTHENTICATION_BACKENDS=dje.ldap_backend.DejaCodeLDAPBackend
    AUTH_LDAP_SERVER_URI=ldap://ldap.server.com:389
    AUTH_LDAP_USER_DN="ou=users,dc=example,dc=com"
    AUTH_LDAP_USER_FILTERSTR="(uid=%(user)s)"
    AUTH_LDAP_AUTOCREATE_USER=False
    AUTH_LDAP_ALWAYS_UPDATE_USER=False

Configuration 2
---------------

* LDAP as the first way to log-in, and then using a DejaCode user account if
  the authentication through LDAP was not successful.
* Encrypted connections with the LDAP server.
* Binding to the LDAP server using ``cn=admin,ou=users,dc=example,dc=com`` for
  the distinguished name and ``pw`` the password.
* Users are located using the ``cn`` attribute with the
  ``ou=users,dc=example,dc=com`` distinguished name.
* Users will be automatically created or updated. New users will be located in
  the "nexB" dataspace.
* Users attributes will be mapped according to the ``AUTH_LDAP_USER_ATTR_MAP``
  values.

.. code-block:: python

    AUTHENTICATION_BACKENDSdje.ldap_backend.DejaCodeLDAPBackend,django.contrib.auth.backends.ModelBackend
    AUTH_LDAP_SERVER_URI=ldaps://ldap.server.com:636
    AUTH_LDAP_BIND_DN=cn=admin,ou=users,dc=example,dc=com
    AUTH_LDAP_BIND_PASSWORD=pw
    AUTH_LDAP_USER_DN="ou=users,dc=example,dc=com"
    AUTH_LDAP_USER_FILTERSTR="(cn=%(user)s)"
    AUTH_LDAP_AUTOCREATE_USER=True
    AUTH_LDAP_DATASPACE=nexB
    AUTH_LDAP_ALWAYS_UPDATE_USER=True
    AUTH_LDAP_USER_ATTR_MAP=first_name=givenName,last_name=sn,email=mail
