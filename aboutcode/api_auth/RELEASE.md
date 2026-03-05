# Release instructions for `aboutcode.api_auth`

### Automated release workflow

- Create a new `aboutcode.api_auth-release-x.x.x` branch
- Update the version in:
  - `api_auth-pyproject.toml`
  - `aboutcode/api_auth/__init__.py`
- Commit and push this branch
- Create a PR and merge once approved
- Tag and push to trigger the `publish-pypi-release-aboutcode-api-auth.yml` workflow 
  that takes care of building the distribution archives and upload those to pypi::
  ```
  VERSION=x.x.x  # <- Set the new version here
  TAG=aboutcode.api_auth/$VERSION
  git tag -a $TAG -m ""
  git push origin $TAG
  ```

### Manual build

```
cd dejacode
source .venv/bin/activate
pip install flot
flot --pyproject api_auth-pyproject.toml --sdist --wheel --output-dir dist/
```

The distribution archives will be available in the local `dist/` directory.
