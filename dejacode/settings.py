#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

# Common Django settings for all deployments of DejaCode

import sys
import tempfile
from pathlib import Path

import environ

# The home directory of the dejacode user that owns the installation.
PROJECT_DIR = environ.Path(__file__) - 1
ROOT_DIR = PROJECT_DIR - 1

# Environment
ENV_FILE = "/etc/dejacode/.env"
if not Path(ENV_FILE).exists():
    ENV_FILE = ROOT_DIR(".env")

env = environ.Env()
environ.Env.read_env(ENV_FILE)  # Reading the .env file into os.environ

# Security
SECRET_KEY = env.str("SECRET_KEY")
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=[".localhost", "127.0.0.1", "[::1]", "host.docker.internal", "172.17.0.1"],
)
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
# SECURITY WARNING: don't run with debug turned on in production
DEBUG = env.bool("DEJACODE_DEBUG", default=False)

# True if running tests through `./manage test`
IS_TESTS = "test" in sys.argv

TEST_RUNNER = "dje.tests.DejaCodeTestRunner"

DEJACODE_LOG_LEVEL = env.str("DEJACODE_LOG_LEVEL", "INFO")

# A list of all the people who get code error notifications.
# Example: DEJACODE_ADMINS="Blake <blake@domain.org>, Alice Judge <alice@domain.org>"
ADMINS = env.list("DEJACODE_ADMINS", default=[])
MANAGERS = ADMINS

# Database settings
DATABASES = {
    "default": {
        "ENGINE": env.str("DATABASE_ENGINE", "django.db.backends.postgresql"),
        "HOST": env.str("DATABASE_HOST", "localhost"),
        "PORT": env.str("DATABASE_PORT", "5432"),
        "NAME": env.str("DATABASE_NAME", "dejacode_db"),
        "USER": env.str("DATABASE_USER", default="dejacode"),
        "PASSWORD": env.str("DATABASE_PASSWORD", default=""),
        "ATOMIC_REQUESTS": True,
        "CONN_MAX_AGE": 600,  # 10min lifetime connection
    }
}

# Allow Anonymous users to access @accept_anonymous views with the `public` data.
ANONYMOUS_USERS_DATASPACE = env.str("ANONYMOUS_USERS_DATASPACE", default=None)

# guardian: ANONYMOUS_USER_NAME is set to None, anonymous user object
# permissions-are disabled.
ANONYMOUS_USER_NAME = env.str("ANONYMOUS_USER_NAME", default=None)

# An administrative User in the Reference Dataspace can see and copy data from
# every Dataspace; otherwise, the User can only see data from
# his assigned Dataspace and copy from the Reference Dataspace.
# The default Reference Dataspace is always 'nexB' unless the following
# setting is set to another existing Dataspace.
# If set to an empty value or a non-existing Dataspace, 'nexB' will be
# considered the Reference Dataspace.
REFERENCE_DATASPACE = env.str("REFERENCE_DATASPACE", default="nexB")

# Enable the CloneDataset view using the following dataspace as reference.
TEMPLATE_DATASPACE = env.str("TEMPLATE_DATASPACE", default=None)

# Local time zone for this installation. Choices can be found here:
# https://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
TIME_ZONE = env.str("TIME_ZONE", default="US/Pacific")

SITE_ID = env.int("SITE_ID", default=1)
SITE_URL = env.str("SITE_URL", default="")

ENABLE_SELF_REGISTRATION = env.bool("ENABLE_SELF_REGISTRATION", default=False)
HCAPTCHA_SITEKEY = env.str("HCAPTCHA_SITEKEY", default="")
HCAPTCHA_SECRET = env.str("HCAPTCHA_SECRET", default="")

# This instructs the browser to only send these cookies over HTTPS connections.
# Note that this will mean that sessions will not work over HTTP, and the CSRF
# protection will prevent any POST data being accepted over HTTP
# (which is fine as we are redirecting all HTTP traffic to HTTPS).
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)

# DejaCode User Model
AUTH_USER_MODEL = "dje.DejacodeUser"


# This is defined here as a do-nothing function because we can't import
# django.utils.translation -- that module depends on the settings.
def gettext_noop(s):
    return s


# Available Language code for this installation.
# Add support for a custom translation using the 'en-gb' one, as the
# language locale needs to exist in django/conf/locale/ to avoid an IOError.
LANGUAGES = [
    ("en", gettext_noop("English")),
    ("en-gb", gettext_noop("Custom English")),
]

# Set the language for this installation. More choices can be found here:
LANGUAGE_CODE = env.str("LANGUAGE_CODE", default="en")

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = env.bool("USE_I18N", default=True)

# Using 'locale' for the directory name in the project folder clashes with
# Python standard library module and raise an ImportWarning.
LOCALE_PATHS = [
    PROJECT_DIR("localization"),
]

# A full Python path to a Python package that contains format definitions for
# project locales. If not None, Django will check for a formats.py file, under
# the directory named as the current locale, and will use the formats defined
# on this file.
FORMAT_MODULE_PATH = "dejacode.formats"

# Absolute path to the directory static files should be collected to.
# Hardcoded to avoid any path resolution issues, especially with symlinks.
STATIC_ROOT = env.str("STATIC_ROOT", default="var/dejacode/static/")

# URL prefix for static files.
STATIC_URL = env.str("STATIC_URL", default="/static/")

# This setting defines the additional locations the staticfiles app will traverse if the
# FileSystemFinder finder is enabled, e.g. if you use the collectstatic or findstatic
# management command or use the static file serving view.
STATICFILES_DIRS = [
    PROJECT_DIR("static"),
]

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Hardcoded to avoid any path resolution issues, especially with symlinks.
# Note that we do not rely on the MEDIA_URL system to send files.
MEDIA_ROOT = env.str("MEDIA_ROOT", default="var/dejacode/media/")

# File upload
MAX_UPLOAD_SIZE = env.int("MAX_UPLOAD_SIZE", default=31457280)  # 30M
FILE_UPLOAD_PERMISSIONS = 0o644  # -rw-rw-r--

# https://docs.djangoproject.com/en/dev/ref/settings/#data-upload-max-number-fields
# Set to 10 times the default value (1,000)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

# hCaptcha script location for registration form
HCAPTCHA_JS_API_URL = env.str("HCAPTCHA_JS_API_URL", default="/static/js/hcaptcha.js")

EXTRA_MIDDLEWARE = env.list("EXTRA_MIDDLEWARE", default=[])

MIDDLEWARE = [
    # GZipMiddleware should be placed before any other middleware that need to
    # read or write the response body so that compression happens afterward.
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "dje.middleware.ProhibitInQueryStringMiddleware",
    "django.middleware.http.ConditionalGetMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # OTPMiddleware needs to come after AuthenticationMiddleware
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "dje.middleware.LastAPIAccessMiddleware",
    *EXTRA_MIDDLEWARE,
    # AxesMiddleware should be the last middleware in the MIDDLEWARE list.
    # It only formats user lockout messages and renders Axes lockout responses
    # on failed user authentication attempts from login views.
    # If you do not want Axes to override the authentication response
    # you can skip installing the middleware and use your own views.
    "axes.middleware.AxesMiddleware",
]

# Security
SECURE_CONTENT_TYPE_NOSNIFF = env.bool("SECURE_CONTENT_TYPE_NOSNIFF", default=True)
SECURE_CROSS_ORIGIN_OPENER_POLICY = env.str(
    "SECURE_CROSS_ORIGIN_OPENER_POLICY", default="same-origin"
)

X_FRAME_OPTIONS = "DENY"
# Note: The CSRF_COOKIE_HTTPONLY cannot be activated yet without breaking all
# the AJAX (POST, PUT, etc..) requests, like the annotation system for example.
# It will be required to configure the following:
# https://docs.djangoproject.com/en/dev/ref/csrf/
# CSRF_COOKIE_HTTPONLY = True
# Also, security.W004 SECURE_HSTS_SECONDS and security.W008 SECURE_SSL_REDIRECT
# are handled at the web server level.
SILENCED_SYSTEM_CHECKS = [
    "security.W004",
    "security.W008",
    "security.W017",
    "urls.W005",
    "admin.E039",
]

# Set the following to True to enable ClamAV scan on uploaded files
# This requires the installation of ClamAV
# See https://www.clamav.net/documents/installing-clamav
# Also, you need to set the StreamMaxLength value in /etc/clamav/clamd.conf
# bigger than the MAX_UPLOAD_SIZE setting.
CLAMD_ENABLED = env.bool("CLAMD_ENABLED", default=False)
# Use ClamdNetworkSocket in place of ClamdUnixSocket
CLAMD_USE_TCP = env.bool("CLAMD_USE_TCP", default=True)
CLAMD_TCP_ADDR = env.str("CLAMD_TCP_ADDR", default="127.0.0.1")

# The following password validation apply to 3 the password entry locations:
# - Change password: /account/password_change/
# - Password reset: /account/password_reset/
# - User registration: /account/register/
# Notes: CommonPasswordValidator is not useful since none of the password in that list contain
# a special character
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "dje.validators.SpecialCharacterPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
]

AUTHENTICATION_BACKENDS = env.list(
    "AUTHENTICATION_BACKENDS",
    default=[
        "django.contrib.auth.backends.ModelBackend",
    ],
)

# AxesBackend should be the first backend in the AUTHENTICATION_BACKENDS list.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesBackend",
    *AUTHENTICATION_BACKENDS,
    "guardian.backends.ObjectPermissionBackend",
]

ROOT_URLCONF = "dejacode.urls"

WSGI_APPLICATION = "dejacode.wsgi.application"

SECURE_PROXY_SSL_HEADER = env.tuple(
    "SECURE_PROXY_SSL_HEADER", default=("HTTP_X_FORWARDED_PROTO", "https")
)

# Using named URL patterns to reduce configuration duplication and URL
# translation compatibility.
LOGIN_URL = env.str("LOGIN_URL", default="login")
LOGIN_REDIRECT_URL = env.str("LOGIN_REDIRECT_URL", default="home")

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "debug": DEBUG,
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "dje.context_processors.dejacode_context",
                "dje.client_data.client_data_context_processor",
            ],
        },
    }
]

# The order of INSTALLED_APPS is significant!
# Django will look for a template in the INSTALLED_APP order and will use the
# one it finds first.
# Therefore, all templates overrides regarding the admin should be located in
# 'dje' app template/ folder.
# Also, 'dje' must come before 'grappelli', and 'grappelli' before
# 'django.contrib.admin'.
# On the other hand, the management commands will override each others if the
# app is declared after another in the list.
PREREQ_APPS = [
    "dje",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "django.contrib.sites",
    "django.contrib.humanize",
    "django.contrib.postgres",
    "grappelli.dashboard",
    "grappelli",
    "django.contrib.admin",
    "rest_framework",
    "rest_framework.authtoken",
    "django_rq",
    "crispy_forms",
    "crispy_bootstrap5",
    "guardian",
    "django_filters",
    "rest_hooks",
    "notifications",
    "axes",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "hcaptcha_field",
]

PROJECT_APPS = [
    "organization",
    "license_library",
    "component_catalog",
    "product_portfolio",
    "workflow",
    "reporting",
    "purldb",
    "policy",
    "notification",
]

EXTRA_APPS = env.list("EXTRA_APPS", default=[])

INSTALLED_APPS = PREREQ_APPS + PROJECT_APPS + EXTRA_APPS

SITE_TITLE = env.str("SITE_TITLE", default="DejaCode")
HEADER_TEMPLATE = env.str("HEADER_TEMPLATE", default="includes/header.html")
FOOTER_TEMPLATE = env.str("FOOTER_TEMPLATE", default="includes/footer.html")

GRAPPELLI_INDEX_DASHBOARD = "dje.dashboard.DejaCodeDashboard"
GRAPPELLI_CLEAN_INPUT_TYPES = False

FAVICON_HREF = env.str("FAVICON_HREF", default=f"{STATIC_URL}img/favicon.ico")

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Instead of sending out real emails the console backend just writes the emails
# that would be sent to the standard output.
EMAIL_BACKEND = env.str("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env.str("EMAIL_HOST", default="")
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)

# An email address displayed in UI for users to reach the support team.
DEJACODE_SUPPORT_EMAIL = env.str("DEJACODE_SUPPORT_EMAIL", default="")

# Enable this setting to display a "Tools" section in the navbar including
# links to the "Requests" and "Reporting" views.
SHOW_TOOLS_IN_NAV = env.bool("SHOW_TOOLS_IN_NAV", default=True)

# Set False to hide the "Product Portfolio" section in the navbar.
SHOW_PP_IN_NAV = env.bool("SHOW_PP_IN_NAV", default=True)

# An integer specifying how many objects should be displayed per page.
PAGINATE_BY = env.int("PAGINATE_BY", default=None)

ADMIN_FORMS_CONFIGURATION = env.dict("ADMIN_FORMS_CONFIGURATION", default={})

# Location of the changelog file
CHANGELOG_PATH = ROOT_DIR("CHANGELOG.rst")

# Display a "Report Scan Issues" button in Scan tab
# Format: "dataspace_name=request_template_UUID,"
SCAN_ISSUE_REQUEST_TEMPLATE = env.dict("SCAN_ISSUE_REQUEST_TEMPLATE", default={})

# https://docs.djangoproject.com/en/dev/topics/http/sessions/
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_EXPIRE_AT_BROWSER_CLOSE = env.bool("SESSION_EXPIRE_AT_BROWSER_CLOSE", default=False)
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=28800)  # 8 hours
# Prevent from erasing a session of another Django app when running multiple `runserver`
# instances side by side on the on same host (different ports).
SESSION_COOKIE_NAME = "dejacode_sessionid"

# Removed the "django.core.files.uploadhandler.MemoryFileUploadHandler",
# to force every file to be uploaded to the temp folder, even if smaller than
# FILE_UPLOAD_MAX_MEMORY_SIZE
FILE_UPLOAD_HANDLERS = [
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]

REDIS_URL = env.str("REDIS_URL", default="redis://127.0.0.1:6379")

# Default setup for the cache
# See https://docs.djangoproject.com/en/dev/topics/cache/
CACHE_BACKEND = env.str("CACHE_BACKEND", default="django.core.cache.backends.locmem.LocMemCache")
CACHES = {
    "default": {
        "BACKEND": CACHE_BACKEND,
        "LOCATION": REDIS_URL,
        "TIMEOUT": 900,  # 15 minutes, in seconds
    },
    "vulnerabilities": {
        "BACKEND": CACHE_BACKEND,
        "LOCATION": REDIS_URL,
        "TIMEOUT": 3600,  # 1 hour, in seconds
        "KEY_PREFIX": "vuln",
    },
}

# Job Queue
RQ_QUEUES = {
    "default": {
        "HOST": env.str("DEJACODE_REDIS_HOST", default="localhost"),
        "PORT": env.str("DEJACODE_REDIS_PORT", default="6379"),
        "PASSWORD": env.str("DEJACODE_REDIS_PASSWORD", default=""),
        "DEFAULT_TIMEOUT": env.int("DEJACODE_REDIS_DEFAULT_TIMEOUT", default=360),
    },
}


def enable_rq_eager_mode():
    """
    Enable the eager mode for the RQ tasks system.
    Meaning the tasks will run directly sychroniously without the need of a worker.
    Setting ASYNC to False in RQ_QUEUES will run jobs synchronously, but a running
    Redis server is still needed to store job data.
    This function patch the django_rq.get_redis_connection to always return a fake
    redis connection using the `fakeredis` library.
    """
    import django_rq.queues
    from fakeredis import FakeRedis
    from fakeredis import FakeStrictRedis

    for queue_config in RQ_QUEUES.values():
        queue_config["ASYNC"] = False

    def get_fake_redis_connection(config, use_strict_redis):
        return FakeStrictRedis() if use_strict_redis else FakeRedis()

    django_rq.queues.get_redis_connection = get_fake_redis_connection


DEJACODE_ASYNC = env.bool("DEJACODE_ASYNC", default=False)
if not DEJACODE_ASYNC or IS_TESTS:
    enable_rq_eager_mode()


# https://docs.djangoproject.com/en/dev/topics/logging/#configuring-logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"
        },
        "simple": {"format": "%(levelname)s %(message)s"},
        "django.server": {
            "()": "django.utils.log.ServerFormatter",
            "format": "[%(server_time)s] %(message)s",
        },
    },
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "handlers": {
        "null": {
            "class": "logging.NullHandler",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
        "django.server": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "django.server",
        },
        # "dejacode.api": {
        #     "level": "INFO",
        #     "class": "logging.FileHandler",
        #     "filename": "/var/dejacode/log/dejacode_api.log",
        # },
    },
    "loggers": {
        "django": {
            "handlers": ["null"] if IS_TESTS else ["console"],
            "propagate": True,
            "level": DEJACODE_LOG_LEVEL,
        },
        # This is required to send the email notification on ERRORS.
        "django.request": {
            "handlers": ["mail_admins"],
            "level": "ERROR",
            "propagate": True,
        },
        # Set DEJACODE_LOG_LEVEL=DEBUG to display all SQL queries in the console.
        "django.db.backends": {
            "level": DEJACODE_LOG_LEVEL,
        },
        "dje": {
            "handlers": ["null"] if IS_TESTS else ["console"],
            "propagate": False,
            "level": DEJACODE_LOG_LEVEL,
        },
        "dje.tasks": {
            "handlers": ["null"] if IS_TESTS else ["console"],
            "propagate": False,
            "level": DEJACODE_LOG_LEVEL,
        },
        # "dejacode.api": {
        #     "handlers": ["dejacode.api"],
        #     "propagate": False,
        #     "level": "INFO",
        # },
        "dejacode_toolkit": {
            "handlers": ["null"] if IS_TESTS else ["console"],
            "propagate": False,
            "level": "DEBUG" if DEBUG else DEJACODE_LOG_LEVEL,
        },
        "django_auth_ldap": {
            "handlers": ["null"] if IS_TESTS else ["console"],
            "propagate": False,
            "level": DEJACODE_LOG_LEVEL,
        },
    },
}

# https://django-grappelli.readthedocs.org/en/latest/customization.html#autocomplete-lookups
GRAPPELLI_AUTOCOMPLETE_SEARCH_FIELDS = {
    "license_library": {
        "license": [
            "key__icontains",
            "name__icontains",
            "short_name__icontains",
        ],
    },
    "organization": {
        "owner": ["name__icontains"],
    },
    "component_catalog": {
        "component": ["name_version__icontains"],
        "package": [
            "filename__icontains",
            "type_name_version__icontains",
        ],
    },
    "product_portfolio": {
        "product": ["name_version__icontains"],
        "codebaseresource": ["path__icontains"],
        "productcomponent": ["component__name__icontains"],
        "productpackage": [
            "package__filename__icontains",
            "package__download_url__icontains",
        ],
    },
}

REST_API_RATE_THROTTLE = env.str("REST_API_RATE_THROTTLE", default="2/second")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        "rest_framework.permissions.DjangoModelPermissions",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "dje.api_custom.DJEOrderingFilter",
        "dje.api_custom.DJESearchFilter",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "dje.api_custom.DJEBrowsableAPIRenderer",
    ),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": REST_API_RATE_THROTTLE,
    },
    "DEFAULT_PAGINATION_CLASS": "dje.api_custom.PageSizePagination",
    "DEFAULT_SCHEMA_CLASS": "rest_framework.schemas.coreapi.AutoSchema",
    "VIEW_NAME_FUNCTION": "dje.api_custom.get_view_name",
    "URL_FIELD_NAME": "api_url",  # Default 'url' used as a field on the Package model
}

# django-registration
# The registration is only available on dejacode.com instances
# Although, this setting and registration views are needed for the user creation.
ACCOUNT_ACTIVATION_DAYS = 10

# https://github.com/zapier/django-rest-hooks
HOOK_FINDER = "notification.models.find_and_fire_hook"
HOOK_DELIVERER = "notification.tasks.deliver_hook_wrapper"
HOOK_EVENTS = {
    # 'any.event.name': 'App.Model.Action' (created/updated/deleted)
    "request.added": "workflow.Request.created+",
    "request.updated": "workflow.Request.updated+",
    "request_comment.added": "workflow.RequestComment.created+",
    "user.added_or_updated": None,
    "user.locked_out": None,
}
# Provide context variables to the `Webhook` values such as `extra_headers`.
HOOK_ENV = env.dict("HOOK_ENV", default={})

# Django-axes
# Enable or disable Axes plugin functionality
AXES_ENABLED = env.bool("AXES_ENABLED", default=False)
# The integer number of login attempts allowed before the user is locked out.
AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
# If set, specifies a template to render when a user is locked out.
AXES_LOCKOUT_TEMPLATE = env.str("AXES_LOCKOUT_TEMPLATE", default="axes_lockout.html")
# If True, only lock based on username, and never lock based on IP
# if attempts to exceed the limit.
AXES_ONLY_USER_FAILURES = True
# If True, a successful login will reset the number of failed logins.
AXES_RESET_ON_SUCCESS = True
# If True, disable writing login and logout access logs to database,
# so the admin interface will not have user login trail for successful user
# authentication.
AXES_DISABLE_ACCESS_LOG = True

# 2FA with django-otp
OTP_TOTP_ISSUER = "DejaCode"

# https://docs.djangoproject.com/en/dev/releases/3.2/#customizing-type-of-auto-created-primary-keys
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

DATASPACE_DOMAIN_REDIRECT = env.dict("DATASPACE_DOMAIN_REDIRECT", default={})
LOGIN_FORM_ALERT = env.str("LOGIN_FORM_ALERT", default="")

# Debug toolbar
DEBUG_TOOLBAR = env.bool("DEJACODE_DEBUG_TOOLBAR", default=False)
if DEBUG and DEBUG_TOOLBAR:
    INSTALLED_APPS.append("debug_toolbar")
    MIDDLEWARE.append("debug_toolbar.middleware.DebugToolbarMiddleware")
    INTERNAL_IPS = ["127.0.0.1"]

if IS_TESTS:
    # Silent the django-axes logging during tests
    LOGGING["loggers"].update({"axes": {"handlers": ["null"]}})
    # Do not pollute the MEDIA_ROOT location while running the tests.
    MEDIA_ROOT = tempfile.TemporaryDirectory().name
    # Set a faster hashing algorithm for running the tests
    # https://docs.djangoproject.com/en/dev/topics/testing/overview/#password-hashing
    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]
    # Disabled the migration system when running tests to save time
    # DATABASES["default"].update({"TEST": {"MIGRATE": False}})
    # High throttle rate when running tests
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["user"] = "1000/second"


# LDAP Configuration

import ldap
from django_auth_ldap.config import GroupOfNamesType
from django_auth_ldap.config import LDAPSearch

# This authentication backend enables users to authenticate against an
# LDAP server.
# To enable LDAP Authentication, first, set the following in your .env
# and provide values for the following settings.
# AUTHENTICATION_BACKENDS=dje.ldap_backend.DejaCodeLDAPBackend

# The URI of the LDAP server. "ldap://ldap.server.com:389"
AUTH_LDAP_SERVER_URI = env.str("AUTH_LDAP_SERVER_URI", default="")

# By default, LDAP connections are unencrypted.
# If you need a secure connection to the LDAP server, you can either use an
# 'ldaps://' URI or enable the StartTLS extension.
AUTH_LDAP_START_TLS = env.bool("AUTH_LDAP_START_TLS", default=True)

# AUTH_LDAP_BIND_DN and AUTH_LDAP_BIND_PASSWORD should be set with the
# distinguished name and password to use when binding to the LDAP server.
# Use empty strings (the default) for an anonymous bind.
AUTH_LDAP_BIND_DN = env.str("AUTH_LDAP_BIND_DN", default="")
AUTH_LDAP_BIND_PASSWORD = env.str("AUTH_LDAP_BIND_PASSWORD", default="")

# The following setting is required to locate a user in the LDAP directory.
# The filter parameter should contain the placeholder %(user)s for the username.
# It must return exactly one result for authentication to succeed.
# The distinguished name of the search base.
# AUTH_LDAP_USER_DN="ou=users,dc=example,dc=com"
AUTH_LDAP_USER_DN = env.str("AUTH_LDAP_USER_DN", default="")
# An optional filter string (e.g. ‘(objectClass=person)’).
# In order to be valid, filterstr must be enclosed in parentheses.
# AUTH_LDAP_USER_FILTERSTR="(uid=%(user)s)"
AUTH_LDAP_USER_FILTERSTR = env.str("AUTH_LDAP_USER_FILTERSTR", default="")

AUTH_LDAP_USER_SEARCH = LDAPSearch(AUTH_LDAP_USER_DN, ldap.SCOPE_SUBTREE, AUTH_LDAP_USER_FILTERSTR)

# When AUTH_LDAP_AUTOCREATE_USER is True (default), a new DejaCode user will be
# created in the database with the minimum permission (a read-only user).
# Enabling this setting also requires a valid dataspace name for the
# AUTH_LDAP_DATASPACE setting (see below).
# Set AUTH_LDAP_AUTOCREATE_USER to False in order to limit authentication to
# users that already exist in the database only, in which case new users must be
# manually created by a DejaCode administrator using the application.
AUTH_LDAP_AUTOCREATE_USER = env.bool("AUTH_LDAP_AUTOCREATE_USER", default=True)

# The following value is required when AUTH_LDAP_AUTOCREATE_USER is True.
# New DejaCode users created on the first LDAP authentication will be located in
# this Dataspace.
AUTH_LDAP_DATASPACE = env.str("AUTH_LDAP_DATASPACE", default="")

# AUTH_LDAP_USER_ATTR_MAP is used to copy LDAP directory information into
# DejaCode user objects, at creation time (see AUTH_LDAP_AUTOCREATE_USER) or
# during updates (see AUTH_LDAP_ALWAYS_UPDATE_USER).
# This dictionary maps DejaCode user fields to (case-insensitive) LDAP attribute
# names.
# AUTH_LDAP_USER_ATTR_MAP=first_name=givenName,last_name=sn,email=mail
AUTH_LDAP_USER_ATTR_MAP = env.dict("AUTH_LDAP_USER_ATTR_MAP", default={})

# By default, all mapped user fields will be updated each time the user logs in.
# To disable this, set AUTH_LDAP_ALWAYS_UPDATE_USER to False.
AUTH_LDAP_ALWAYS_UPDATE_USER = env.bool("AUTH_LDAP_ALWAYS_UPDATE_USER", default=True)

# To associate LDAP groups and DejaCode groups:
# 1. Create the DejaCode groups and associate permissions through the DejaCode
#    admin interface. From the Admin dashboard: Administration > Groups.
# 2. Enable the following settings to enable LDAP groups retrieval.
#    Set the proper AUTH_LDAP_GROUP_DN and AUTH_LDAP_GROUP_FILTERSTR values matching
#    for your LDAP configuration.
AUTH_LDAP_FIND_GROUP_PERMS = env.bool("AUTH_LDAP_FIND_GROUP_PERMS", default=False)
# AUTH_LDAP_GROUP_DN="ou=groups,dc=example,dc=com"
AUTH_LDAP_GROUP_DN = env.str("AUTH_LDAP_GROUP_DN", default="")
# In order to be valid, filterstr must be enclosed in parentheses.
# AUTH_LDAP_GROUP_FILTERSTR="(objectClass=groupOfNames)"
AUTH_LDAP_GROUP_FILTERSTR = env.str("AUTH_LDAP_GROUP_FILTERSTR", default="")

AUTH_LDAP_GROUP_TYPE = GroupOfNamesType()
AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
    AUTH_LDAP_GROUP_DN, ldap.SCOPE_SUBTREE, AUTH_LDAP_GROUP_FILTERSTR
)
