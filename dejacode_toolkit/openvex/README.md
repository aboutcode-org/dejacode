OpenVEX Models
==============

Install the code generator
--------------------------

$ pip install 'datamodel-code-generator'

Generate the models
-------------------

$ datamodel-codegen \
    --input dejacode_toolkit/openvex/openvex_json_schema_0.2.0.json \
    --output dejacode_toolkit/openvex/__init__.py \
    --output-model-type msgspec.Struct \
    --input-file-type jsonschema \
    --target-python-version 3.13 \
    --custom-file-header-path dejacode_toolkit/HEADER \
    --wrap-string-literal \
    --use-double-quotes \
    --disable-future-imports
