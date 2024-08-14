/*
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#
*/
// This code adds an edit link next to a autocomplete raw_id input in the admin UI.
// This is inspired/forked from edit-related-link.js
(function ($) {
  $(document).ready(function () {
    NEXB.install_edit_autocomplete_links = function (elem) {
      // We are building the Edit links based on the href of the Add link
      // If there is no Add link (no permission) then we don't build/display the Edit link
      elem.find(".ui-autocomplete-input").each(function () {
        var hidden_field = $(this).next(".grp-autocomplete-hidden-field");
        var lookup_link = $(this).siblings(".related-lookup");
        // Get the URL without the arguments
        var add_href = lookup_link.attr("href").split("?").shift();
        var pk = hidden_field.val();
        var grp_autocomplete_wrapper = $(this).parent();

        var field_id = hidden_field.attr("id");
        var add_link = $(
          '<a id="add_' +
            field_id +
            '" href="' +
            add_href +
            'add/?_to_field=id&amp;_popup=1" class="grp-related-widget-wrapper-link grp-add-related grp-add-another related-widget-wrapper-link add-related add-another raw-id-add" title="Add another"></a>'
        );
        var edit_link = $(
          '<a href="#" class="edit-icon edit-icon-autocomplete" title="Edit item" target="_blank">&nbsp;</a>'
        );

        edit_link.hover(function () {
          // Refresh the pk as the select value may have changed
          pk = hidden_field.val();
          var edit_href = _.string.sprintf("%s%s/", add_href, pk);
          console.log(_.string.sprintf("edit_href: %s", edit_href));
          $(this).attr("href", edit_href);
          return false;
        });

        grp_autocomplete_wrapper.after(edit_link);
        grp_autocomplete_wrapper.after(add_link);

        // Display the Edit link only if there's a related object selected on init.
        if (!hidden_field.val()) {
          $(edit_link).hide();
        }

        // This catch action that impact the hidden_field value.
        hidden_field.bind("change focus keyup", function () {
          hidden_field.val() ? $(edit_link).show() : $(edit_link).hide();
        });
        // This catch action in the dropdown listing.
        $(".ui-autocomplete").click(function () {
          hidden_field.val() ? $(edit_link).show() : $(edit_link).hide();
        });
      });
    };
    NEXB.install_edit_autocomplete_links($(document));

    // add the edit link to a new inline form when the user adds one
    $("a.grp-add-handler").click(function () {
      var group = $(this).parents('[id$="-group"]');
      var last_index = group.find('[id$="-TOTAL_FORMS"]').val() - 1;
      var form = $(group.find(".grp-dynamic-form")[last_index]);
      NEXB.install_edit_autocomplete_links(form);
    });
  });
})(grp.jQuery);
