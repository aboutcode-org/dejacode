CSAF Models
===========

Install the code generator
--------------------------

$ pip install 'datamodel-code-generator'

Generate the models
-------------------

$ TARGET_PYTHON_VERSION=3.13

# --use-schema-description \
# --use-field-description \

$ datamodel-codegen \
    --input dejacode_toolkit/openvex/openvex_json_schema_0.2.0.json \
    --output dejacode_toolkit/openvex/__init__.py \
    --output-model-type dataclasses.dataclass \
    --input-file-type jsonschema \
    --target-python-version $TARGET_PYTHON_VERSION \
    --custom-file-header-path dejacode_toolkit/HEADER \
    --disable-future-imports

$ make valid
