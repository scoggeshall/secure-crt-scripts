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

### EXOS CLI Crawler Suite
Read-only help crawlers for Extreme EXOS / Switch Engine (`?` help only; discovered commands are never executed).

- Suite guide: [`helpers/README-exos-crawler-suite.md`](helpers/README-exos-crawler-suite.md)
- Show help crawler: [`helpers/exos-show-help-crawler.py`](helpers/exos-show-help-crawler.py)
- Config help crawler: [`helpers/exos-config-help-crawler.py`](helpers/exos-config-help-crawler.py)
- Config context crawler: [`helpers/exos-config-mode-crawler.py`](helpers/exos-config-mode-crawler.py)

---

## Design Principles

- No hardcoded paths (the EXOS crawlers default to the user's `Documents` folder and accept the `EXOS_CRAWLER_OUTPUT_ROOT` override)
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
- documentation (a README, or for script families a shared guide such as the
  [EXOS suite guide](helpers/README-exos-crawler-suite.md))
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

