# Nove Test — User Documentation

Nove Test is a **polyglot test orchestration CLI**. One binary wraps six
native test engines behind a single command surface. The `novetest test`
verb executes your suite through the native engine, persists a Run Record,
derives coverage / regression / fault-localization facts, and synthesizes a
prioritized, evidence-cited recommendation — all under one stable
`novetest/v1` JSON contract.

This documentation ships in **two parallel sets** — same flow, same
verbs, same conceptual model, but tuned to two very different audiences:

| If you are … | Read … |
|---|---|
| **A human at a terminal**, running `novetest` interactively, watching the output scroll by | [`human/`](./human/README.md) — examples are scannable terminal text (glyph + summary lines), prose is narrative, no JSON parsing required. |
| **An AI agent**, a CI pipeline, a script, or any caller that consumes the structured envelope | [`agent/`](./agent/README.md) — examples are full JSON envelopes (`schema: "novetest/v1"`), exit-code tables, deterministic routing on `recommendations[].category`. |

The two sets cover the **same surface in the same order**:

| Topic | Human file | Agent file |
|---|---|---|
| Audience + working example | [human/README.md](./human/README.md) | [agent/README.md](./agent/README.md) |
| Install + sanity checks | [human/install.md](./human/install.md) | [agent/install.md](./agent/install.md) |
| The canonical happy path | [human/quick-start.md](./human/quick-start.md) | [agent/quick-start.md](./agent/quick-start.md) |
| Per-language toolchains | [human/languages.md](./human/languages.md) | [agent/languages.md](./agent/languages.md) |
| Reading the output, follow-ups | [human/after-test.md](./human/after-test.md) | [agent/after-test.md](./agent/after-test.md) |
| Deeper verbs (memory, replay, …) | [human/advanced.md](./human/advanced.md) | [agent/advanced.md](./agent/advanced.md) |
| Common errors + fixes | [human/troubleshooting.md](./human/troubleshooting.md) | [agent/troubleshooting.md](./agent/troubleshooting.md) |

---

## Which mode does Nove Test default to?

It auto-detects, and you almost never have to override:

| Where you are | Default output mode | How to lock it explicitly |
|---|---|---|
| Interactive terminal (stdout is a TTY) | `text` (human surface) | `novetest --output text <verb>` or `NOVETEST_OUTPUT=text` |
| Piped, redirected, or scripted | `json` (full envelope) | `novetest --output json <verb>` or `NOVETEST_OUTPUT=json` |
| Streaming many runs (CI log) | (opt-in) `ndjson` | `novetest --output ndjson <verb>` or `NOVETEST_OUTPUT=ndjson` |

Precedence: **explicit `--output` flag > `NOVETEST_OUTPUT` env > TTY
auto-detect**. The `--output` flag is global and may appear **anywhere**
in the command line (it is stripped before the verb is dispatched).
JSON mode is pretty-printed (indent 2, keys sorted alphabetically); NDJSON
is one compact line per envelope.

AI agents should pin `NOVETEST_OUTPUT=json` once at session start and parse
the envelope deterministically. Humans get pretty text on a TTY by default
and can ignore the JSON path entirely.

---

## Status

- **Release**: v0.1.2 (Latest on GitHub Releases)
- **Platforms**: Linux x86_64, Linux aarch64, macOS universal2 (one fat
  binary covering Intel + Apple Silicon), Windows x86_64.
- **Schema**: `novetest/v1` — top-level keys
  `{schema, command, ok, data, errors, warnings}`.
- **Engines** (ecosystem → `engine_name`, with their real constraints):

  | Ecosystem | `engine_name` | Constraint | Coverage facts |
  |---|---|---|---|
  | python | `pytest` | — | yes |
  | javascript-typescript | `jest` | — | yes |
  | java | `junit` | JUnit 5 (Jupiter) only — JUnit 4 / TestNG rejected | yes |
  | go | `go-test` | — | **no** (tests run, but coverage is not consumed) |
  | rust | `cargo-test` | requires cargo-nextest | yes |
  | dotnet | `xunit` | xUnit v2 only — NUnit / MSTest rejected | yes |

Nove Test does **not** replace your test runner — it shells out to the
native engine you already use. See the project [README](../../README.md) for
the highest-level pitch and roadmap. This documentation focuses on **using**
the CLI; design internals (recommendation taxonomy, SBFL math, replay
classification) live under [`design/`](..).
