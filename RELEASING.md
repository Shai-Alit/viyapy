# Releasing viyapy

Releases are published to PyPI automatically by `.github/workflows/release.yml`
when a `v*` tag is pushed. Publishing uses **PyPI Trusted Publishing (OIDC)**, so
no API token is stored in the repository.

## One-time setup (per project)

Configure the trusted publisher on PyPI so it will accept uploads from this
workflow:

1. Go to the [viyapy project on PyPI](https://pypi.org/project/viyapy/) →
   *Manage* → *Publishing* (or, for the very first release, use PyPI's
   *pending publisher* form under your account).
2. Add a **GitHub** publisher with:
   - Owner: `Shai-Alit`
   - Repository: `viyapy`
   - Workflow name: `release.yml`
   - Environment: `pypi`
3. In GitHub → *Settings* → *Environments*, create an environment named `pypi`
   (optionally add a required reviewer so a human approves each publish).

## Cutting a release

1. Make sure `main` is green and the `CHANGELOG.md` `[Unreleased]` section lists
   everything in the release.
2. Move the `[Unreleased]` entries under a new `[X.Y.Z]` heading with today's
   date, and set `version` in `pyproject.toml` to `X.Y.Z` (no `.devN` suffix).
   Commit on a branch and merge via PR.
3. From the merge commit on `main`, tag and push:

   ```bash
   git checkout main && git pull
   git tag -a vX.Y.Z -m "viyapy X.Y.Z"
   git push origin vX.Y.Z
   ```

4. The `Release` workflow builds the sdist + wheel, runs `twine check`, verifies
   the tag matches the built version, smoke-installs the wheel in a clean venv,
   and publishes to PyPI. Watch the run; approve the `pypi` environment if a
   reviewer is required.
5. Confirm the new version on [PyPI](https://pypi.org/project/viyapy/) and that
   the docs site redeployed.

## After a release

Bump `version` in `pyproject.toml` to the next planned version with a `.dev0`
suffix (e.g. `3.0.1.dev0`) and add a fresh empty `[Unreleased]` section to
`CHANGELOG.md`.

## If something goes wrong

PyPI does not allow re-uploading a version that already exists. If a release is
broken, yank it on PyPI and publish a new patch version — never try to reuse a
version number.
