# VOSS Configuration Mode Crawler

## Overview

`voss-config-mode-crawler.py` discovers VOSS/Fabric Engine CLI help inside configuration submodes that cannot be fully explored from the global `(config)#` prompt.

Examples include `(config-ospf)#`, `(config-ospf-area)#`, `(config-bgp)#`, `(config-isis)#`, and `(config-if)#`.

Unlike the global configuration crawler, this script intentionally enters selected modes using controlled example values and recursively crawls the question-mark help available inside those modes.

## Purpose

Use this crawler to document syntax associated with OSPF, OSPF areas, BGP, IS-IS, SPBM-related IS-IS syntax, physical interfaces, VLAN interfaces, loopback interfaces, and other contexts defined in `MODE_PROFILES`.

## Intended Environment

- Extreme VOSS / Fabric Engine
- SecureCRT
- Serial console
- Offline, lab, or decommissioned device

This script is not strictly read-only. Some mode-entry commands may temporarily modify running configuration. The script never saves the configuration.

## Operation

For each enabled profile, the crawler:

1. Returns to exact global configuration mode `(config)#`.
2. Executes required mode-entry commands.
3. Validates the expected submode prompt.
4. Recursively queries literal keywords with `?`.
5. Records dynamic placeholders.
6. Cancels partial help commands with Ctrl+C.
7. Exits back to exact global configuration mode.
8. Runs configured cleanup commands.
9. Verifies global configuration mode before the next profile.
10. Returns to privileged EXEC after all profiles complete.

## Safe Values

The script uses a `SAFE_VALUES` or baseline-derived value dictionary when a mode requires an actual argument. Typical values include physical interfaces, VLAN interfaces, loopbacks, OSPF areas, BGP AS numbers, SPBM instances, and a DHCP Server test subnet (RFC 5737 TEST-NET-1, 192.0.2.0/24).

Review all values before running the crawler. They must be appropriate for the offline test device and should not conflict with configuration that needs to be preserved.

## Mode Profiles

`MODE_PROFILES` defines each configuration context.

A profile can contain:

- `name` — Human-readable name.
- `enabled` — Whether the profile runs.
- `entry_commands` — Commands executed to enter the context.
- `crawl_root` — Optional command prefix queried inside the mode.
- `expected_prompt_patterns` — Prompt validation expressions.
- `cleanup_commands` — Commands used to remove temporary configuration.

Profiles can cover Global SPBM syntax, IS-IS, IS-IS SPBM instances, physical interfaces, interface SPBM syntax, VLAN interfaces, OSPF, OSPF areas, BGP, loopbacks, DHCP Server subnets, RIP, and additional baseline-driven contexts.

The DHCP Server Subnet profile enters the submode opened by `ip dhcp-server subnet <network>/<mask>` (VOSS 9.0+), where `pool`, `router`, `ntp-servers`, `domain-name-servers`, `lease-time`, and `domain-name` are configured before `exit`. It uses the RFC 5737 TEST-NET-1 prefix (192.0.2.0/24) as a safe entry value so it cannot collide with a real subnet. The exact submode prompt string isn't published by Extreme and may vary by release, so `expected_prompt_patterns` lists several plausible candidates; if none match on your device, the script logs the actual detected prompt in its "Unexpected prompt after profile entry" error so the pattern can be corrected.

## SPBM Coverage

SPBM discovery spans multiple contexts because Fabric Engine does not expose all SPBM syntax through one dedicated submode.

The crawler can inspect:

    (config)#spbm ?

It can enter IS-IS:

    (config)#router isis
    (config-isis)#?

It can inspect an SPBM instance:

    (config-isis)#spbm 1 ?

It can also inspect interface-level syntax:

    (config-if)#isis spbm 1 ?

## Baseline-Driven Expansion

The crawler can use deployment baseline values to resolve placeholders needed to reach realistic command contexts, including loopbacks, client and transit VLANs, multicast VLANs, physical uplinks, MLT, LACP, DHCP relay, PIM, ACLs, TACACS/ISE, SNMP, OSPF, and IS-IS/SPBM.

The baseline is a source of safe example values, not a configuration script to apply blindly. Only commands required to enter a target mode should be executed. Other syntax should be probed with `?` whenever possible.

## Mode Navigation

Every profile must begin from exact global configuration mode:

    (config)#

After a profile, the script sends `exit` as needed until global configuration is restored. If normal unwinding fails, it can return to privileged EXEC and re-enter `configure terminal`.

This prevents a new profile from accidentally running inside the previous profile's context.

## Cleanup

Profiles that create temporary objects should define cleanup commands. Examples can include temporary BGP processes, loopbacks, or OSPF areas.

Cleanup is attempted, but an interrupted script cannot guarantee cleanup. Use an offline or disposable test configuration and inspect the running configuration afterward.

The crawler never runs `save config`.

## Output

Files are written to:

    C:\scripts\secure-crt\outputs\mode-help\

Filename format:

    YYYYMMDD-HHMMSS_<HOSTNAME>_mode-help.txt

The output records profile names, entry commands, crawl roots, cleanup commands, detected prompts, queries, crawl depth, captured help, literal children, placeholders, errors, cleanup status, and final statistics.

## Limits

Typical crawl boundaries include:

    MAX_DEPTH_PER_MODE = 25
    MAX_COMMANDS_PER_MODE = 10000
    MAX_TOTAL_COMMANDS = 50000
    MAX_MODE_EXIT_ATTEMPTS = 12

## Usage

1. Connect to an offline VOSS/Fabric Engine device over serial console.
2. Review all safe or baseline-derived values.
3. Review enabled `MODE_PROFILES`.
4. Verify temporary objects and cleanup commands.
5. Run `voss-config-mode-crawler.py`.
6. Review the profile preview.
7. Type `MODECRAWL` to begin.
8. Allow profile cleanup to finish.
9. Review the generated `mode-help` output.
10. Inspect the running configuration before reusing the device.

## Crawler Suite

The three crawlers cover progressively deeper CLI layers:

    voss-show-help-crawler.py
        Operational show-command discovery.

    voss-config-help-crawler.py
        Global configuration command discovery.

    voss-config-mode-crawler.py
        Configuration submode discovery using controlled mode entry.

Together they cover:

    EXEC show commands
        ->
    Global configuration commands
        ->
    Configuration submode commands
