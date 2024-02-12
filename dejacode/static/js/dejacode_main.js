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


/*!
* Color mode toggler for Bootstrap's docs (https://getbootstrap.com/)
* Copyright 2011-2023 The Bootstrap Authors
* Licensed under the Creative Commons Attribution 3.0 Unported License.
* https://getbootstrap.com/docs/5.3/customize/color-modes/#javascript
*/

(() => {
'use strict'

const getStoredTheme = () => localStorage.getItem('theme')
const setStoredTheme = theme => localStorage.setItem('theme', theme)

const getPreferredTheme = () => {
  const storedTheme = getStoredTheme()
  if (storedTheme) {
    return storedTheme
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

const setTheme = theme => {
  if (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    document.documentElement.setAttribute('data-bs-theme', 'dark')
  } else {
    document.documentElement.setAttribute('data-bs-theme', theme)
  }
}

setTheme(getPreferredTheme())

const showActiveTheme = (theme, focus = false) => {
  const themeSwitcher = document.querySelector('#bd-theme')

  if (!themeSwitcher) {
    return
  }

  const themeSwitcherText = document.querySelector('#bd-theme-text')
  const activeThemeIcon = document.querySelector('.theme-icon-active use')
  const btnToActive = document.querySelector(`[data-bs-theme-value="${theme}"]`)
  const svgOfActiveBtn = btnToActive.querySelector('svg use').getAttribute('href')

  document.querySelectorAll('[data-bs-theme-value]').forEach(element => {
    element.classList.remove('active')
    element.setAttribute('aria-pressed', 'false')
  })

  btnToActive.classList.add('active')
  btnToActive.setAttribute('aria-pressed', 'true')
  activeThemeIcon.setAttribute('href', svgOfActiveBtn)
  const themeSwitcherLabel = `${themeSwitcherText.textContent} (${btnToActive.dataset.bsThemeValue})`
  themeSwitcher.setAttribute('aria-label', themeSwitcherLabel)

  if (focus) {
    themeSwitcher.focus()
  }
}

window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  const storedTheme = getStoredTheme()
  if (storedTheme !== 'light' && storedTheme !== 'dark') {
    setTheme(getPreferredTheme())
  }
})

window.addEventListener('DOMContentLoaded', () => {
  showActiveTheme(getPreferredTheme())

  document.querySelectorAll('[data-bs-theme-value]')
    .forEach(toggle => {
      toggle.addEventListener('click', () => {
        const theme = toggle.getAttribute('data-bs-theme-value')
        setStoredTheme(theme)
        setTheme(theme)
        showActiveTheme(theme, true)
      })
    })
})
})()
