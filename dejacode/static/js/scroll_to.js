/*
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#
*/
document.addEventListener('DOMContentLoaded', function () {
    function scrollTo(id) {
        // "html" is for Firefox compatibility and "body" for webkit
        $('html,body').scrollTop($(id).offset().top - 60);
    }

    $('a[data-scroll-to]').each(function() {
        var scroll_to = $(this).data("scroll-to");
        var href = $(this).attr('href');

        if (top.location.hash === href) scrollTo(scroll_to);
        $(this).click(function() {
            // WARNING: Do not e.preventDefault() as it will prevent from updating the location.hash
            scrollTo(scroll_to);
        });
    });
});