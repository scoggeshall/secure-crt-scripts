# SecureCRT Scripts

Collection of SecureCRT Python scripts for network operations and troubleshooting workflows.

This repository consolidates reusable tooling into a single location with consistent structure and behavior.

---

## Scripts

### OUI Lookup
Offline MAC → vendor lookup using Wireshark `manuf.txt`.

- Detects MAC from screen, clipboard, or input
- Displays vendor
- Optionally runs ARP lookup

Path:
`oui-lookup/oui-lookup.py`

---

### Cable Test
Automates TDR cable diagnostics on supported Cisco platforms.

- Extracts interface from screen/selection
- Runs TDR test
- Waits for completion
- Displays results

Path:
`cable-test/cable-test.py`

---

### Quick Logo All
Closes all SecureCRT tabs cleanly.

- Sends `exit` to all connected sessions
- Skips disconnected tabs
- Closes all tabs except current

Path:
`quick-logo-all/quick-logo-all.py`

---

## Design Principles

- No hardcoded paths
- Scripts operate on active SecureCRT context
- Prefer detection over user input
- Safe execution (confirm before sending commands)
- Portable across environments

---

## Usage Model

All scripts are intended to be:

1. Run inside SecureCRT
2. Context-aware (selection, screen, clipboard)
3. Fast to execute during live troubleshooting

---

## Structure

Each script is self-contained:

- script file
- README
- supporting data (if required)

This allows scripts to be:
- reused independently
- tested in isolation
- expanded without affecting others

---

## Future Improvements

- Standard argument handling
- Shared helper module
- Logging consistency
- Additional network automation scripts