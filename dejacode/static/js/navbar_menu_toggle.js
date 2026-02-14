/*
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#
*/

// Mutual exclusion for DejaCode dropdown and Hamburger menu
document.addEventListener('DOMContentLoaded', function() {
  const dejaCodeDropdown = document.querySelector('.navbar-brand .dropdown-toggle');
  const hamburgerCollapse = document.getElementById('navbarCollapse');
  
  if (dejaCodeDropdown && hamburgerCollapse) {
    // When DejaCode dropdown opens, close hamburger
    dejaCodeDropdown.addEventListener('show.bs.dropdown', function() {
      const bsCollapse = bootstrap.Collapse.getInstance(hamburgerCollapse);
      if (bsCollapse) {
        bsCollapse.hide();
      }
    });
    
    // When hamburger opens, close DejaCode dropdown
    hamburgerCollapse.addEventListener('show.bs.collapse', function() {
      const bsDropdown = bootstrap.Dropdown.getInstance(dejaCodeDropdown);
      if (bsDropdown) {
        bsDropdown.hide();
      }
    });
  }
});
