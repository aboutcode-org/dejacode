.. _how_to_3:

=============================================
How To 3 - Downloading SBOM for Your Products
=============================================

You can obtain both **CycloneDX and SPDX Software Bill of Materials (SBOM)** documents
either through the web user interface (UI) or via the REST API endpoints.

Web User Interface
==================

1. Navigate to the product details view.
2. Click on the "Share" menu.
3. Download the desired SBOM format from the available options.

REST API Endpoints
==================

You can programmatically fetch the SBOMs using the following dedicated endpoint URLs of
the REST API:

- CycloneDX: ``/api/v2/products/{uuid}/cyclonedx_sbom/``
- SPDX: ``/api/v2/products/{uuid}/spdx_document/``

Replace ``{uuid}`` with the unique identifier of your product.

You can also provide your prefered CycloneDX spec version using the ``spec_version``
query argument such as: ``/api/v2/products/{uuid}/cyclonedx_sbom/?spec_version=1.6``
