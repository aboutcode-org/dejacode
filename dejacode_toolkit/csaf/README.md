CSAF Models
===========

Install the code generator
--------------------------

$ pip install 'datamodel-code-generator[http]'

Generate the models
-------------------

$ TARGET_PYTHON_VERSION=3.12
$ datamodel-codegen \
    --input dejacode_toolkit/csaf/schema_v2.0/csaf_json_schema.json \
    --output dejacode_toolkit/csaf/ \
    --output-model-type pydantic_v2.BaseModel \
    --input-file-type jsonschema \
    --target-python-version $TARGET_PYTHON_VERSION \
    --custom-file-header-path dejacode_toolkit/csaf/HEADER \
    --use-schema-description \
    --use-default-kwarg

$ rm dejacode_toolkit/csaf/cvss_v2.py dejacode_toolkit/csaf/cvss_v3.py
$ make valid
