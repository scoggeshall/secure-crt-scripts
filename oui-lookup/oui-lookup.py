# $language = "python"
# $interface = "1.0"

import os
import re

SCRIPT_VERSION = "2.1"
OUI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manuf.txt")


def NormalizeMAC(mac_text):
    """Return a 12-character uppercase MAC for OUI matching only."""
    clean = re.sub(r'[^0-9A-Fa-f]', '', mac_text).upper()
    return clean if len(clean) == 12 else None


def ExtractMACPreserve(text):
    """
    Find a MAC address and return both:
      1. The exact formatting found on the switch or supplied by the user.
      2. A normalized 12-character value for manuf.txt lookup.
    """
    if not text:
        return (None, None)

    patterns = [
        re.compile(r'\b[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\b'),
        re.compile(r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b'),
        re.compile(r'\b[0-9A-Fa-f]{12}\b'),
    ]

    for pat in patterns:
        match = pat.search(text)
        if match:
            preserved = match.group(0).strip()
            normalized = NormalizeMAC(preserved)
            if normalized:
                return (preserved, normalized)

    return (None, None)


def GetSelectedMAC():
    try:
        tab = crt.GetScriptTab()
        screen = tab.Screen
    except Exception:
        crt.Dialog.MessageBox(
            "Unable to access SecureCRT screen.",
            "OUI Lookup Error",
            0
        )
        return (None, None)

    # Prefer explicitly selected text.
    try:
        preserved, normalized = ExtractMACPreserve(screen.Selection.strip())
        if preserved:
            return (preserved, normalized)
    except Exception:
        pass

    # Then try clipboard contents.
    try:
        preserved, normalized = ExtractMACPreserve(crt.Clipboard.Text.strip())
        if preserved:
            return (preserved, normalized)
    except Exception:
        pass

    # Then search near the cursor.
    try:
        row = screen.CurrentRow
        text = screen.Get(
            max(1, row - 5),
            1,
            min(row + 5, screen.Rows),
            screen.Columns
        )
        preserved, normalized = ExtractMACPreserve(text)
        if preserved:
            return (preserved, normalized)
    except Exception:
        pass

    # Last automatic attempt: search the visible terminal screen.
    try:
        text = screen.Get(1, 1, screen.Rows, screen.Columns)
        preserved, normalized = ExtractMACPreserve(text)
        if preserved:
            return (preserved, normalized)
    except Exception:
        pass

    mac_input = crt.Dialog.Prompt(
        "No MAC detected.\nEnter manually:",
        "OUI Lookup",
        "",
        False
    )
    return ExtractMACPreserve(mac_input)


def ParseManufPrefix(raw_prefix):
    raw_prefix = raw_prefix.strip()

    if "/" in raw_prefix:
        base, bits = raw_prefix.split("/", 1)
        try:
            bits = int(bits)
        except Exception:
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
    """Use only the normalized MAC value when searching manuf.txt."""
    if not normalized12:
        return "Invalid MAC address."

    if not os.path.exists(OUI_FILE):
        return "OUI database not found:\n" + OUI_FILE

    best_bits = -1
    best_vendor = None
    best_prefix = None

    try:
        with open(OUI_FILE, "rb") as oui_handle:
            data = oui_handle.read().decode("utf-8", "ignore")

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
                "Vendor:\n" +
                best_vendor + "\n" +
                "OUI Match: " + best_prefix + "/" + str(best_bits)
            )

        return "Vendor not found.\nOUI Prefix: " + normalized12[:6]

    except Exception as error:
        return "Error reading OUI file:\n" + str(error)


def Main():
    try:
        tab = crt.GetScriptTab()
        screen = tab.Screen
    except Exception:
        return

    mac_preserved, mac_normalized = GetSelectedMAC()

    if not mac_preserved or not mac_normalized:
        crt.Dialog.MessageBox(
            "No MAC address found.\nHighlight or copy one first.",
            "OUI Lookup v" + SCRIPT_VERSION,
            0
        )
        return

    vendor = LookupVendor(mac_normalized)
    # Critical behavior:
    # Use the exact MAC format detected from the switch for the ARP command.
    command = "show ip arp | inc " + mac_preserved

    msg = (
        "MAC Address From Switch\n"
        "------------------------------\n" +
        mac_preserved + "\n\n\n"
        "Vendor Match\n"
        "------------------------------\n" +
        vendor + "\n\n\n"
        "Command\n"
        "------------------------------\n" +
        command + "\n\n\n"
        "Choose an action:\n"
        "Yes = Send to active session\n"
        "No = Copy to clipboard\n"
        "Cancel = Do nothing"
    )

    # MB_YESNOCANCEL = 3
    response = crt.Dialog.MessageBox(msg, "OUI Lookup v" + SCRIPT_VERSION, 3)

    # IDYES = 6
    if response == 6:
        screen.Send(command + "\r")

    # IDNO = 7
    elif response == 7:
        crt.Clipboard.Format = "CF_TEXT"
        crt.Clipboard.Text = command
        crt.Dialog.MessageBox(
            "Command copied to clipboard:\n\n" + command,
            "OUI Lookup v" + SCRIPT_VERSION,
            0
        )


Main()