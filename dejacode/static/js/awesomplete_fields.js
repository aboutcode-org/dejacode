/*
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#
*/
(function($){
    $(document).ready(function(){
        let awesomplete_data = NEXB.client_data.awesomplete_data;
        $.each(awesomplete_data, function (key, value) {
             let input = $("input[id$='" + key + "']");   // Supports Inlines
             input.each(function() {
                 new Awesomplete(this, {
                     list: value,
                     minChars: 1,
                     maxItems: 10,
                     autoFirst: true
                 });
             });
        });
    });
})(grp.jQuery);