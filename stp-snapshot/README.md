# STP Snapshot

SecureCRT scripts for Cisco IOS/IOS-XE spanning-tree discovery and lightweight snapshot comparison.

Raw command output is the source of truth. CSV parsing is intentionally simple and is meant to help triage, not replace manual review.

## When to use stp-quick-view.py

Use `stp-quick-view.py` when you are already connected to one switch and want a fast, read-only STP view in the active tab.

It runs against the active tab only, does not connect to other sessions, and does not save output.

Commands:

- `terminal length 0`
- `show spanning-tree summary`
- `show spanning-tree root`
- `show spanning-tree blockedports`
- `show spanning-tree inconsistentports`
- `show spanning-tree detail | include ieee|occurr|from|is executing|Number of topology changes|last topology change`
- `show interfaces trunk`

## When to use multi-stp-snapshot.py

Use `multi-stp-snapshot.py` when you want a saved STP snapshot across multiple SecureCRT sessions.

The script reads `sessions.txt`, connects to one saved SecureCRT session at a time, runs read-only discovery commands, saves raw output per device, and builds simple CSVs under:

`C:\scripts\secure-crt\outputs\stp-snapshot\<timestamp>`

If the active tab is already connected, the script defaults to cancel. It will only reuse and disconnect that tab if you explicitly type `CONTINUE` at the prompt.

Commands:

- `terminal length 0`
- `show spanning-tree summary`
- `show spanning-tree root`
- `show spanning-tree blockedports`
- `show spanning-tree inconsistentports`
- `show spanning-tree detail | include ieee|occurr|from|is executing|Number of topology changes|last topology change`
- `show interfaces trunk`
- `show etherchannel summary`
- `show interfaces description`

## sessions.txt

Add one SecureCRT session name per line. Use names as they appear in the SecureCRT Connect dialog, excluding the leading `Sessions\` folder.

Blank lines and lines beginning with `#` are ignored.

Example:

```text
CoreSwitch01
Access\IDF-1\Switch01
Access\IDF-2\Switch02
```

Do not store passwords, tokens, or other credentials in `sessions.txt`; use saved SecureCRT session settings or an existing local credential pattern.

## expected-roots.csv

`expected-roots.csv` is optional. If it exists and contains active mappings, `multi-stp-snapshot.py` generates `stp-root-check.csv`.

If you are not using expected-root validation yet, keep the template as `expected-roots.example.csv` until you are ready to use it. Only name the file `expected-roots.csv` when you want the snapshot script to read it.

If `expected-roots.csv` exists but contains only comments, blanks, or a header, the script does not generate an empty `stp-root-check.csv`. It adds this note to `run-summary.csv` and the final message:

`expected-roots.csv exists but contains no active mappings.`

Format:

```csv
vlan,expected_root_session
VLAN0001,CoreSwitch01
10,Distribution\Building-A\Core-A
```

The `expected_root_session` value should match a session name from `sessions.txt`. Observed root sessions are inferred from devices that report `Root bridge for:` in `show spanning-tree summary`, so review raw output if a result is `WARN` or unexpected.

## CSV Outputs

`run-summary.csv`

Connection and collection result per session. Use this first to see which devices succeeded, failed, or were missing from a comparison.

`stp-summary.csv`

Simple summary fields from `show spanning-tree summary`, including STP mode, VLANs the device reports itself as root for, blocked port total, and inconsistent port total.

`stp-roots.csv`

Parsed rows from `show spanning-tree root`: session, instance, root ID, cost, and root port.

`stp-port-issues.csv`

Parsed blocked and inconsistent port rows from `show spanning-tree blockedports` and `show spanning-tree inconsistentports`.

`stp-topology-changes.csv`

Parsed topology-change counters, last-change text, and source interface where available from the filtered `show spanning-tree detail` command.

`stp-uplink-context.csv`

Simple trunk, EtherChannel, and interface-description context from `show interfaces trunk`, `show etherchannel summary`, and `show interfaces description`.

`stp-root-check.csv`

Generated only when `expected-roots.csv` exists and contains active mappings. Compares expected root sessions to observed root sessions where the script can infer them.

## compare-stp-snapshots.py

Use `compare-stp-snapshots.py` after you have two saved snapshot folders from `multi-stp-snapshot.py`.

The script prompts for:

- Previous snapshot folder
- Current snapshot folder

It does not connect to devices. It reads local CSV files and writes these files into the current snapshot folder:

- `stp-diff.txt`
- `stp-diff.csv`

It flags:

- root bridge changed
- root port changed
- root-check failed
- root-check recovered
- root-check changed
- root-check missing from one snapshot
- new blocked port
- cleared blocked port
- new inconsistent port
- cleared inconsistent port
- topology change counter increased
- session failed now but succeeded before
- session missing from current snapshot

`stp-root-check.csv` is optional. When it exists in one or both snapshots, the compare script includes root-check results in the diff. When it is missing from both snapshots, comparison continues without root-check checks.

The comparison is intentionally simple. Use the raw files from both snapshots when a difference needs confirmation.

## stp-open-latest.py

Use `stp-open-latest.py` when you want to quickly return to the most recent local snapshot output.

It opens the newest folder under:

`C:\scripts\secure-crt\outputs\stp-snapshot`

If `stp-diff.txt` exists in that newest folder, it opens the diff file. Otherwise it opens the folder in File Explorer.
