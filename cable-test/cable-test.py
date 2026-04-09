# $language = "python"
# $interface = "1.0"

import re
import time

TDR_WAIT = 10  # seconds to wait for test to complete

def ExtractInterface(text):
    """Find interface name like Gi1/0/9, Te2/0/23, Fa0/1, etc."""
    if not text:
        return None
    pattern = re.compile(r'\b([A-Za-z]{2,3}\d+(?:/\d+){1,2})\b')
    m = pattern.search(text)
    return m.group(0) if m else None


def GetSelectedInterface():
    """Obtain interface name from selection, clipboard, or nearby text."""
    tab = crt.GetScriptTab()
    screen = tab.Screen

    # 1️⃣ Highlighted text
    try:
        sel = screen.Selection.strip()
        iface = ExtractInterface(sel)
        if iface:
            return iface
    except:
        pass

    # 2️⃣ Clipboard
    try:
        clip = crt.Clipboard.Text.strip()
        iface = ExtractInterface(clip)
        if iface:
            return iface
    except:
        pass

    # 3️⃣ Nearby text
    try:
        row = screen.CurrentRow
        text = screen.Get(max(1, row - 3), 1, min(row + 3, screen.Rows), screen.Columns)
        iface = ExtractInterface(text)
        if iface:
            return iface
    except:
        pass

    return None


def Main():
    tab = crt.GetScriptTab()
    screen = tab.Screen
    screen.IgnoreEscape = True

    iface = GetSelectedInterface()
    if not iface:
        return  # nothing highlighted

    # Detect device prompt
    screen.Synchronous = True
    screen.Send("\r")
    time.sleep(0.3)
    row = screen.CurrentRow
    prompt = screen.Get(row, 0, row, screen.CurrentColumn - 1).strip()
    
    # --- Run TDR test ---
    cmd1 = "test cable-diagnostics tdr interface " + iface
    screen.Send(cmd1 + "\r")
    # Wait for prompt with timeout
    screen.WaitForString(prompt, 5)

    screen.Synchronous = False

    # --- Wait while TDR completes ---
    time.sleep(TDR_WAIT)

    # --- Show results ---
    cmd2 = "show cable-diagnostics tdr interface " + iface
    screen.Send(cmd2 + "\r")

    # Return control cleanly
    screen.Synchronous = False


Main()