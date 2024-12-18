CSAF Models
===========

Install the code generator
--------------------------

$ pip install 'datamodel-code-generator[http]'

Generate the models
-------------------

$ datamodel-codegen --input dejacode_toolkit/csaf/schema_v2.0/csaf_json_schema.json \
                    --output dejacode_toolkit/csaf/ \
                    --output-model-type pydantic_v2.BaseModel \
                    --input-file-type jsonschema \
                    --target-python-version 3.12
