---
description: Release a new version to GitHub
argument-hint: <semver, e.g. 0.3.0>
---

Release version `$1` by running these commands in order. Stop and report
immediately if any step fails, do not attempt to recover automatically.

```bash
git push origin main
git tag v$1 && git push origin v$1
python tools/build_plugin_branch.py --ref v$1 && git push origin claude-plugin
```

The new tag alone, not `--tags`: that pushes every local tag, including one
made for a version that was never published.

If the demo book was rebuilt for this release, attach it to the new GitHub
release as `looped-flows_ko.pdf` straight after the tag is pushed. The README
links to `releases/download/v$1/looped-flows_ko.pdf`, and until the file is
there the link is dead.

The third line refreshes the branch Anthropic's plugin directory follows. It
builds from the tag the second line made, and the directory publishes the new
version from there.

`$1` is bare semver (e.g. `0.3.0`). The `v` prefix is applied only to the git
tag.

Do not skip the tag: it is the only version anchor in the repository.

If the push fails after the tag exists locally, fix the cause and push the tag
again. Do not force-overwrite a tag that is already on the remote (`git tag -f`
followed by `git push --tags --force`) without explicit user approval, someone
may already have fetched it.

**ClawHub is not part of this fork's release.**
Upstream, `deusyu/translate-book`, publishes there under the name
`translate-book`. This repository does not, and publishing a fork under a name
someone else owns is not ours to do.
