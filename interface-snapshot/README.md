# Interface Snapshot (SecureCRT Script)

Runs a quick Cisco interface troubleshooting snapshot from the active SecureCRT tab.

## What it does

Detects an interface from:

- highlighted text
- clipboard
- nearby screen output
- manual input fallback

Then runs:

```text
show interfaces <interface>
show interfaces <interface> status
show interfaces <interface> switchport
show running-config interface <interface>
show mac address-table interface <interface>
show cdp neighbors <interface> detail