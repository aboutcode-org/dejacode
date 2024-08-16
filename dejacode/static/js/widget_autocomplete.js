/*
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#
*/
(function ($) {
    'use strict';
    function remove_purl_separators(input) {
        return input.replace('pkg:', '').replace('@', ' ').replace('/', ' ');
    }
    window.AutocompleteWidget = {
        init: function (
            field_selector,
            object_field_id,
            object_link_id,
            display_attribute
        ) {
            let field_input = $(field_selector);
            let object_id_input = $(object_field_id);
            let object_id_link = $(object_link_id);
            let api_url = field_input.data('api_url');

            console.log('Setup autocomplete for', field_input, api_url);
            let awesomplete = new Awesomplete(field_input.get(0), {
                list: [],
                minChars: 1,
                maxItems: 20,
                autoFirst: false,

                filter: function (text, input) {
                    // Add support for matching in purl fields, ignoring the separators.
                    // https://github.com/LeaVerou/awesomplete/issues/16858
                    //
                    // Supported format:
                    // - pkg:pypi/django@2.0.1
                    // - pypi/django@2.0.1
                    // - django@2.0.1
                    // - django 2.0.1
                    // - pypi django 2.0.1

                    let text_clean = remove_purl_separators(text);
                    let input_clean = remove_purl_separators(input.trim());
                    return RegExp(
                        Awesomplete.$.regExpEscape(input_clean),
                        'i'
                    ).test(text_clean);
                },

                replace: function (text) {
                    this.input.value = text.label;
                    // Store the entire API response to the input for future use
                    this.input.apiResponse = text.value;

                    object_id_input.val(text.value.uuid);
                    object_id_link.prop('href', text.value.absolute_url);
                    object_id_link.show();
                },
            });

            field_input.on('input', function () {
                let input_value = $(this).val();
                if (input_value.length >= awesomplete.minChars) {
                    $.ajax({
                        url:
                            api_url +
                            `?format=json&page_size=${awesomplete.maxItems}&autocomplete=1&search=${input_value}`,
                        success: function (response) {
                            if (response.count > 0) {
                                let choices = [];
                                $(response.results).each(function () {
                                    let display_label = this[display_attribute];
                                    choices.push([display_label, this]); // [label, value]
                                });
                                awesomplete.list = choices;
                                awesomplete.evaluate();
                            }
                        },
                    });
                } else {
                    object_id_input.val('');
                    object_id_link.hide();
                }
            });
        },
    };
})($);
