## Release setup

This project is prepared for tagged releases and PyPI Trusted Publishing, but some release prerequisites live outside the repository.

## In-repo release shape

- Release tags must match `v*`
- The release workflow should build `dist/*`
- The workflow should attach the wheel and source distribution to the GitHub Release
- The same built artifacts should be used for PyPI publishing

## GitHub Release artifacts

Each release should publish these artifacts on the GitHub Release page:

- `dist/*.whl`
- `dist/*.tar.gz`

## PyPI Trusted Publishing

PyPI publishing is expected to use Trusted Publishing rather than username and password credentials or API token secrets.

The GitHub Actions workflow should use the environment named `pypi` and request OIDC-based publishing for PyPI.

## External prerequisites

PyPI trusted publisher registration must be configured on PyPI for `alma3lol/SpeakToMeMCP`.

That external registration cannot be validated purely in-repo. A correct workflow file is necessary, but publish will still fail until the PyPI-side trusted publisher entry exists and matches the repository `alma3lol/SpeakToMeMCP`, workflow file `.github/workflows/release.yml`, and environment `pypi`.

## Minimum checklist

1. Create a version tag matching `v*`
2. Confirm the workflow is configured to create a GitHub Release
3. Confirm the workflow uploads the wheel and sdist as GitHub Release artifacts
4. Confirm the workflow publishes to PyPI with Trusted Publishing
5. Confirm PyPI has a trusted publisher registered for this repository and workflow
