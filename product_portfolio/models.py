#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.html import format_html_join
from django.utils.translation import gettext_lazy as _

import guardian.shortcuts
from notifications.signals import notify

from component_catalog.models import CONFIGURATION_STATUS_HELP
from component_catalog.models import BaseStatusMixin
from component_catalog.models import ComponentRelationshipMixin
from component_catalog.models import DefaultOnAdditionFieldMixin
from component_catalog.models import DefaultOnAdditionMixin
from component_catalog.models import KeywordsMixin
from component_catalog.models import LicenseExpressionMixin
from component_catalog.models import Package
from component_catalog.models import component_mixin_factory
from dje import tasks
from dje.fields import LastModifiedByField
from dje.models import DataspacedManager
from dje.models import DataspacedModel
from dje.models import DataspacedQuerySet
from dje.models import History
from dje.models import HistoryFieldsMixin
from dje.models import ReferenceNotesMixin
from dje.models import colored_icon_mixin_factory
from dje.validators import generic_uri_validator
from dje.validators import validate_url_segment
from dje.validators import validate_version
from vulnerabilities.fetch import fetch_for_queryset
from vulnerabilities.models import Vulnerability

RELATION_LICENSE_EXPRESSION_HELP_TEXT = _(
    "The License Expression assigned to a DejaCode Product Package or Product "
    'Component is an editable value equivalent to a "concluded license" as determined '
    "by a curator who has performed analysis to clarify or correct the declared "
    "license expression, which may have been assigned automatically "
    "(from a scan or an associated package definition) when the Package or Component "
    "was originally created, or which may require the assertion of a choice of license."
    "A license expression defines the relationship of one  or more licenses to a "
    "software object. More than one applicable license can be expressed as "
    '"license-key-a AND license-key-b". A choice of applicable licenses can be '
    'expressed as "license-key-a OR license-key-b", and you can indicate the '
    "primary (preferred) license by placing it first, on the left-hand side of the "
    "OR relationship. The relationship words (OR, AND) can be combined as needed, "
    "and the use of parentheses can be applied to clarify the meaning; for example "
    '"((license-key-a AND license-key-b) OR (license-key-c))". An exception '
    'to a license can be expressed as "license-key WITH license-exception-key".'
)


class FieldChangesMixin:
    """
    Check field values changes.
    The original values are cached when loaded from the db to avoid making
    extra queries.

    https://docs.djangoproject.com/en/dev/ref/models/instances/#customizing-model-loading
    """

    @classmethod
    def from_db(cls, db, field_names, values):
        """Store the original field values as loaded from the db on the instance."""
        new = super().from_db(db, field_names, values)
        new._loaded_values = dict(zip(field_names, values))
        return new

    def has_changed(self, field_name):
        """
        Return True if the provided `field_name` value has changed since it
        was loaded from the db.
        """
        loaded_values = getattr(self, "_loaded_values", None)
        if loaded_values and getattr(self, field_name) != loaded_values[field_name]:
            return True
        return False


class ProductStatus(BaseStatusMixin, DataspacedModel):
    request_to_generate = models.ForeignKey(
        to="workflow.RequestTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        limit_choices_to={
            "content_type__app_label": "product_portfolio",
            "content_type__model": "product",
            "include_applies_to": True,
        },
        help_text=_(
            "Identify the product-based Request Template to use for generating "
            "a Request when a Product is set to this status. "
            "Note that this Template should not include any custom required "
            "fields, since DejaCode will be creating the Request automatically."
        ),
    )

    class Meta(BaseStatusMixin.Meta):
        verbose_name_plural = _("product status")


class ProductSecuredManager(DataspacedManager):
    """
    WARNING: The security is always enabled on this manager.
    If a user context is not provided to `get_queryset()`, the returned QuerySet
    will always be empty.
    """

    # This `is_secured` attribute does not act as the security enabler,
    # but is rather used to let the manager consumer knows that a user context
    # needs to be provided in order to get the proper results.
    # See also the `is_secured()` function.
    is_secured = True

    def get_by_natural_key(self, dataspace_name, uuid):
        """
        PP fixtures are only used in tests and to populate a dev database.
        We could remove product_portfolio related fixtures and replace by
        a command to create Product data providing a User context.
        """
        return self.model.unsecured_objects.get(dataspace__name=dataspace_name, uuid=uuid)

    def get_queryset(self, user=None, perms="view_product", include_inactive=False):
        """
        Force the object level protection at the QuerySet level.
        Always Return an empty QuerySet unless a `user` is provided.

        >>> Product.objects.all()
        []
        >>> Product.objects.get_queryset()
        []
        >>> Product.objects.get_queryset(user)
        [Product1, Product2, ...]
        """
        queryset_class = super().get_queryset()

        if not user:
            return queryset_class.none()

        queryset = guardian.shortcuts.get_objects_for_user(
            user, perms, klass=queryset_class, accept_global_perms=False
        ).scope(user.dataspace)

        if include_inactive:
            return queryset

        return queryset.filter(is_active=True)

    def get_related_secured_queryset(self, user):
        """
        Return the secured QuerySet scoped to the provided `user`.
        This is required to get the proper QuerySet on calling a `ManyRelatedManager`,
        for example when using `instance.product_set`, since the `get_queryset` method
        of this related manager is not the one define here on `ProductSecuredManager`.
        """
        related_manager = self
        target_model = related_manager.model
        secured_queryset = target_model.objects.get_queryset(user)
        through_model = related_manager.through

        return through_model.objects.filter(
            **{
                related_manager.source_field_name: related_manager.instance,
                f"{related_manager.target_field_name}__in": secured_queryset,
            }
        )


BaseProductMixin = component_mixin_factory("product")


class Product(BaseProductMixin, FieldChangesMixin, KeywordsMixin, DataspacedModel):
    license_expression = models.CharField(
        max_length=1024,
        blank=True,
        db_index=True,
        help_text=_(
            "On a product in DejaCode, a license expression defines the "
            "relationship of one or more licenses to that software as declared by its "
            'licensor. More than one applicable license can be expressed as "license-key-a '
            'AND license-key-b". A choice of applicable licenses can be expressed as '
            '"license-key-a OR license-key-b", and you can indicate the primary (preferred) '
            "license by placing it first, on the left-hand side of the OR relationship. "
            "The relationship words (OR, AND) can be combined as needed, and the use of "
            'parentheses can be applied to clarify the meaning; for example "((license-key-a '
            'AND license-key-b) OR (license-key-c))". An exception to a license can be '
            'expressed as "license-key WITH license-exception-key".'
        ),
    )

    is_active = models.BooleanField(
        verbose_name=_("active"),
        default=True,
        db_index=True,
        help_text=_(
            "When set to Yes, this field indicates that a product definition is currently "
            "in use (active). When set to No, this field indicates that a product is deprecated "
            "(inactive), is no longer used, and the product will not appear in the user views. "
            "Note that this indicator applies only to a specific product version."
        ),
    )

    configuration_status = models.ForeignKey(
        to="product_portfolio.ProductStatus",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=CONFIGURATION_STATUS_HELP,
    )

    contact = models.CharField(
        max_length=255,
        blank=True,
        help_text=_(
            "Identifies the person in your organization responsible for the development and "
            "release of the Product."
        ),
    )

    licenses = models.ManyToManyField(
        to="license_library.License",
        through="ProductAssignedLicense",
    )

    components = models.ManyToManyField(
        to="component_catalog.Component",
        through="ProductComponent",
    )

    packages = models.ManyToManyField(
        to="component_catalog.Package",
        through="ProductPackage",
    )

    objects = ProductSecuredManager()

    # WARNING: Bypass the security system implemented in ProductSecuredManager.
    # This is to be used only in a few cases where the User scoping is not appropriated.
    # For example: `self.dataspace.product_set(manager='unsecured_objects').count()`
    unsecured_objects = DataspacedManager()

    class Meta(BaseProductMixin.Meta):
        permissions = (("view_product", "Can view product"),)
        # Defaults to ('add', 'change', 'delete', 'view')
        # Removed 'view' to avoid conflict with pre-django 2.1 custom `view_product`.
        default_permissions = ("add", "change", "delete")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.has_changed("configuration_status_id"):
            self.actions_on_status_change()

    def get_attribution_url(self):
        return self.get_url("attribution")

    def get_scan_all_packages_url(self):
        return self.get_url("scan_all_packages")

    def get_import_from_scan_url(self):
        return self.get_url("import_from_scan")

    def get_add_customcomponent_ajax_url(self):
        return self.get_url("add_customcomponent_ajax")

    def get_manage_components_url(self):
        return self.get_url("manage_components")

    def get_manage_packages_url(self):
        return self.get_url("manage_packages")

    def get_license_summary_url(self):
        return self.get_url("license_summary")

    def get_check_package_version_url(self):
        return self.get_url("check_package_version")

    def get_load_sboms_url(self):
        return self.get_url("load_sboms")

    def get_import_manifests_url(self):
        return self.get_url("import_manifests")

    def get_pull_project_data_url(self):
        return self.get_url("pull_project_data")

    def get_improve_packages_from_purldb_url(self):
        return self.get_url("improve_packages_from_purldb")

    @property
    def cyclonedx_bom_ref(self):
        return str(self.uuid)

    def can_be_changed_by(self, user):
        perms = guardian.shortcuts.get_perms(user, self)
        has_change_permission_on_product = "change_product" in perms

        return all(
            [
                user.has_perm("product_portfolio.change_product"),
                has_change_permission_on_product,
            ]
        )

    def actions_on_status_change(self):
        """Call post `save()`, when this instance `configuration_status` changes."""
        if not self.configuration_status:
            return

        request_template = self.configuration_status.request_to_generate
        if request_template and self.last_modified_by:
            request_template.create_request(
                title=f"Review Product {self} in {self.configuration_status} status",
                requester=self.last_modified_by,
                object_id=self.id,
            )

    @cached_property
    def all_packages(self):
        return Package.objects.filter(
            models.Q(id__in=self.packages.all()) | models.Q(component__in=self.components.all())
        ).distinct()

    def get_merged_descendant_ids(self):
        """
        Return a list of Component ids collected on the Product descendants:
        including ProductComponent and Subcomponent.
        """
        productcomponents = self.productcomponents.catalogs()
        ids = []
        for pc in productcomponents:
            ids.append(pc.component.id)
            ids.extend(pc.component.get_descendant_ids())
        return list(set(ids))

    @staticmethod
    def get_feature_values(queryset):
        return (
            queryset.exclude(feature="")
            .order_by("feature")
            .distinct()
            .values_list("feature", flat=True)
        )

    def get_feature_datalist(self):
        unique_features = set(self.get_feature_values(self.productcomponents))
        unique_features.update(self.get_feature_values(self.productpackages))
        options = format_html_join(
            "", "<option>{}</option>", ((feature,) for feature in sorted(unique_features))
        )
        return format_html('<datalist id="feature_datalist">{}</datalist>', options)

    @property
    def css_icon(self):
        return "fa-briefcase"

    def get_spdx_packages(self):
        return list(self.productcomponents.catalogs()) + list(self.productpackages.all())

    def get_cyclonedx_components(self):
        return [
            *list(self.productcomponents.catalogs().order_by("id")),
            *list(self.productpackages.all().order_by("id")),
        ]

    def get_relationship_model(self, obj):
        """Return the relationship model class for a given object."""
        relationship_models = {
            "component": ProductComponent,
            "package": ProductPackage,
        }
        object_model_name = obj._meta.model_name  # "component" or "package"
        relationship_model = relationship_models.get(object_model_name)
        if not relationship_model:
            raise ValueError(f"Unsupported object model: {object_model_name}")

        return relationship_model

    def find_assigned_other_versions(self, obj):
        """
        Look for the same objects with a different version already assigned to the product.
        Return the relation queryset for the objects with a different version.
        """
        object_model_name = obj._meta.model_name  # "component" or "package"
        relationship_model = self.get_relationship_model(obj)

        # Craft the lookups excluding the version field
        no_version_object_lookups = {
            f"{object_model_name}__{field_name}": getattr(obj, field_name)
            for field_name in obj.get_identifier_fields(purl_fields_only=True)
            if field_name != "version"
        }

        filters = {
            "product": self,
            "dataspace": obj.dataspace,
            **no_version_object_lookups,
        }
        excludes = {
            f"{object_model_name}__id": obj.id,
        }

        return relationship_model.objects.exclude(**excludes).filter(**filters)

    def assign_object(self, obj, user, replace_version=False):
        """
        Assign a provided ``obj`` (either a Component or Package) to this Product.
        Return a tuple with the status ("created", "updated", "unchanged") and the relationship
        object.
        """
        object_model_name = obj._meta.model_name  # "component" or "package"
        relationship_model = self.get_relationship_model(obj)

        filters = {
            "product": self,
            "dataspace": obj.dataspace,
            object_model_name: obj,
        }

        # 1. Check if a relation for this object already exists
        if relationship_model.objects.filter(**filters).exists():
            return "unchanged", None

        # 2. Find an existing relation for another version of the same object
        #    when replace_version is provided.
        if replace_version:
            other_assigned_versions = self.find_assigned_other_versions(obj)
            if len(other_assigned_versions) == 1:
                existing_relation = other_assigned_versions[0]
                other_version_object = getattr(existing_relation, object_model_name)
                existing_relation.update(**{object_model_name: obj, "last_modified_by": user})
                message = f'Updated {object_model_name} "{other_version_object}" to "{obj}"'
                History.log_change(user, self, message)
                return "updated", existing_relation

        # 3. Otherwise, create a new relation
        defaults = {
            "license_expression": obj.license_expression,
            "created_by": user,
            "last_modified_by": user,
        }
        created_relation = relationship_model.objects.create(**filters, **defaults)
        History.log_addition(user, created_relation)
        History.log_change(user, self, f'Added {object_model_name} "{obj}"')
        return "created", created_relation

    def assign_objects(self, related_objects, user, replace_version=False):
        """
        Assign provided ``related_objects`` (either a Component or Package) to this Product.
        Return counts of created, updated, and unchanged objects.
        """
        created_count = 0
        updated_count = 0
        unchanged_count = 0

        for obj in related_objects:
            status, relation = self.assign_object(obj, user, replace_version)
            if status == "created":
                created_count += 1
            elif status == "updated":
                updated_count += 1
            else:
                unchanged_count += 1

        if created_count > 0 or updated_count > 0:
            self.last_modified_by = user
            self.save()

        return created_count, updated_count, unchanged_count

    def scan_all_packages_task(self, user):
        """
        Submit a Scan request to ScanCode.io for each package assigned to this Product.
        Only packages with a proper download URL are sent.
        """
        package_urls = [
            package.download_url
            for package in self.all_packages
            if package.download_url.startswith(("http", "https"))
        ]

        tasks.scancodeio_submit_scan.delay(
            uris=package_urls,
            user_uuid=user.uuid,
            dataspace_uuid=user.dataspace.uuid,
        )

    def improve_packages_from_purldb(self, user):
        """Update all Packages assigned to the Product using PurlDB data."""
        updated_packages = []
        for package in self.packages.all():
            updated_fields = package.update_from_purldb(user)
            if updated_fields:
                updated_packages.append(package)
        return updated_packages

    def fetch_vulnerabilities(self):
        """Fetch and update the vulnerabilties of all the Package of this Product."""
        return fetch_for_queryset(self.all_packages, self.dataspace)

    def get_vulnerability_qs(self, prefetch_related_packages=False):
        """Return a QuerySet of all Vulnerability instances related to this product"""
        qs = Vulnerability.objects.filter(affected_packages__in=self.packages.all())

        if prefetch_related_packages:
            package_qs = Package.objects.filter(product=self).only_rendering_fields()
            qs = qs.prefetch_related(models.Prefetch("affected_packages", package_qs))

        return qs


class ProductRelationStatus(BaseStatusMixin, DataspacedModel):
    class Meta(BaseStatusMixin.Meta):
        verbose_name_plural = _("product relation status")


ColoredIconMixin = colored_icon_mixin_factory(
    verbose_name="product item purpose",
    icon_blank=True,
)


class ProductItemPurpose(
    DefaultOnAdditionFieldMixin,
    ColoredIconMixin,
    DataspacedModel,
):
    label = models.CharField(
        max_length=50,
        help_text=_(
            "Concise name to identify the Purpose of the Product Component or " "Product Package."
        ),
    )

    text = models.TextField(
        help_text=_("Descriptive text to define the Purpose precisely."),
    )

    class Meta:
        unique_together = (("dataspace", "label"), ("dataspace", "uuid"))
        ordering = ["label"]

    def __str__(self):
        return self.label

    @property
    def label_with_icon(self):
        icon_html = self.get_icon_as_html()
        if icon_html:
            return format_html(
                '{}<span class="ms-1">{}</span>',
                icon_html,
                self.label,
            )

        return self.label


class ProductSecuredQuerySet(DataspacedQuerySet):
    def product_secured(self, user=None, perms="view_product"):
        """Filter based on the Product object permission."""
        if not user:
            return self.none()

        product_qs = Product.objects.get_queryset(user, perms)
        return self.filter(product__in=product_qs)

    def product(self, product):
        """Filter based on the provided ``product`` object."""
        return self.filter(product=product)


class ProductComponentQuerySet(ProductSecuredQuerySet):
    def catalogs(self):
        return self.filter(component__isnull=False)

    def customs(self):
        return self.filter(component__isnull=True)


class ProductRelationshipMixin(
    DefaultOnAdditionMixin,
    LicenseExpressionMixin,
    ComponentRelationshipMixin,
    ReferenceNotesMixin,
    HistoryFieldsMixin,
    DataspacedModel,
):
    product = models.ForeignKey(
        to="product_portfolio.Product",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        # Bypass the validation in ForeignKey.validate()
        # Required since we do not have control over the QuerySet in that method.
        parent_link=True,
    )

    review_status = models.ForeignKey(
        to="product_portfolio.ProductRelationStatus",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text=_(
            "The status of the Component or Package in the Product review and approval "
            "cycle, if known. Use a review_status that has been defined by your system "
            "administrator."
        ),
    )

    purpose = models.ForeignKey(
        to="product_portfolio.ProductItemPurpose",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    feature = models.CharField(
        blank=True,
        max_length=70,
        help_text=_("Use this field to group components that are used together in a product."),
    )

    issue_ref = models.CharField(
        blank=True,
        max_length=40,
        help_text=_(
            "Reference (an ID or short title) for an Issue with a Product Inventory Item "
            "that needs to be addressed. Details of the issue and the actions taken may be "
            "recorded in another system."
        ),
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        is_addition = not self.pk
        if is_addition:
            self.set_review_status_from_policy()
        super().save(*args, **kwargs)

    def set_review_status_from_policy(self):
        """
        Apply the status from the policy if the review_status was not provided,
        or if the provided one is the default.
        """
        if not self.review_status or self.review_status.default_on_addition:
            if status_from_policy := self.get_status_from_item_policy():
                self.review_status = status_from_policy

    def get_status_from_item_policy(self):
        """
        Return the `associated_product_relation_status` from the related item
        (component or package) usage policy.
        """
        if related_item := self.related_component_or_package:
            if usage_policy := related_item.usage_policy:
                if status := usage_policy.associated_product_relation_status:
                    return status

    def as_spdx(self):
        """
        Set the `license_concluded` using the license choice of the relationship,
        while the component/package license is set in the `license_declared`.
        """
        return self.related_component_or_package.as_spdx(
            license_concluded=self.concluded_license_expression_spdx,
        )

    def as_cyclonedx(self):
        return self.related_component_or_package.as_cyclonedx(
            license_expression_spdx=self.concluded_license_expression_spdx,
        )

    @cached_property
    def inventory_item_compliance_alert(self):
        """
        Return the list of all existing `compliance_alert` through this related
        inventory item `usage_policy.compliance_alert`.
        """
        if inventory_item := self.related_component_or_package:
            if inventory_item.usage_policy:
                if compliance_alert := inventory_item.usage_policy.compliance_alert:
                    return compliance_alert.lower()

    def compliance_table_class(self):
        """
        Override the LicenseExpressionMixin default logic to return the CSS class
        for a table row based on the related inventory item
        ``usage_policy.compliance_alert`` in place of the ``compliance_alerts`` from
        licenses.
        """
        compliance_alert = self.inventory_item_compliance_alert
        if compliance_alert == "error":
            return "table-danger"
        elif compliance_alert == "warning":
            return "table-warning"


class ProductComponent(ProductRelationshipMixin):
    component = models.ForeignKey(
        to="component_catalog.Component",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="productcomponents",
    )

    # This should be on the ProductRelationshipMixin but for some reason
    # it makes test_productcomponent_import_license_expression fail
    # This license_expression is never generated but always stored.
    license_expression = models.CharField(
        _("Concluded license expression"),
        max_length=1024,
        blank=True,
        db_index=True,
        help_text=RELATION_LICENSE_EXPRESSION_HELP_TEXT,
    )

    licenses = models.ManyToManyField(
        to="license_library.License",
        through="ProductComponentAssignedLicense",
    )

    # The following optional fields are are placeholders until the ProductComponent is validated.
    # When validated, the values of the Component FK are used instead.

    name = models.CharField(
        blank=True,
        max_length=70,
        validators=[validate_url_segment],
        help_text=_(
            "A descriptive name for the Component (Component name). If you identified a "
            'DejaCode Component in the "component" field, this is not necessary; '
            "otherwise, you should provide the name used by the authors of the "
            "component."
        ),
    )

    version = models.CharField(
        blank=True,
        max_length=50,
        validators=[validate_version],
        help_text=_(
            "The version of the Component (Component version). If you identified a "
            'DejaCode Component in the "component" field, this is not necessary; '
            "otherwise, you should provide the version used by the authors of the "
            "Component."
        ),
    )

    owner = models.CharField(
        blank=True,
        max_length=70,
        help_text=_(
            "The creator, author, or source name of the Component. If you identified a "
            'DejaCode component in the "component" field, this is not necessary; '
            "otherwise, you should provide the name of the owner as provided by that "
            "owner in the Component documentation."
        ),
    )

    copyright = models.TextField(
        blank=True,
        help_text=_(
            "The copyright statement for this Component. If you identified a DejaCode "
            'Component in the "component" field, this is not necessary.'
        ),
    )

    homepage_url = models.URLField(
        _("Homepage URL"),
        blank=True,
        max_length=1024,
        help_text=_(
            "URL to the source of the Component Package. If you identified a DejaCode "
            'Component in the "component" field, this is not necessary.'
        ),
    )

    download_url = models.CharField(
        _("Download URL"),
        blank=True,
        max_length=1024,
        validators=[generic_uri_validator],
        help_text=_(
            "URL to the source of the Component Package. Once validated this should point to a "
            'Package. If you identified a DejaCode Component in the "component" field, and if it '
            "already has a Package defined with the download_url, then this is not necessary."
        ),
    )

    primary_language = models.CharField(
        db_index=True,
        max_length=50,
        blank=True,
        help_text=_("The primary programming language associated with the component."),
    )

    objects = DataspacedManager.from_queryset(ProductComponentQuerySet)()

    class Meta:
        verbose_name = _("product component relationship")
        unique_together = (("product", "component"), ("dataspace", "uuid"))
        ordering = ["product", "component"]
        permissions = (
            (
                "change_review_status_on_productcomponent",
                "Can change the review_status of product component relationship",
            ),
        )

    def __str__(self):
        if self.component:
            return str(self.component)
        if self.name or self.version:
            return f"{self.name} {self.version}"
        return "(Component data missing)"  # a value is required for the changelist link

    @property
    def permission_protected_fields(self):
        return {"review_status": "change_review_status_on_productcomponent"}

    @property
    def is_custom_component(self):
        return not self.component_id

    @property
    def has_custom_values(self):
        custom_fields = [
            "name",
            "value",
            "owner",
            "copyright",
            "homepage_url",
            "download_url",
            "primary_language",
        ]
        return any(getattr(self, field, None) for field in custom_fields)


class ProductPackage(ProductRelationshipMixin):
    package = models.ForeignKey(
        to="component_catalog.Package",
        on_delete=models.PROTECT,
        related_name="productpackages",
    )

    # This should be on the ComponentRelationshipMixin but for some reason
    # it makes test_productcomponent_import_license_expression fail
    # This license_expression is never generated but always stored.
    license_expression = models.CharField(
        _("Concluded license expression"),
        max_length=1024,
        blank=True,
        db_index=True,
        help_text=RELATION_LICENSE_EXPRESSION_HELP_TEXT,
    )

    licenses = models.ManyToManyField(
        to="license_library.License",
        through="ProductPackageAssignedLicense",
    )

    objects = DataspacedManager.from_queryset(ProductSecuredQuerySet)()

    class Meta:
        verbose_name = _("product package relationship")
        unique_together = (("product", "package"), ("dataspace", "uuid"))
        ordering = ["product", "package"]
        permissions = (
            (
                "change_review_status_on_productpackage",
                "Can change the review_status of product package relationship",
            ),
        )

    def __str__(self):
        return str(self.package)

    @property
    def permission_protected_fields(self):
        return {"review_status": "change_review_status_on_productpackage"}


class ProductAssignedLicense(DataspacedModel):
    product = models.ForeignKey(
        to="product_portfolio.Product",
        on_delete=models.CASCADE,
    )

    license = models.ForeignKey(
        to="license_library.License",
        on_delete=models.PROTECT,
    )

    class Meta:
        unique_together = (("product", "license"), ("dataspace", "uuid"))
        ordering = ("product__name", "license__name")
        verbose_name = _("product assigned license")

    def __str__(self):
        return f"{self.product} is under {self.license}."


class ProductComponentAssignedLicense(DataspacedModel):
    productcomponent = models.ForeignKey(
        to="product_portfolio.ProductComponent",
        on_delete=models.CASCADE,
    )

    license = models.ForeignKey(
        to="license_library.License",
        on_delete=models.PROTECT,
    )

    class Meta:
        unique_together = (("productcomponent", "license"), ("dataspace", "uuid"))
        ordering = ("productcomponent__name", "license__name")
        verbose_name = _("productcomponent assigned license")

    def __str__(self):
        return f"{self.productcomponent} is under {self.license}."


class ProductPackageAssignedLicense(DataspacedModel):
    productpackage = models.ForeignKey(
        to="product_portfolio.ProductPackage",
        on_delete=models.CASCADE,
    )

    license = models.ForeignKey(
        to="license_library.License",
        on_delete=models.PROTECT,
    )

    class Meta:
        unique_together = (("productpackage", "license"), ("dataspace", "uuid"))
        ordering = ("productpackage", "license__name")
        verbose_name = _("productpackage assigned license")

    def __str__(self):
        return f"{self.productpackage} is under {self.license}."


class CodebaseResourceQuerySet(ProductSecuredQuerySet):
    def default_select_prefetch(self):
        return self.select_related(
            "product_component__component__dataspace",
            "product_package__package__dataspace",
        ).prefetch_related(
            "related_deployed_from__deployed_from",
            "related_deployed_to__deployed_to",
        )


class CodebaseResource(
    HistoryFieldsMixin,
    DataspacedModel,
):
    product = models.ForeignKey(
        to="product_portfolio.Product",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        # Bypass the validation in ForeignKey.validate()
        # Required since we do not have control over the QuerySet in that method.
        parent_link=True,
    )

    path = models.CharField(
        max_length=2000,
        help_text=_(
            "The full path value of a codebase resource (file or directory) in either the "
            "development or deployment codebase of a product."
        ),
    )

    is_deployment_path = models.BooleanField(
        default=False,
        help_text=_(
            "When set to Yes, indicates that this codebase resource identifies a path in the "
            "Deployment codebase. When set to No (the default value), indicates that this "
            "codebase resource identifies a path in the Development codebase."
        ),
    )

    product_component = models.ForeignKey(
        to="product_portfolio.ProductComponent",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)ss",
    )

    product_package = models.ForeignKey(
        to="product_portfolio.ProductPackage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)ss",
    )

    additional_details = models.JSONField(
        blank=True,
        default=dict,
        help_text=_(
            "An optional JSON-formatted field to identify additional codebase resource attributes "
            "such as name, type, sha1, size, etc."
        ),
    )

    admin_notes = models.TextField(
        blank=True,
        help_text=_(
            "Comments about the product codebase resource, provided by administrators, "
            "intended for viewing and maintenance by administrators only.",
        ),
    )

    deployed_to = models.ManyToManyField(
        to="product_portfolio.CodebaseResource",
        through="product_portfolio.CodebaseResourceUsage",
    )

    objects = DataspacedManager.from_queryset(CodebaseResourceQuerySet)()

    class Meta:
        verbose_name = _("codebase resource")
        unique_together = (
            ("product", "path"),
            ("dataspace", "uuid"),
        )
        ordering = ("product", "path")

    def __str__(self):
        return self.path

    def clean(self, from_api=False):
        if self.product_component_id and self.product_component.product_id != self.product_id:
            raise ValidationError(f"{self.product_component} is not available on {self.product}.")

        if self.product_package_id and self.product_package.product_id != self.product_id:
            raise ValidationError(f"{self.product_package} is not available on {self.product}.")

        super().clean(from_api)

    @property
    def deployed_from_paths(self):
        return [resource.deployed_from.path for resource in self.related_deployed_from.all()]

    @property
    def deployed_to_paths(self):
        return [resource.deployed_to.path for resource in self.related_deployed_to.all()]


class CodebaseResourceUsage(
    HistoryFieldsMixin,
    DataspacedModel,
):
    deployed_from = models.ForeignKey(
        to="product_portfolio.CodebaseResource",
        on_delete=models.CASCADE,
        related_name="related_deployed_to",
    )

    deployed_to = models.ForeignKey(
        to="product_portfolio.CodebaseResource",
        on_delete=models.PROTECT,
        related_name="related_deployed_from",
    )

    class Meta:
        verbose_name = _("codebase resource usage")
        unique_together = (
            ("deployed_from", "deployed_to"),
            ("dataspace", "uuid"),
        )
        ordering = ("deployed_from", "deployed_to")

    def __str__(self):
        return f"{self.deployed_from} -> {self.deployed_to}"

    def clean(self, from_api=False):
        if self.deployed_from_id == self.deployed_to_id:
            raise ValidationError("A codebase resource cannot deploy to itself.")


class ProductInventoryItem(ProductRelationshipMixin):
    """
    Product inventory database view.

    This model is not managed by the Django migration system.
    It allows to interact with the underlying
    `product_portfolio_productinventoryitem` database view.
    It is mostly used by the reporting system.

    All the `ForeignKey` field need to be overridden with the
    `on_delete=models.DO_NOTHING` to prevent any OperationalError on related
    objects deletion.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        primary_key=True,
    )

    product = models.ForeignKey(
        to="product_portfolio.Product",
        on_delete=models.DO_NOTHING,
    )

    component = models.ForeignKey(
        to="component_catalog.Component",
        null=True,
        on_delete=models.DO_NOTHING,
    )

    package = models.ForeignKey(
        to="component_catalog.Package",
        null=True,
        on_delete=models.DO_NOTHING,
    )

    review_status = models.ForeignKey(
        to="product_portfolio.ProductRelationStatus",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
    )

    purpose = models.ForeignKey(
        to="product_portfolio.ProductItemPurpose",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
    )

    usage_policy = models.ForeignKey(
        to="policy.UsagePolicy",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
    )

    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.DO_NOTHING,
    )

    last_modified_by = LastModifiedByField(
        on_delete=models.DO_NOTHING,
    )

    license_expression = models.CharField(
        _("Concluded license expression"),
        max_length=1024,
        blank=True,
    )

    item = models.CharField(
        blank=True,
        max_length=1024,
    )

    item_type = models.CharField(
        blank=True,
        max_length=20,
        choices=(
            ("component", "component"),
            ("package", "package"),
        ),
    )

    class Meta:
        managed = False
        db_table = "product_portfolio_productinventoryitem"

    # Forced to None since licenses FK are not available on this view
    licensing = None

    # The SQL to create the view, requires to be manually updated on model changes.
    raw_sql = """
    DROP VIEW IF EXISTS product_portfolio_productinventoryitem;
    CREATE VIEW product_portfolio_productinventoryitem
    AS
       SELECT pc.uuid, pc.component_id, NULL as package_id,
           CONCAT(component.name, ' ', component.version) as item,  'component' as item_type,
           pc.dataspace_id, pc.product_id,  pc.review_status_id, pc.feature,
           component.usage_policy_id, pc.created_date, pc.last_modified_date,
           pc.reference_notes, pc.purpose_id, pc.notes, pc.is_deployed, pc.is_modified,
           pc.extra_attribution_text, pc.package_paths, pc.issue_ref, pc.license_expression,
           pc.created_by_id, pc.last_modified_by_id
       FROM product_portfolio_productcomponent AS pc
       INNER JOIN component_catalog_component AS component ON pc.component_id=component.id
       UNION ALL
       SELECT pp.uuid, NULL as component_id, pp.package_id, package.filename as item,
           'package' as item_type, pp.dataspace_id, pp.product_id, pp.review_status_id,
           pp.feature, package.usage_policy_id, pp.created_date, pp.last_modified_date,
           pp.reference_notes, pp.purpose_id, pp.notes, pp.is_deployed, pp.is_modified,
           pp.extra_attribution_text, pp.package_paths, pp.issue_ref, pp.license_expression,
           pp.created_by_id, pp.last_modified_by_id
       FROM product_portfolio_productpackage AS pp
       INNER JOIN component_catalog_package AS package ON pp.package_id=package.id
    ;
    """


def generate_input_file_path(instance, filename):
    dataspace = instance.dataspace
    return f"{dataspace}/scancode_project/{instance.uuid}/{filename}"


class ScanCodeProjectQuerySet(ProductSecuredQuerySet):
    def in_progress(self):
        in_progress_statuses = [
            ScanCodeProject.Status.SUBMITTED,
            ScanCodeProject.Status.IMPORT_STARTED,
        ]
        return self.filter(status__in=in_progress_statuses)


class ScanCodeProject(HistoryFieldsMixin, DataspacedModel):
    """Wrap a ScanCode.io Project."""

    class ProjectType(models.TextChoices):
        IMPORT_FROM_MANIFEST = "IMPORT_FROM_MANIFEST", _("Import from Manifest")
        LOAD_SBOMS = "LOAD_SBOMS", _("Load SBOMs")
        PULL_FROM_SCANCODEIO = "PULL_FROM_SCANCODEIO", _("Pull from ScanCode.io")
        IMPROVE_FROM_PURLDB = "IMPROVE_FROM_PURLDB", _("Improve from PurlDB")

    class Status(models.TextChoices):
        SUBMITTED = "submitted"
        IMPORT_STARTED = "importing"
        SUCCESS = "success", _("Completed")
        FAILURE = "failure"

    uuid = models.UUIDField(
        _("UUID"),
        default=uuid.uuid4,
        editable=False,
        unique=True,  # Copy of this model is not allowed
    )
    product = models.ForeignKey(
        to="product_portfolio.Product",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
    )
    type = models.CharField(
        max_length=50,
        choices=ProjectType.choices,
        db_index=True,
        help_text="The type of import, for the ProjectType choices.",
    )
    project_uuid = models.UUIDField(
        _("Project UUID"),
        null=True,
        editable=False,
        help_text="UUID of the ScanCode.io project instance.",
    )
    input_file = models.FileField(
        upload_to=generate_input_file_path,
        max_length=350,
    )
    update_existing_packages = models.BooleanField(
        default=False,
    )
    scan_all_packages = models.BooleanField(
        default=False,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        db_index=True,
    )
    import_log = models.JSONField(
        blank=True,
        default=list,
        editable=False,
    )
    results = models.JSONField(
        blank=True,
        default=dict,
    )

    objects = DataspacedManager.from_queryset(ScanCodeProjectQuerySet)()

    class Meta:
        unique_together = ("dataspace", "uuid")
        ordering = ["-created_date"]

    def __str__(self):
        return f"ScanCodeProject uuid={self.uuid} project_uuid={self.project_uuid}."

    def append_to_log(self, message, save=False):
        """Append the `message` string to the `log` field of this instance."""
        message = message.strip()
        self.import_log.append(message)
        if save:
            self.save()

    @property
    def input_file_filename(self):
        if self.input_file:
            return Path(self.input_file.path).name

    @property
    def has_errors(self):
        return len(self.results.get("errors", []))

    @property
    def can_start_import(self):
        """Return True if the import has not completed and is not in progress."""
        blocking_statuses = [
            ScanCodeProject.Status.IMPORT_STARTED,
            ScanCodeProject.Status.SUCCESS,
            ScanCodeProject.Status.FAILURE,
        ]
        return self.status not in blocking_statuses

    def import_data_from_scancodeio(self):
        """Wrap to trigger the data import from ScanCode.io of the related Project."""
        from product_portfolio.importers import ImportPackageFromScanCodeIO

        importer = ImportPackageFromScanCodeIO(
            user=self.created_by,
            project_uuid=self.project_uuid,
            product=self.product,
            update_existing=self.update_existing_packages,
            scan_all_packages=self.scan_all_packages,
        )
        created, existing, errors = importer.save()

        self.results = {
            "created": created,
            "existing": existing,
            "errors": errors,
        }
        self.save()

        return created, existing, errors

    def notify(self, verb, description):
        """Send a notification about this instance."""
        notify.send(
            sender=self.created_by,
            verb=verb,
            action_object=self.product,
            recipient=self.created_by,
            description=description,
        )


class ProductDependency(HistoryFieldsMixin, DataspacedModel):
    product = models.ForeignKey(
        to="product_portfolio.Product",
        related_name="dependencies",
        on_delete=models.CASCADE,
    )
    dependency_uid = models.CharField(
        max_length=1024,
        help_text=_("The unique identifier of this dependency."),
    )
    for_package = models.ForeignKey(
        to="component_catalog.Package",
        related_name="declared_dependencies",
        help_text=_("The package that declares this dependency."),
        on_delete=models.CASCADE,
        editable=False,
        blank=True,
        null=True,
    )
    resolved_to_package = models.ForeignKey(
        to="component_catalog.Package",
        related_name="resolved_from_dependencies",
        help_text=_(
            "The resolved package for this dependency. "
            "If empty, it indicates the dependency is unresolved."
        ),
        on_delete=models.SET_NULL,
        editable=False,
        blank=True,
        null=True,
    )
    declared_dependency = models.CharField(
        max_length=1024,
        blank=True,
        help_text=_(
            "A dependency as stated in a project manifest or lockfile, which may be "
            "required or optional, and may be associated with specific version ranges."
        ),
    )
    extracted_requirement = models.CharField(
        max_length=256,
        blank=True,
        help_text=_("The version requirements of this dependency."),
    )
    scope = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("The scope of this dependency, how it is used in a project."),
    )
    datasource_id = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("The identifier for the datafile handler used to obtain this dependency."),
    )
    is_runtime = models.BooleanField(
        default=False,
        help_text=_("True if this dependency is a runtime dependency."),
    )
    is_optional = models.BooleanField(
        default=False,
        help_text=_("True if this dependency is an optional dependency"),
    )
    is_resolved = models.BooleanField(
        default=False,
        help_text=_(
            "True if this dependency version requirement has been pinned "
            "and this dependency points to an exact version."
        ),
    )
    is_direct = models.BooleanField(
        default=False,
        help_text=_("True if this is a direct, first-level dependency relationship for a package."),
    )

    objects = DataspacedManager.from_queryset(ProductSecuredQuerySet)()

    class Meta:
        unique_together = (("product", "dependency_uid"), ("dataspace", "uuid"))
        verbose_name = "product dependency"
        verbose_name_plural = "product dependencies"
        ordering = ["dependency_uid"]
        indexes = [
            models.Index(fields=["scope"]),
            models.Index(fields=["is_runtime"]),
            models.Index(fields=["is_optional"]),
            models.Index(fields=["is_resolved"]),
            models.Index(fields=["is_direct"]),
        ]

    def __str__(self):
        return self.dependency_uid

    def save(self, *args, **kwargs):
        """Make sure a Package dependency cannot resolve to itself."""
        if self.for_package and self.resolved_to_package:
            if self.for_package == self.resolved_to_package:
                raise ValidationError(
                    "The 'for_package' cannot be the same as 'resolved_to_package'."
                )
        super().save(*args, **kwargs)
