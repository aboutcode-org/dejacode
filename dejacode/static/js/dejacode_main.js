/*
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#
*/

function setupTooltips() {
  // Enables all tooltips
  const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  const tooltips = Array.from(tooltipTriggerList).map(element => {
    return new bootstrap.Tooltip(element, {
      container: 'body'
    });
  });
}

function setupPopovers() {
  // Enables all popovers
  const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
  const popovers = Array.from(popoverTriggerList).map(element => {
    return new bootstrap.Popover(element, {
      container: 'body',
      html: true
    });
  });
}

function setupSelectionCheckboxes() {
  const selectAllCheckbox = document.getElementById("checkbox-select-all");
  if (!selectAllCheckbox) return;

  const parentTable = selectAllCheckbox.closest("table");
  const rowCheckboxes = parentTable.querySelectorAll("tbody input[type='checkbox']");
  let lastChecked; // Store the last checked checkbox

  if (!rowCheckboxes) return;

  // Select-all checkboxes
  if (selectAllCheckbox) {
    selectAllCheckbox.addEventListener("click", function() {
      rowCheckboxes.forEach(function(checkbox) {
        checkbox.checked = selectAllCheckbox.checked;
      });
    });
  }

  // Add a click event listener to each row checkbox to handle individual selections
  rowCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener("click", function (event) {
      if (event.shiftKey && lastChecked) {
        // Determine the index of the clicked checkbox
        const currentCheckboxIndex = Array.from(rowCheckboxes).indexOf(checkbox);
        const lastCheckedIndex = Array.from(rowCheckboxes).indexOf(lastChecked);

        // Determine the range of checkboxes to check/uncheck
        const startIndex = Math.min(currentCheckboxIndex, lastCheckedIndex);
        const endIndex = Math.max(currentCheckboxIndex, lastCheckedIndex);

        // Toggle the checkboxes within the range
        for (let i = startIndex; i <= endIndex; i++) {
          rowCheckboxes[i].checked = checkbox.checked;
        }
      }

      // Update the last checked checkbox
      lastChecked = checkbox;

      // Check if all row checkboxes are checked and update the "Select All" checkbox accordingly
      if (selectAllCheckbox) {
        selectAllCheckbox.checked = Array.from(rowCheckboxes).every((cb) => cb.checked);
      }

    });
  });
}

function setupBackToTop() {
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
}

function setupHTMX() {
  // Triggered after new content has been swapped in
  document.body.addEventListener('htmx:afterSwap', function(evt) {
    const loadedContent = evt.detail.elt;

    // Enables all tooltip and popover of the inserted HTML
    Array.from(loadedContent.querySelectorAll('[data-bs-toggle="tooltip"]')).forEach(element => {
      new bootstrap.Tooltip(element, { container: 'body' });
    });
    Array.from(loadedContent.querySelectorAll('[data-bs-toggle="popover"]')).forEach(element => {
      new bootstrap.Popover(element, { container: 'body' });
    });

    // Disable the tab if a "disable-tab" CSS class if found in the loaded content
    if (loadedContent.querySelectorAll('.disable-tab').length > 0) {
        const tabPaneElement = loadedContent.closest('.tab-pane');
        // Find the corresponding button using its aria-controls attribute
        const buttonId = tabPaneElement.getAttribute('aria-labelledby');
        const button = document.querySelector(`#${buttonId}`);
        if (button) {
            button.disabled = true;
        }
    }
  });

  // Triggered when an HTTP response error (non-200 or 300 response code) occurs
  document.addEventListener('htmx:responseError', function (event) {
    event.target.innerHTML = '<div class="h5 ms-4 text-danger">Error fetching</div>';
  });
}

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

  // Search selection in the header
  $('#search-selector-list a').click(function(event) {
    event.preventDefault();
    $('#search-form').attr('action', $(this).attr('href'));
    $('#search-selector-content').html($(this).html());
    $('#search-input').focus();
  });

  setupTooltips();
  setupPopovers();
  setupSelectionCheckboxes();
  setupBackToTop();
  setupHTMX();
});
