Release notes
=============

### Version 5.1.0-dev

- Upgrade Python version to 3.12 and Django to 5.0.x
  https://github.com/nexB/dejacode/issues/50

- Replace Celery by RQ for async job queue and worker.
  https://github.com/nexB/dejacode/issues/6

- Add support for CycloneDX spec version "1.6".
  In the UI and API, older spe version such as "1.4" and "1.5" are also available as
  download.
  https://github.com/nexB/dejacode/pull/79

- Lookup in PurlDB by purl in Add Package form.
  When a Package URL is available in the context of the "Add Package" form,
  for example when using a link from the Vulnerabilities tab,
  data is fetched from the PurlDB to initialize the form.
  https://github.com/nexB/dejacode/issues/47

- If you select two versions of the same Product in the Product list, or two different
  Products, and click the Compare button, you can now download the results of the
  comparison to a .xlsx file, making it easy to share the information with your
  colleagues.
  https://github.com/nexB/dejacode/issues/7

- Add dark theme support in UI.
  https://github.com/nexB/dejacode/issues/25

- Add "Load Packages from SBOMs", "Import scan results", and
  "Pull ScanCode.io project data" feature as Product action in the REST API.
  https://github.com/nexB/dejacode/issues/59

- Add REST API endpoints to download SBOMs as CycloneDX and SPDX.
  https://github.com/nexB/dejacode/issues/60

- Refactor the "Import manifest" feature as "Load SBOMs".
  https://github.com/nexB/dejacode/issues/61

- Add support to import packages from manifest.
  https://github.com/nexB/dejacode/issues/65

- Add a vulnerability link to the VulnerableCode app in the Vulnerability tab.
  https://github.com/nexB/dejacode/issues/4

- Add a DEJACODE_SUPPORT_EMAIL setting for support email address customization.
  https://github.com/nexB/dejacode/issues/76

- Show the individual PURL fields in the Package details view.
  https://github.com/nexB/dejacode/issues/83

- Fix the logout link of the admin app.
  https://github.com/nexB/dejacode/issues/89

- Display full commit in the version displayed in the UI
  https://github.com/nexB/dejacode/issues/88

### Version 5.0.1

- Improve the stability of the "Check for new Package versions" feature.
  https://github.com/nexB/dejacode/issues/17

- Improve the support for SourgeForge download URLs.
  https://github.com/nexB/dejacode/issues/26

### Version 5.0.0

Initial release.
