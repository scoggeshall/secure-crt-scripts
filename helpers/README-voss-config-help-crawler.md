# VOSS Configuration Help Crawler

## Overview

`voss-config-help-crawler.py` recursively discovers and records the VOSS/Fabric Engine global configuration command help tree.

It enters global configuration mode, begins with `(config)#?`, and recursively queries discovered paths such as `vlan ?`, `vlan create ?`, `router ospf ?`, and `spanning-tree ?`. Discovered commands are queried with question-mark help and are not executed with Enter.

## Purpose

Use this crawler to document configuration syntax exposed from VOSS global configuration mode. It can help build CLI references, compare Fabric Engine releases, discover available features, and provide source material for future SecureCRT automation.

## Intended Environment

- Extreme VOSS / Fabric Engine
- SecureCRT
- Recommended transport: Serial console
- Recommended target: Offline, lab, or decommissioned device

## Operation

The crawler:

1. Detects the privileged EXEC prompt.
2. Runs `terminal length 64`.
3. Enters `configure terminal`.
4. Sends `?` at `(config)#`.
5. Parses literal lowercase keywords.
6. Recursively queries discovered command paths.
7. Records dynamic placeholders.
8. Detects repeatable option lists.
9. Enforces depth, command-count, and token-count limits.
10. Cancels partial commands with Ctrl+C.
11. Returns to privileged EXEC when finished.

## Safety

Discovered configuration commands are not executed with Enter. For example, the crawler may send `router ospf ?`, but it does not execute `router ospf`.

The script intentionally executes only the commands required to prepare the session, including `terminal length 64` and `configure terminal`.

## Repeatable Option Protection

Some CLI branches allow options in multiple orders. A naive recursive crawler can generate thousands of equivalent permutations.

The crawler compares parent and child option sets and skips branches that appear to be reordered selections from the same repeatable list. It also enforces:

    MAX_COMMAND_TOKENS = 24

This provides a secondary boundary against unexpectedly long command paths.

## Output

Files are written to:

    C:\scripts\secure-crt\outputs\config-help\

Filename format:

    YYYYMMDD-HHMMSS_<HOSTNAME>_config-help.txt

The output records query numbers, crawl depth, commands, captured help, literal children, placeholders, permutation-guard decisions, failures, and final statistics.

## Temporary Capture Data

SecureCRT native session logging is used to capture help output. Temporary capture data may be stored under:

    C:\scripts\secure-crt\outputs\config-help\_capture\

SecureCRT can retain a log-file handle briefly after logging is stopped. If a capture file remains after an interrupted run, remove it after SecureCRT releases the handle.

## Limits

    MAX_DEPTH = 25
    MAX_COMMANDS = 20000
    MAX_COMMAND_TOKENS = 24
    MIN_REPEATABLE_CHOICES = 2
    MAX_REPEATABLE_CHOICES = 32

## Usage

1. Connect to an offline, lab, or decommissioned VOSS/Fabric Engine device.
2. Run `voss-config-help-crawler.py`.
3. Type `CRAWL` when prompted.
4. Allow the crawler to complete.
5. Review the generated file in the `config-help` output directory.

## Relationship to the Mode Crawler

This crawler explores syntax reachable from global configuration mode without intentionally entering discovered submodes.

For syntax that only appears after entering contexts such as `(config-ospf)#`, `(config-bgp)#`, or `(config-if)#`, use `voss-config-mode-crawler.py`.
