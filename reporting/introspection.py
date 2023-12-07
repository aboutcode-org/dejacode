#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import apps
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import ValidationError
from django.db.models.fields.related import RelatedField


def get_model_label(model):
    return f"{model._meta.app_label}:{model._meta.model_name}"


class ModelIntrospector:
    def get_related_models(
        self,
        model_classes,
        a_set=None,
        get_fields=True,
        get_m2m=True,
        get_related_m2m=True,
        get_related=True,
    ):
        if a_set is None:
            a_set = set(model_classes)

        for model_class in model_classes:
            mapping = self.get_query_name_map(
                model_class,
                get_fields=get_fields,
                get_m2m=get_m2m,
                get_related_m2m=get_related_m2m,
                get_related=get_related,
            )
            for field, model in mapping.items():
                if model is not None and model not in a_set:
                    a_set.add(model)
                    a_set.update(self.get_related_models([model], a_set))

        return list(a_set)

    def get_model_data(
        self,
        model_classes,
        model_whitelist=None,
        get_fields=True,
        omit_foreign_key_fields=False,
        get_m2m=True,
        get_related_m2m=True,
        get_related=True,
        get_generic_relation=False,
        field_whitelist=None,
    ):
        model_data = {}
        for model_class in model_classes:
            limit_to = None
            if model_whitelist and field_whitelist:
                limit_to = field_whitelist.get(model_class)

            model_data[get_model_label(model_class)] = {
                "fields": self.get_fields(
                    model_class,
                    get_fields=get_fields,
                    omit_foreign_key_fields=omit_foreign_key_fields,
                    get_m2m=get_m2m,
                    get_related_m2m=get_related_m2m,
                    get_related=get_related,
                    get_generic_relation=get_generic_relation,
                    limit_to=limit_to,
                ),
                "grouped_fields": self.get_grouped_fields(
                    model_class,
                    get_fields=get_fields,
                    get_m2m=get_m2m,
                    get_related_m2m=get_related_m2m,
                    get_related=get_related,
                    get_generic_relation=get_generic_relation,
                    limit_to=limit_to,
                ),
                "meta": self.get_meta(
                    model_class,
                    get_fields=get_fields,
                    get_m2m=get_m2m,
                    get_related_m2m=get_related_m2m,
                    get_related=get_related,
                    get_generic_relation=get_generic_relation,
                    limit_to=limit_to,
                ),
            }

        if model_whitelist:
            model_data = self.apply_whitelist(model_data, model_whitelist)

        return model_data

    @staticmethod
    def apply_whitelist(model_data, model_whitelist):
        whitelist_names = [get_model_label(m) for m in model_whitelist]
        # Using list() to make a copy to avoid the following error in Python3:
        # RuntimeError: dictionary changed size during iteration
        for model_name, value in list(model_data.items()):
            if model_name not in whitelist_names:
                del model_data[model_name]
            else:
                for field_name, meta_value in list(value["meta"].items()):
                    # Check if the field is permitted
                    if "model" in meta_value and meta_value["model"] not in whitelist_names:
                        # Remove the non-permitted field from 'fields'
                        if field_name in value["fields"]:
                            value["fields"].remove(field_name)

                        # Remove the non-permitted field from 'grouped_fields'
                        for item in value["grouped_fields"]:
                            if item["value"] == field_name:
                                value["grouped_fields"].remove(item)

                        # Remove the non-permitted field from 'meta'
                        del value["meta"][field_name]
        return model_data

    def get_fields(
        self,
        model_class,
        get_fields,
        omit_foreign_key_fields,
        get_m2m,
        get_related_m2m,
        get_related,
        get_generic_relation,
        limit_to,
    ):
        fields = self.get_query_name_map(
            model_class,
            get_fields=get_fields,
            omit_foreign_key_fields=omit_foreign_key_fields,
            get_m2m=get_m2m,
            get_related_m2m=get_related_m2m,
            get_related=get_related,
            get_generic_relation=get_generic_relation,
            limit_to=limit_to,
        )
        return sorted(fields.keys())

    def get_grouped_fields(
        self,
        model_class,
        get_fields,
        get_m2m,
        get_related_m2m,
        get_related,
        get_generic_relation,
        limit_to,
    ):
        output = []

        if get_fields:
            fk_symbol = " >>"
            opts = model_class._meta
            mapping = self.get_query_name_map(
                model_class,
                get_fields=get_fields,
                get_m2m=False,
                get_related_m2m=False,
                get_related=False,
                get_generic_relation=False,
                limit_to=limit_to,
            )

            output.extend(
                [
                    {
                        "label": field + fk_symbol if opts.get_field(field).many_to_one else field,
                        "value": field,
                        "group": "Direct Fields",
                    }
                    for field in sorted(mapping.keys())
                ]
            )

        if get_m2m:
            mapping = self.get_query_name_map(
                model_class,
                get_fields=False,
                get_m2m=get_m2m,
                get_related_m2m=False,
                get_related=False,
                get_generic_relation=False,
                limit_to=limit_to,
            )
            output.extend(
                [
                    {
                        "label": field,
                        "value": field,
                        "group": "Many to Many Fields",
                    }
                    for field in sorted(mapping.keys())
                ]
            )

        if get_related_m2m:
            mapping = self.get_query_name_map(
                model_class,
                get_fields=False,
                get_m2m=False,
                get_related_m2m=get_related_m2m,
                get_related=False,
                get_generic_relation=False,
                limit_to=limit_to,
            )
            output.extend(
                [
                    {
                        "label": field,
                        "value": field,
                        "group": "Related Many to Many Fields",
                    }
                    for field in sorted(mapping.keys())
                ]
            )

        if get_related:
            mapping = self.get_query_name_map(
                model_class,
                get_fields=False,
                get_m2m=False,
                get_related_m2m=False,
                get_related=get_related,
                get_generic_relation=get_generic_relation,
                limit_to=limit_to,
            )
            output.extend(
                [
                    {
                        "label": field,
                        "value": field,
                        "group": "Related Fields",
                    }
                    for field in sorted(mapping.keys())
                ]
            )

        return output

    def get_meta(
        self,
        model_class,
        get_fields,
        get_m2m,
        get_related_m2m,
        get_related,
        get_generic_relation,
        limit_to,
    ):
        meta = {}
        mapping = self.get_query_name_map(
            model_class,
            get_fields=get_fields,
            get_m2m=get_m2m,
            get_related_m2m=get_related_m2m,
            get_related=get_related,
            get_generic_relation=get_generic_relation,
            limit_to=limit_to,
        )
        for field, model in mapping.items():
            if not model:
                value = {}
            else:
                value = {"model": get_model_label(model)}
            meta[field] = value
        return meta

    @staticmethod
    def get_query_name_map(
        model_class,
        get_fields,
        get_m2m,
        get_related_m2m,
        get_related,
        omit_foreign_key_fields=False,
        get_generic_relation=False,
        limit_to=None,
    ):
        """
        Return a dictionary that maps all related field names (including reverse
        relation names) to their corresponding models.

        ``django.db.models.options.Options.init_name_map()`` was used as a
        reference.
        """
        out = {}
        opts = model_class._meta
        fields = opts.get_fields()

        if limit_to:
            fields = [f for f in fields if f.name in limit_to]

        # Hardcoded exception to remove the `is_active` field from reporting.
        if model_class.__name__ == "Product":
            fields = [f for f in fields if f.name != "is_active"]

        if get_fields:
            out.update(
                {
                    f.name: f.related_model if isinstance(f, RelatedField) else None
                    for f in fields
                    if not f.is_relation
                    or f.one_to_one
                    or (f.many_to_one and f.related_model)
                    and not (f.many_to_one and omit_foreign_key_fields)
                }
            )

        if get_m2m:
            out.update(
                {f.name: f.related_model for f in fields if f.many_to_many and not f.auto_created}
            )

        if get_related_m2m:
            out.update(
                {
                    f.name: f.field.model
                    for f in opts.get_fields(include_hidden=True)
                    if f.many_to_many and f.auto_created
                }
            )

        if get_related:
            out.update(
                {
                    f.name: f.field.model
                    for f in fields
                    if (f.one_to_many or f.one_to_one) and f.auto_created
                }
            )

        if get_generic_relation:
            out.update({f.name: f.related_model for f in fields if isinstance(f, GenericRelation)})

        return out

    @staticmethod
    def get_model_class_via_field_traversal(
        fields, starting_model, model_data, return_foreign_keys_only=False
    ):
        """
        Return the model class of the last field of the given field list by
        traversing relationships through each field of the list.
        """
        model_class = starting_model
        fields_len = len(fields)

        for index, field in enumerate(fields):
            # True during the last loop. In that case, we always want to return
            # the current model class and not the class of the last field.
            if index == fields_len - 1:  # Last loop
                return model_class

            model_label = get_model_label(model_class)
            current_model_data = model_data.get(model_label)
            if not current_model_data:
                continue

            field_data = current_model_data["meta"].get(field)
            if field_data is None:  # Warning: direct fields Return {}
                return

            related_model = field_data.get("model")
            if related_model:  # Relational field
                model_class = apps.get_model(*related_model.split(":"))
            elif return_foreign_keys_only:
                model_class = None

        return model_class

    def validate_field_traversal_of_model_data(self, fields, starting_model, model_data):
        model_class = self.get_model_class_via_field_traversal(fields, starting_model, model_data)
        if model_class:
            # Last field validation, not part of get_model_class_via_field_traversal
            last_field = fields[-1]
            if last_field in model_data[get_model_label(model_class)].get("fields", []):
                return model_class
        raise ValidationError("Invalid field value")

    def get_model_field_via_field_traversal(
        self, fields, starting_model, model_data, return_foreign_keys_only=False
    ):
        model = self.get_model_class_via_field_traversal(
            fields, starting_model, model_data, return_foreign_keys_only
        )
        last_field = fields[-1]
        try:
            field_object = model._meta.get_field(last_field)
        except FieldDoesNotExist:
            return
        return field_object


introspector = ModelIntrospector()
