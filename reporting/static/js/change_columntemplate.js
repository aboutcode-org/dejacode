/*
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#
*/
define([
    'jquery',
    'ember',
    'underscore',
    'underscore.string',
    'nexb',
    'text!handlebars/column_template_assigned_field_inline_form.handlebars',
    'text!handlebars/column_template_assigned_field_inline.handlebars',
    'jqueryui',
], function (
    $,
    Ember,
    _,
    _s,
    nexb,
    column_template_assigned_field_inline_form_template_source,
    column_template_assigned_field_inline_template_source
) {
    var initialContentType =
        nexb.App.client_data.content_type_map[$('#id_content_type').val()];

    var ColumnTemplateAssignedFieldInlineForm =
        nexb.ContentTypeAwareInlineForm.extend({
            templateFunction: Ember.Handlebars.compile(
                column_template_assigned_field_inline_form_template_source
            ),
            init: function () {
                this.set('selectedFields', []);

                var initialData = this.get('initialData');
                if (!Ember.isNone(initialData)) {
                    if (initialData.field_name) {
                        var fields = initialData.field_name.split('__');
                        this.get('selectedFields').setObjects(fields);
                    }
                    this.set('displayNameValue', initialData.display_name);
                    this.set('seqValue', initialData.seq);
                }
            },

            // Field
            fieldNameName: function () {
                return _s.sprintf(
                    '%s-%s-field_name',
                    this.get('formsetPrefix'),
                    this.get('formsetIndex')
                );
            }.property('formsetPrefix', 'formsetIndex'),
            selectedFields: null,
            fieldNameValue: function () {
                var selectedFields = this.get('selectedFields');
                if (Ember.isEmpty(selectedFields)) {
                    return '';
                }
                // Filter out empty values
                var fields = selectedFields.filter(function (
                    item,
                    index,
                    enumerable
                ) {
                    return !Ember.isEmpty(item);
                });
                return fields.join('__');
            }.property('selectedFields.@each'),
            fieldNameSelector: function () {
                var controller = this;
                return nexb.FieldSelectorView.extend({
                    controller: controller,
                });
            }.property(),

            // Display Name
            displayNameName: function () {
                return _s.sprintf(
                    '%s-%s-display_name',
                    this.get('formsetPrefix'),
                    this.get('formsetIndex')
                );
            }.property('formsetPrefix', 'formsetIndex'),
            displayNameValue: '',

            // Seq
            seqName: function () {
                return _s.sprintf(
                    '%s-%s-seq',
                    this.get('formsetPrefix'),
                    this.get('formsetIndex')
                );
            }.property('formsetPrefix', 'formsetIndex'),
            seqValue: null,

            getIdentifier: function () {
                return this.get('fieldNameValue');
            },
        });

    var ColumnTemplateInline = nexb.ContentTypeAwareInline.extend(
        nexb.DraggableRowsInlineMixin,
        {
            templateFunction: Ember.Handlebars.compile(
                column_template_assigned_field_inline_template_source
            ),
            formsetPrefix:
                nexb.App.client_data
                    .column_template_assigned_field_formset_prefix,
            initialFormCount:
                nexb.App.client_data
                    .column_template_assigned_field_formset_initial_form_count,
            hasErrors: function () {
                return nexb.App.client_data
                    .column_template_assigned_field_formset_formset_has_errors;
            }.property(),
            getInitialInlineData: function () {
                return nexb.App.client_data.column_template_assigned_fields;
            },
            getFormClass: function () {
                return ColumnTemplateAssignedFieldInlineForm;
            },
            sortablePropertyName: 'seqValue',
        }
    );

    var columnTemplateInline = ColumnTemplateInline.create({
        contentType: initialContentType,
    });

    // Bind the value of the content type field to the controller
    $('#id_content_type').change(function (event) {
        var pk = event.target.value;
        var contentType = nexb.App.client_data.content_type_map[pk];
        columnTemplateInline.set('contentType', contentType);
    });

    $(function () {
        $('#columntemplate_spinner').remove();
        columnTemplateInline.appendView('#ember_content');
    });
});
