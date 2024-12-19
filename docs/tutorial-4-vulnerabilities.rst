.. _user_tutorial_4_vulnerabilities:

Tutorial 4 - Managing Product Vulnerabilities
=============================================

Sign into DejaCode.

Create a Product
----------------

1. Select :guilabel:`Products` from the main menu bar.

2. Click the green :guilabel:`Add Product` button. Enter the values you know.
   Refer to :ref:`data_model_product` for details about each field.

3. Set a **name**, then click the :guilabel:`Add Product` button at the bottom
   of the form.

Load Scan Results to your Product
---------------------------------

1. Download the following ScanCode Scan results example from:

   `<https://github.com/aboutcode-org/dejacode/tree/main/docs/sboms/starship_engine_2.0_scan_results.json>`_.

2. On the Product details page, from the :guilabel:`Action` dropdown, select
   :guilabel:`Import from Scan`:

   * Click the :guilabel:`Choose File` button under the **Upload file** field.
   * Select the **starship_engine_2.0_scan_results.json** file and click the
     :guilabel:`Open` button.
   * Click the :guilabel:`Import` button.

3. View your import results in the :guilabel:`Inventory` tab.

Review Vulnerabilities Affecting Your Product
---------------------------------------------

1. Navigate to the :guilabel:`Inventory` tab on the Product details page.
   Vulnerable packages are marked with an icon.

2. Open the :guilabel:`Vulnerability` tab for a comprehensive view of all
   vulnerabilities associated with your Product.

Conduct Vulnerability Analysis
------------------------------

1. Review each vulnerability in the :guilabel:`Vulnerability` tab.
2. Add details or analysis for each vulnerability as needed, which will
   enhance reporting and exports.

Export CycloneDX SBOM with VEX
------------------------------

1. On the Product details page, from the :guilabel:`Share` dropdown, select
   :guilabel:`CycloneDX SBOM + VEX`.

2. The analysis details you provide for product package vulnerabilities are
   included in the ``vulnerabilities`` section of the CycloneDX VEX output.
