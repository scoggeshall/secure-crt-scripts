# Cable Test (SecureCRT Script)

Automates cable diagnostics (TDR) on supported network devices.

---

## What it does

- Detects interface from:
  - highlighted text
  - clipboard
  - nearby screen output
- Runs:
  - `test cable-diagnostics tdr interface <interface>`
- Waits for completion
- Runs:
  - `show cable-diagnostics tdr interface <interface>`

---

## Requirements

- Device must support TDR commands
- Active SecureCRT session

---

## Usage

1. Highlight or copy an interface (e.g. `Gi1/0/9`)
2. Run the script
3. Script executes diagnostics automatically

---

## Behavior Notes

- Uses a fixed wait timer (`TDR_WAIT`)
- Assumes device prompt remains stable
- Does not validate platform compatibility

---

## Future Improvements

- Detect platform support
- Parse output for faults
- Add configurable wait time