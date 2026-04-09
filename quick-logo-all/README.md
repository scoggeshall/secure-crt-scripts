# Close All Sessions (SecureCRT Script)

Closes all open SecureCRT tabs safely.

---

## What it does

- Sends `exit` to all connected sessions
- Skips disconnected sessions
- Closes all tabs except the one running the script

---

## Usage

1. Run script from any tab
2. All other tabs will:
   - receive `exit`
   - be closed

---

## Safety Notes

- Does not force disconnects
- Preserves the current tab
- Provides summary of skipped tabs

---

## Behavior Details

- Iterates through all tabs
- Tracks disconnected sessions
- Closes tabs in reverse order to avoid index issues

---

## Future Improvements

- Confirmation prompt before execution
- Option to exclude specific tabs