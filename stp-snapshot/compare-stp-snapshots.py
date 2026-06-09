# $language = "python"
# $interface = "1.0"

# Compare two local multi-stp-snapshot.py output folders.
# This script is local-only and does not connect to any device.

import codecs
import datetime
import os


SCRIPT_TITLE = "Compare STP Snapshots"
OUTPUT_ROOT = r"C:\scripts\secure-crt\outputs\stp-snapshot"

REQUIRED_COMPARE_FILES = [
    "stp-summary.csv",
    "stp-roots.csv",
    "stp-port-issues.csv",
    "stp-topology-changes.csv",
    "run-summary.csv",
]

OPTIONAL_ROOT_CHECK_FILE = "stp-root-check.csv"

DIFF_HEADERS = [
    "change_type",
    "session",
    "instance",
    "interface",
    "previous",
    "current",
    "note",
]


def Main():
    previous_folder = prompt_folder("Previous snapshot folder:", OUTPUT_ROOT)
    if previous_folder is None:
        return

    current_folder = prompt_folder("Current snapshot folder:", OUTPUT_ROOT)
    if current_folder is None:
        return

    if not os.path.isdir(previous_folder):
        crt.Dialog.MessageBox("Previous snapshot folder not found:\n\n" + previous_folder, SCRIPT_TITLE)
        return

    if not os.path.isdir(current_folder):
        crt.Dialog.MessageBox("Current snapshot folder not found:\n\n" + current_folder, SCRIPT_TITLE)
        return

    if os.path.abspath(previous_folder).lower() == os.path.abspath(current_folder).lower():
        crt.Dialog.MessageBox("Choose two different snapshot folders.", SCRIPT_TITLE)
        return

    previous = load_snapshot(previous_folder)
    current = load_snapshot(current_folder)

    diffs = []
    add_missing_file_diffs(diffs, previous_folder, current_folder)
    compare_run_summary(diffs, previous["run-summary.csv"], current["run-summary.csv"])
    compare_roots(diffs, previous["stp-roots.csv"], current["stp-roots.csv"])
    compare_port_issues(diffs, previous["stp-port-issues.csv"], current["stp-port-issues.csv"])
    compare_topology_changes(diffs, previous["stp-topology-changes.csv"], current["stp-topology-changes.csv"])
    compare_stp_summary(diffs, previous["stp-summary.csv"], current["stp-summary.csv"])
    compare_root_checks(
        diffs,
        previous_folder,
        current_folder,
        previous[OPTIONAL_ROOT_CHECK_FILE],
        current[OPTIONAL_ROOT_CHECK_FILE]
    )

    csv_path = os.path.join(current_folder, "stp-diff.csv")
    text_path = os.path.join(current_folder, "stp-diff.txt")

    write_csv(csv_path, DIFF_HEADERS, diffs)
    write_text_file(text_path, render_text_diff(previous_folder, current_folder, diffs))

    crt.Dialog.MessageBox(
        "STP snapshot comparison complete.\n\n" +
        "Changes flagged: " + str(len(diffs)) + "\n\n" +
        "Text diff:\n" + text_path + "\n\n" +
        "CSV diff:\n" + csv_path,
        SCRIPT_TITLE
    )


def prompt_folder(message, default_value):
    value = crt.Dialog.Prompt(message, SCRIPT_TITLE, default_value, False)
    if value is None:
        return None
    value = value.strip().strip('"')
    if value == "":
        return None
    return value


def load_snapshot(folder):
    data = {}
    for file_name in REQUIRED_COMPARE_FILES:
        data[file_name] = read_csv(os.path.join(folder, file_name))
    data[OPTIONAL_ROOT_CHECK_FILE] = read_csv(os.path.join(folder, OPTIONAL_ROOT_CHECK_FILE))
    return data


def add_missing_file_diffs(diffs, previous_folder, current_folder):
    for file_name in REQUIRED_COMPARE_FILES:
        previous_path = os.path.join(previous_folder, file_name)
        current_path = os.path.join(current_folder, file_name)

        if not os.path.exists(previous_path):
            add_diff(
                diffs,
                "input file missing",
                "",
                "",
                "",
                "",
                file_name,
                "Previous snapshot is missing " + file_name
            )

        if not os.path.exists(current_path):
            add_diff(
                diffs,
                "input file missing",
                "",
                "",
                "",
                file_name,
                "",
                "Current snapshot is missing " + file_name
            )


def compare_run_summary(diffs, previous_rows, current_rows):
    previous_by_session = rows_by_key(previous_rows, ["session"])
    current_by_session = rows_by_key(current_rows, ["session"])

    for key in previous_by_session:
        previous_row = previous_by_session[key]
        current_row = current_by_session.get(key)
        session = previous_row.get("session", "")

        if current_row is None:
            add_diff(
                diffs,
                "session missing from current snapshot",
                session,
                "",
                "",
                previous_row.get("status", ""),
                "",
                "Session existed in previous run-summary.csv but not current run-summary.csv."
            )
            continue

        previous_status = previous_row.get("status", "")
        current_status = current_row.get("status", "")
        if previous_status == "OK" and current_status != "OK":
            add_diff(
                diffs,
                "session failed now but succeeded before",
                session,
                "",
                "",
                previous_status,
                current_status,
                current_row.get("error", "")
            )


def compare_roots(diffs, previous_rows, current_rows):
    previous_by_key = rows_by_key(previous_rows, ["session", "instance"])
    current_by_key = rows_by_key(current_rows, ["session", "instance"])

    for key in previous_by_key:
        if key not in current_by_key:
            continue

        previous_row = previous_by_key[key]
        current_row = current_by_key[key]
        session = previous_row.get("session", "")
        instance = previous_row.get("instance", "")

        previous_root = previous_row.get("root_id", "")
        current_root = current_row.get("root_id", "")
        if previous_root != current_root:
            add_diff(
                diffs,
                "root bridge changed",
                session,
                instance,
                "",
                previous_root,
                current_root,
                "Root ID changed for this session and instance."
            )

        previous_port = previous_row.get("root_port", "")
        current_port = current_row.get("root_port", "")
        if previous_port != current_port:
            add_diff(
                diffs,
                "root port changed",
                session,
                instance,
                "",
                previous_port,
                current_port,
                "Root port changed for this session and instance."
            )


def compare_port_issues(diffs, previous_rows, current_rows):
    previous_blocked = port_issue_map(previous_rows, "blockedports")
    current_blocked = port_issue_map(current_rows, "blockedports")
    previous_inconsistent = port_issue_map(previous_rows, "inconsistentports")
    current_inconsistent = port_issue_map(current_rows, "inconsistentports")

    compare_issue_set(diffs, previous_blocked, current_blocked, "new blocked port", "cleared blocked port")
    compare_issue_set(diffs, previous_inconsistent, current_inconsistent, "new inconsistent port", "cleared inconsistent port")


def compare_issue_set(diffs, previous_map, current_map, new_label, cleared_label):
    for key in current_map:
        if key not in previous_map:
            row = current_map[key]
            add_diff(
                diffs,
                new_label,
                row.get("session", ""),
                row.get("instance", ""),
                row.get("interface", ""),
                "",
                row.get("detail", ""),
                "Present in current snapshot but not previous snapshot."
            )

    for key in previous_map:
        if key not in current_map:
            row = previous_map[key]
            add_diff(
                diffs,
                cleared_label,
                row.get("session", ""),
                row.get("instance", ""),
                row.get("interface", ""),
                row.get("detail", ""),
                "",
                "Present in previous snapshot but not current snapshot."
            )


def compare_topology_changes(diffs, previous_rows, current_rows):
    previous_by_key = rows_by_key(previous_rows, ["session", "instance"])
    current_by_key = rows_by_key(current_rows, ["session", "instance"])

    for key in previous_by_key:
        if key not in current_by_key:
            continue

        previous_row = previous_by_key[key]
        current_row = current_by_key[key]
        previous_count = parse_int(previous_row.get("topology_changes", ""))
        current_count = parse_int(current_row.get("topology_changes", ""))

        if previous_count is None or current_count is None:
            continue

        if current_count > previous_count:
            add_diff(
                diffs,
                "topology change counter increased",
                current_row.get("session", ""),
                current_row.get("instance", ""),
                current_row.get("from_interface", ""),
                str(previous_count),
                str(current_count),
                "Last change: " + current_row.get("last_change", "")
            )


def compare_stp_summary(diffs, previous_rows, current_rows):
    previous_by_session = rows_by_key(previous_rows, ["session"])
    current_by_session = rows_by_key(current_rows, ["session"])

    fields = ["mode", "root_bridge_for", "blocked_total", "inconsistent_total"]
    for key in previous_by_session:
        if key not in current_by_session:
            continue

        previous_row = previous_by_session[key]
        current_row = current_by_session[key]
        session = previous_row.get("session", "")

        for field in fields:
            previous_value = previous_row.get(field, "")
            current_value = current_row.get(field, "")
            if previous_value != current_value:
                add_diff(
                    diffs,
                    "stp summary changed",
                    session,
                    "",
                    "",
                    previous_value,
                    current_value,
                    field + " changed in stp-summary.csv."
                )


def compare_root_checks(diffs, previous_folder, current_folder, previous_rows, current_rows):
    previous_path = os.path.join(previous_folder, OPTIONAL_ROOT_CHECK_FILE)
    current_path = os.path.join(current_folder, OPTIONAL_ROOT_CHECK_FILE)
    previous_exists = os.path.exists(previous_path)
    current_exists = os.path.exists(current_path)

    if not previous_exists and not current_exists:
        return

    if previous_exists and not current_exists:
        add_diff(
            diffs,
            "root-check missing from one snapshot",
            "",
            "",
            "",
            OPTIONAL_ROOT_CHECK_FILE,
            "",
            "Previous snapshot has stp-root-check.csv, but current snapshot does not."
        )
        return

    if current_exists and not previous_exists:
        add_diff(
            diffs,
            "root-check missing from one snapshot",
            "",
            "",
            "",
            "",
            OPTIONAL_ROOT_CHECK_FILE,
            "Current snapshot has stp-root-check.csv, but previous snapshot does not."
        )
        return

    previous_by_key = rows_by_key(previous_rows, ["session", "vlan"])
    current_by_key = rows_by_key(current_rows, ["session", "vlan"])

    for key in current_by_key:
        current_row = current_by_key[key]
        previous_row = previous_by_key.get(key)

        if previous_row is None:
            add_root_check_missing_row(diffs, "", current_row, "Current snapshot has this root-check row, but previous snapshot does not.")
            continue

        compare_root_check_row(diffs, previous_row, current_row)

    for key in previous_by_key:
        if key not in current_by_key:
            previous_row = previous_by_key[key]
            add_root_check_missing_row(diffs, previous_row, "", "Previous snapshot has this root-check row, but current snapshot does not.")


def compare_root_check_row(diffs, previous_row, current_row):
    previous_result = previous_row.get("result", "").strip().upper()
    current_result = current_row.get("result", "").strip().upper()
    session = current_row.get("session", "")
    vlan = current_row.get("vlan", "")
    previous_text = format_root_check_row(previous_row)
    current_text = format_root_check_row(current_row)

    if current_result == "FAIL" and previous_result != "FAIL":
        add_diff(
            diffs,
            "root-check failed",
            session,
            vlan,
            "",
            previous_text,
            current_text,
            current_row.get("note", "")
        )
        return

    if previous_result == "FAIL" and current_result != "FAIL":
        add_diff(
            diffs,
            "root-check recovered",
            session,
            vlan,
            "",
            previous_text,
            current_text,
            current_row.get("note", "")
        )
        return

    if previous_text != current_text:
        add_diff(
            diffs,
            "root-check changed",
            session,
            vlan,
            "",
            previous_text,
            current_text,
            "Root-check row changed."
        )


def add_root_check_missing_row(diffs, previous_row, current_row, note):
    session = ""
    vlan = ""
    if current_row != "":
        session = current_row.get("session", "")
        vlan = current_row.get("vlan", "")
    elif previous_row != "":
        session = previous_row.get("session", "")
        vlan = previous_row.get("vlan", "")

    add_diff(
        diffs,
        "root-check missing from one snapshot",
        session,
        vlan,
        "",
        format_root_check_row(previous_row),
        format_root_check_row(current_row),
        note
    )


def format_root_check_row(row):
    if row == "" or row is None:
        return ""

    return (
        "result=" + row.get("result", "") +
        "; observed_root=" + row.get("observed_root", "") +
        "; expected_root=" + row.get("expected_root", "") +
        "; note=" + row.get("note", "")
    )


def port_issue_map(rows, source):
    result = {}
    for row in rows:
        if row.get("source", "") != source:
            continue
        key = make_key(row, ["session", "instance", "interface"])
        result[key] = row
    return result


def rows_by_key(rows, fields):
    result = {}
    for row in rows:
        key = make_key(row, fields)
        if key not in result:
            result[key] = row
    return result


def make_key(row, fields):
    values = []
    for field in fields:
        values.append(row.get(field, "").strip().lower())
    return "\x1f".join(values)


def parse_int(value):
    try:
        return int(str(value).strip())
    except Exception:
        return None


def add_diff(diffs, change_type, session, instance, interface_name, previous, current, note):
    diffs.append({
        "change_type": change_type,
        "session": session,
        "instance": instance,
        "interface": interface_name,
        "previous": previous,
        "current": current,
        "note": note,
    })


def render_text_diff(previous_folder, current_folder, diffs):
    lines = []
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("STP Snapshot Diff\n")
    lines.append("Generated: " + now + "\n")
    lines.append("Previous: " + previous_folder + "\n")
    lines.append("Current: " + current_folder + "\n")
    lines.append("Changes flagged: " + str(len(diffs)) + "\n")
    lines.append("\n")

    if len(diffs) == 0:
        lines.append("No differences were flagged by the simple comparison rules.\n")
        return "".join(lines)

    for diff in diffs:
        lines.append("- " + diff.get("change_type", "") + "\n")
        if diff.get("session", "") != "":
            lines.append("  Session: " + diff.get("session", "") + "\n")
        if diff.get("instance", "") != "":
            lines.append("  Instance: " + diff.get("instance", "") + "\n")
        if diff.get("interface", "") != "":
            lines.append("  Interface: " + diff.get("interface", "") + "\n")
        lines.append("  Previous: " + diff.get("previous", "") + "\n")
        lines.append("  Current: " + diff.get("current", "") + "\n")
        if diff.get("note", "") != "":
            lines.append("  Note: " + diff.get("note", "") + "\n")
        lines.append("\n")

    return "".join(lines)


def read_csv(path):
    if not os.path.exists(path):
        return []

    rows = []
    handle = codecs.open(path, "r", "utf-8")
    try:
        headers = None
        for line in handle:
            line = line.rstrip("\r\n")
            if line == "":
                continue

            values = parse_csv_line(line)
            if headers is None:
                headers = values
                continue

            row = {}
            for index in range(0, len(headers)):
                value = ""
                if index < len(values):
                    value = values[index]
                row[headers[index]] = value
            rows.append(row)
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


def write_csv(path, headers, rows):
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


def write_text_file(path, data):
    handle = codecs.open(path, "w", "utf-8")
    try:
        handle.write(data)
    finally:
        handle.close()


def normalize_text(text):
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\x1b", "")
    text = text.replace("\n\r", "\r\n")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return text


Main()
