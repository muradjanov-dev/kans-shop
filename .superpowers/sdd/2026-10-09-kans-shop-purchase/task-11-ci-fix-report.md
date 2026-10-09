# Task 11 CI workflow validation fix

Run `37982511678` failed during workflow validation with no jobs created. `gh run view` reports `conclusion: failure`, `jobs: []`, and workflow name `.github/workflows/ci.yml`.

## Root cause

`actionlint 1.7.12` reproduced three invalid expressions in `jobs.backend.env`: `runner.temp` at `ENV_FILE`, `MEDIA_ROOT`, and `PRIVATE_MEDIA_ROOT`. GitHub's [context availability table](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability) excludes `runner` from `jobs.<job_id>.env`; it is available in step-level `env` and `run`. This is a workflow validation error before runner allocation, consistent with the run having no jobs.

## Change

Replaced those three values with isolated ephemeral-runner paths under `/tmp`. Kept the empty `ENV_FILE`, synthetic tokens/database URLs, test-only media roots, read-only `contents: read` permissions, non-persisted checkout credentials, and job steps unchanged. The workflow still has no deployment job or production secret references.

## Verification

- Before the change, `actionlint .github/workflows/ci.yml` reported exactly the three disallowed `runner` context uses.
- After the change, `actionlint 1.7.12 .github/workflows/ci.yml` passed.
- Ruby YAML parsing passed.
- A workflow-semantic check confirmed backend test paths are under `/tmp`, workflow permission is limited to `contents: read`, only backend/frontend jobs exist, and no secret-context references or deployment job were introduced.
- `git diff --check` passed.

The hosted run was not re-triggered here. Root will push the commit and verify the replacement run; no application code or full test suites were changed or run.
