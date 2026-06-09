# $language = "python"
# $interface = "1.0"

# Cisco IOS/IOS-XE multi-session STP snapshot collector.
#
# Reads SecureCRT session names from sessions.txt in this script folder,
# connects to each session one at a time, saves raw command output per device,
# and creates simple CSV summaries where parsing is practical.
#
# SecureCRT compatibility:
#   - Avoids f-strings, pathlib, type annotations, and Python 3-only syntax.
#   - Uses existing SecureCRT session definitions for connection/authentication.
#   - Do not put passwords, tokens, or other credentials in sessions.txt.

import codecs
import datetime
import os
import re


SCRIPT_TITLE = "Multi STP Snapshot"

SCRIPT_DIRECTORY_FALLBACK = r"C:\scripts\secure-crt\stp-snapshot"
OUTPUT_ROOT = r"C:\scripts\secure-crt\outputs\stp-snapshot"
SESSIONS_FILE_NAME = "sessions.txt"
EXPECTED_ROOTS_FILE_NAME = "expected-roots.csv"
EXPECTED_ROOTS_EMPTY_NOTE = "expected-roots.csv exists but contains no active mappings."

COMMAND_TIMEOUT_SECONDS = 90
COMMAND_DELAY_MS = 500
DISCONNECT_WAIT_MS = 500
DISCONNECT_WAIT_ATTEMPTS = 60

COMMANDS = [
    ("Disable Paging", "terminal length 0"),
    ("STP Summary", "show spanning-tree summary"),
    ("STP Root", "show spanning-tree root"),
    ("STP Blocked Ports", "show spanning-tree blockedports"),
    ("STP Inconsistent Ports", "show spanning-tree inconsistentports"),
    ("STP Topology Changes", "show spanning-tree detail | include ieee|occurr|from|is executing|Number of topology changes|last topology change"),
    ("Interface Trunks", "show interfaces trunk"),
    ("EtherChannel Summary", "show etherchannel summary"),
    ("Interface Descriptions", "show interfaces description"),
]

RUN_SUMMARY_HEADERS = [
    "session",
    "status",
    "prompt",
    "raw_file",
    "error",
]

STP_SUMMARY_HEADERS = [
    "session",
    "mode",
    "root_bridge_for",
    "blocked_total",
    "inconsistent_total",
    "summary_note",
]

ROOT_HEADERS = [
    "session",
    "instance",
    "root_id",
    "cost",
    "root_port",
]

PORT_ISSUE_HEADERS = [
    "session",
    "source",
    "instance",
    "interface",
    "detail",
]

TOPOLOGY_HEADERS = [
    "session",
    "instance",
    "protocol",
    "topology_changes",
    "last_change",
    "from_interface",
    "note",
]

UPLINK_CONTEXT_HEADERS = [
    "session",
    "source",
    "interface",
    "context",
    "detail",
]

ROOT_CHECK_HEADERS = [
    "session",
    "vlan",
    "observed_root",
    "expected_root",
    "result",
    "note",
]

COMMAND_ERROR_TERMS = [
    "invalid input",
    "ambiguous command",
    "incomplete command",
    "unknown command",
    "unrecognized command",
    "% invalid",
    "% ambiguous",
    "% incomplete",
]


def Main():
    script_directory = get_script_directory()
    sessions_path = os.path.join(script_directory, SESSIONS_FILE_NAME)
    expected_roots_path = os.path.join(script_directory, EXPECTED_ROOTS_FILE_NAME)

    if not os.path.exists(sessions_path):
        crt.Dialog.MessageBox(
            "Session list file not found:\n\n" +
            sessions_path + "\n\n" +
            "Create sessions.txt with one SecureCRT session name per line.",
            SCRIPT_TITLE
        )
        return

    sessions = read_sessions(sessions_path)
    if len(sessions) == 0:
        crt.Dialog.MessageBox(
            "No sessions found in:\n\n" +
            sessions_path + "\n\n" +
            "Add one SecureCRT session name per line. Blank lines and # comments are ignored.",
            SCRIPT_TITLE
        )
        return

    if crt.Session.Connected:
        if not confirm_active_tab_reuse():
            return
        disconnect_current_session()

    expected_roots_file_exists = os.path.exists(expected_roots_path)
    expected_roots = []
    if expected_roots_file_exists:
        expected_roots = read_expected_roots(expected_roots_path)
    expected_roots_note = ""
    if expected_roots_file_exists and len(expected_roots) == 0:
        expected_roots_note = EXPECTED_ROOTS_EMPTY_NOTE

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_directory = os.path.join(OUTPUT_ROOT, timestamp)
    raw_directory = os.path.join(output_directory, "raw")
    ensure_directory(raw_directory)

    run_summary_rows = []
    stp_summary_rows = []
    root_rows = []
    port_issue_rows = []
    topology_rows = []
    uplink_context_rows = []

    for session in sessions:
        result = collect_session(session, raw_directory)
        run_summary_rows.append({
            "session": session,
            "status": result.get("status", ""),
            "prompt": result.get("prompt", ""),
            "raw_file": result.get("raw_file", ""),
            "error": result.get("error", ""),
        })

        if result.get("status") == "OK":
            parsed = parse_session_outputs(session, result.get("outputs", {}))
            stp_summary_rows.append(parsed["summary"])
            root_rows.extend(parsed["roots"])
            port_issue_rows.extend(parsed["port_issues"])
            topology_rows.extend(parsed["topology_changes"])
            uplink_context_rows.extend(parsed["uplink_context"])

    if expected_roots_note != "":
        run_summary_rows.append({
            "session": EXPECTED_ROOTS_FILE_NAME,
            "status": "NOTE",
            "prompt": "",
            "raw_file": "",
            "error": expected_roots_note,
        })

    write_csv(os.path.join(output_directory, "run-summary.csv"), RUN_SUMMARY_HEADERS, run_summary_rows)
    write_csv(os.path.join(output_directory, "stp-summary.csv"), STP_SUMMARY_HEADERS, stp_summary_rows)
    write_csv(os.path.join(output_directory, "stp-roots.csv"), ROOT_HEADERS, root_rows)
    write_csv(os.path.join(output_directory, "stp-port-issues.csv"), PORT_ISSUE_HEADERS, port_issue_rows)
    write_csv(os.path.join(output_directory, "stp-topology-changes.csv"), TOPOLOGY_HEADERS, topology_rows)
    write_csv(os.path.join(output_directory, "stp-uplink-context.csv"), UPLINK_CONTEXT_HEADERS, uplink_context_rows)

    if expected_roots_file_exists and len(expected_roots) > 0:
        root_check_rows = build_root_check_rows(expected_roots, stp_summary_rows, root_rows)
        write_csv(os.path.join(output_directory, "stp-root-check.csv"), ROOT_CHECK_HEADERS, root_check_rows)

    message_extra = ""
    if expected_roots_note != "":
        message_extra = "\n\n" + expected_roots_note

    crt.Dialog.MessageBox(
        "STP snapshot complete.\n\n" +
        "Sessions processed: " + str(len(sessions)) + "\n" +
        "Output folder:\n" + output_directory + "\n\n" +
        "Raw output is saved under the raw folder. CSV parsing is intentionally simple; " +
        "review raw output when a CSV field is blank or unclear." +
        message_extra,
        SCRIPT_TITLE
    )


def confirm_active_tab_reuse():
    response = crt.Dialog.Prompt(
        "The active tab is currently connected.\n\n" +
        "Cancel:\n" +
        "Leave this tab connected and stop the script.\n\n" +
        "Continue and allow the script to reuse/disconnect this tab:\n" +
        "Type CONTINUE to disconnect this tab and process sessions.txt one session at a time.\n\n" +
        "Default is Cancel.",
        SCRIPT_TITLE,
        "Cancel",
        False
    )

    if response is None:
        return False

    if response.strip().upper() == "CONTINUE":
        return True

    return False


def collect_session(session, raw_directory):
    result = {
        "session": session,
        "status": "ERROR",
        "prompt": "",
        "raw_file": os.path.join(raw_directory, sanitize_filename(session) + ".txt"),
        "error": "",
        "outputs": {},
    }

    raw_lines = []
    add_raw_header(raw_lines, session)

    try:
        crt.Session.Connect('/S "' + session + '"')
    except ScriptError:
        result["error"] = crt.GetLastErrorMessage()
    except Exception as exc:
        result["error"] = str(exc)

    if not crt.Session.Connected:
        if result["error"] == "":
            result["error"] = "SecureCRT did not report an active connection after Connect()."
        raw_lines.append("Connection failed: " + result["error"] + "\n")
        write_text_file(result["raw_file"], "".join(raw_lines))
        return result

    try:
        crt.Screen.Synchronous = True
        crt.Screen.IgnoreEscape = True
        wait_for_screen_idle()

        prompt = get_current_prompt()
        result["prompt"] = prompt

        if prompt == "":
            result["error"] = "Could not detect the CLI prompt."
            raw_lines.append("Prompt detection failed. Place the session at the device prompt and try again.\n")
            return result

        for label, command in COMMANDS:
            output = run_command(command, prompt)
            result["outputs"][command] = output
            add_raw_command_output(raw_lines, label, command, output)

        result["status"] = "OK"
    except Exception as exc:
        result["error"] = str(exc)
        raw_lines.append("\nScript error while collecting this session: " + result["error"] + "\n")
    finally:
        write_text_file(result["raw_file"], "".join(raw_lines))
        disconnect_current_session()

    return result


def run_command(command, prompt):
    crt.Screen.Send(command + "\r")

    # Move past the command echo before reading output where possible.
    crt.Screen.WaitForString("\r", 3)
    crt.Screen.WaitForString("\n", 3)

    output = crt.Screen.ReadString(prompt, COMMAND_TIMEOUT_SECONDS)
    if output is None:
        output = ""

    crt.Sleep(COMMAND_DELAY_MS)
    return normalize_text(output).strip()


def wait_for_screen_idle():
    wait_count = 0
    while wait_count < 10:
        if not crt.Screen.WaitForCursor(1):
            break
        wait_count += 1


def get_current_prompt():
    row = crt.Screen.CurrentRow
    col = crt.Screen.CurrentColumn - 1
    if col < 1:
        col = 1
    prompt = crt.Screen.Get(row, 0, row, col)
    return prompt.strip()


def disconnect_current_session():
    if crt.Session.Connected:
        crt.Session.Disconnect()

    attempt = 0
    while crt.Session.Connected and attempt < DISCONNECT_WAIT_ATTEMPTS:
        crt.Sleep(DISCONNECT_WAIT_MS)
        attempt += 1


def parse_session_outputs(session, outputs):
    summary_output = outputs.get("show spanning-tree summary", "")
    root_output = outputs.get("show spanning-tree root", "")
    blocked_output = outputs.get("show spanning-tree blockedports", "")
    inconsistent_output = outputs.get("show spanning-tree inconsistentports", "")
    topology_output = outputs.get("show spanning-tree detail | include ieee|occurr|from|is executing|Number of topology changes|last topology change", "")
    trunk_output = outputs.get("show interfaces trunk", "")
    etherchannel_output = outputs.get("show etherchannel summary", "")
    description_output = outputs.get("show interfaces description", "")

    summary = parse_stp_summary(session, summary_output)
    summary["blocked_total"] = parse_port_total(blocked_output, "blocked")
    summary["inconsistent_total"] = parse_port_total(inconsistent_output, "inconsistent")

    roots = parse_stp_roots(session, root_output)
    port_issues = []
    port_issues.extend(parse_blocked_ports(session, blocked_output))
    port_issues.extend(parse_inconsistent_ports(session, inconsistent_output))
    topology_changes = parse_topology_changes(session, topology_output)
    uplink_context = []
    uplink_context.extend(parse_trunk_context(session, trunk_output))
    uplink_context.extend(parse_etherchannel_context(session, etherchannel_output))
    uplink_context.extend(parse_interface_descriptions(session, description_output))

    return {
        "summary": summary,
        "roots": roots,
        "port_issues": port_issues,
        "topology_changes": topology_changes,
        "uplink_context": uplink_context,
    }


def parse_stp_summary(session, output):
    mode = ""
    root_bridge_for = ""
    note = detect_command_error(output)

    for line in normalize_text(output).split("\n"):
        stripped = line.strip()

        match = re.search(r"Switch is in\s+(.+?)\s+mode", stripped, re.I)
        if match:
            mode = match.group(1).strip()

        match = re.search(r"Root bridge for:\s*(.*)$", stripped, re.I)
        if match:
            root_bridge_for = match.group(1).strip()

    return {
        "session": session,
        "mode": mode,
        "root_bridge_for": root_bridge_for,
        "blocked_total": "",
        "inconsistent_total": "",
        "summary_note": note,
    }


def parse_port_total(output, label):
    text = normalize_text(output)
    lower = text.lower()

    pattern = r"Number of\s+" + re.escape(label) + r"\s+ports.*?:\s*(\d+)"
    match = re.search(pattern, text, re.I)
    if match:
        return match.group(1)

    if "no " + label in lower:
        return "0"

    return ""


def parse_stp_roots(session, output):
    rows = []

    for line in normalize_text(output).split("\n"):
        stripped = line.strip()

        if not is_stp_data_line(stripped):
            continue

        parts = re.split(r"\s{2,}", stripped)
        if len(parts) >= 7:
            rows.append({
                "session": session,
                "instance": parts[0],
                "root_id": parts[1],
                "cost": parts[2],
                "root_port": parts[-1],
            })
            continue

        match = re.match(r"^(\S+)\s+(.+?)\s+(\d+)\s+\d+\s+\d+\s+\d+\s+(\S+)$", stripped)
        if match:
            rows.append({
                "session": session,
                "instance": match.group(1),
                "root_id": match.group(2).strip(),
                "cost": match.group(3),
                "root_port": match.group(4),
            })

    return rows


def parse_blocked_ports(session, output):
    rows = []

    for line in normalize_text(output).split("\n"):
        stripped = line.strip()

        if not is_stp_data_line(stripped):
            continue

        parts = re.split(r"\s{2,}", stripped)
        if len(parts) < 2:
            continue

        instance = parts[0]
        interface_text = parts[1]
        interfaces = re.split(r"[,\s]+", interface_text)

        for interface_name in interfaces:
            interface_name = interface_name.strip()
            if is_interface_token(interface_name):
                rows.append({
                    "session": session,
                    "source": "blockedports",
                    "instance": instance,
                    "interface": interface_name,
                    "detail": "blocked",
                })

    return rows


def parse_inconsistent_ports(session, output):
    rows = []

    for line in normalize_text(output).split("\n"):
        stripped = line.strip()

        if not is_stp_data_line(stripped):
            continue

        parts = re.split(r"\s{2,}", stripped)
        if len(parts) < 3:
            continue

        rows.append({
            "session": session,
            "source": "inconsistentports",
            "instance": parts[0],
            "interface": parts[1],
            "detail": parts[2],
        })

    return rows


def parse_topology_changes(session, output):
    rows = []
    current = None
    note = detect_command_error(output)

    for line in normalize_text(output).split("\n"):
        stripped = line.strip()
        if stripped == "":
            continue

        match = re.match(r"^(\S+)\s+is executing\s+(.+)$", stripped, re.I)
        if match:
            if current is not None:
                rows.append(current)
            current = {
                "session": session,
                "instance": match.group(1),
                "protocol": match.group(2).strip(),
                "topology_changes": "",
                "last_change": "",
                "from_interface": "",
                "note": note,
            }
            continue

        if current is None:
            continue

        match = re.search(r"Number of topology changes\s+(\d+)", stripped, re.I)
        if match:
            current["topology_changes"] = match.group(1)

        match = re.search(r"(?:last topology change|last change)\s+(?:occurred\s+)?(.+)$", stripped, re.I)
        if match:
            current["last_change"] = match.group(1).strip()

        match = re.match(r"^from\s+(.+)$", stripped, re.I)
        if match:
            current["from_interface"] = match.group(1).strip()

    if current is not None:
        rows.append(current)

    if len(rows) == 0 and note != "":
        rows.append({
            "session": session,
            "instance": "",
            "protocol": "",
            "topology_changes": "",
            "last_change": "",
            "from_interface": "",
            "note": note,
        })

    return rows


def parse_trunk_context(session, output):
    rows = []
    section = "trunk"
    note = detect_command_error(output)

    for line in normalize_text(output).split("\n"):
        stripped = line.strip()
        lower = stripped.lower()

        if stripped == "":
            continue

        if lower.startswith("port ") and "vlan" in lower:
            section = stripped
            continue

        first = first_token(stripped)
        if not is_interface_token(first):
            continue

        detail = stripped[len(first):].strip()
        if note != "":
            detail = append_note(detail, note)

        rows.append({
            "session": session,
            "source": "show interfaces trunk",
            "interface": first,
            "context": section,
            "detail": detail,
        })

    if len(rows) == 0 and note != "":
        rows.append(make_context_note(session, "show interfaces trunk", note))

    return rows


def parse_etherchannel_context(session, output):
    rows = []
    note = detect_command_error(output)

    for line in normalize_text(output).split("\n"):
        stripped = line.strip()
        if stripped == "":
            continue

        match = re.match(r"^\d+\s+(\S*Po\d+\S*)\s+(\S+)\s+(.*)$", stripped, re.I)
        if not match:
            continue

        port_channel = match.group(1)
        protocol = match.group(2)
        members_text = match.group(3).strip()
        detail = "protocol=" + protocol + "; members=" + members_text
        if note != "":
            detail = append_note(detail, note)

        rows.append({
            "session": session,
            "source": "show etherchannel summary",
            "interface": port_channel,
            "context": "port-channel",
            "detail": detail,
        })

        members = extract_interface_tokens(members_text)
        for member in members:
            rows.append({
                "session": session,
                "source": "show etherchannel summary",
                "interface": member,
                "context": "etherchannel-member",
                "detail": "port-channel=" + port_channel + "; protocol=" + protocol,
            })

    if len(rows) == 0 and note != "":
        rows.append(make_context_note(session, "show etherchannel summary", note))

    return rows


def parse_interface_descriptions(session, output):
    rows = []
    note = detect_command_error(output)

    for line in normalize_text(output).split("\n"):
        stripped = line.rstrip()
        if stripped.strip() == "":
            continue

        first = first_token(stripped)
        if not is_interface_token(first):
            continue

        detail = stripped[len(first):].strip()
        if note != "":
            detail = append_note(detail, note)

        rows.append({
            "session": session,
            "source": "show interfaces description",
            "interface": first,
            "context": "description",
            "detail": detail,
        })

    if len(rows) == 0 and note != "":
        rows.append(make_context_note(session, "show interfaces description", note))

    return rows


def build_root_check_rows(expected_roots, stp_summary_rows, root_rows):
    rows = []
    observed_by_vlan = build_observed_root_sessions(stp_summary_rows, root_rows)

    for expected in expected_roots:
        vlan_text = expected.get("vlan", "")
        normalized_vlan = normalize_vlan(vlan_text)
        expected_root = expected.get("expected_root_session", "")
        observed_roots = observed_by_vlan.get(normalized_vlan, [])
        observed_root = ";".join(observed_roots)
        result = "WARN"
        note = "No observed root session was parsed for this VLAN."

        if len(observed_roots) > 0:
            if contains_session(observed_roots, expected_root):
                result = "PASS"
                note = "Expected root session was observed as root."
            else:
                result = "FAIL"
                note = "Observed root session does not match expected root session."

        rows.append({
            "session": expected_root,
            "vlan": vlan_text,
            "observed_root": observed_root,
            "expected_root": expected_root,
            "result": result,
            "note": note,
        })

    return rows


def build_observed_root_sessions(stp_summary_rows, root_rows):
    observed = {}

    for row in stp_summary_rows:
        session = row.get("session", "")
        vlan_text = row.get("root_bridge_for", "")
        vlans = parse_instance_list(vlan_text)
        for vlan in vlans:
            add_observed_root(observed, vlan, session)

    for row in root_rows:
        root_port = row.get("root_port", "")
        if not root_port_indicates_this_bridge(root_port):
            continue
        add_observed_root(observed, row.get("instance", ""), row.get("session", ""))

    return observed


def add_observed_root(observed, vlan_text, session):
    vlan = normalize_vlan(vlan_text)
    if vlan == "" or session == "":
        return
    if vlan not in observed:
        observed[vlan] = []
    if session not in observed[vlan]:
        observed[vlan].append(session)


def parse_instance_list(text):
    values = []
    cleaned = text.replace(";", ",")
    parts = re.split(r"[,\s]+", cleaned)

    for part in parts:
        part = part.strip()
        if part == "":
            continue

        if "-" in part:
            pieces = part.split("-", 1)
            if len(pieces) != 2:
                continue
            start = parse_vlan_number(pieces[0])
            end = parse_vlan_number(pieces[1])
            if start is None or end is None:
                continue
            if start > end:
                start, end = end, start
            for vlan_number in range(start, end + 1):
                values.append("VLAN" + str(vlan_number))
            continue

        normalized = normalize_vlan(part)
        if normalized != "":
            values.append(normalized)

    return values


def normalize_vlan(value):
    value = str(value).strip()
    if value == "":
        return ""

    match = re.search(r"(\d+)$", value)
    if match:
        return "VLAN" + str(int(match.group(1)))

    return value.upper()


def parse_vlan_number(value):
    match = re.search(r"(\d+)$", value.strip(), re.I)
    if not match:
        return None
    return int(match.group(1))


def root_port_indicates_this_bridge(value):
    lower = value.lower()
    if "this" in lower and "root" in lower:
        return True
    if lower in ["root", "self"]:
        return True
    return False


def contains_session(values, expected):
    expected_lower = expected.strip().lower()
    for value in values:
        if value.strip().lower() == expected_lower:
            return True
    return False


def is_stp_data_line(line):
    if line == "":
        return False
    if line.startswith("-"):
        return False
    lower = line.lower()
    if lower.startswith("name "):
        return False
    if lower.startswith("vlan ") or lower.startswith("root "):
        return False
    if lower.startswith("number of "):
        return False
    if lower.startswith("switch is "):
        return False
    return re.match(r"^(vlan\d+|mst\d+|mst|pvst|rapid-pvst)\b", line, re.I) is not None


def is_interface_token(value):
    if value == "":
        return False
    if value.lower() in ["none", "n/a", "-"]:
        return False
    return re.match(
        r"^(fa|fas|fastethernet|gi|gig|gigabitethernet|te|ten|tengigabitethernet|tw|twe|twentyfivegige|twentyfivegigabitethernet|fo|forty|fortygigabitethernet|hu|hundred|hundredgige|eth|et|ethernet|po|port-channel)\S+$",
        value,
        re.I
    ) is not None


def first_token(value):
    parts = value.strip().split()
    if len(parts) == 0:
        return ""
    return parts[0]


def extract_interface_tokens(value):
    interfaces = []
    parts = re.split(r"[,\s]+", value)

    for part in parts:
        cleaned = re.sub(r"\(.*?\)", "", part.strip())
        if is_interface_token(cleaned) and cleaned not in interfaces:
            interfaces.append(cleaned)

    return interfaces


def append_note(detail, note):
    if detail == "":
        return note
    return detail + "; " + note


def make_context_note(session, source, note):
    return {
        "session": session,
        "source": source,
        "interface": "",
        "context": "note",
        "detail": note,
    }


def detect_command_error(output):
    lower = normalize_text(output).lower()
    for term in COMMAND_ERROR_TERMS:
        if term in lower:
            return "Command output may contain an IOS error: " + term
    return ""


def get_script_directory():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return SCRIPT_DIRECTORY_FALLBACK


def read_sessions(path):
    sessions = []
    handle = codecs.open(path, "r", "utf-8")
    try:
        for line in handle:
            session = line.strip()
            if session == "":
                continue
            if session.startswith("#"):
                continue
            sessions.append(session)
    finally:
        handle.close()
    return sessions


def read_expected_roots(path):
    rows = []
    handle = codecs.open(path, "r", "utf-8")
    try:
        for line in handle:
            stripped = line.strip()
            if stripped == "":
                continue
            if stripped.startswith("#"):
                continue

            parts = parse_csv_line(stripped)
            if len(parts) < 2:
                continue

            vlan = parts[0].strip()
            expected_root_session = parts[1].strip()

            if vlan.lower() == "vlan" and expected_root_session.lower() == "expected_root_session":
                continue

            if vlan == "" or expected_root_session == "":
                continue

            rows.append({
                "vlan": vlan,
                "expected_root_session": expected_root_session,
            })
    finally:
        handle.close()

    return rows


def parse_csv_line(line):
    values = []
    current = ""
    in_quotes = False
    index = 0

    while index < len(line):
        char = line[index]

        if char == '"':
            if in_quotes and index + 1 < len(line) and line[index + 1] == '"':
                current += '"'
                index += 1
            else:
                in_quotes = not in_quotes
        elif char == "," and not in_quotes:
            values.append(current)
            current = ""
        else:
            current += char

        index += 1

    values.append(current)
    return values


def ensure_directory(path):
    if not os.path.exists(path):
        os.makedirs(path)


def sanitize_filename(value):
    value = value.strip()
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value)
    value = value.strip("-._")
    if value == "":
        value = "UNKNOWN"
    return value


def normalize_text(text):
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\x1b", "")
    text = text.replace("\n\r", "\r\n")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return text


def add_raw_header(lines, session):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append("Cisco IOS/IOS-XE STP Snapshot\n")
    lines.append("Session: " + session + "\n")
    lines.append("Generated: " + now + "\n")
    lines.append("\n")


def add_raw_command_output(lines, label, command, output):
    lines.append("=" * 78 + "\n")
    lines.append(label + "\n")
    lines.append("Command: " + command + "\n")
    lines.append("=" * 78 + "\n")
    if output.strip() == "":
        lines.append("[No output captured]\n")
    else:
        lines.append(output + "\n")
    lines.append("\n")


def write_text_file(path, data):
    ensure_directory(os.path.dirname(path))
    handle = codecs.open(path, "w", "utf-8")
    try:
        handle.write(data)
    finally:
        handle.close()


def write_csv(path, headers, rows):
    ensure_directory(os.path.dirname(path))
    handle = codecs.open(path, "w", "utf-8")
    try:
        handle.write(",".join(headers) + "\r\n")
        for row in rows:
            values = []
            for header in headers:
                values.append(csv_escape(row.get(header, "")))
            handle.write(",".join(values) + "\r\n")
    finally:
        handle.close()


def csv_escape(value):
    value = normalize_text(value).strip()
    value = value.replace("\n", " ")
    if '"' in value or "," in value or "\r" in value or "\n" in value:
        return '"' + value.replace('"', '""') + '"'
    return value


Main()
