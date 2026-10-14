# EXOS CLI Crawler Suite

## Overview

Three self-contained SecureCRT Python scripts record the Extreme EXOS / Switch Engine CLI help tree. EXOS has a flat CLI (no mode hierarchy), so each crawler starts at one or more command roots, sends `<command> ?`, parses the help text, and follows literal keywords.

| Script | Starting root(s) | Confirmation word | Output directory |
|---|---|---|---|
| `exos-show-help-crawler.py` | `show` | `SHOWCRAWL` | `C:\scripts\secure-crt\outputs\exos-show-help\` |
| `exos-config-help-crawler.py` | `configure` | `CONFIGCRAWL` | `C:\scripts\secure-crt\outputs\exos-config-help\` |
| `exos-config-mode-crawler.py` (context crawler) | `configure`, `enable`, `disable`, `create`, `delete`, `unconfigure` | `CONTEXTCRAWL` | `C:\scripts\secure-crt\outputs\exos-context-help\` |

Output file name: `YYYYMMDD-HHMMSS_<HOSTNAME>_<suffix>.txt`, where the suffix is `show-help`, `config-help` or `context-help`.

The output directory is a constant (`OUTPUT_ROOT`) at the top of each script. The repository principle of "no hardcoded paths" is not met by these crawlers: edit `OUTPUT_ROOT` if `C:\scripts\secure-crt\outputs\` does not suit your machine. Each script is self-contained (the shared helper block is duplicated in all three); this guide covers all three rather than one README per script.

## Safety model

- Only question-mark help is sent (`<command> ?`, no Enter) and then canceled with Ctrl+C. Discovered commands are never executed.
- Commands that ARE executed (Enter pressed), all read-only except paging:
  - `show management` (read the CLI paging state)
  - `show version`, `show switch` (platform metadata)
  - `disable cli paging` and later `enable cli paging` (see below)
- Requires an active, connected tab at an EXOS prompt ending in `#` or `>`.
- SecureCRT session logging is used to capture help text. If the session was already logging, it is stopped during the crawl and re-started (append) afterward.

## Run flow

1. Prompt detection, then a confirmation dialog; type the confirmation word.
2. The output file is created with a header (prompt, roots, limits) and platform metadata.
3. CLI paging is handled (below), then the crawl runs.
4. A final summary is appended and a message box shows the counts.

## Limits

| Constant | Show | Config | Context |
|---|---|---|---|
| Max depth | `MAX_DEPTH = 25` | `MAX_DEPTH = 25` | `MAX_DEPTH_PER_ROOT = 25` |
| Max help queries | `MAX_COMMANDS = 10000` | `MAX_COMMANDS = 20000` | `MAX_COMMANDS_PER_ROOT = 8000`, `MAX_TOTAL_COMMANDS = 30000` |
| Max command tokens | 24 | 24 | 24 |
| Placeholder branches per query | n/a | n/a | `MAX_PLACEHOLDER_BRANCHES_PER_QUERY = 2` |

Timing: `IDLE_SECONDS = 1`, `MAX_IDLE_CHECKS = 180` (about 180 s of continuous output before a query is declared incomplete).

## Behavior details

### Duplicate prevention
A command is recorded when it is enqueued, not only when processed, so alternate paths cannot queue it twice (case-insensitive). The context crawler shares this set across all roots. The final summary reports "Duplicate commands not re-queued". Depth, command-count and token limits are unchanged.

### Timeouts (incomplete queries)
`wait_for_screen_idle()` returns `False` if the screen never goes idle. A query where either wait (after `?`, or after Ctrl+C) times out is logged as `INCOMPLETE QUERY`; its output is not parsed and no children are queued. The count appears as "Incomplete queries (timeouts)" in the summary and message box. Raise `MAX_IDLE_CHECKS` or the delays on slow links, then re-run.

### Error responses
Output containing `%%` / `%` lines or "invalid input", "ambiguous command", "incomplete command" or "unknown command" is logged as `ERROR RESPONSE`, counted, not parsed, and not expanded.

### CLI paging
Before changing anything the scripts run `show management` and look for a `CLI paging : Enabled|Disabled` line.

- Enabled: paging is disabled for the crawl and `enable cli paging` is sent on completion, cancellation or error (`finally` block).
- Disabled: paging is left untouched and nothing is restored.
- State not readable: a Yes/No dialog explains the limitation (paging will be disabled and then set to *enabled*, the EXOS default, even if it was disabled before). Answering No stops before paging is changed.

The `show management` field label is an assumption (see Unverified items). Detection failure falls back to the confirmation dialog.

### Platform metadata
`show version` and `show switch` output is captured and the EXOS/Switch Engine version, system type, boot ROM and hardware lines are parsed into the header. A failed, incomplete or unparsable metadata query is recorded in the file and counted ("Metadata query failures") but does not stop the crawl. The raw captured text also remains in the output file.

### Parsing
Help lines of the form `token  description` are classified:

- Literal: lowercase, starts with a letter, no underscore (e.g. `detail`, `ports`). Followed.
- Placeholder: starts with `<`, `[`, `{` or `|`, contains `_`, or contains an uppercase letter (e.g. `<vlan_name>`, `VR-NAME`). Recorded, not followed by the show/config crawlers.
- `<cr>` is an end-of-command marker and is ignored.
- Prompt echoes, `^` and `%` lines are ignored.

## Context crawler: placeholders

The context crawler maps recognized placeholders to the example values in `BASELINE_VALUES` and appends them to the command in later `?` queries (for example `configure vlan Default ?`). At most two resolved placeholder branches are followed per query. The values are only ever typed before `?`, never executed. Unrecognized placeholders are recorded as unresolved.

Review before running (shown in the confirmation dialog and written to the output header):

| Key | Default | Notes |
|---|---|---|
| `vlan` | `Default` | Should be a VLAN name that exists on the switch |
| `vlan_id` | `1` | |
| `port` | `1:1` | Use a port that exists (stacks use `slot:port`) |
| `vr` | `VR-Default` | |
| `area`, `router_id`, `ip`, `ip2`, `network`, `mask`, `prefix`, `as`, `metric`, `tag` | documentation/example values | `192.0.2.x` ranges |
| `name` | `CRAWL_TEST` | Generic names/profiles |
| `mac`, `domain` | `02:00:00:00:00:01`, `example.invalid` | |

Because the device parser validates context-sensitive values in help (e.g. nonexistent VLAN names), a poor example value can make the device return an error or hide branches; that branch is then logged, not expanded. The roots `disable`, `delete` and `unconfigure` are only queried with `?` as well.

## Tests

    python3 -m unittest discover -s helpers/tests -v

Tests cover parser classification, timeout handling, duplicate queue prevention, paging-state restoration (success, error, cancellation, unknown state), and metadata parsing, using fake SecureCRT objects. The scripts avoid Python 3-only syntax, but only Python 3.12 was used to compile and test them; verify against the Python version in your SecureCRT.

## Feature coverage checklist

The VLAN, LLDP, STP, LAG/MLAG, loop-protection, routing and multicast guides were not available in this repository, so this checklist lists the feature areas a crawl should be reviewed for. Treat the live device parser as authoritative for version-specific syntax; tick items only after reviewing a real crawl.

- [ ] VLANs (`configure vlan`, `create vlan`, tagging, `show vlan`)
- [ ] LLDP (`configure lldp`, `enable/disable lldp`, `show lldp`)
- [ ] STP (`configure stpd`, `create stpd`, `show stpd`)
- [ ] LAG/MLAG (`enable sharing`, `create mlag`, `configure mlag`, `show mlag`)
- [ ] Loop protection (`configure elrp-client`, `enable elrp-client`, `show elrp`, ERPS)
- [ ] Routing (`configure iproute`, `configure ospf`, `configure bgp`, `show iproute`)
- [ ] Multicast (`configure igmp`, `configure pim`, `show igmp`, `show pim`)

## Unverified (needs a live EXOS device)

- No real EXOS `?` captures were available; test fixtures are synthetic approximations. Nothing here is live-device validated.
- Exact wording of the `show management` paging line and of the `show version` / `show switch` fields.
- Real `?` output formats across supported EXOS/Switch Engine versions (placeholder styles, camel-case tokens, wrapped lines, `<cr>` handling).
- Whether uppercase/camel-case tokens are ever legitimate literals.
- Error-message wording used for error classification.
- Behavior of the context crawler's example values against real device validation.
- Python version embedded in the target SecureCRT.
