#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.contrib import messages
from django.contrib.admin.widgets import AdminURLFieldWidget
from django.db import transaction
from django.forms import modelform_factory
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.functional import cached_property

import packageurl
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML
from crispy_forms.layout import Field
from crispy_forms.layout import Fieldset
from crispy_forms.layout import Layout
from crispy_forms.layout import Submit

from component_catalog.license_expression_dje import LicenseExpressionFormMixin
from component_catalog.models import PACKAGE_URL_FIELDS
from component_catalog.models import AcceptableLinkage
from component_catalog.models import Component
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import ComponentKeyword
from component_catalog.models import Package
from component_catalog.models import Subcomponent
from component_catalog.programming_languages import PROGRAMMING_LANGUAGES
from component_catalog.widgets import UsagePolicyWidgetWrapper
from dejacode_toolkit.scancodeio import ScanCodeIO
from dje import tasks
from dje.forms import DataspacedAdminForm
from dje.forms import DataspacedModelForm
from dje.forms import DefaultOnAdditionLabelMixin
from dje.forms import Group
from dje.forms import JSONListField
from dje.forms import OwnerChoiceField
from dje.forms import autocomplete_placeholder
from dje.mass_update import DejacodeMassUpdateForm
from dje.models import History
from dje.widgets import AdminAwesompleteInputWidget
from dje.widgets import AutocompleteInput
from dje.widgets import AwesompleteInputWidget
from dje.widgets import DatePicker
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductPackage


class SetKeywordsChoicesFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if keywords_field := self.fields.get("keywords"):
            keywords_qs = ComponentKeyword.objects.scope(self.dataspace)
            labels = keywords_qs.values_list("label", flat=True)
            keywords_field.widget.attrs.update({"data-list": ", ".join(labels)})


class KeywordsField(JSONListField):
    def __init__(self, **kwargs):
        widget = AutocompleteInput(
            attrs={
                "data-api_url": reverse_lazy("api_v2:componentkeyword-list"),
            },
            display_link=False,
            display_attribute="label",
        )
        kwargs.setdefault("widget", widget)
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)


class ComponentForm(
    LicenseExpressionFormMixin,
    DefaultOnAdditionLabelMixin,
    DataspacedModelForm,
):
    default_on_addition_fields = ["configuration_status"]
    save_as = True
    clone_m2m_classes = [
        ComponentAssignedPackage,
        Subcomponent,
    ]
    color_initial = True

    keywords = KeywordsField()

    packages_ids = forms.CharField(
        widget=forms.HiddenInput,
        required=False,
    )

    class Meta:
        model = Component
        fields = [
            "name",
            "version",
            "owner",
            "copyright",
            "holder",
            "notice_text",
            "license_expression",
            "release_date",
            "description",
            "homepage_url",
            "bug_tracking_url",
            "code_view_url",
            "vcs_url",
            "primary_language",
            "cpe",
            "configuration_status",
            "keywords",
            "notice_text",
            "is_license_notice",
            "is_copyright_notice",
            "is_notice_in_codebase",
            "notice_filename",
            "notice_url",
            "dependencies",
            "usage_policy",
            "packages_ids",
        ]
        field_classes = {
            "owner": OwnerChoiceField,
        }
        widgets = {
            "copyright": forms.Textarea(attrs={"rows": 2}),
            "notice_text": forms.Textarea(attrs={"rows": 2}),
            "description": forms.Textarea(attrs={"rows": 2}),
            "holder": forms.Textarea(attrs={"rows": 2}),
            "owner": AutocompleteInput(
                attrs={
                    "data-api_url": reverse_lazy("api_v2:owner-list"),
                },
                display_link=False,
                display_attribute="name",
            ),
            "release_date": DatePicker,
            "primary_language": AwesompleteInputWidget(
                attrs=autocomplete_placeholder,
                data_list=",".join(PROGRAMMING_LANGUAGES),
            ),
            "dependencies": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_packages_ids(self):
        packages_ids = self.cleaned_data.get("packages_ids")
        if packages_ids:
            packages_ids = packages_ids.split(",")
            for package_id in packages_ids:
                try:
                    int(package_id)
                except ValueError:
                    raise forms.ValidationError(f"Wrong value type for {package_id}")
        return packages_ids

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)

        packages_ids = self.cleaned_data.get("packages_ids")
        if packages_ids:
            packages = Package.objects.scope(self.user.dataspace).filter(id__in=packages_ids)
            for package in packages:
                ComponentAssignedPackage.objects.create(
                    component=instance,
                    package=package,
                    dataspace=instance.dataspace,
                )

        # Update the completion_level once everything including m2m were saved
        instance.update_completion_level()

        return instance

    @property
    def helper(self):
        helper = super().helper

        helper.layout = Layout(
            Fieldset(
                None,
                Group("name", "version", "owner"),
                HTML("<hr>"),
                "license_expression",
                Group("copyright", "holder"),
                "notice_text",
                Group("notice_filename", "notice_url"),
                Group("is_license_notice", "is_copyright_notice", "is_notice_in_codebase"),
                HTML("<hr>"),
                Group("description", "keywords"),
                Group("primary_language", "cpe"),
                Group("dependencies", "release_date"),
                HTML("<hr>"),
                Group("homepage_url", "code_view_url"),
                Group("bug_tracking_url", "vcs_url"),
                HTML("<hr>"),
                Group("usage_policy", "configuration_status"),
                HTML("<hr>"),
                "packages_ids",
                Submit("submit", self.submit_label, css_class="btn-success"),
                self.save_as_new_submit,
            ),
        )

        return helper


BaseComponentAjaxForm = modelform_factory(
    Component,
    form=ComponentForm,
    fields=[
        "name",
        "version",
        "owner",
        "license_expression",
        "homepage_url",
        "description",
    ],
)


class ComponentAjaxForm(BaseComponentAjaxForm):
    @property
    def helper(self):
        helper = super().helper
        helper.form_tag = False

        helper.layout = Layout(
            Fieldset(
                None,
                Group("name", "version", "owner"),
                "license_expression",
                Group("description", "homepage_url"),
            ),
        )

        return helper


class PackageFieldsValidationMixin:
    """Enforce the Filename or Package URL requirement."""

    def clean(self):
        cleaned_data = super().clean()

        purl_values = [cleaned_data.get(field_name) for field_name in PACKAGE_URL_FIELDS]

        if any(purl_values):
            try:
                packageurl.PackageURL(*purl_values)
            except ValueError as e:
                raise forms.ValidationError(e)
        elif not cleaned_data.get("filename"):
            raise forms.ValidationError("A Filename or a Package URL (type + name) is required.")

        return cleaned_data


class PackageForm(
    LicenseExpressionFormMixin,
    PackageFieldsValidationMixin,
    DataspacedModelForm,
):
    save_as = True
    color_initial = True

    keywords = KeywordsField()

    collect_data = forms.BooleanField(
        required=False,
        initial=True,
        label=(
            "Automatically collect the SHA1, MD5, and Size using the "
            "Download URL and apply them to the package definition."
        ),
    )

    class Meta:
        model = Package
        fields = [
            "filename",
            "download_url",
            "md5",
            "sha1",
            "sha256",
            "sha512",
            "size",
            "release_date",
            "primary_language",
            "cpe",
            "description",
            "keywords",
            "notes",
            "usage_policy",
            "license_expression",
            "copyright",
            "holder",
            "author",
            "homepage_url",
            "vcs_url",
            "code_view_url",
            "bug_tracking_url",
            "repository_homepage_url",
            "repository_download_url",
            "api_data_url",
            "notice_text",
            "dependencies",
            "type",
            "namespace",
            "name",
            "version",
            "qualifiers",
            "subpath",
            "collect_data",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "copyright": forms.Textarea(attrs={"rows": 2}),
            "notice_text": forms.Textarea(attrs={"rows": 2}),
            "holder": forms.Textarea(attrs={"rows": 1}),
            "author": forms.Textarea(attrs={"rows": 1}),
            "dependencies": forms.Textarea(attrs={"rows": 2}),
            "release_date": DatePicker,
            "primary_language": AwesompleteInputWidget(
                attrs=autocomplete_placeholder,
                data_list=",".join(PROGRAMMING_LANGUAGES),
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        scancodeio = ScanCodeIO(self.user)
        self.submit_scan_enabled = all(
            [
                self.is_addition,
                scancodeio.is_configured(),
                self.dataspace.enable_package_scanning,
            ]
        )

    @property
    def helper(self):
        helper = super().helper

        scancode_notice = None
        if self.submit_scan_enabled:
            scancode_notice = HTML(
                '<div class="text-muted mb-3">'
                "<strong>Package scanning is enabled in your Dataspace</strong>, "
                "DejaCode will also submit the package to ScanCode.io and the "
                'results will be returned to the "Scan" detail tab of the package '
                "when that scan is complete."
                "</div>"
            )

        package_url = HTML(
            '<div class="row m-0 ps-1 mb-3">'
            '   Package URL:<code class="ms-2" id="id_package_url"></code>'
            "</div>"
        )

        helper.layout = Layout(
            Fieldset(
                None,
                Group("filename", "download_url"),
                HTML("<hr>"),
                package_url,
                Group("type", "namespace", "name"),
                Group("version", "qualifiers", "subpath"),
                HTML("<hr>"),
                "license_expression",
                Group("copyright", "notice_text"),
                Group("holder", "author"),
                HTML("<hr>"),
                Group("description", "keywords"),
                Group("primary_language", "cpe"),
                Group("size", "release_date"),
                Group("dependencies", "notes"),
                HTML("<hr>"),
                Group("homepage_url", "code_view_url"),
                Group("bug_tracking_url", "vcs_url"),
                HTML("<hr>"),
                Group("md5", "sha1"),
                Group("sha256", "sha512"),
                HTML("<hr>"),
                Group("usage_policy", None),
                HTML("<hr>"),
                Field("collect_data", wrapper_class="text-muted"),
                scancode_notice,
                Submit("submit", self.submit_label, css_class="btn-success"),
                self.save_as_new_submit,
            ),
        )

        return helper

    def save(self, *args, **kwargs):
        """
        Add data collection and ScanCode.io scanning if enabled and available.
        Set `data_collected` and `scan_submitted` in the `cleaned_data` to be
        used for crafting the proper message in `get_success_message`.
        """
        instance = super().save(*args, **kwargs)

        download_url = self.cleaned_data.get("download_url")
        collect_data = self.cleaned_data.get("collect_data")

        if collect_data and download_url:
            transaction.on_commit(lambda: tasks.package_collect_data.delay(instance.id))
            self.cleaned_data["data_collected"] = True

        if self.submit_scan_enabled and download_url:
            tasks.scancodeio_submit_scan.delay(
                uris=download_url,
                user_uuid=self.user.uuid,
                dataspace_uuid=self.user.dataspace.uuid,
            )
            self.cleaned_data["scan_submitted"] = True

        return instance


class BaseScanToPackageForm(LicenseExpressionFormMixin, DataspacedModelForm):
    @property
    def helper(self):
        helper = FormHelper()
        helper.form_method = "post"
        helper.form_id = f"{self.prefix}-form"
        helper.form_tag = False
        return helper


class ScanToPackageForm(BaseScanToPackageForm):
    prefix = "scan-to-package"

    package_url = forms.CharField(
        label="Package URL",
        required=False,
    )

    class Meta:
        model = Package
        fields = [
            "package_url",
            "license_expression",
            "copyright",
            "primary_language",
            "description",
            "homepage_url",
            "release_date",
            "notice_text",
            "dependencies",
        ]
        widgets = {
            "copyright": forms.Textarea(attrs={"rows": 2}),
            "description": forms.Textarea(attrs={"rows": 2}),
            "notice_text": forms.Textarea(attrs={"rows": 2}),
            "dependencies": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Store the original value from the instance for usage in changed_data()
        self.original_package_url = self.instance.package_url

        # Do not include the package_url field if a value is already set on the instance
        if self.instance.package_url:
            del self.fields["package_url"]

        if not kwargs.get("data"):
            self.fields = self.fields_with_initial_value()

    def fields_with_initial_value(self):
        kept_fields = {}

        for field_name, field in self.fields.items():
            if not self.initial.get(field_name):
                continue

            instance_value = getattr(self.instance, field_name, None)
            help_text = "No current value"
            if instance_value:
                help_text = f"Current value: {instance_value}"
            field.help_text = help_text

            kept_fields[field_name] = field

        return kept_fields

    def clean_package_url(self):
        package_url = self.cleaned_data.get("package_url")
        if package_url:
            self.instance.set_package_url(package_url)
        return package_url

    @cached_property
    def changed_data(self):
        """
        Workaround to make sure the `package_url` was really changed
        since it's not a bound field on the ModelForm.
        """
        changed_data = super().changed_data

        if "package_url" in changed_data:
            if self.instance.package_url == self.original_package_url:
                changed_data.remove("package_url")

        return changed_data


class ScanSummaryToPackageForm(BaseScanToPackageForm):
    prefix = "scan-summary-to-package"

    class Meta:
        model = Package
        fields = [
            "license_expression",
            "primary_language",
            "holder",
        ]
        widgets = {
            "holder": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not kwargs.get("data"):
            self.set_help_text_with_initial_value()

    def set_help_text_with_initial_value(self):
        for field_name, field in self.fields.items():
            instance_value = getattr(self.instance, field_name, None)
            help_text = "No current value"
            if instance_value:
                help_text = f"Current value: {instance_value}"
            field.help_text = help_text


class BaseAddToProductForm(
    LicenseExpressionFormMixin, DefaultOnAdditionLabelMixin, DataspacedModelForm
):
    relation_fk_field = None
    default_on_addition_fields = ["review_status", "purpose"]

    class Meta:
        fields = [
            "product",
            "license_expression",
            "review_status",
            "purpose",
            "notes",
            "is_deployed",
            "is_modified",
            "extra_attribution_text",
            "feature",
            "issue_ref",
        ]
        widgets = {
            "package": forms.widgets.HiddenInput,
            "component": forms.widgets.HiddenInput,
            "notes": forms.Textarea(attrs={"rows": 2}),
            "extra_attribution_text": forms.Textarea(attrs={"rows": 2}),
            "copyright": forms.Textarea(attrs={"rows": 2}),
            "reference_notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, user, *args, **kwargs):
        relation_instance = kwargs.pop(self.relation_fk_field, None)

        super().__init__(user, *args, **kwargs)

        product_field = self.fields["product"]
        perms = ["view_product", "change_product"]
        product_field.queryset = Product.objects.get_queryset(user, perms=perms)

        if relation_instance:
            help_text = f'"{relation_instance}" will be assigned to the selected product.'
            product_field.help_text = help_text

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_method = "post"
        helper.form_id = "add-to-product-form"
        helper.form_tag = False
        helper.modal_title = "Add to Product"
        helper.modal_id = "add-to-product-modal"
        return helper

    def save(self, *args, **kwargs):
        """
        Log a change in the Product History for Product relationship addition
        and edition.
        """
        instance = super().save(*args, **kwargs)
        product = instance.product

        if getattr(instance, "is_custom_component", False):
            relation_model_name = "custom component"
        else:
            relation_model_name = self.relation_fk_field

        if self.is_addition:
            message = f'Added {relation_model_name} "{self.instance}"'
        else:
            fields = ", ".join(self.changed_data)
            message = f'Changed {relation_model_name} "{self.instance}" {fields}'

        History.log_change(self.user, product, message)
        product.last_modified_by = self.user
        product.save()

        return instance


class PackageAddToProductForm(BaseAddToProductForm):
    relation_fk_field = "package"

    class Meta(BaseAddToProductForm.Meta):
        model = ProductPackage
        fields = ["package"] + BaseAddToProductForm.Meta.fields


class ComponentAddToProductForm(BaseAddToProductForm):
    relation_fk_field = "component"

    class Meta(BaseAddToProductForm.Meta):
        model = ProductComponent
        fields = ["component"] + BaseAddToProductForm.Meta.fields


class AddToProductAdminForm(forms.Form):
    use_required_attribute = False
    product = forms.ModelChoiceField(
        required=True,
        queryset=Product.objects.none(),
    )
    ids = forms.CharField(widget=forms.widgets.HiddenInput)
    replace_existing_version = forms.BooleanField(
        required=False,
        initial=False,
        label="Replace existing relationships by newer version.",
        help_text=(
            "Select this option to replace any existing relationships with a different version "
            "of the same object. "
            "If more than one version of the object is already assigned, no replacements will be "
            "made, and the new version will be added instead."
        ),
    )

    def __init__(self, request, model, relation_model, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.model = model
        self.relation_model = relation_model
        self.dataspace = request.user.dataspace
        self.fields["product"].queryset = Product.objects.get_queryset(
            request.user, perms=["view_product", "change_product"]
        )

    def get_selected_objects(self):
        ids = self.initial.get("ids") or self.cleaned_data["ids"]
        return self.model.objects.scope(self.dataspace).filter(pk__in=ids.split(","))

    def save(self):
        product = self.cleaned_data["product"]

        return product.assign_objects(
            related_objects=self.get_selected_objects(),
            user=self.request.user,
            replace_version=self.cleaned_data["replace_existing_version"],
        )


class AddToProductMultipleForm(AddToProductAdminForm):
    use_required_attribute = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        verbose_name_plural = self.model._meta.verbose_name_plural
        self.fields["product"].help_text = (
            f"The {verbose_name_plural} that you selected will be assigned "
            f"to the product that you select here.<br>"
            f"You will then be presented with the updated product and will have "
            f"the option to edit those assignments to provide more details about "
            f"how those {verbose_name_plural} are actually used in the product."
        )

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_method = "post"
        helper.form_id = "add-to-product-form"
        helper.form_tag = False
        opts = self.model._meta
        viewname = f"{opts.app_label}:{opts.model_name}_list"
        helper.form_action = reverse(viewname)
        helper.modal_title = "Add to Product"
        helper.modal_id = "add-to-product-modal"
        return helper


class AddToComponentFormMixin(forms.Form):
    object_id = forms.CharField(widget=forms.HiddenInput, required=False)
    component = forms.CharField(
        required=True,
        widget=AutocompleteInput(
            attrs={
                "style": "width: 400px !important;",
                "data-api_url": reverse_lazy("api_v2:component-list"),
            },
        ),
    )

    def new_component_from_package_link(self):
        if self.user.has_perm("component_catalog.add_component"):
            component_add_url = reverse("component_catalog:component_add")

            href = "#"
            package = (self.initial or {}).get("package")
            if package:
                href = f"{component_add_url}?package_ids={package.id}"

            return HTML(
                f'<div class="text-center">'
                f'  <a href="{href}" '
                f'     id="new-component-link" '
                f'     class="btn btn-success" '
                f'     data-add-url="{component_add_url}">'
                f"    Add Component from Package data"
                f"  </a>"
                f"</div>"
                f"<hr>"
            )

    def clean_component(self):
        object_id = self.cleaned_data.get("object_id")
        try:
            component = Component.objects.scope(self.dataspace).get(uuid=object_id)
        except Component.DoesNotExist:
            raise forms.ValidationError("Invalid Component.")
        return component

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_method = "post"
        helper.form_id = "add-to-component-form"
        helper.form_tag = False
        helper.modal_title = "Add to Component"
        helper.modal_id = "add-to-component-modal"
        helper.layout = Layout(
            Fieldset(
                None,
                self.new_component_from_package_link(),
                "object_id",
                "component",
            ),
        )
        return helper


class AddToComponentForm(AddToComponentFormMixin, DataspacedModelForm):
    class Meta:
        model = ComponentAssignedPackage
        fields = [
            "object_id",
            "component",
            "package",
        ]
        widgets = {
            "package": forms.widgets.HiddenInput,
        }

    @property
    def helper(self):
        helper = super().helper
        helper.layout = Layout(
            helper.layout,
            "package",
        )
        return helper


class AddMultipleToComponentForm(AddToComponentFormMixin):
    use_required_attribute = True
    ids = forms.CharField(widget=forms.widgets.HiddenInput)

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user = request.user
        self.dataspace = request.user.dataspace
        self.model = Package

    def get_selected_objects(self):
        if "ids" in self.initial:
            ids = self.initial["ids"].split(",")
        else:
            ids = self.cleaned_data["ids"].split(",")
        return self.model.objects.scope(self.dataspace).filter(pk__in=ids)

    def save(self):
        component = self.cleaned_data["component"]
        user = self.request.user
        created_count = 0
        unchanged_count = 0

        selected_objects = self.get_selected_objects()
        for obj in selected_objects:
            filters = {
                "component": component,
                "package": obj,
                "dataspace": obj.dataspace,
            }
            relation_obj, created = ComponentAssignedPackage.objects.get_or_create(**filters)
            if created:
                History.log_addition(user, relation_obj)
                History.log_change(user, component, f'Added package "{obj}"')
                created_count += 1
            else:
                unchanged_count += 1

        if created_count:
            component.last_modified_by = user
            component.save()

        return created_count, unchanged_count

    @property
    def helper(self):
        helper = super().helper
        opts = self.model._meta
        viewname = f"{opts.app_label}:{opts.model_name}_list"
        helper.form_action = reverse(viewname)
        helper.layout = Layout(
            helper.layout,
            "ids",
        )
        return helper


class UsagePolicyAdminFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        usage_policy_field = self.fields.get("usage_policy")
        if usage_policy_field:
            rel = self._meta.model._meta.get_field("usage_policy").remote_field
            base_widget = usage_policy_field.widget.widget
            usage_policy_field.widget = UsagePolicyWidgetWrapper(
                base_widget, rel, self.admin_site, object_instance=self.instance
            )

    def clean(self):
        """
        Raise a warning when a license_expression is changed and the usage_policy from the
        primary license differs from the package usage_policy.
        """
        cleaned_data = super().clean()

        license_expression = self.cleaned_data.get("license_expression")
        conditions = [
            self.instance,
            self.instance.usage_policy,
            "license_expression" in self.changed_data,
            license_expression,
        ]

        if all(conditions):
            fake_instance = self._meta.model(
                license_expression=license_expression,
                dataspace=self.instance.dataspace,
            )
            policy_from_license = fake_instance.get_policy_from_primary_license()
            if policy_from_license and policy_from_license != self.instance.usage_policy:
                msg = (
                    f"The changed license assignment does not match the currently assigned "
                    f'usage policy: "{self.instance.usage_policy}" != "{policy_from_license}" '
                    f"from {fake_instance.primary_license}"
                )
                messages.warning(self.request, msg)

        return cleaned_data


class AcceptableLinkagesFormMixin(forms.Form):
    acceptable_linkages = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        dataspace = getattr(self, "dataspace", None) or getattr(  # MassUpdate
            self.instance, "dataspace", None
        )  # AdminForm

        if dataspace:
            qs = AcceptableLinkage.objects.scope(dataspace)
            choices = [(choice.label, choice.label) for choice in qs]
            acceptable_linkages_field = self.fields["acceptable_linkages"]
            acceptable_linkages_field.choices = choices
            help_text = Component._meta.get_field("acceptable_linkages").help_text
            acceptable_linkages_field.help_text = help_text


class ComponentAdminForm(
    LicenseExpressionFormMixin,
    UsagePolicyAdminFormMixin,
    AcceptableLinkagesFormMixin,
    SetKeywordsChoicesFormMixin,
    DataspacedAdminForm,
):
    keywords = JSONListField(
        required=False,
        widget=AdminAwesompleteInputWidget(attrs=autocomplete_placeholder),
    )

    def __init__(self, *args, **kwargs):
        # Required for SetKeywordsChoicesFormMixin
        self.dataspace = self.request.user.dataspace
        super().__init__(*args, **kwargs)


class SubcomponentLicenseExpressionFormMixin(LicenseExpressionFormMixin):
    relation_fk_field = "child"


class SubcomponentAdminForm(SubcomponentLicenseExpressionFormMixin, DataspacedAdminForm):
    def clean_reference_notes(self):
        """Propagate the reference_notes from the child Component if available and not provided."""
        reference_notes = self.cleaned_data.get("reference_notes")
        child = self.cleaned_data.get("child")

        if not reference_notes and child and child.reference_notes:
            return child.reference_notes

        return reference_notes


class PackageAdminForm(
    LicenseExpressionFormMixin,
    UsagePolicyAdminFormMixin,
    PackageFieldsValidationMixin,
    SetKeywordsChoicesFormMixin,
    DataspacedAdminForm,
):
    keywords = JSONListField(
        required=False,
        widget=AdminAwesompleteInputWidget(attrs=autocomplete_placeholder),
    )

    class Meta:
        widgets = {
            "download_url": AdminURLFieldWidget,
        }

    def _get_purldb_uuid(self):
        """Return the `purldb_uuid` value if available in the `request`."""
        request = getattr(self, "request", None)
        if request:
            return request.GET.get("purldb_uuid", None)

    def _set_purldb_uuid_on_instance(self):
        """Force the `purldb_uuid`, if available, on the `self.instance`"""
        purldb_uuid = self._get_purldb_uuid()
        if purldb_uuid:
            self.instance.uuid = purldb_uuid

    def __init__(self, *args, **kwargs):
        # Required for SetKeywordsChoicesFormMixin
        self.dataspace = self.request.user.dataspace

        super().__init__(*args, **kwargs)
        # Override the readonly value for the UUID.
        # This is only for the visual value in the form and has no impact on the saved value.
        # A new value is always re-generated at save time so we have to
        # override it in `self.save()` as well.
        self._set_purldb_uuid_on_instance()

    def save(self, commit=True):
        # Replaces the auto-generated UUID but the purldb_uuid if available.
        self._set_purldb_uuid_on_instance()
        return super().save(commit)


class ComponentMassUpdateForm(
    LicenseExpressionFormMixin,
    AcceptableLinkagesFormMixin,
    SetKeywordsChoicesFormMixin,
    DejacodeMassUpdateForm,
):
    raw_id_fields = ["owner"]
    keywords = JSONListField(
        required=False,
        widget=AwesompleteInputWidget(attrs=autocomplete_placeholder),
    )

    class Meta:
        fields = [
            "version",
            "owner",
            "copyright",
            "holder",
            "license_expression",
            "reference_notes",
            "description",
            "homepage_url",
            "vcs_url",
            "code_view_url",
            "bug_tracking_url",
            "primary_language",
            "project",
            "codescan_identifier",
            "type",
            "notice_text",
            "is_license_notice",
            "is_copyright_notice",
            "is_notice_in_codebase",
            "notice_filename",
            "notice_url",
            "website_terms_of_use",
            "dependencies",
            "configuration_status",
            "is_active",
            "usage_policy",
            "curation_level",
            "guidance",
            "admin_notes",
            "keywords",
            "approval_reference",
            "ip_sensitivity_approved",
            "affiliate_obligations",
            "affiliate_obligation_triggers",
            "concluded_license",
            "legal_comments",
            "sublicense_allowed",
            "express_patent_grant",
            "covenant_not_to_assert",
            "indemnification",
            "legal_reviewed",
            "distribution_formats_allowed",
            "acceptable_linkages",
            "export_restrictions",
            "approved_download_location",
            "approved_community_interaction",
        ]


class SubcomponentMassUpdateForm(DejacodeMassUpdateForm):
    class Meta:
        fields = [
            "reference_notes",
            "usage_policy",
            "purpose",
            "notes",
            "is_deployed",
            "is_modified",
            "extra_attribution_text",
            "package_paths",
        ]


class PackageMassUpdateForm(
    LicenseExpressionFormMixin, SetKeywordsChoicesFormMixin, DejacodeMassUpdateForm
):
    keywords = JSONListField(
        required=False,
        widget=AwesompleteInputWidget(attrs=autocomplete_placeholder),
    )

    class Meta:
        fields = [
            "release_date",
            "primary_language",
            "description",
            "project",
            "notes",
            "dependencies",
            "copyright",
            "holder",
            "author",
            "license_expression",
            "reference_notes",
            "usage_policy",
            "homepage_url",
            "notice_text",
            "type",
            "namespace",
            "name",
            "version",
            "qualifiers",
            "subpath",
        ]


class SetPolicyForm(forms.Form):
    def __init__(self, request, model_class, policy_attr, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.dataspace = request.user.dataspace
        self.model_class = model_class
        self.policy_attr = policy_attr

    def save(self):
        checked_ids = [
            key.replace("checked_id_", "")
            for key, value in self.data.items()
            if key.startswith("checked_id_") and value == "on"
        ]

        qs = self.get_objects().filter(pk__in=checked_ids)
        for obj in qs:
            obj.usage_policy = getattr(obj, self.policy_attr)
            obj.save()

        return len(qs)

    def get_objects(self):
        ids = self.initial["ids"].split(",")
        return (
            self.model_class.objects.scope(self.dataspace)
            .filter(pk__in=ids)
            .select_related("usage_policy")
        )
