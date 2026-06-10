# Third-Party Notices

Nove Test redistributes or links to third-party software covered by
the licenses below. Apache License 2.0 section 4(d) requires
preservation of these notices in all derivative works.

## Runtime dependencies (shipped in the published wheel)

### cyclopts (>=3.0)

- Project: https://github.com/BrianPugh/cyclopts
- License: Apache License 2.0
- Copyright (c) Brian Pugh and cyclopts contributors

### numpy (>=1.26)

- Project: https://github.com/numpy/numpy
- License: BSD 3-Clause License
- Copyright (c) 2005-present, NumPy Developers

The full text of each license is reproduced in the installed package
metadata (pip-managed under `*.dist-info/`). Distribution of those
metadata files satisfies the respective attribution clauses.

## Vendored binary (sidecar in the published wheel)

### JUnit Platform Console Standalone (1.11.4)

- File: `src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar`
- Project: https://github.com/junit-team/junit5
- License: Eclipse Public License 2.0
- SHA-256 pin: `b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc`
- Distributed unmodified per decision `agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md`.
- Per-file NOTICES (with EPL 2.0 section 3.3 unmodified-distribution
  statement) live alongside the jar at
  [`src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt`](./src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt).

## Install-time bootstrap (downloaded by PyApp on first run)

### PyApp (0.22.0)

- Project: https://github.com/ofek/pyapp
- License: Apache License 2.0 OR MIT
- Copyright (c) Ofek Lev

### python-build-standalone CPython

- Project: https://github.com/indygreg/python-build-standalone
- License: Python Software Foundation License plus permissive licenses
  for sub-components (OpenSSL, libffi, ncurses, etc.)

These artifacts are not shipped inside the Nove Test wheel — PyApp
downloads them on first invocation of the installed binary. They are
listed here for completeness of attribution.
