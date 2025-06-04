Release notes
=============

### Version 5.3.1-dev (unreleased)

- Upgrade Python version to 3.13 and Django to 5.2.x
  https://github.com/aboutcode-org/dejacode/pull/315
  https://github.com/aboutcode-org/dejacode/pull/312

- Add REST API "actions" in package endpoint to track the scan status and fetch results:
  * `/packages/{uuid}/scan_info/` Scan information including the current status.
  * `/packages/{uuid}/scan_results/` Scan results.
  * `/packages/{uuid}/scan_summary/` Scan summary.
  * `/packages/{uuid}/scan_data_download_zip/` Download all scan data: results and
    summary, as a zip file.
  https://github.com/aboutcode-org/dejacode/issues/272

- Add new `is_locked` "Locked inventory" field to the ProductStatus model.
  When a Product is locked through his status, its inventory cannot be modified.
  https://github.com/aboutcode-org/dejacode/issues/189

### Version 5.3.0

- Rename ProductDependency is_resolved to is_pinned.
  https://github.com/aboutcode-org/dejacode/issues/189

- Add new fields on the Vulnerability model: `exploitability`, `weighted_severity`,
  `risk_score`. The field are displayed in all relevant part of the UI where
  vulnerability data is available.
  https://github.com/aboutcode-org/dejacode/issues/98

- Introduce a new VulnerabilityAnalysis model based on CycloneDX spec:
  https://cyclonedx.org/docs/1.6/json/#vulnerabilities_items_analysis
  A VulnerabilityAnalysis is always assigned to a Vulnerability object and a
  ProductPackage relation.
  The values for a VulnerabilityAnalysis are display in the Product "Vulnerabilities"
  tab.
  A "Edit" button can be used to open a form in a model to provided analysis data.
  Those new VEX related columns can be sorted and filtered.
  The VulnerabilityAnalysis data is exported in the VEX (only) and SBOM+VEX (combined)
  outputs.
  https://github.com/aboutcode-org/dejacode/issues/98

- Add the ability to propagate vulnerability analysis data to other affected products.
  A new "Propagate analysis to:" section in now displayed the "Vulnerability analysis"
  modal. The list of products containing the same package as the one currently being
  analysed are listed and can be selected for "analysis propagation".
  https://github.com/aboutcode-org/dejacode/issues/105

- Add vulnerabilities REST API endpoint that mimics the content and features of the
  vulnerabilities list view.
  Add `risk_score` and `affected_by_vulnerabilities` fields in Package endpoint.
  Add `vulnerability_analyses` field in Product and ProductPackage endpoints.
  Add `is_vulnerable` and `affected_by` filters in Product, Package, and ProductPackage
  endpoints.
  Add `risk_score` filter in Package endpoint.
  https://github.com/aboutcode-org/dejacode/issues/104

- Add new `is_reachable` field on the VulnerabilityAnalysis model.
  It can be used to declare if a this vulnerability is reachable, not reachable, or
  if this fact is not known in the context of a Product Package.
  Reachability column added in the "Vulnerability" tab.
  Add filter by "Reachability" from the column header.
  The is_reachable value can be set from the "Vulnerability analysis" modal form.
  Add a VulnerabilityAnalysis REST API endpoint.
  https://github.com/aboutcode-org/dejacode/issues/103

- Add `override_unknown` option in `update_from_data` method.
  This is enabled in the context of updating Package data from the PurlDB, a Scan, and
  an import. Fields with "unknown" values will be override with values available in the
  new `data` dict.
  https://github.com/aboutcode-org/dejacode/issues/202

- Add the `vulnerabilities_risk_threshold` field to the Product and
  DataspaceConfiguration models.
  This threshold helps prioritize and control the level of attention to vulnerabilities.
  https://github.com/aboutcode-org/dejacode/issues/97

- Add the `vulnerabilities_risk_threshold` field to the Product and
  DataspaceConfiguration models.
  This threshold helps prioritize and control the level of attention to vulnerabilities.
  https://github.com/aboutcode-org/dejacode/issues/97

- Add the ability to download a CSAF VEX document from the Product details view "Share"
  menu.
  https://github.com/aboutcode-org/dejacode/issues/107

- Add exposure_factor field to the ProductItemPurpose model and a weighted_risk_score
  on the ProductPackage model.
  The weighted_risk_score is computed from the package.risk_score and
  purpose.exposure_factor values.
  https://github.com/aboutcode-org/dejacode/issues/102

- Add the vulnerability icon in Product list view.
  A "Is Vulnerable" filter is also available.
  The count in the Vulnerability tab was improve to include the count of affected
  packages and the count of unique vulnerabilities.
  Note that those count reflect the current risk threshold.
  https://github.com/aboutcode-org/dejacode/issues/102

- Enable the delete_selected action on RequestTemplateAdmin.
  https://github.com/aboutcode-org/dejacode/issues/243

- The data rendering format was simplified for improved readability from
  "Jan. 27, 2025, 07:55:54 a.m. UTC" to "Jan 27, 2025, 7:55 AM UTC".
  The dates are now always rendered using this same format across the app.
  The user timezone is automatically discovered and activated to the whole app using
  the browser JavaScript `timeZone` API
  The user's automatic timezone can be overridden using the new
  ``DejacodeUser.timezone`` database field.
  The timezone value can be defined from the User > "Profile Settings" form.
  This value always takes precedence when defined.
  In case the timezone is not defined by the user, or cannot be detected from the
  browser, the date rendering always fallback to UTC.
  Note: all the "humanized dates" such as "Modified 23 hours ago" have the whole
  date syntax available in their `title` option, available on hovering the text with
  the cursor for a couple seconds.
  https://github.com/aboutcode-org/dejacode/issues/243

- Set the "usage_policy" in update_fields list in SetPolicyFromLicenseMixin.
  The associated package/license policy was properly set on the model in
  SetPolicyFromLicenseMixin but the usage_policy entry was missing from the
  update_fields. As a result the usage_policy value was not included in the UPDATE.
  https://github.com/aboutcode-org/dejacode/issues/200

- Improve the Owner assignment process on a Product/Component form.
  Owner not found in the Dataspace are now automatically created.
  https://github.com/aboutcode-org/dejacode/issues/239

- Updated the label of the following Product actions.
  The labels were updated everywhere in the UI (page title, documentation,
  import log, etc...) for consistency:
  - Import data from Scan -> Import ScanCode scan results
  - Load Packages from SBOMs -> Import SBOM
  - Import Packages from manifests -> Import Package manifests
  - Pull ScanCode.io Project data -> Import ScanCode.io project
  Improve the rendering and layout of the Import related forms for consistency,
  simplicity, and readability.
  https://github.com/aboutcode-org/dejacode/issues/241

- Refine the way the PURL fragments are handled in searches.
  https://github.com/aboutcode-org/dejacode/issues/286

- Fix an issue with ``urlize_target_blank`` when the URL contains curly braces.

- Add the ability to download Product "Imports" input file.
  https://github.com/aboutcode-org/dejacode/issues/156

- Fix a logic issue in the ``ImportPackageFromScanCodeIO.import_package`` that occurs when
  multiple packages with the same PURL, but different download_url or filename,
  are present in the Dataspace.
  https://github.com/aboutcode-org/dejacode/issues/295

- Fix a logic issue in the ``ImportPackageFromScanCodeIO.import_dependencies`` to
  prevent the creation of duplicated "resolved" dependencies.
  https://github.com/aboutcode-org/dejacode/issues/297

- Display the filename/download_url in the Inventory tab.
  https://github.com/aboutcode-org/dejacode/issues/303

- Improve exception support in improve_packages_from_purldb task.
  In case of an exception, the error is properly logged on the Import instance.
  https://github.com/aboutcode-org/dejacode/issues/303

- Refine the ``update_from_purldb`` function to avoid any IntegrityError.
  Also, when multiple entries are returned from the PurlDB, only the common values are
  merged and kept for the data update.
  https://github.com/aboutcode-org/dejacode/issues/303

- Add a new "Package Set" tab to the Package details view.
  This tab displays related packages grouped by their normalized ("plain") Package URL.
  https://github.com/aboutcode-org/dejacode/issues/276

- Refine get_purldb_entries to compare on plain PackageURL.
  Including the qualifiers and subpaths in the comparison was too restrictive.
  https://github.com/aboutcode-org/dejacode/issues/307

### Version 5.2.1

- Fix the models documentation navigation.
  https://github.com/aboutcode-org/dejacode/issues/182

- Fix the validity of SPDX outputs.
  https://github.com/aboutcode-org/dejacode/issues/180

- Add ability to start and delete package scans from the Product inventory tab.
  https://github.com/aboutcode-org/dejacode/pull/281

### Version 5.2.0

- Add visual indicator in hierarchy views, when an object on the far left or far right
  also belong or have a hierarchy (relationship tree).
  https://github.com/aboutcode-org/dejacode/issues/70

- Add search and pagination on the Product Inventory tab.
  https://github.com/aboutcode-org/dejacode/issues/3
  https://github.com/aboutcode-org/dejacode/issues/112

- Fix an issue displaying the "Delete" button in the "Edit Product Relationship"
  modal form.
  https://github.com/aboutcode-org/dejacode/issues/128

- Add support for PURL(s) in the "Add Package" modal.
  If the PURL type is supported by the packageurl_python library, a download URL
  will be generated for creating the package and submitting a scan.
  https://github.com/aboutcode-org/dejacode/issues/131

- Leverage PurlDB during the "Add Package" process.
  DejaCode will look up the PurlDB to retrieve and fetch all available data to
  create the package.
  https://github.com/aboutcode-org/dejacode/issues/131

- Populate the Package notice_text using "*NOTICE*" file content from Scan "key files".
  https://github.com/aboutcode-org/dejacode/issues/136

- Added 2 new license related fields on the Component and Package models:
  * declared_license_expression
  * other_license_expression
  https://github.com/aboutcode-org/dejacode/issues/63

- Added 2 properties on the Component and Package models:
  * declared_license_expression_spdx (computed from declared_license_expression)
  * other_license_expression_spdx (computed from other_license_expression)
  https://github.com/aboutcode-org/dejacode/issues/63

- Removed 2 fields: Package.declared_license and Component.concluded_license
  https://github.com/aboutcode-org/dejacode/issues/63

- The new license fields are automatically populated from the Package scan
  "Update packages automatically from scan".
  The new license fields are pre-filled in the Package form when using the
  "Add Package" from a PurlDB entry.
  The new license fields are pre-filled in the Component form when using the
  "Add Component from Package data".
  The license expression values provided in the form for the new field is now
  properly checked and return a validation error when incorrect.
  https://github.com/aboutcode-org/dejacode/issues/63

- Use the declared_license_expression_spdx value in SPDX outputs.
  https://github.com/aboutcode-org/dejacode/issues/63

- Add new ProductDependency model to support relating Packages in the context of a
  Product.
  https://github.com/aboutcode-org/dejacode/issues/138

- Add a task scheduler service to the Docker Compose stack.
  This service runs a dedicated ``setupcron`` management command to create the
  application's scheduled cron jobs.
  The scheduler is configured to run the daily vulnerabilities update task.
  https://github.com/aboutcode-org/dejacode/issues/94

- Add a new Vulnerability model and all the code logic to fetch and create
  Vulnerability records and assign those to Package/Component through ManyToMany
  relationships.
  A fetchvulnerabilities management command is available to fetch all the relevant
  data from VulnerableCode for a given Dataspace.
  The latest vulnerability data refresh date is displayed in the Admin dashboard in a
  new "Data updates" section in the bottom right corner.
  It is also available in the "Integration Status" page.
  The Package/Component views that display vulnerability information (icon or tab)
  are now using the data from the Vulnerability model in place of calling the
  VulnerableCode API on each request. This results into much better performances as
  we do not depend on the VulnerableCode service to render the DejaCode view anymore.
  Also, this will make Vulnerability data available in the Reporting system.
  The vulnerability icon is displayed next to the Package/Component identifier in the
  Product views: "Inventory", "Hierarchy", "Dependencies" tabs.
  The vulnerability data is available in Reporting either through the is_vulnerable
  property on Package/Component column template or going through the full
  affected_by_vulnerabilities m2m field.
  This is available in both Query and ColumnTemplate.
  The vulnerabilities are fetched each time a Package is created/modified
  (note that a purl is required on the package for the lookup).
  Also, all the Packages of a Product are updated with latest vulnerabilities from
  the VulnerableCode service following importing data in Product using:
  - Import data from Scan
  - Load Packages from SBOMs
  - Import Packages from manifests
  - Pull ScanCode.io Project data
  https://github.com/aboutcode-org/dejacode/issues/94

- Add a new Vulnerabilities list available from the "Tools" menu when
  ``enable_vulnerablecodedb_access`` is enabled on a Dataspace.
  This implementation focuses on ranking/sorting: Vulnerabilities can be sorted and
  filtered by severity score.
  It's also possible to sort by the count of affected packages to help prioritize.
  https://github.com/aboutcode-org/dejacode/issues/94

- Display warning when a "download_url" could not be determined from a PURL in
  "Add Package".
  https://github.com/aboutcode-org/dejacode/issues/163

- Add a Vulnerabilities tab in the Product details view.
  https://github.com/aboutcode-org/dejacode/issues/95

- Add a "Improve Packages from PurlDB" action in the Product details view.
  https://github.com/aboutcode-org/dejacode/issues/45

- Add the ability to download the CycloneDX VEX-only and SBOM+VEX combined outputs.
  https://github.com/aboutcode-org/dejacode/issues/108

### Version 5.1.0

- Upgrade Python version to 3.12 and Django to 5.0.x
  https://github.com/aboutcode-org/dejacode/issues/50

- Replace Celery by RQ for async job queue and worker.
  https://github.com/aboutcode-org/dejacode/issues/6

- Add support for CycloneDX spec version "1.6".
  In the UI and API, older spe version such as "1.4" and "1.5" are also available as
  download.
  https://github.com/aboutcode-org/dejacode/pull/79

- Lookup in PurlDB by purl in Add Package form.
  When a Package URL is available in the context of the "Add Package" form,
  for example when using a link from the Vulnerabilities tab,
  data is fetched from the PurlDB to initialize the form.
  https://github.com/aboutcode-org/dejacode/issues/47

- If you select two versions of the same Product in the Product list, or two different
  Products, and click the Compare button, you can now download the results of the
  comparison to a .xlsx file, making it easy to share the information with your
  colleagues.
  https://github.com/aboutcode-org/dejacode/issues/7

- Add dark theme support in UI.
  https://github.com/aboutcode-org/dejacode/issues/25

- Add "Load Packages from SBOMs", "Import scan results", and
  "Pull ScanCode.io project data" feature as Product action in the REST API.
  https://github.com/aboutcode-org/dejacode/issues/59

- Add REST API endpoints to download SBOMs as CycloneDX and SPDX.
  https://github.com/aboutcode-org/dejacode/issues/60

- Refactor the "Import manifest" feature as "Load SBOMs".
  https://github.com/aboutcode-org/dejacode/issues/61

- Add support to import packages from manifest.
  https://github.com/aboutcode-org/dejacode/issues/65

- Add a vulnerability link to the VulnerableCode app in the Vulnerability tab.
  https://github.com/aboutcode-org/dejacode/issues/4

- Add a DEJACODE_SUPPORT_EMAIL setting for support email address customization.
  https://github.com/aboutcode-org/dejacode/issues/76

- Show the individual PURL fields in the Package details view.
  https://github.com/aboutcode-org/dejacode/issues/83

- Fix the logout link of the admin app.
  https://github.com/aboutcode-org/dejacode/issues/89

- Display full commit in the version displayed in the UI
  https://github.com/aboutcode-org/dejacode/issues/88

- Refine the Product comparison logic for Packages.
  The type and namespace fields are now used along the name field to match similar
  Packages (excluding the version).
  https://github.com/aboutcode-org/dejacode/issues/113

- Refactor the implementation of Keywords on forms to allow more flexibilty.
  Existing Keywords are suggested for consistency but any values is now allowed.
  https://github.com/aboutcode-org/dejacode/issues/48

- Display Product inventory count on the Product list view.
  https://github.com/aboutcode-org/dejacode/issues/81

- Always display the full Package URL in the UI view including the "pkg:" prefix.
  https://github.com/aboutcode-org/dejacode/issues/115

- Add a new AboutCode tab in Package details view.
  https://github.com/aboutcode-org/dejacode/issues/42

- Enhance Package Import to support modifications.
  https://github.com/aboutcode-org/dejacode/issues/84

- Add an option on the "Add to Product" form to to replace any existing relationships
  with a different version of the same object by the selected object.
  https://github.com/aboutcode-org/dejacode/issues/12

### Version 5.0.1

- Improve the stability of the "Check for new Package versions" feature.
  https://github.com/aboutcode-org/dejacode/issues/17

- Improve the support for SourgeForge download URLs.
  https://github.com/aboutcode-org/dejacode/issues/26

### Version 5.0.0

Initial release.
