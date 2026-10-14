# EXOS CLI Crawler Suite

## Overview

Three self-contained SecureCRT Python scripts record the Extreme EXOS / Switch Engine CLI help tree. EXOS has a flat CLI (no mode hierarchy), so each crawler starts at one or more command roots, sends `<command> ?`, parses the help text, and follows literal keywords.

| Script | Starting root(s) | Confirmation word | Output directory |
|---|---|---|---|
| `exos-show-help-crawler.py` | `show` | `SHOWCRAWL` | `<output base>/exos-show-help/` |
| `exos-config-help-crawler.py` | `configure` | `CONFIGCRAWL` | `<output base>/exos-config-help/` |
| `exos-config-mode-crawler.py` (context crawler) | `configure`, `enable`, `disable`, `create`, `delete`, `unconfigure` | `CONTEXTCRAWL` | `<output base>/exos-context-help/` |

Output file name: `YYYYMMDD-HHMMSS_<HOSTNAME>_<suffix>.txt`, where the suffix is `show-help`, `config-help` or `context-help`.

### Output location

`<output base>` defaults to `Documents\SecureCRT-Outputs` under the current user's home directory (`os.path.expanduser("~")`); no drive letter or username is embedded. The single override is the environment variable `EXOS_CRAWLER_OUTPUT_ROOT`, which replaces the base directory (the per-crawler subfolder is still appended). It must be set before SecureCRT starts. The directory is created if missing; if it is not writable the script fails when creating the file. Each script is self-contained (the shared helper block is duplicated in all three), and this one suite guide documents all three; there is no per-script README.

## Safety model

- Only question-mark help is sent (`<command> ?`, no Enter) and then canceled with Ctrl+C. Discovered commands are never executed.
- Commands that ARE executed (Enter pressed), all read-only except the paging setting:
  - `show management` (read the CLI paging state)
  - `show version`, `show switch` (platform metadata)
  - `disable cli paging` and later `enable cli paging` (see below)
- Requires an active, connected tab at an EXOS prompt ending in `#` or `>`.
- SecureCRT session logging is used to capture help text. If the session was already logging, it is stopped during the crawl and re-started (append) afterward.

## Run flow

1. Prompt detection, then a confirmation dialog; type the confirmation word.
2. The output file is created with a header (prompt, roots, limits).
3. CLI paging is handled first (below). If paging could not be disabled, the crawl is skipped.
4. Platform metadata (`show version`, `show switch`) is collected, then the crawl runs.
5. Paging is restored, a final summary is appended, and a message box shows the counts.

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

### Read-only command timeouts
If `show management`, `show version`, `show switch` or a paging command does not finish (screen never idle), the script sends Ctrl+C and confirms a CLI prompt is visible before sending anything else. If no prompt is recovered it raises an error: metadata collection stops, and paging commands report failure rather than being sent blindly.

### CLI paging
Before changing anything the scripts run `show management` and look for a `CLI paging : Enabled|Disabled` line.

- Enabled: the restore action (`enable cli paging`) is recorded first, then `disable cli paging` is sent. The restore is attempted on completion, cancellation, error, and after a failed or timed-out disable (in case paging did change).
- Disabled: paging is left untouched and nothing is restored.
- State not readable: a Yes/No dialog explains the limitation (paging will be disabled and then set to *enabled*, the EXOS default, even if it was disabled before). Answering No stops before paging is changed.
- A failed disable skips the crawl. A failed restore does not raise; both are recorded in the output file (`CLI paging restore: FAILED`, "Paging failures" in the summary) and in the final dialog under "PAGING PROBLEMS". Check the setting manually when that appears. If the script itself raises, the failure is only guaranteed to be in the output file, since the final dialog is not reached.

Success means the command completed without a timeout or an error response; the resulting state is not re-read from the device.

The `show management` field label is an assumption (see Unverified items).

### Platform metadata
`show version` and `show switch` output is captured (after paging is handled) and the EXOS/Switch Engine version, system type, boot ROM and hardware lines are parsed into the output. A failed, incomplete or unparsable metadata query is recorded and counted ("Metadata query failures") but does not stop the crawl. The raw captured text also remains in the output file.

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

The tests use SYNTHETIC fixtures and fake SecureCRT/CLI objects. They are not captures from a live EXOS device and do not validate real EXOS output or the SecureCRT runtime. They cover parser classification, timeout handling (including read-only command cancellation and prompt confirmation), duplicate queue prevention, the paging lifecycle (command order, disable failure, restore failure, error/cancellation cleanup, and visibility of failures in the output and final dialog), output-path resolution, and metadata parsing. The scripts avoid Python 3-only syntax, but only Python 3.12 was used to compile and test them.

## Feature coverage checklist

The VLAN, LLDP, STP, LAG/MLAG, loop-protection, routing and multicast guides were not available in the workspace, so this checklist is NOT derived from them. It lists the feature areas a crawl should be reviewed for. Treat the live device parser as authoritative for version-specific syntax; tick items only after reviewing a real crawl.

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
- The target SecureCRT's embedded Python runtime (scripts have only been compiled/tested on Python 3.12 with fakes), plus SecureCRT's behavior for `Screen.WaitForCursor`, session logging and dialogs.
- Whether `Documents\\SecureCRT-Outputs` is writable in your environment.
- Paging restore is not re-verified against the device after it is sent.
