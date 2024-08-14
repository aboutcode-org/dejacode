/*
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#
*/
if (typeof grp !== "undefined") {
  $ = grp.jQuery;
}

(function ($) {
  let operators = ["AND", "OR", "WITH"];
  let expression_field_name = NEXB.client_data.expression_field_name;

  function update_license_list(related_field, awesomplete_instance) {
    let object_id = related_field.val();
    if (!object_id) return false;

    $.ajax({
      url: related_field.api_url + "?format=json" + "&id=" + object_id,
      success: function (result) {
        if (result.count == 1) {
          let related_object_license_data = [];
          let related_object_data = result.results[0];

          if (!related_object_data.license_expression) {
            console.log(
              "No licenses from " +
                related_field.model_name +
                ".id=" +
                object_id +
                ", loading all license data."
            );
            return false;
          }

          $(related_object_data.licenses_summary).each(function () {
            let license_str = this.short_name + " (" + this.key + ")";
            related_object_license_data.push([license_str, this.key]); // [label, value]
          });

          let license_choices_expression =
            related_object_data.license_choices_expression;
          let new_header =
            related_field.model_name +
            ' license expression: <code class="license_expression">' +
            related_object_data.license_expression +
            "</code>";
          if (
            license_choices_expression &&
            related_object_data.license_expression != license_choices_expression
          )
            new_header +=
              '&nbsp;&rArr;&nbsp;&nbsp;License choices: <code class="license_expression">' +
              license_choices_expression +
              "</code>";
          update_related_field_header(related_field, new_header);

          $(related_object_data.license_choices).each(function () {
            let license_str = this.short_name + " (" + this.key + ")";
            related_object_license_data.push([license_str, this.key]); // [label, value]
          });

          awesomplete_instance.list = operators.concat(
            related_object_license_data
          );
          awesomplete_instance.evaluate();
          awesomplete_instance.close();
          console.log(
            "Updated license data from " +
              related_field.model_name +
              ".id=" +
              object_id +
              ": " +
              related_object_license_data
          );
        }
      },
    });
  }

  function update_related_field_header(related_field, header_html) {
    let inline_fieldset = related_field.parents("fieldset");
    let expression_header = inline_fieldset.find(
      "div.license-expression-header"
    );
    if (expression_header[0]) $(expression_header[0]).html(header_html);
  }

  function handle_related_field(related_field, awesomplete_instance) {
    if (related_field.val()) {
      update_license_list(related_field, awesomplete_instance);
    } else {
      // Reloads the original license_data when the Component is removed
      awesomplete_instance.list = operators.concat(
        NEXB.client_data.license_data
      );
      awesomplete_instance.evaluate();
      awesomplete_instance.close();
      update_related_field_header(related_field, "");
      console.log(
        "Loaded all license data for #" + awesomplete_instance.input.id
      );
    }
  }

  setup_awesomplete_builder = function (
    element,
    related_field,
    max_items,
    license_data
  ) {
    if (!element) return false;
    console.log("Setup license expression builder for #" + element.id);

    max_items = max_items || 100;
    license_data = license_data || NEXB.client_data.license_data;

    let awesomplete = new Awesomplete(element, {
      list: operators.concat(license_data),
      minChars: 1, // Minimum characters the user has to type before the autocomplete popup shows up.
      maxItems: max_items, // Maximum number of suggestions to display.
      autoFirst: false, // Should the first element be automatically selected?

      // Controls how entries get matched.
      // By default, the input can match anywhere in the string and it's a case insensitive match.
      filter: function (text, input) {
        return Awesomplete.FILTER_CONTAINS(text, input.match(/[^\s]*$/)[0]);
      },

      // Controls how list items are generated.
      // Function that takes two parameters, the first one being the suggestion text and
      // the second one the user’s input and returns a list item.
      item: function (text, input) {
        return Awesomplete.ITEM(text, input.match(/[^\s]*$/)[0]);
      },

      // Controls how the user's selection replaces the user's input.
      // For example, this is useful if you want the selection to only partially replace the user's input.
      replace: function (text) {
        let before = this.input.value.match(/^.+\s\s*|/)[0];
        this.input.value = before + text.value + " ";
      },

      // Controls how list items are ordered.
      // Using `false` to keep the default license_data ordering
      sort: false,
    });

    // Open the dropdown on click
    Awesomplete.$(element).addEventListener("click", function () {
      if (awesomplete.ul.childNodes.length === 0) {
        awesomplete.minChars = 0;
        awesomplete.evaluate();
      } else if (awesomplete.ul.hasAttribute("hidden")) {
        awesomplete.open();
      } else {
        awesomplete.close();
      }
    });

    if (related_field && related_field.length) {
      related_field.model_name = $(element).attr("related_model_name");
      related_field.api_url = $(element).attr("related_api_url");

      related_field.bind("change focus keyup blur", function () {
        handle_related_field(related_field, awesomplete);
      });
      // Run it once at setup time to load proper license_data from related_object (component/package)
      handle_related_field(related_field, awesomplete);
      console.log(
        "Add related",
        related_field.model_name,
        "with API URL",
        related_field.api_url
      );
    }
  };

  function add_expression_builder(license_expression_field) {
    let fieldset = $(license_expression_field).parents("fieldset");
    let related_component_field = fieldset.find(
      "input[name$='component'], input[name$='child'], input[name$='package']"
    );
    setup_awesomplete_builder(
      license_expression_field,
      related_component_field
    );
  }

  function add_expression_builder_in_inlines_on_add_another(form) {
    let license_expression_fields = form.find(
      "[id$='" + expression_field_name + "']"
    );
    license_expression_fields.each(function () {
      add_expression_builder(this);
    });
  }

  // Only true in the admin context
  if (NEXB.patch_grappelli_grp_inline) {
    $(document).ready(function () {
      // Collects all license_expression fields in main form and inlines, excluding "*-__prefix__-license_expression"
      let license_expression_fields = $(
        "[id$='" + expression_field_name + "']"
      ).not("[id$='__-" + expression_field_name + "']");
      license_expression_fields.each(function () {
        add_expression_builder(this);
      });
      NEXB.patch_grappelli_grp_inline(
        add_expression_builder_in_inlines_on_add_another
      );
    });
  }
})($);
