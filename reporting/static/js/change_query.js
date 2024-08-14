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
  "jquery",
  "ember",
  "underscore",
  "underscore.string",
  "nexb",
  "text!handlebars/filter_inline.handlebars",
  "text!handlebars/filter_inline_form.handlebars",
  "text!handlebars/order_field_inline.handlebars",
  "text!handlebars/order_field_inline_form.handlebars",
  "jqueryui",
], function (
  $,
  Ember,
  _,
  _s,
  nexb,
  filter_inline_template_source,
  filter_inline_form_template_source,
  order_field_inline_template_source,
  order_field_inline_form_template_source
) {
  var initialContentType =
    nexb.App.client_data.content_type_map[$("#id_content_type").val()];

  var FilterInlineForm = nexb.ContentTypeAwareInlineForm.extend({
    templateFunction: Ember.Handlebars.compile(
      filter_inline_form_template_source
    ),
    init: function () {
      this.set("selectedFields", []);

      var initialData = this.get("initialData");
      if (!Ember.isNone(initialData)) {
        if (initialData.field_name) {
          var fields = initialData.field_name.split("__");
          this.get("selectedFields").setObjects(fields);
        }
        this.set("lookupValue", initialData.lookup);
        this.set("valueValue", initialData.value);
        this.set("runtimeParameterValue", initialData.runtime_parameter);
        this.set("negateValue", initialData.negate);
      }
    },

    // Field
    fieldNameName: function () {
      return _s.sprintf(
        "%s-%s-field_name",
        this.get("formsetPrefix"),
        this.get("formsetIndex")
      );
    }.property("formsetPrefix", "formsetIndex"),
    selectedFields: null,
    fieldNameValue: function () {
      var selectedFields = this.get("selectedFields");
      if (Ember.isEmpty(selectedFields)) {
        return "";
      }
      // Filter out empty values
      var fields = selectedFields.filter(function (item, index, enumerable) {
        return !Ember.isEmpty(item);
      });
      return fields.join("__");
    }.property("selectedFields.@each"),
    fieldNameSelector: function () {
      var controller = this;
      return nexb.FieldSelectorView.extend({
        controller: controller,
      });
    }.property(),

    // Lookup
    lookupName: function () {
      return _s.sprintf(
        "%s-%s-lookup",
        this.get("formsetPrefix"),
        this.get("formsetIndex")
      );
    }.property("formsetPrefix", "formsetIndex"),
    lookupValue: null,
    lookupContent: function () {
      return nexb.App.client_data.lookups;
    }.property(),
    lookupSelect: function () {
      var controller = this;
      return Ember.Select.extend({
        prompt: "---------",
        controller: controller,
        contentBinding: "controller.lookupContent",
        optionLabelPath: "content.label",
        optionValuePath: "content.value",
        valueBinding: "controller.lookupValue",
      });
    }.property(),

    // Value
    valueName: function () {
      return _s.sprintf(
        "%s-%s-value",
        this.get("formsetPrefix"),
        this.get("formsetIndex")
      );
    }.property("formsetPrefix", "formsetIndex"),
    valueValue: "",

    // Runtime Parameter
    runtimeParameterName: function () {
      return _s.sprintf(
        "%s-%s-runtime_parameter",
        this.get("formsetPrefix"),
        this.get("formsetIndex")
      );
    }.property("formsetPrefix", "formsetIndex"),
    runtimeParameterValue: false,
    runtimeParameterCheckbox: function () {
      var controller = this;
      return Ember.Checkbox.extend({
        controller: controller,
        checkedBinding: "controller.runtimeParameterValue",
      });
    }.property(),

    // Negate (NOT)
    negateName: function () {
      return _s.sprintf(
        "%s-%s-negate",
        this.get("formsetPrefix"),
        this.get("formsetIndex")
      );
    }.property("formsetPrefix", "formsetIndex"),
    negateValue: false,
    negateCheckbox: function () {
      var controller = this;
      return Ember.Checkbox.extend({
        controller: controller,
        checkedBinding: "controller.negateValue",
      });
    }.property(),
  });

  var FilterInline = nexb.ContentTypeAwareInline.extend({
    templateFunction: Ember.Handlebars.compile(filter_inline_template_source),
    formsetPrefix: nexb.App.client_data.filter_formset_prefix,
    initialFormCount: nexb.App.client_data.filter_formset_initial_form_count,
    allErrors: nexb.App.client_data.filter_formset_all_errors,
    hasErrors: function () {
      return nexb.App.client_data.filter_formset_has_errors;
    }.property(),
    getInitialInlineData: function () {
      return nexb.App.client_data.filters;
    },
    getFormClass: function () {
      return FilterInlineForm;
    },
  });

  var filterInline = FilterInline.create({
    contentType: initialContentType,
  });

  var OrderFieldInlineForm = nexb.ContentTypeAwareInlineForm.extend({
    templateFunction: Ember.Handlebars.compile(
      order_field_inline_form_template_source
    ),
    init: function () {
      var initialData = this.get("initialData");
      if (!Ember.isNone(initialData)) {
        this.set("fieldNameValue", initialData.field_name);
        this.set("sortValue", initialData.sort);
        this.set("seqValue", initialData.seq);
      }
    },

    // Field
    fieldNameName: function () {
      return _s.sprintf(
        "%s-%s-field_name",
        this.get("formsetPrefix"),
        this.get("formsetIndex")
      );
    }.property("formsetPrefix", "formsetIndex"),
    fieldNameValue: null,
    fieldNameContent: function () {
      return nexb.App.client_data.order_field_model_data[
        this.get("contentType")
      ]["fields"];
    }.property("contentType"),
    fieldNameSelect: function () {
      var controller = this;
      return Ember.Select.extend({
        prompt: "---------",
        controller: controller,
        contentBinding: "controller.fieldNameContent",
        valueBinding: "controller.fieldNameValue",
      });
    }.property(),

    // Sort
    sortName: function () {
      return _s.sprintf(
        "%s-%s-sort",
        this.get("formsetPrefix"),
        this.get("formsetIndex")
      );
    }.property("formsetPrefix", "formsetIndex"),
    sortValue: null,
    sortSelect: function () {
      var controller = this;
      return Ember.Select.extend({
        controller: controller,
        content: nexb.App.client_data.sort_options,
        valueBinding: "controller.sortValue",
      });
    }.property(),

    // Seq
    seqName: function () {
      return _s.sprintf(
        "%s-%s-seq",
        this.get("formsetPrefix"),
        this.get("formsetIndex")
      );
    }.property("formsetPrefix", "formsetIndex"),
    seqValue: null,

    getIdentifier: function () {
      return this.get("fieldNameValue");
    },
  });

  var OrderFieldInline = nexb.ContentTypeAwareInline.extend(
    nexb.DraggableRowsInlineMixin,
    {
      templateFunction: Ember.Handlebars.compile(
        order_field_inline_template_source
      ),
      formsetPrefix: nexb.App.client_data.order_field_formset_prefix,
      initialFormCount:
        nexb.App.client_data.order_field_formset_initial_form_count,
      getInitialInlineData: function () {
        return nexb.App.client_data.order_fields;
      },
      getFormClass: function () {
        return OrderFieldInlineForm;
      },
      sortablePropertyName: "seqValue",
    }
  );

  var orderFieldInline = OrderFieldInline.create({
    contentType: initialContentType,
  });

  // Bind the value of the content type field to the filter controller
  // Bind the value of the content type field to the order field controller
  $("#id_content_type").change(function (event) {
    var pk = event.target.value;
    var contentType = nexb.App.client_data.content_type_map[pk];
    filterInline.set("contentType", contentType);
    orderFieldInline.set("contentType", contentType);
  });

  $(function () {
    $("#filter_spinner").remove();
    filterInline.appendView("#ember_content");
    orderFieldInline.appendView("#ember_content");
  });
});
