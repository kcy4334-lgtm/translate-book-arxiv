---
description: Release a new version to GitHub
argument-hint: <semver, e.g. 0.3.0>
---

Release version `$1` by running these two commands in order. Stop and report
immediately if either step fails — do not attempt to recover automatically.

```bash
git push origin main
git tag v$1 && git push --tags
```

`$1` is bare semver (e.g. `0.3.0`). The `v` prefix is applied only to the git
tag.

Do not skip the tag: it is the only version anchor in the repository.

If the push fails after the tag exists locally, fix the cause and push the tag
again. Do not force-overwrite a tag that is already on the remote (`git tag -f`
followed by `git push --tags --force`) without explicit user approval — someone
may already have fetched it.

**ClawHub is not part of this fork's release.**
Upstream — `deusyu/translate-book` — publishes there under the name
`translate-book`. This repository does not, and publishing a fork under a name
someone else owns is not ours to do.
