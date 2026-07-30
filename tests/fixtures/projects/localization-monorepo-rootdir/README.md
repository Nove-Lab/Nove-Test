# localization-monorepo-rootdir

`localization-shared-defect`, re-planted one directory down under a
**repo-level pytest config**. It pins the silent no-op Manual Test reported
as L1 issue 1 (2026-07-30).

## Layout

```
pytest.ini            ← repo root config; NOT part of the novetest workspace
svc/pyproject.toml    ← sub-project with NO [tool.pytest.ini_options]
svc/shared_defect/    ← identical to the localization-shared-defect fixture
svc/tests/
```

The novetest workspace is **`svc/`** (that is where `novetest init` runs).
Because `svc/` carries no pytest config of its own, pytest walks up to
`../pytest.ini` and resolves its rootdir *above* the workspace:

```
node ids       svc/tests/test_totals.py::test_total_percentage_discount_with_tax
coverage facts tests/test_totals.py
```

## What it demonstrates

Run `novetest test tests/` from `svc/`, then `novetest localization latest`.

| filter | `test_file_locations_excluded` | rank 1 |
| --- | --- | --- |
| exact match only (`088091e`) | `0` | `tests/test_totals.py::test_total_percentage_discount_with_tax` — the wave-1 P1 envelope, verbatim |
| with path-suffix re-key (today) | `7` (`basis: path_suffix`) | `shared_defect/totals.py::invoice_total` |

The `0` was the sharp part: it is exactly what a healthy no-op reports on an
ecosystem whose node ids carry no file path, so nothing in the envelope
distinguished "nothing to drop" from "the path bases never lined up".
`metadata.test_file_exclusion_basis` now names which of the two happened.
