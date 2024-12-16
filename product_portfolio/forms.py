#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import BaseModelFormSet
from django.forms.formsets import DELETION_FIELD_NAME
from django.urls import reverse_lazy
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from crispy_forms.bootstrap import InlineCheckboxes
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML
from crispy_forms.layout import Fieldset
from crispy_forms.layout import Layout
from crispy_forms.layout import Submit
from guardian.shortcuts import assign_perm

from component_catalog.forms import BaseAddToProductForm
from component_catalog.forms import ComponentAddToProductForm
from component_catalog.forms import KeywordsField
from component_catalog.forms import PackageAddToProductForm
from component_catalog.forms import SetKeywordsChoicesFormMixin
from component_catalog.license_expression_dje import LicenseExpressionFormMixin
from component_catalog.models import Component
from component_catalog.programming_languages import PROGRAMMING_LANGUAGES
from dejacode_toolkit.scancodeio import ScanCodeIO
from dje import tasks
from dje.fields import SmartFileField
from dje.forms import ColorCodeFormMixin
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
from product_portfolio.models import CodebaseResource
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductPackage
from product_portfolio.models import ScanCodeProject


class NameVersionValidationFormMixin:
    """
    Add unique_together validation.
    This validation is usually handled at the model level during the
    `Model._perform_unique_checks` method.
    Since the secured manager logic is not available there,
    the queryset during unique validation is empty.
    We are duplicating that logic here with the proper `get_queryset` call.
    """

    def clean(self):
        cleaned_data = super().clean()

        model = self._meta.model
        user = self.user if getattr(self, "user", None) else self.request.user
        dataspace_id = self.instance.dataspace_id or user.dataspace_id

        lookup_kwargs = {
            "dataspace_id": dataspace_id,
            "name": cleaned_data.get("name"),
            "version": cleaned_data.get("version", ""),
        }

        # For this validation, we cannot limit the QS only to the user access
        # but we need to validate against the whole Dataspace.
        qs = model.unsecured_objects.filter(**lookup_kwargs)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            unique_check = [field for field in lookup_kwargs.keys() if field != "dataspace_id"]
            raise self.instance.unique_error_message(model, unique_check)


class ProductForm(
    LicenseExpressionFormMixin,
    DefaultOnAdditionLabelMixin,
    NameVersionValidationFormMixin,
    DataspacedModelForm,
):
    default_on_addition_fields = ["configuration_status"]
    save_as = True
    clone_m2m_classes = [
        ProductComponent,
        ProductPackage,
        CodebaseResource,
    ]

    keywords = KeywordsField()

    class Meta:
        model = Product
        fields = [
            "name",
            "version",
            "owner",
            "copyright",
            "notice_text",
            "license_expression",
            "release_date",
            "description",
            "homepage_url",
            "primary_language",
            "is_active",
            "configuration_status",
            "contact",
            "keywords",
            "vulnerabilities_risk_threshold",
        ]
        field_classes = {
            "owner": OwnerChoiceField,
        }
        widgets = {
            "copyright": forms.Textarea(attrs={"rows": 2}),
            "notice_text": forms.Textarea(attrs={"rows": 2}),
            "description": forms.Textarea(attrs={"rows": 2}),
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
        }

    def assign_object_perms(self, user):
        assign_perm("view_product", user, self.instance)

        if user.has_perm("product_portfolio.change_product"):
            assign_perm("change_product", user, self.instance)

        if user.has_perm("product_portfolio.delete_product"):
            assign_perm("delete_product", user, self.instance)

    @property
    def helper(self):
        helper = super().helper

        helper.layout = Layout(
            Fieldset(
                None,
                Group("name", "version", "owner"),
                HTML("<hr>"),
                "license_expression",
                Group("copyright", "notice_text"),
                HTML("<hr>"),
                Group("description", "keywords"),
                Group("primary_language", "homepage_url", "contact"),
                HTML("<hr>"),
                Group("is_active", "configuration_status", "release_date"),
                HTML("<hr>"),
                Group("vulnerabilities_risk_threshold", HTML(""), HTML("")),
                HTML("<hr>"),
                Submit("submit", self.submit_label, css_class="btn-success"),
                self.save_as_new_submit,
            ),
        )

        return helper


class ProductAdminForm(
    LicenseExpressionFormMixin,
    NameVersionValidationFormMixin,
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


class ProductComponentLicenseExpressionFormMixin(LicenseExpressionFormMixin):
    relation_fk_field = "component"


class ProductRelatedAdminForm(DataspacedAdminForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # `product` is not in self.fields when used in Inlines
        is_inline = "product" not in self.fields
        if not is_inline:
            product_qs = Product.objects.get_queryset(self.request.user, "change_product")
            self.fields["product"].queryset = product_qs


class ProductComponentAdminForm(
    ProductComponentLicenseExpressionFormMixin,
    ProductRelatedAdminForm,
):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["feature"].widget = AdminAwesompleteInputWidget(data_list="#feature_datalist")


class ProductPackageAdminForm(ProductComponentAdminForm):
    relation_fk_field = "package"


class ProductMassUpdateForm(SetKeywordsChoicesFormMixin, DejacodeMassUpdateForm):
    keywords = JSONListField(
        required=False,
        widget=AwesompleteInputWidget(attrs=autocomplete_placeholder),
    )

    class Meta:
        fields = [
            "version",
            "copyright",
            "notice_text",
            "description",
            "keywords",
            "homepage_url",
            "primary_language",
            "admin_notes",
            "configuration_status",
            "contact",
            "vcs_url",
            "code_view_url",
            "bug_tracking_url",
            "keywords",
        ]


class ProductComponentMassUpdateForm(DejacodeMassUpdateForm):
    class Meta:
        fields = [
            "review_status",
            "purpose",
            "notes",
            "is_deployed",
            "is_modified",
            "extra_attribution_text",
            "package_paths",
            "feature",
            "reference_notes",
            "issue_ref",
            "name",
            "version",
            "owner",
            "copyright",
            "homepage_url",
            "primary_language",
        ]


class ProductPackageMassUpdateForm(DejacodeMassUpdateForm):
    class Meta:
        fields = [
            "review_status",
            "purpose",
            "notes",
            "is_deployed",
            "is_modified",
            "extra_attribution_text",
            "package_paths",
            "feature",
            "reference_notes",
            "issue_ref",
        ]


class AttributionConfigurationForm(forms.Form):
    pc_query = forms.ModelChoiceField(
        label=_("Product component query"),
        required=False,
        queryset=None,
        help_text="Optionally select a query that will restrict the selected "
        "Product components to those that meet your criteria for attribution "
        "obligations.",
    )

    component_query = forms.ModelChoiceField(
        label=_("Component query"),
        required=False,
        queryset=None,
        help_text="Optionally select a query that will restrict the selected "
        "components to those that meet your criteria for attribution "
        "obligations.",
    )

    is_deployed = forms.BooleanField(
        label=_("Exclude components that are not deployed on the product"),
        required=False,
        initial=True,
        help_text="If checked, only deployed components will be included in the generated "
        "attribution document. If unchecked, all product components will be included "
        "in the generated attribution document, both deployed and not deployed.",
    )

    all_license_texts = forms.BooleanField(
        label=_("Include all component licenses"),
        required=False,
        initial=True,
        help_text="If checked, all licenses associated with a component will be identified in "
        "the attribution document, along with links to the license texts.",
    )

    subcomponent_hierarchy = forms.BooleanField(
        label=_("Include complete subcomponent hierarchy"),
        required=False,
        initial=True,
        help_text="If checked, all subcomponents of the product components will be included "
        "in the generated attribution document. If not checked, only the components "
        "directly assigned to the product will be included.",
    )

    toc_as_nested_list = forms.BooleanField(
        label=_("Display components as hierarchy"),
        required=False,
        initial=True,
        help_text="If checked the components list will be displayed as a hierarchy. "
        "Otherwise as a plain list.",
    )

    include_homepage_url = forms.BooleanField(
        label=_("Include component homepage URL"),
        required=False,
        initial=False,
        help_text="If checked, the homepage URL associated with a component will be printed "
        "before the copyright notice.",
    )

    include_standard_notice = forms.BooleanField(
        label=_("Include standard notice"),
        required=False,
        initial=False,
        help_text="If checked, the standard notice associated with a product component license "
        "will be printed after the license expression.",
    )

    group_by_feature = forms.BooleanField(
        label=_("Group components and packages by feature"),
        required=False,
        initial=False,
        help_text="If checked, the attribution list will group the components and packages of "
        "the product within each feature.",
    )

    include_packages = forms.BooleanField(
        label=_("Include packages"),
        required=False,
        initial=False,
        help_text="If checked, the attribution will include the packages directly assigned "
        "to the product.",
    )

    def __init__(self, request, *args, **kwargs):
        """Scope the Query QuerySet to user dataspace and ContentType."""
        super().__init__(*args, **kwargs)

        from reporting.models import Query

        scoped_queryset = Query.objects.scope(request.user.dataspace)
        self.fields["pc_query"].queryset = scoped_queryset.get_for_model(ProductComponent)
        self.fields["pc_query"].widget.attrs["class"] = "span7"
        self.fields["component_query"].queryset = scoped_queryset.get_for_model(Component)
        self.fields["component_query"].widget.attrs["class"] = "span7"

    def clean(self):
        cleaned_data = super().clean()
        pc_query = cleaned_data.get("pc_query")
        component_query = cleaned_data.get("component_query")

        subcomponent_hierarchy = cleaned_data.get("subcomponent_hierarchy")
        toc_as_nested_list = cleaned_data.get("toc_as_nested_list")
        group_by_feature = cleaned_data.get("group_by_feature")

        if pc_query and component_query:
            raise forms.ValidationError("Only one Query type allowed at once.")

        for query in [pc_query, component_query]:
            if query and not query.is_valid():
                raise forms.ValidationError("Query not valid.")

        if toc_as_nested_list and not subcomponent_hierarchy:
            raise forms.ValidationError(
                'Subcomponent as nested lists requires "Include complete subcomponent hierarchy".'
            )

        if group_by_feature and not toc_as_nested_list:
            raise forms.ValidationError(
                'Grouping components by feature requires "Display components as hierarchy".'
            )

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_method = "get"
        helper.form_id = "attribution-configuration-form"
        helper.attrs = {"autocomplete": "off"}
        helper.add_input(Submit("submit", "Generate Attribution"))
        return helper


class ComparisonExcludeFieldsForm(forms.Form):
    FIELD_CHOICES = (
        ("purpose", "Purpose"),
        ("notes", "Notes"),
        ("is_deployed", "Is Deployed"),
        ("is_modified", "Is Modified"),
        ("extra_attribution_text", "Extra Attribution Text"),
        ("package_paths", "Package Paths"),
        ("license_expression", "License Expression"),
        ("review_status", "Review Status"),
    )

    exclude = forms.MultipleChoiceField(
        label="",
        choices=FIELD_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_id = "exclude_fields_form"
        helper.form_method = "get"
        helper.attrs = {"autocomplete": "off"}

        helper.layout = Layout(
            HTML('<div class="mb-2">Exclude fields from comparison:</div>'),
            InlineCheckboxes("exclude"),
            Submit("submit", _("Exclude selected")),
        )

        return helper


class ProductItemPurposeForm(ColorCodeFormMixin, DataspacedAdminForm):
    pass


class ProductRelationFormMixin:
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        product_field = self.fields["product"]
        product_field.widget = forms.widgets.HiddenInput()

    def get_expression_widget_attrs(self):
        attrs = super().get_expression_widget_attrs()

        if not self.relation_fk_field:
            return

        relation_field = getattr(self.instance, self.relation_fk_field, None)
        if not relation_field:
            return

        licenses_qs = relation_field.licenses.for_expression()
        keys = licenses_qs.values_list("key", flat=True)
        if keys:
            keys = list(keys) + ["AND", "OR", "WITH"]
            attrs["data-list"] = ", ".join(keys)
        return attrs

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_method = "post"
        helper.form_id = "update-productrelation-form"
        helper.form_tag = True
        helper.disable_csrf = True
        # Do not include the media since the form is injected in the
        # HTML content through AJAX request and this may cause browser issues.
        helper.include_media = False
        return helper


class ProductPackageForm(
    ProductRelationFormMixin,
    PackageAddToProductForm,
):
    pass


class ProductComponentForm(
    ProductRelationFormMixin,
    ComponentAddToProductForm,
):
    pass


class ProductCustomComponentForm(
    ProductRelationFormMixin,
    BaseAddToProductForm,
):
    relation_fk_field = None

    class Meta(BaseAddToProductForm.Meta):
        model = ProductComponent
        fields = [
            "name",
            "version",
            "owner",
            "copyright",
            "homepage_url",
            "download_url",
            "primary_language",
            "reference_notes",
        ] + BaseAddToProductForm.Meta.fields


class ImportFromScanForm(forms.Form):
    upload_file = SmartFileField(extensions=["json"])
    create_codebase_resources = forms.BooleanField(
        label=_('Create Codebase Resources (from <code>"files"</code>)'),
        required=False,
        initial=False,
        help_text=_(
            "Create Codebase Resources on the Product you are updating to "
            "identify the paths in your codebase that provide the location of "
            "imported Packages."
        ),
    )
    stop_on_error = forms.BooleanField(
        label=_("Stop and cancel import on data validation error"),
        required=False,
        initial=False,
        help_text=_(
            "When checked, the whole import process will be stopped and "
            "reverted (no objects created) if a data entry is not valid in the "
            "DejaCode context. By default, those validation issues are skipped "
            "and displayed as warnings."
        ),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        self.dataspace = user.dataspace
        super().__init__(*args, **kwargs)

    @property
    def helper(self):
        helper = FormHelper()
        helper.add_input(Submit("import", "Import"))
        return helper

    def save(self, product):
        from product_portfolio.importers import ImportFromScan

        sid = transaction.savepoint()
        importer = ImportFromScan(
            product,
            self.user,
            upload_file=self.cleaned_data.get("upload_file"),
            create_codebase_resources=self.cleaned_data.get("create_codebase_resources"),
            stop_on_error=self.cleaned_data.get("stop_on_error"),
        )

        try:
            warnings, created_counts = importer.save()
        except ValidationError:
            transaction.savepoint_rollback(sid)
            raise

        transaction.savepoint_commit(sid)

        if self.dataspace.enable_vulnerablecodedb_access:
            product.fetch_vulnerabilities()

        return warnings, created_counts


class BaseProductImportFormView(forms.Form):
    project_type = None
    input_label = ""

    input_file = SmartFileField(
        label=_("file or zip archive"),
        required=True,
    )

    update_existing_packages = forms.BooleanField(
        label=_("Update existing packages with discovered packages data"),
        required=False,
        initial=False,
        help_text=_(
            "If checked, the discovered packages from the manifest that are already "
            "existing in your Dataspace will be updated with ScanCode data. "
            "Note that only the empty fields will be updated. "
            "By default (un-checked), existing packages will be assign to the product "
            "without any modification."
        ),
    )
    scan_all_packages = forms.BooleanField(
        label=_("Scan all packages of this product post-import"),
        required=False,
        initial=False,
        help_text=_(
            "If checked, multiple scans will be initiated on the ScanCode.io server "
            "for all of the packages assigned to your product."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["input_file"].label = _(f"{self.input_label} file or zip archive")

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_method = "post"
        helper.form_id = "import-manifest-form"
        helper.attrs = {"autocomplete": "off"}
        helper.add_input(Submit("submit", "Load Packages", css_class="btn-success"))
        return helper

    def submit(self, product, user):
        scancode_project = ScanCodeProject.objects.create(
            product=product,
            dataspace=product.dataspace,
            type=self.project_type,
            input_file=self.cleaned_data.get("input_file"),
            update_existing_packages=self.cleaned_data.get("update_existing_packages"),
            scan_all_packages=self.cleaned_data.get("scan_all_packages"),
            created_by=user,
        )

        transaction.on_commit(
            lambda: tasks.scancodeio_submit_project.delay(
                scancodeproject_uuid=scancode_project.uuid,
                user_uuid=user.uuid,
                pipeline_name=self.pipeline_name,
            )
        )


class LoadSBOMsForm(BaseProductImportFormView):
    project_type = ScanCodeProject.ProjectType.LOAD_SBOMS
    input_label = "SBOM"
    pipeline_name = "load_sbom"


class ImportManifestsForm(BaseProductImportFormView):
    project_type = ScanCodeProject.ProjectType.IMPORT_FROM_MANIFEST
    input_label = "Manifest"
    pipeline_name = "resolve_dependencies"


class StrongTextWidget(forms.Widget):
    def render(self, name, value, attrs=None, renderer=None):
        if value:
            return (
                f'<div class="object_display">'
                f'<strong>{value.get_absolute_link(target="_blank")}</strong>'
                f"</div>"
            )


class ProductRelationInlineFormMixin:
    can_add_perm = None

    def __init__(self, filterset, *args, **kwargs):
        self.filterset = filterset

        super().__init__(*args, **kwargs)

        labels = [
            ("notes", "Review notes"),
            ("is_modified", "Modified"),
            ("is_deployed", "Deployed"),
        ]

        for field_name, label in labels:
            field = self.fields.get(field_name)
            if field:
                field.label = label

        instance = kwargs.get("instance")
        object_display = self.fields["object_display"]
        if instance:
            object_display.initial = instance.related_component_or_package
            object_display.widget = StrongTextWidget()
            object_display.disabled = True
        elif self.can_add_perm:
            object_display.widget.can_add = self.user.has_perm(self.can_add_perm)

        # Builds the headers only for the first form entry of the formset.
        # The table headers in `table_inline_formset.html` are loaded from
        # `formset.forms.0`.
        if self.filterset and self.prefix == "form-0":
            self.make_sortable_headers()

    def make_sortable_headers(self):
        """Inject sort and filter links in the field labels to be displayed as table headers."""
        sortable_fields = []
        sort_filter = self.filterset.filters.get("sort")
        if sort_filter:
            sortable_fields = list(sort_filter.param_map.keys())

        query_no_sort = self.filterset.get_query_no_sort()
        current_sort = self.filterset.data.get("sort", "") if self.filterset else "no-sort"

        for field_name in sortable_fields:
            field = self.fields.get(field_name)
            if not field:
                continue

            active = ""
            reverse = ""
            direction = ""

            if field_name in current_sort:
                active = "active"
                direction = "-up"
                if not current_sort.startswith("-"):
                    reverse = "-"
                    direction = "-down"

            params = "?"
            if query_no_sort:
                params += f"{query_no_sort}&"

            sort_link_template = (
                '<a href="{}sort={}{}" class="sort {}" '
                '   aria-label="Sort">'
                '<i class="fas fa-sort{}"></i>'
                "</a>"
            )
            sort_link = format_html(
                sort_link_template, params, reverse, field_name, active, direction
            )

            if field_name in ["component", "package"]:
                field = self.fields["object_display"]

            filter_form = ""
            filterable_fields = [
                "review_status",
                "purpose",
                "is_deployed",
                "is_modified",
            ]
            if field_name in filterable_fields:
                filter_form = self.filterset.form[field_name]

            field.label = format_html("{} {} {}", field.label, sort_link, filter_form)


class ProductComponentInlineForm(
    ProductRelationInlineFormMixin,
    ProductComponentForm,
):
    can_add_perm = "component_catalog.add_component"

    object_display = forms.CharField(
        label="Component",
        required=True,
        widget=AutocompleteInput(
            attrs={
                "data-api_url": reverse_lazy("api_v2:component-list"),
            },
            display_link=False,
            can_add=False,
        ),
    )

    def clean(self):
        component = self.cleaned_data.get("component")
        if not component:
            self.add_error("object_display", "Invalid Component.")


class ProductPackageInlineForm(
    ProductRelationInlineFormMixin,
    ProductPackageForm,
):
    can_add_perm = None  # Package inline addition is not implemented

    object_display = forms.CharField(
        label="Package",
        required=True,
        widget=AutocompleteInput(
            attrs={
                "data-api_url": reverse_lazy("api_v2:package-list"),
            },
            display_link=False,
            can_add=False,
        ),
    )

    def clean(self):
        package = self.cleaned_data.get("package")
        if not package:
            self.add_error("object_display", "Invalid Package.")


class TableInlineFormSetHelper(FormHelper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.form_tag = False
        self.template = "bootstrap5/table_inline_formset.html"


class BaseProductRelationshipInlineFormSet(BaseModelFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_delete_label_as_icon()

    def set_delete_label_as_icon(self):
        """Replace the default "Delete" label by an icon."""
        icon = "far fa-trash-alt"
        icon_template = (
            '<span title="Delete" data-bs-toggle="tooltip" data-bs-placement="top">'
            '  <i class="{}"></i>'
            "</span>"
        )
        icon_label = format_html(icon_template, icon)

        for form in self.forms:
            deletion_field = form.fields.get(DELETION_FIELD_NAME)
            if deletion_field:
                deletion_field.label = icon_label

    def delete_existing(self, obj, commit=True):
        """Log a deletion in the Product History."""
        user = self.form_kwargs["user"]
        product = obj.product
        related_model_name = obj._meta.model_name.replace("product", "")
        delete_message = f'Deleted {related_model_name}  "{obj}"'

        super().delete_existing(obj, commit)

        History.log_change(user, product, message=delete_message)
        product.last_modified_by = user
        product.save()


class ProductGridConfigurationForm(forms.Form):
    FIELD_CHOICES = (
        ("license_expression", "License expression"),
        ("review_status", "Review status"),
        ("purpose", "Purpose"),
        ("notes", "Review notes"),
        ("is_deployed", "Deployed"),
        ("is_modified", "Modified"),
        ("extra_attribution_text", "Extra attribution text"),
        ("feature", "Feature"),
        ("issue_ref", "Issue ref"),
    )

    displayed_fields = forms.MultipleChoiceField(
        label="Displayed columns:",
        choices=FIELD_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    @classmethod
    def get_fields_name(cls):
        return [field_name for field_name, _ in cls.FIELD_CHOICES]

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_id = "grid_configuration_form"
        helper.form_method = "post"
        helper.attrs = {"autocomplete": "off"}
        helper.form_tag = False
        return helper


class PullProjectDataForm(forms.Form):
    project_name_or_uuid = forms.CharField(
        label=_("Project name or UUID"),
        required=True,
    )
    update_existing_packages = forms.BooleanField(
        label=_("Update existing packages from pulled data"),
        required=False,
        initial=False,
        help_text=_(
            "If checked, the discovered packages from the Project that are already "
            "existing in your Dataspace will be updated with ScanCode.io data. "
            "Note that only the empty fields will be updated. "
            "By default (un-checked), existing packages will be assign to the product "
            "without any modification."
        ),
    )

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_tag = False
        helper.form_method = "post"
        helper.form_id = "pull-project-data-form"
        helper.attrs = {"autocomplete": "off"}
        return helper

    def get_project_data(self, project_name_or_uuid, user):
        scancodeio = ScanCodeIO(user.dataspace)
        for field_name in ["name", "uuid"]:
            project_data = scancodeio.find_project(**{field_name: project_name_or_uuid})
            if project_data:
                return project_data

    def submit(self, product, user):
        project_name_or_uuid = self.cleaned_data.get("project_name_or_uuid")
        project_data = self.get_project_data(project_name_or_uuid, user)

        if not project_data:
            msg = f'Project "{project_name_or_uuid}" not found on ScanCode.io.'
            raise ValidationError(msg)

        scancode_project = ScanCodeProject.objects.create(
            product=product,
            dataspace=product.dataspace,
            type=ScanCodeProject.ProjectType.PULL_FROM_SCANCODEIO,
            project_uuid=project_data.get("uuid"),
            update_existing_packages=self.cleaned_data.get("update_existing_packages"),
            scan_all_packages=False,
            status=ScanCodeProject.Status.SUBMITTED,
            created_by=user,
        )

        transaction.on_commit(
            lambda: tasks.pull_project_data_from_scancodeio.delay(
                scancodeproject_uuid=scancode_project.uuid,
            )
        )
