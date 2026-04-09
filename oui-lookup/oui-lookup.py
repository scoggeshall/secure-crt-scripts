# $language = "python"
# $interface = "1.0"

# Offline SecureCRT OUI Lookup (UTF-8 safe, Python 2.7)
# SecureCRT 8.7.3 compatible
# Version: 2026-01

import os
import re

# ============================================================================
# CONFIGURATION
# ============================================================================
OUI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manuf.txt")

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _NormalizeMAC(mac_text):
    clean = re.sub(r'[^0-9A-Fa-f]', '', mac_text).upper()
    return clean if len(clean) == 12 else None


def ExtractMACPreserve(text):
    if not text:
        return (None, None)

    patterns = [
        re.compile(r'\b[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\b'),  # Cisco
        re.compile(r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b'),        # Colon/dash
        re.compile(r'\b[0-9A-Fa-f]{12}\b'),                               # Plain
    ]

    for pat in patterns:
        m = pat.search(text)
        if m:
            preserved = m.group(0).strip()
            normalized = _NormalizeMAC(preserved)
            if normalized:
                return (preserved, normalized)

    return (None, None)


def GetSelectedMAC():
    try:
        tab = crt.GetScriptTab()
        screen = tab.Screen
    except:
        crt.Dialog.MessageBox("Unable to access SecureCRT screen.", "OUI Lookup Error", 0)
        return (None, None)

    try:
        preserved, normalized = ExtractMACPreserve(screen.Selection.strip())
        if preserved:
            return (preserved, normalized)
    except:
        pass

    try:
        preserved, normalized = ExtractMACPreserve(crt.Clipboard.Text.strip())
        if preserved:
            return (preserved, normalized)
    except:
        pass

    try:
        row = screen.CurrentRow
        text = screen.Get(max(1, row-5), 1, min(row+5, screen.Rows), screen.Columns)
        preserved, normalized = ExtractMACPreserve(text)
        if preserved:
            return (preserved, normalized)
    except:
        pass

    try:
        text = screen.Get(1, 1, screen.Rows, screen.Columns)
        preserved, normalized = ExtractMACPreserve(text)
        if preserved:
            return (preserved, normalized)
    except:
        pass

    mac_input = crt.Dialog.Prompt("No MAC detected.\nEnter manually:", "OUI Lookup", "", False)
    return ExtractMACPreserve(mac_input)


def GetOUIPrefix(normalized12):
    return normalized12[:6] if normalized12 else None


def LookupVendor(normalized12):
    prefix = GetOUIPrefix(normalized12)
    if not prefix:
        return "Invalid MAC address."

    if not os.path.exists(OUI_FILE):
        return "OUI database not found:\n" + OUI_FILE

    try:
        f = open(OUI_FILE, "rb")
        data = f.read().decode("utf-8", "ignore")
        f.close()

        for line in data.splitlines():
            if not line or line.startswith("#"):
                continue
            line_clean = line.replace(':', '').replace('-', '').replace('\t', ' ')
            if line_clean.upper().startswith(prefix):
                parts = line.strip().split(None, 1)
                return "Vendor: " + parts[1].strip() if len(parts) > 1 else "Vendor not labeled"

        return "Vendor not found.\nOUI Prefix: " + prefix

    except Exception as e:
        return "Error reading OUI file:\n" + str(e)


# ============================================================================
# MAIN
# ============================================================================

def Main():
    try:
        tab = crt.GetScriptTab()
        screen = tab.Screen
        screen.Synchronous = True
    except:
        return

    mac_preserved, mac_norm = GetSelectedMAC()
    if not mac_preserved or not mac_norm:
        crt.Dialog.MessageBox(
            "No MAC address found.\nHighlight or copy one first.",
            "OUI Lookup",
            0
        )
        return

    vendor = LookupVendor(mac_norm)

    command = "show ip arp | inc " + mac_preserved

    msg = (
        "MAC: " + mac_preserved + "\n\n" +
        vendor + "\n\n" +
        "Run the following command?\n\n" +
        command
    )

    resp = crt.Dialog.MessageBox(msg, "OUI Lookup", 4)  # Yes / No

    if resp == 6:  # IDYES
        screen.Send(command + "\r")

    try:
        screen.Synchronous = False
    except:
        pass


Main()
