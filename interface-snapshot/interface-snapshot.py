# $language = "python"
# $interface = "1.0"

import re
import time

COMMAND_DELAY = 0.25


def ExtractInterface(text):
    if not text:
        return None

    patterns = [
        r'\b(?:Fa|Gi|Te|Twe|Fo|Hu|Eth)\d+(?:/\d+){1,3}\b',
        r'\b(?:FastEthernet|GigabitEthernet|TenGigabitEthernet|TwentyFiveGigE|TwentyFiveGigabitEthernet|FortyGigabitEthernet|HundredGigE|Ethernet)\d+(?:/\d+){1,3}\b',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)

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
        "Interface Snapshot",
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
        crt.Dialog.MessageBox(
            "No valid interface found.",
            "Interface Snapshot",
            0
        )
        return

    msg = (
        "Interface Snapshot\n"
        "------------------\n"
        "Interface: " + iface + "\n\n"
        "Commands to run:\n\n"
        "show interfaces " + iface + "\n"
        "show interfaces " + iface + " status\n"
        "show interfaces " + iface + " switchport\n"
        "show running-config interface " + iface + "\n"
        "show mac address-table interface " + iface + "\n"
        "show cdp neighbors " + iface + " detail\n\n"
        "Send these commands to the active session?"
    )

    resp = crt.Dialog.MessageBox(msg, "Interface Snapshot", 4)

    if resp != 6:
        return

    commands = [
        "show interfaces " + iface,
        "show interfaces " + iface + " status",
        "show interfaces " + iface + " switchport",
        "show running-config interface " + iface,
        "show mac address-table interface " + iface,
        "show cdp neighbors " + iface + " detail",
    ]

    for command in commands:
        screen.Send(command + "\r")
        time.sleep(COMMAND_DELAY)


Main()