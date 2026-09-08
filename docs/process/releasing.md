# 1 Publishing Petrus

Petrus is distributed as `petrus-runtime` and imported as `petrus`. The first
release is prepared as `0.1.0a1`, with the Alpha development-status classifier.
PyPI already has an unrelated project named `petrus`. On 2026-09-08, PyPI's
project API returned 404 for `petrus-runtime` and `petrus-net`. This checks for
an existing project; it does not reserve a name or guarantee PyPI will accept it.

## 1a Version policy

`pyproject.toml` owns the version. Use three numeric components and an optional
PEP 440 prerelease suffix. Git tags prepend `v` to the exact metadata version.

| Stage | Package version example | GitHub release tag | GitHub prerelease |
| --- | --- | --- | --- |
| Alpha, APIs and capabilities still taking shape | `0.1.0a1` | `v0.1.0a1` | Yes |
| Beta, intended scope ready for broader testing | `0.1.0b1` | `v0.1.0b1` | Yes |
| Release candidate | `0.1.0rc1` | `v0.1.0rc1` | Yes |
| Ordinary pre-1.0 release | `0.1.0` | `v0.1.0` | No |

Advance the suffix for another candidate, such as `0.1.0a2`. Once an ordinary
`0.x.y` version is published, increment the patch for compatible fixes and the
minor for new capabilities or breaking API changes. Document breaking changes
explicitly. `0.x` alone is not a package-manager prerelease; `a`, `b`, and `rc`
suffixes carry that meaning. Users can opt into candidates with `--pre`, or
install a specific version such as `petrus-runtime==0.1.0a1`.

Moving to `1.0.0` requires a deliberate Navigator decision about supported APIs
and compatibility, followed by updating the release guard and this policy.
Roadmap completion never advances the major version automatically. When moving
to beta, also change the classifier to `Development Status :: 4 - Beta`.

## 1b One-time account setup

Push the publishing workflow to `henriquebastos/petrus` before creating the
release. Local project policy requires Navigator approval before that push.

In the repository's Settings > Environments, create an environment named `pypi`.
The release publication is the publishing trigger; a required environment
reviewer is optional and would add a separate approval to each release.

Sign in to PyPI and open [Publishing](https://pypi.org/manage/account/publishing/).
Add a pending GitHub publisher with these exact fields:

| Field | Value |
| --- | --- |
| PyPI project name | `petrus-runtime` |
| Owner | `henriquebastos` |
| Repository name | `petrus` |
| Workflow name | `release-check.yml` |
| Environment name | `pypi` |

The workflow field is the filename, not the displayed Actions title or its
full repository path. Trusted Publishing uses GitHub OIDC and short-lived
credentials; no stored PyPI token is needed. A pending publisher creates the
project on the first successful upload and becomes its normal publisher.
It does not reserve the package name before upload.

## 1c Prepare and publish a release

1. Set the intended version in `pyproject.toml`, update current status in the
   README and briefing, and record release notes with the capabilities,
   breaking changes, and support limits. Refresh the lock deliberately with
   `UV_FROZEN=0 uv lock`; inspect its diff for unrelated dependency changes.
2. Commit the release preparation and push after Navigator approval. Optionally
   run **Release validation and publishing** manually on that commit first.
   Manual runs qualify and retain packages without uploading to PyPI.
3. Create a GitHub release from the intended commit, using its exact version
   tag, initially `v0.1.0a1`. Mark alpha, beta, and release-candidate versions as
   prereleases. Publish the release when ready to upload to PyPI.
4. Inspect the Actions run. It validates the release tag/channel, runs the
   scheduled DST campaign and `scripts/check release`, builds the source
   archive and a wheel from that archive, checks metadata with Twine, and runs
   the README example from an isolated wheel installation. Passing artifacts
   are retained as `distributions` and uploaded by the separate `publish` job.
5. Confirm the version and both files on PyPI. In a fresh Python 3.14 environment,
   install `petrus-runtime==0.1.0a1` and run the README example. Record the
   release URL and observed result in the release milestone.

The workflow listens to `release: published`, including prereleases published
from drafts. Creating a draft, pushing a branch, or pushing a tag alone does
not upload packages. A release validates and builds the tagged checkout,
not whichever commit `main` reaches later. The workflow never creates releases.

For a local package check:

```sh
uv run --frozen python -m build
uv run --frozen twine check --strict dist/*
```

Use a fresh output directory when checking another version. The full release
qualification and its prerequisites remain in the
[development guide](development-guide.md).

## 1d Failed runs and recovery

A validation or build failure prevents the publishing job from running. Fix the
cause and prepare a new release commit and version if the source must change.
An account-configuration failure can be retried after fixing the publisher
fields or environment. Re-run only the failed publishing job so it downloads
the same retained artifacts.

An interrupted upload may have accepted the wheel or source archive before
failing. Inspect the version's files on PyPI first. The workflow deliberately
does not use `skip-existing`, so a duplicate upload fails visibly. Preserve
the retained artifacts and compare their SHA-256 digests with PyPI's files
before arranging a missing-file upload. If the artifact bytes must change,
publish a new version. PyPI does not allow replacing an uploaded filename;
deleting a release does not make its filenames reusable.

If a published version is defective, yank it through PyPI and publish a fixed
version. Editing or deleting the GitHub release does not undo a PyPI upload.

## 1e References

Checked against official documentation on 2026-09-08:

- [Create a PyPI project with a Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [Configure a GitHub publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
- [Publish using OIDC](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [GitHub release events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#release)
- [Python version specifiers](https://packaging.python.org/en/latest/specifications/version-specifiers/)
- [PyPI filename reuse policy](https://pypi.org/help/#file-name-reuse)
