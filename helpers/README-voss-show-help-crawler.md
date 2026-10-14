# VOSS Show Help Crawler

## Overview

`voss-show-help-crawler.py` is a SecureCRT Python script that recursively discovers and records the VOSS/Fabric Engine `show` command help tree.

It begins with `show ?`, parses literal CLI keywords, and recursively queries paths such as `show ip ?`, `show ip ospf ?`, `show vlan ?`, and `show spanning-tree ?`. Dynamic values such as VLAN IDs, IP addresses, interface identifiers, and `WORD` placeholders are recorded but are not automatically populated or followed.

## Purpose

Use this crawler to build a searchable operational and troubleshooting command reference directly from a VOSS/Fabric Engine device. It is useful for discovering available `show` commands, comparing CLI capabilities between software versions, and identifying commands that may not be obvious from documentation.

## Intended Environment

- Extreme VOSS / Fabric Engine
- SecureCRT
- Active connected tab
- Read-only CLI help discovery

## Operation

The crawler detects the current prompt, sets `terminal length 64`, and starts with `show ?`. It captures help through SecureCRT native session logging, follows discovered lowercase literal keywords, records placeholders, and uses Ctrl+C to cancel each partial command without executing it.

## Safety

The crawler is intended to be read-only. The only normal command intentionally executed is `terminal length 64`. Question-mark help is requested without pressing Enter.

## Output

Files are written to:

    C:\scripts\secure-crt\outputs\show-help\

Filename format:

    YYYYMMDD-HHMMSS_<HOSTNAME>_show-help.txt

The output records query numbers, crawl depth, commands, literal children, placeholders, captured help, failures, and final statistics.

## Limits

    MAX_DEPTH = 25
    MAX_COMMANDS = 10000

## Usage

1. Connect to the VOSS/Fabric Engine device in SecureCRT.
2. Make the desired session the active tab.
3. Run `voss-show-help-crawler.py`.
4. Type `CRAWL` when prompted.
5. Review the generated file in the `show-help` output directory.

## Placeholder Handling

Literal keywords such as `ip`, `ospf`, `vlan`, and `spanning-tree` are followed. Dynamic tokens such as `<1-4094>`, `WORD`, `IP-ADDRESS`, and `PORT` are recorded but not followed.

## Notes

The crawler uses cursor-idle detection to determine when help output has finished rendering. Increase the timing values in the script if a slow connection produces incomplete captures.
