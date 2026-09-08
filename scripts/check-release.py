"""Refuse a release whose public tag or channel disagrees with its package."""

import json
import os
import re
import tomllib
from pathlib import Path


def main() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
    version = project["version"]
    match = re.fullmatch(r"0\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?P<pre>(?:a|b|rc)(?:0|[1-9][0-9]*))?", version)
    if match is None:
        raise SystemExit(f"Release version must follow the 0.x policy, for example 0.1.0a1; got {version!r}")

    release = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())["release"]
    if release["tag_name"] != f"v{version}":
        raise SystemExit(f"Release tag must be v{version}; got {release['tag_name']!r}")
    expected_prerelease = match["pre"] is not None
    if release["prerelease"] is not expected_prerelease:
        raise SystemExit(f"GitHub prerelease must be {expected_prerelease} for version {version}")
    if release["draft"] is not False:
        raise SystemExit("A draft release cannot publish to PyPI")
    print(f"Release matches {project['name']} {version}")


if __name__ == "__main__":
    main()
