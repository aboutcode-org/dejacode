Release notes
=============

### Version 5.1.1-dev

- Add visual indicator in hierarchy views, when an object on the far left or far right
  also belong or have a hierarchy (relationship tree).
  https://github.com/nexB/dejacode/issues/70

- Add search and pagination on the Product Inventory tab.
  https://github.com/nexB/dejacode/issues/3
  https://github.com/nexB/dejacode/issues/112

- Fix an issue displaying the "Delete" button in the "Edit Product Relationship"
  modal form.
  https://github.com/nexB/dejacode/issues/128

- Add support for PURL(s) in the "Add Package" modal.
  If the PURL type is supported by the packageurl_python library, a download URL
  will be generated for creating the package and submitting a scan.
  https://github.com/nexB/dejacode/issues/131

- Leverage PurlDB during the "Add Package" process.
  DejaCode will look up the PurlDB to retrieve and fetch all available data to
  create the package.
  https://github.com/nexB/dejacode/issues/131

- Populate the Package notice_text using "*NOTICE*" file content from Scan "key files".
  https://github.com/nexB/dejacode/issues/136

- Added 2 new license related fields on the Component and Package models:
  * declared_license_expression
  * other_license_expression
  https://github.com/nexB/dejacode/issues/63

- Added 2 properties on the Component and Package models:
  * declared_license_expression_spdx (computed from declared_license_expression)
  * other_license_expression_spdx (computed from other_license_expression)
  https://github.com/nexB/dejacode/issues/63

- Removed 2 fields: Package.declared_license and Component.concluded_license
  https://github.com/nexB/dejacode/issues/63

- The new license fields are automatically populated from the Package scan
  "Update packages automatically from scan".
  The new license fields are pre-filled in the Package form when using the
  "Add Package" from a PurlDB entry.
  The new license fields are pre-filled in the Component form when using the
  "Add Component from Package data".
  The license expression values provided in the form for the new field is now
  properly checked and return a validation error when incorrect.
  https://github.com/nexB/dejacode/issues/63

- Use the declared_license_expression_spdx value in SPDX outputs.
  https://github.com/nexB/dejacode/issues/63

- Add new ProductDependency model to support relating Packages in the context of a
  Product.
  https://github.com/nexB/dejacode/issues/138

- Update link references of ownership from nexB to aboutcode-org.
  https://github.com/aboutcode-org/dejacode/issues/158

### Version 5.1.0

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

- Refine the Product comparison logic for Packages.
  The type and namespace fields are now used along the name field to match similar
  Packages (excluding the version).
  https://github.com/nexB/dejacode/issues/113

- Refactor the implementation of Keywords on forms to allow more flexibilty.
  Existing Keywords are suggested for consistency but any values is now allowed.
  https://github.com/nexB/dejacode/issues/48

- Display Product inventory count on the Product list view.
  https://github.com/nexB/dejacode/issues/81

- Always display the full Package URL in the UI view including the "pkg:" prefix.
  https://github.com/nexB/dejacode/issues/115

- Add a new AboutCode tab in Package details view.
  https://github.com/nexB/dejacode/issues/42

- Enhance Package Import to support modifications.
  https://github.com/nexB/dejacode/issues/84

- Add an option on the "Add to Product" form to to replace any existing relationships
  with a different version of the same object by the selected object.
  https://github.com/nexB/dejacode/issues/12

### Version 5.0.1

- Improve the stability of the "Check for new Package versions" feature.
  https://github.com/nexB/dejacode/issues/17

- Improve the support for SourgeForge download URLs.
  https://github.com/nexB/dejacode/issues/26

### Version 5.0.0

Initial release.
