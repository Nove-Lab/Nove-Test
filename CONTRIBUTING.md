# Contributing to Nove Test

Thanks for your interest. Adoption is the bottleneck for Nove Test
right now — pull requests, issue reports, and documentation
improvements are all very welcome.

## License of your contribution

Nove Test is released under the Apache License 2.0 (see [`LICENSE`](./LICENSE)).
Contributions are accepted under a Contributor License Agreement:

- Individual contributors: [`CLA.md`](./CLA.md)
- Organization-affiliated contributors: [`CCLA.md`](./CCLA.md)

The CLA is **not a copyright assignment** — you keep your copyright.
The CLA grants Nove Lab a perpetual, royalty-free, sublicensable
license that lets us relicense future versions if strategically
necessary (e.g., issuing a v0.X.0 under different terms). This is the
standard pattern used by Apache, Kubernetes (CNCF), Google, and
Microsoft open-source projects.

## How to contribute

1. Fork the repository.
2. Create a feature branch from `main`.
3. Make your change. Run `uv run pytest -q tests/unit tests/integration`
   and `uv run mypy --strict src/novetest` locally to verify.
4. Open a pull request against `main`.
5. On your first PR, the CLA Assistant bot will comment with a link to
   sign the CLA. Sign once and all future PRs are covered.
6. A maintainer reviews. We aim for first response within a week.

## Reporting bugs

Open a GitHub issue with:

- Minimal reproduction steps
- Expected vs actual output
- `novetest --version --output json` output
- Operating system and Python version (if relevant)

## Commercial license inquiries

For commercial terms, custom indemnification, support contracts, or
dual-licensing of derivative products: `admin.nove@gmail.com`
