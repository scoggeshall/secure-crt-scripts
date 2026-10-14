# VOSS Baseline Verification Crawler

`voss-baseline-verification-crawler.py` is a SecureCRT Python script for a **disposable, non-production Extreme Fabric Engine/VOSS lab switch connected by serial console**.

It builds a small temporary routed configuration, uses the live VOSS CLI to discover and execute relevant `show` commands, records the results, and then tears the temporary configuration back down.

The goal is not simply to crawl command syntax. It is to connect:

```text
configuration command
        ↓
running configuration/state
        ↓
show/help syntax
        ↓
operational verification command
```

This makes the output useful for developing VOSS configuration templates, verification procedures, SecureCRT automation, and command references.

## Safety Scope

This script **changes the running configuration**.

It is intended for:

- Offline lab switches
- Disposable test switches
- Serial-console CLI research
- VOSS/Fabric Engine syntax validation
- Building configuration-to-verification mappings

It is **not intended for production switches**.

The script never intentionally runs:

```text
save config
```

By default:

```python
FULL_LAB_TEARDOWN = True
ENABLE_PHYSICAL_MLT_TEST = False
```

`FULL_LAB_TEARDOWN = True` means cleanup is intentionally aggressive and can disable global OSPF, PIM, and IPv4 routing after the test configuration has been removed.

## Requirements

- SecureCRT with Python scripting support
- Active serial-console session to a VOSS/Fabric Engine switch
- Privileged EXEC access
- Writable output directory:

```text
C:\scripts\secure-crt\outputs\baseline-verification
```

No external Python packages are required.

## Starting Mode

Start the script from a connected serial session.

Privileged EXEC mode is preferred:

```text
5320-24P-8XE-FabricEngine:1#
```

The script contains prompt recovery logic and attempts to normalize the session before configuration begins.

Do not leave partially typed commands on the command line before starting the crawler.

## Confirmation

The script displays the disposable values it intends to use before making changes.

To continue, enter:

```text
BUILDVERIFY
```

Anything else cancels the run.

## Disposable Baseline

The default baseline uses documentation/test addressing and high-numbered disposable VLANs.

Representative values include:

| Purpose | Default |
| --- | --- |
| Loopback | `99` |
| Loopback IP | `192.0.2.99/32` |
| Client VLAN | `3901` |
| Client gateway | `198.51.100.1/24` |
| Transit VLAN | `3902` |
| Transit IP | `203.0.113.1/30` |
| Multicast VLAN | `3903` |
| OSPF area | `0.0.0.255` |
| DHCP servers | `192.0.2.10`, `192.0.2.11` |
| PIM RP | `192.0.2.254` |
| Multicast prefix | `239.255.0.0/16` |
| ACL | `1901` |

The script performs a preflight check on important values before configuration is sent.

## Test Workflow

The crawler performs four major phases.

### 1. Build disposable configuration

The default build exercises:

- IPv4 routing
- OSPF
- Loopback routing
- Routed client VLAN
- DHCP relay
- Routed transit VLAN
- PIM sparse mode
- Multicast-enabled VLAN
- ACL creation and attachment

The loopback syntax intentionally differs from VLAN-interface OSPF syntax.

Loopback example:

```text
interface loopback 99
ip address 99 192.0.2.99/32
ip area 99 0.0.0.255
ip ospf 99
exit
```

VLAN example:

```text
interface vlan 3901
ip address 198.51.100.1 255.255.255.0
ip dhcp-relay
ip ospf area 0.0.0.255
ip ospf network passive
ip ospf enable
exit
```

These patterns are based on the VOSS CLI syntax gathered by the related configuration crawlers rather than assuming Cisco-style syntax.

### 2. Normalize configuration mode

After every configuration section, the script verifies that it has returned to global configuration mode:

```text
(config)#
```

This prevents a malformed or unexpected command from leaving the following section inside a nested mode such as:

```text
(config-ospf)#
(config-if)#
```

### 3. Discover and execute verification commands

The script returns to privileged EXEC mode and examines targeted `show` command trees.

Examples include:

```text
show vlan
show ip interface
show ip ospf
show ip ospf interface vlan 3901
show ip ospf interface vlan 3902
show ip ospf neighbor
show ip route protocol ospf
show ip dhcp-relay
show ip pim
show ip pim interface vlan 3902
show ip pim interface vlan 3903
show ip pim active-rp
show filter acl
show filter acl config 1901
show filter acl ip 1901
show filter acl statistics 1901
```

The crawler can query `?`, parse the returned grammar, substitute known safe values, and execute a command when the parser indicates that the command is complete with `<cr>`.

### 4. Tear down the lab configuration

Cleanup removes the temporary state created by the test.

This includes, as applicable:

```text
ACL attachment/configuration
DHCP relay forwarding paths
Static PIM RP
PIM mode
Disposable VLANs
Loopback
OSPF area
OSPF global enable
PIM global enable
IPv4 routing
```

The final global feature removal is controlled by:

```python
FULL_LAB_TEARDOWN = True
```

This behavior is appropriate for the disposable lab use case, but is one of the reasons the script should not be used on a production device.

## Physical MLT/LACP Testing

Physical-interface and MLT/LACP testing is disabled by default:

```python
ENABLE_PHYSICAL_MLT_TEST = False
```

This avoids modifying real switch ports during normal baseline-verification runs.

If enabled, review these values first:

```python
"mlt_id"
"mlt_name"
"lacp_key"
"port_1"
"port_2"
```

Enabling this option is materially more disruptive because the script can alter physical interface and VLAN membership state.

## Placeholder Resolution

The show crawler uses known disposable values to continue through CLI placeholders when a safe mapping exists.

Examples include values for:

- VLAN IDs
- ACL IDs
- OSPF area
- MLT ID
- Interface IDs
- IPv4 addresses

Unknown placeholders are not blindly populated.

This prevents the crawler from inventing arbitrary configuration or operational values merely to traverse more of the command tree.

## Recursion Protection

VOSS help output can contain repeatable or order-independent option lists.

Without protection, a crawler can turn a command such as:

```text
foo a b c
```

into permutations such as:

```text
foo a b c
foo a c b
foo b a c
foo b c a
foo c a b
...
```

The verification crawler contains a repeat guard that prevents a literal keyword already present in the current command path from simply being appended again.

It also uses:

- Maximum show depth
- Per-feature query limits
- Total query limits
- Visited-command tracking

The `|` output-filter operator is not treated as a placeholder that should be recursively populated.

## Serial Timing

Serial-console interaction is deliberately paced.

The script uses SecureCRT screen-idle detection instead of relying exclusively on fixed sleeps.

A critical behavior is:

```text
Ctrl+C
  ↓
short delay
  ↓
wait for screen idle
  ↓
read settled prompt
```

This prevents prompt-detection races where SecureCRT reads an empty or partially redrawn prompt immediately after cancelling a command.

## Output

Results are written beneath:

```text
C:\scripts\secure-crt\outputs\baseline-verification
```

A run produces an evidence file containing:

- Build commands
- CLI responses
- Parsed configuration errors
- Show-help queries
- Parsed literal options
- Parsed placeholders
- Executed verification commands
- Operational output
- Cleanup commands
- Cleanup results
- Final summary

The crawler uses temporary SecureCRT capture files while collecting command output.

## Feature Status

Verification features are classified independently from cleanup.

Possible states include:

```text
COMPLETE
PARTIAL - feature query limit reached
PARTIAL - total query limit reached
```

The final summary reports per-feature counts for:

- Help queries
- Executed commands
- Failures
- Completion state

This distinction is important. A feature reaching a safety limit does not mean cleanup failed, and successful cleanup does not mean the verification tree was exhaustively crawled.

## Error Detection

The script checks command output for common VOSS CLI failures, including patterns such as:

```text
% Invalid input
% Incomplete command
Error:
Invalid
Ambiguous
```

A command that produces one of these responses is recorded as a possible error rather than silently treated as successful.

## Relationship to the Other VOSS Crawlers

This script complements the other CLI-discovery tools.

### `voss-show-help-crawler.py`

Explores operational `show` command syntax.

Conceptually:

```text
show ?
show ip ?
show ip ospf ?
...
```

### `voss-config-help-crawler.py`

Explores the global configuration help tree without deliberately creating configuration objects or entering value-dependent modes.

Conceptually:

```text
(config)#?
(config)#ip ?
(config)#router ?
...
```

### `voss-config-mode-crawler.py`

Uses safe values to enter actual configuration modes and discover syntax that cannot be reached from global configuration alone.

Examples:

```text
(config)#router ospf
(config-ospf)#?

(config)#interface vlan 3901
(config-if)#?
```

### `voss-baseline-verification-crawler.py`

Builds known temporary state and then asks:

> How does VOSS expose and verify the configuration we just created?

It is therefore the bridge between **configuration grammar** and **operational verification grammar**.

## Recommended Development Workflow

Use the crawler suite in this order when researching a new Fabric Engine release or platform:

```text
1. Show Help Crawler
       ↓
2. Configuration Help Crawler
       ↓
3. Configuration Mode Crawler
       ↓
4. Baseline Verification Crawler
```

The first three establish the CLI grammar.

The baseline verification crawler then tests how representative configuration appears operationally.

## Before Running on a Different Platform or Release

Review:

```python
BASELINE
SHOW_FEATURES
FULL_LAB_TEARDOWN
ENABLE_PHYSICAL_MLT_TEST
```

CLI syntax can vary by Fabric Engine release, hardware family, enabled feature set, and licensing.

Do not assume that syntax learned from one platform is universally valid.

## Current Design Principle

The crawler should prefer the switch's own parser over assumptions.

When the device advertises:

```text
?
```

that output is treated as the primary source for deciding:

- What keyword exists
- Whether another value is required
- Whether `<cr>` is valid
- Whether a configuration mode was entered
- Which verification path should be explored

That is the core reason for building these crawlers: use the actual VOSS CLI grammar to generate a practical, testable command reference.
