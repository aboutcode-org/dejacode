/*
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#
*/

document.addEventListener('DOMContentLoaded', () => {
  NEXB = {};
  NEXB.client_data = JSON.parse(document.getElementById("client_data").textContent);

  NEXB.displayOverlay = function(text) {
    const overlay = document.createElement('div');
    overlay.id = 'overlay';
    overlay.textContent = text;

    Object.assign(overlay.style, {
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        backgroundColor: 'rgba(0, 0, 0, .5)',
        zIndex: 10000,
        verticalAlign: 'middle',
        paddingTop: '300px',
        textAlign: 'center',
        color: '#fff',
        fontSize: '30px',
        fontWeight: 'bold',
        cursor: 'wait'
    });

    document.body.appendChild(overlay);
  }

  // Enables all tooltips
  const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  const tooltips = Array.from(tooltipTriggerList).map(element => {
    return new bootstrap.Tooltip(element, {
      container: 'body'
    });
  });

  // Enables all popovers
  const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
  const popovers = Array.from(popoverTriggerList).map(element => {
    return new bootstrap.Popover(element, {
      container: 'body',
      html: true
    });
  });

  // Search selection in the header
  $('#search-selector-list a').click(function(event) {
    event.preventDefault();
    $('#search-form').attr('action', $(this).attr('href'));
    $('#search-selector-content').html($(this).html());
    $('#search-input').focus();
  });

  // Get the back-to-top button element
  const backToTopButton = document.getElementById('back-to-top');

  // Add a scroll event listener
  window.addEventListener('scroll', function () {
    if (window.scrollY >= 250) { // Page is scrolled more than 250px
      backToTopButton.style.display = 'block';
    } else {
      backToTopButton.style.display = 'none';
    }
  });

  // Add a click event listener to scroll back to the top
  backToTopButton.addEventListener('click', function () {
    window.scrollTo(0, 0);
  });

});
