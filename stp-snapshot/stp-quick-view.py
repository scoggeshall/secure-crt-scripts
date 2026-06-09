# $language = "python"
# $interface = "1.0"

# Cisco IOS/IOS-XE STP quick view for the active SecureCRT tab.
# Read-only commands only. No output is saved by this script.

import time


SCRIPT_TITLE = "STP Quick View"
COMMAND_DELAY_SECONDS = 0.25

COMMANDS = [
    "terminal length 0",
    "show spanning-tree summary",
    "show spanning-tree root",
    "show spanning-tree blockedports",
    "show spanning-tree inconsistentports",
    "show spanning-tree detail | include ieee|occurr|from|is executing|Number of topology changes|last topology change",
    "show interfaces trunk",
]


def Main():
    tab = crt.GetScriptTab()

    if not tab.Session.Connected:
        crt.Dialog.MessageBox(
            "Not connected. Connect to the Cisco IOS/IOS-XE device in the active tab first.",
            SCRIPT_TITLE
        )
        return

    screen = tab.Screen
    screen.IgnoreEscape = True

    for command in COMMANDS:
        screen.Send(command + "\r")
        time.sleep(COMMAND_DELAY_SECONDS)


Main()
