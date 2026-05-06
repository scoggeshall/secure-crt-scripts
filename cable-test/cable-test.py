# $language = "python"
# $interface = "1.0"

import re
import time

TDR_WAIT = 10


def ExtractInterface(text):
    if not text:
        return None

    patterns = [
        r'\b(?:Fa|Gi|Te|Twe|Fo|Hu|Eth)\d+(?:/\d+){1,3}\b',
        r'\b(?:FastEthernet|GigabitEthernet|TenGigabitEthernet|TwentyFiveGigE|TwentyFiveGigabitEthernet|FortyGigabitEthernet|HundredGigE|Ethernet)\d+(?:/\d+){1,3}\b',
    ]

    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0)

    return None


def GetSelectedInterface():
    tab = crt.GetScriptTab()
    screen = tab.Screen

    try:
        iface = ExtractInterface(screen.Selection.strip())
        if iface:
            return iface
    except:
        pass

    try:
        iface = ExtractInterface(crt.Clipboard.Text.strip())
        if iface:
            return iface
    except:
        pass

    try:
        row = screen.CurrentRow
        text = screen.Get(max(1, row - 5), 1, min(row + 5, screen.Rows), screen.Columns)
        iface = ExtractInterface(text)
        if iface:
            return iface
    except:
        pass

    iface = crt.Dialog.Prompt(
        "No interface detected.\nEnter interface manually:",
        "Cable Diagnostics",
        "",
        False
    )

    return ExtractInterface(iface)


def Main():
    tab = crt.GetScriptTab()
    screen = tab.Screen
    screen.IgnoreEscape = True

    iface = GetSelectedInterface()

    if not iface:
        crt.Dialog.MessageBox("No valid interface found.", "Cable Diagnostics", 0)
        return

    confirm = crt.Dialog.MessageBox(
        "Run TDR cable diagnostics on:\n\n" +
        iface +
        "\n\nThis may briefly disrupt the link on some platforms.\n\nContinue?",
        "Confirm Cable Diagnostics",
        4
    )

    if confirm != 6:
        return

    cmd1 = "test cable-diagnostics tdr interface " + iface
    screen.Send(cmd1 + "\r")

    time.sleep(TDR_WAIT)

    cmd2 = "show cable-diagnostics tdr interface " + iface
    screen.Send(cmd2 + "\r")


Main()