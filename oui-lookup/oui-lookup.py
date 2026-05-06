# $language = "python"
# $interface = "1.0"

import os
import re

OUI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manuf.txt")


def NormalizeMAC(mac_text):
    clean = re.sub(r'[^0-9A-Fa-f]', '', mac_text).upper()
    return clean if len(clean) == 12 else None


def CiscoMAC(normalized12):
    return (
        normalized12[0:4].lower() + "." +
        normalized12[4:8].lower() + "." +
        normalized12[8:12].lower()
    )


def ExtractMACPreserve(text):
    if not text:
        return (None, None)

    patterns = [
        re.compile(r'\b[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\b'),
        re.compile(r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b'),
        re.compile(r'\b[0-9A-Fa-f]{12}\b'),
    ]

    for pat in patterns:
        m = pat.search(text)
        if m:
            preserved = m.group(0).strip()
            normalized = NormalizeMAC(preserved)
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
        text = screen.Get(max(1, row - 5), 1, min(row + 5, screen.Rows), screen.Columns)
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


def ParseManufPrefix(raw_prefix):
    raw_prefix = raw_prefix.strip()

    if "/" in raw_prefix:
        base, bits = raw_prefix.split("/", 1)
        try:
            bits = int(bits)
        except:
            return (None, None)
    else:
        base = raw_prefix
        bits = 24

    clean = re.sub(r'[^0-9A-Fa-f]', '', base).upper()

    if bits == 24:
        needed_hex = 6
    elif bits == 28:
        needed_hex = 7
    elif bits == 36:
        needed_hex = 9
    else:
        return (None, None)

    if len(clean) < needed_hex:
        return (None, None)

    return (clean[:needed_hex], bits)


def LookupVendor(normalized12):
    if not normalized12:
        return "Invalid MAC address."

    if not os.path.exists(OUI_FILE):
        return "OUI database not found:\n" + OUI_FILE

    best_bits = -1
    best_vendor = None
    best_prefix = None

    try:
        f = open(OUI_FILE, "rb")
        data = f.read().decode("utf-8", "ignore")
        f.close()

        for line in data.splitlines():
            if not line or line.startswith("#"):
                continue

            parts = line.strip().split(None, 2)
            if len(parts) < 2:
                continue

            prefix, bits = ParseManufPrefix(parts[0])
            if not prefix:
                continue

            if normalized12.startswith(prefix) and bits > best_bits:
                best_bits = bits
                best_prefix = prefix

                if len(parts) >= 3:
                    best_vendor = parts[2].strip()
                else:
                    best_vendor = parts[1].strip()

        if best_vendor:
            return (
                "Vendor: " + best_vendor + "\n" +
                "OUI Match: " + best_prefix + "/" + str(best_bits)
            )

        return "Vendor not found.\nOUI Prefix: " + normalized12[:6]

    except Exception as e:
        return "Error reading OUI file:\n" + str(e)


def Main():
    try:
        tab = crt.GetScriptTab()
        screen = tab.Screen
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
    mac_cisco = CiscoMAC(mac_norm)

    command = "show ip arp | inc " + mac_cisco

    msg = (
    "MAC Address\n"
    "-----------\n"
    + mac_cisco + "\n\n"
    "Vendor Match\n"
    "------------\n"
    + vendor + "\n\n"
    "Command\n"
    
    + command + "\n\n"
    "Send this command to the active session?"
)

    resp = crt.Dialog.MessageBox(msg, "OUI Lookup", 4)

    if resp == 6:
        screen.Send(command + "\r")

        


Main()