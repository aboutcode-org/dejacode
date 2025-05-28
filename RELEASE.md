# Release instructions for `DejaCode

### Automated release workflow

- Create a new `release-x.x.x` branch
- Update the version in:
  - `setup.cfg`
  - `dejacode/__init__.py`
  - `CHANGELOG.rst` (set date)
- Commit and push this branch
- Create a PR and merge once approved
- Tag and push that tag. This will trigger the `create-github-release.yml`
  and `publish-docker-image.yml` GitHub workflows:
  ```
  VERSION=vx.x.x  # <- Set the new version here
  git tag -a $VERSION -m ""
  git push origin $VERSION
  ```
- Review the GitHub release created by the workflow at 
  https://github.com/aboutcode-org/dejacode/releases/
