# $language = "python"
# $interface = "1.0"

import time

def Main():
    initial_tab = crt.GetScriptTab()
    count = crt.GetTabCount()
    disconnected = []

    # Send exit to all connected tabs
    for i in range(1, count + 1):
        tab = crt.GetTab(i)
        if tab.Session.Connected:
            tab.Screen.Send("exit\r")
        else:
            disconnected.append(str(i))

    # Wait a moment for exits to process
    time.sleep(1)

    # Close all tabs except the one running the script (in reverse order to avoid index shifting)
    for i in range(count, 0, -1):
        tab = crt.GetTab(i)
        if tab.Index != initial_tab.Index:
            tab.Close()

    msg = "Sent 'exit' to all connected tabs and closed them (except this script's tab)."
    if disconnected:
        msg += "\n\nSkipped tabs (not connected): " + ", ".join(disconnected)
    crt.Dialog.MessageBox(msg)

Main()