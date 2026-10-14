# $language = "python"
# $interface = "1.0"

import codecs
import collections
import datetime
import os
import re

SCRIPT_TITLE = "EXOS Configuration Context Crawler"
OUTPUT_ROOT = r"C:\scripts\secure-crt\outputs\exos-context-help"
CONTEXT_ROOTS = ["configure", "enable", "disable", "create", "delete", "unconfigure"]

# EXOS has a flat CLI. This is the equivalent of the VOSS config-mode crawler:
# it fills resolvable syntax placeholders with safe examples and continues ? help.
BASELINE_VALUES = {
    "vlan": "Default",
    "vlan_id": "1",
    "port": "1:1",
    "vr": "VR-Default",
    "area": "0.0.0.0",
    "router_id": "192.0.2.1",
    "ip": "192.0.2.1",
    "ip2": "192.0.2.2",
    "network": "192.0.2.0/24",
    "mask": "255.255.255.0",
    "prefix": "24",
    "as": "65000",
    "metric": "10",
    "tag": "100",
    "name": "CRAWL_TEST",
    "mac": "02:00:00:00:00:01",
    "domain": "example.invalid",
}

IDLE_SECONDS = 1
MAX_IDLE_CHECKS = 180
INITIAL_RENDER_DELAY_MS = 150
AFTER_CANCEL_DELAY_MS = 100
BETWEEN_QUERY_DELAY_MS = 50
NORMAL_COMMAND_DELAY_MS = 300
MAX_DEPTH_PER_ROOT = 25
MAX_COMMANDS_PER_ROOT = 8000
MAX_TOTAL_COMMANDS = 30000
MAX_COMMAND_TOKENS = 24
MAX_PLACEHOLDER_BRANCHES_PER_QUERY = 2


def normalize_placeholder(token):
    return to_text(token).strip().strip("<>[]{}|,").lower()


def resolve_placeholder(token, command):
    raw = normalize_placeholder(token)
    match = re.match(r"^(\d+)-(\d+)$", raw)
    if match:
        low = int(match.group(1)); high = int(match.group(2))
        return "1" if low <= 1 <= high else str(low)
    if "port" in raw:
        return BASELINE_VALUES["port"]
    if "vlan_id" in raw or raw in ("vid", "vlanid"):
        return BASELINE_VALUES["vlan_id"]
    if "vlan" in raw:
        return BASELINE_VALUES["vlan"]
    if "area" in raw:
        return BASELINE_VALUES["area"]
    if "router" in raw and "id" in raw:
        return BASELINE_VALUES["router_id"]
    if raw in ("vr", "vr_name", "virtual_router") or "vr_name" in raw:
        return BASELINE_VALUES["vr"]
    if "mask" in raw:
        return BASELINE_VALUES["mask"]
    if "prefix" in raw and "length" in raw:
        return BASELINE_VALUES["prefix"]
    if "network" in raw:
        return BASELINE_VALUES["network"]
    if "ip" in raw or "address" in raw:
        return BASELINE_VALUES["ip2"] if BASELINE_VALUES["ip"] in command else BASELINE_VALUES["ip"]
    if raw in ("as", "asn", "as_number", "as-number") or "autonomous" in raw:
        return BASELINE_VALUES["as"]
    if "metric" in raw or "cost" in raw:
        return BASELINE_VALUES["metric"]
    if "tag" in raw:
        return BASELINE_VALUES["tag"]
    if "mac" in raw:
        return BASELINE_VALUES["mac"]
    if "domain" in raw:
        return BASELINE_VALUES["domain"]
    if raw in ("name", "profile", "policy", "group", "description", "string", "word", "label"):
        return BASELINE_VALUES["name"]
    return ""


def Main():
    tab = crt.GetScriptTab()
    if not tab.Session.Connected:
        crt.Dialog.MessageBox("Not connected.", SCRIPT_TITLE)
        return
    screen = tab.Screen
    session = tab.Session
    screen.Synchronous = False
    screen.IgnoreEscape = True
    clear_command_line(screen)
    prompt = get_prompt(screen)
    if prompt == "":
        crt.Dialog.MessageBox("Could not detect the EXOS/Switch Engine prompt.", SCRIPT_TITLE)
        return

    preview = []
    for key in sorted(BASELINE_VALUES.keys()):
        preview.append("  " + key + " = " + BASELINE_VALUES[key])
    answer = crt.Dialog.Prompt(
        "This is the EXOS equivalent of the VOSS configuration-mode crawler.\n\n"
        "EXOS uses a flat CLI, so this crawler fills resolvable placeholders and continues ? syntax help.\n\n"
        "Example values:\n" + "\n".join(preview) + "\n\n"
        "No discovered configuration command is executed.\n\nType CONTEXTCRAWL to continue.",
        SCRIPT_TITLE, "", False)
    if answer is None or answer.strip().upper() != "CONTEXTCRAWL":
        return

    ensure_directory(OUTPUT_ROOT)
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = os.path.join(OUTPUT_ROOT, timestamp + "_" + sanitize_filename(hostname_from_prompt(prompt)) + "_context-help.txt")
    previous_logging = session.Logging
    previous_log_file = session.LogFileName
    total_commands = total_literals = total_placeholders = total_resolved = 0
    total_unresolved = total_failures = total_token_skips = 0

    try:
        if session.Logging:
            session.Log(False)
        lines = [
            "EXOS / Switch Engine Configuration Context Crawl\n",
            "Generated: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n",
            "Prompt: " + prompt + "\n",
            "Roots: " + ", ".join(CONTEXT_ROOTS) + "\n",
            "Maximum depth/root: " + str(MAX_DEPTH_PER_ROOT) + "\n",
            "Maximum total commands: " + str(MAX_TOTAL_COMMANDS) + "\n",
            "Maximum command tokens: " + str(MAX_COMMAND_TOKENS) + "\n\nBaseline values:\n"
        ]
        for key in sorted(BASELINE_VALUES.keys()):
            lines.append("  " + key + ": " + BASELINE_VALUES[key] + "\n")
        lines.append("\n")
        write_text(output_path, "".join(lines))
        run_normal_command(screen, "disable cli paging")

        global_visited = set()
        for root_index in range(len(CONTEXT_ROOTS)):
            if total_commands >= MAX_TOTAL_COMMANDS:
                break
            root = CONTEXT_ROOTS[root_index]
            append_text(output_path, "\n" + "#" * 110 + "\nContext Root " + str(root_index + 1) + ": " + root + "\n" + "#" * 110 + "\n")
            queue = collections.deque([{"command": root, "depth": 1}])
            root_count = 0

            while queue:
                if root_count >= MAX_COMMANDS_PER_ROOT or total_commands >= MAX_TOTAL_COMMANDS:
                    break
                item = queue.popleft()
                command = item["command"].strip()
                depth = item["depth"]
                if command.lower() in global_visited:
                    continue
                global_visited.add(command.lower())
                root_count += 1
                total_commands += 1
                append_text(output_path, "\n" + "=" * 110 + "\nRoot: " + root + "\nQuery: " + str(root_count) + "\nTotal Query: " + str(total_commands) + "\nDepth: " + str(depth) + "\nCommand: " + command + " ?\n" + "=" * 110 + "\n")
                try:
                    captured = capture_help_query(screen, session, command, output_path)
                    literals, placeholders = parse_help_entries(captured)
                    total_literals += len(literals)
                    total_placeholders += len(placeholders)
                    resolved = []
                    unresolved = []
                    for placeholder in placeholders:
                        value = resolve_placeholder(placeholder, command)
                        if value:
                            resolved.append((placeholder, value))
                        else:
                            unresolved.append(placeholder)
                    total_resolved += len(resolved)
                    total_unresolved += len(unresolved)
                    result = ["\nParser Results\n", "Literal children: " + str(len(literals)) + "\n", "Value placeholders: " + str(len(placeholders)) + "\n"]
                    if literals:
                        result.append("Children: " + join_values(literals) + "\n")
                    if placeholders:
                        result.append("Placeholders: " + join_values(placeholders) + "\n")
                    if resolved:
                        result.append("Resolved examples:\n")
                        for placeholder, value in resolved:
                            result.append("  " + to_text(placeholder) + " -> " + value + "\n")
                    if unresolved:
                        result.append("Unresolved placeholders: " + join_values(unresolved) + "\n")
                    append_text(output_path, "".join(result))
                    if depth < MAX_DEPTH_PER_ROOT:
                        for option in literals:
                            child = command + " " + option
                            if len(child.split()) > MAX_COMMAND_TOKENS:
                                total_token_skips += 1
                                continue
                            if child.lower() not in global_visited:
                                queue.append({"command": child, "depth": depth + 1})
                        used = 0
                        for placeholder, value in resolved:
                            if used >= MAX_PLACEHOLDER_BRANCHES_PER_QUERY:
                                break
                            child = command + " " + value
                            if len(child.split()) > MAX_COMMAND_TOKENS:
                                total_token_skips += 1
                                continue
                            if child.lower() not in global_visited:
                                queue.append({"command": child, "depth": depth + 1})
                                used += 1
                except Exception as exc:
                    total_failures += 1
                    try:
                        if session.Logging:
                            session.Log(False)
                    except Exception:
                        pass
                    append_text(output_path, "\nERROR: " + to_text(exc) + "\n")
                    clear_command_line(screen)

        append_text(output_path,
            "\n" + "#" * 110 + "\nFinal Crawl Summary\n" + "#" * 110 + "\n"
            "Help commands queried: " + str(total_commands) + "\n"
            "Literal options discovered: " + str(total_literals) + "\n"
            "Placeholders discovered: " + str(total_placeholders) + "\n"
            "Placeholder examples resolved: " + str(total_resolved) + "\n"
            "Unresolved placeholders: " + str(total_unresolved) + "\n"
            "Token-limit branches skipped: " + str(total_token_skips) + "\n"
            "Failures: " + str(total_failures) + "\n")
    finally:
        try:
            if session.Logging:
                session.Log(False)
        except Exception:
            pass
        try:
            run_normal_command(screen, "enable cli paging")
        except Exception:
            pass
        try:
            session.LogFileName = previous_log_file
        except Exception:
            pass
        if previous_logging and previous_log_file:
            try:
                session.Log(True, True, False)
            except Exception:
                pass

    crt.Dialog.MessageBox(
        "Configuration context crawl complete.\n\nHelp commands queried: " + str(total_commands) + "\nLiteral options discovered: " + str(total_literals) + "\nPlaceholders discovered: " + str(total_placeholders) + "\nPlaceholder examples resolved: " + str(total_resolved) + "\nFailures: " + str(total_failures) + "\n\nOutput file:\n" + output_path,
        SCRIPT_TITLE)

def capture_help_query(screen, session, command, output_path):
    clear_command_line(screen)
    start = get_file_size(output_path)
    session.LogFileName = output_path
    session.Log(True, True, False)
    screen.Send(command + " ?")
    crt.Sleep(INITIAL_RENDER_DELAY_MS)
    wait_for_screen_idle(screen)
    screen.Send(chr(3))
    crt.Sleep(AFTER_CANCEL_DELAY_MS)
    wait_for_screen_idle(screen)
    session.Log(False)
    crt.Sleep(BETWEEN_QUERY_DELAY_MS)
    return normalize_capture(read_file_from_offset(output_path, start))


def parse_help_entries(text):
    literals = []
    placeholders = []
    for original in normalize_capture(text).split(u"\n"):
        line = remove_log_prefix(original)
        stripped = line.strip()
        if stripped == u"" or stripped.endswith(u"?") or re.search(u"[>#]\\s*$", stripped):
            continue
        if stripped.startswith(u"^") or stripped.startswith(u"%"):
            continue

        match = re.match(u"^\\s*([^\\s]+)\\s{2,}\\S.*$", line)
        if not match:
            continue
        token = match.group(1).strip().strip(u",")
        if is_literal(token):
            if token not in literals:
                literals.append(token)
        elif is_placeholder(token):
            if token not in placeholders:
                placeholders.append(token)
    return literals, placeholders


def is_literal(token):
    return re.match(u"^[a-z][a-z0-9_.:/-]*$", token) is not None


def is_placeholder(token):
    if token.startswith((u"<", u"[", u"{", u"|")):
        return True
    if u"_" in token:
        return True
    if token.upper() == token and re.search(u"[A-Z]", token):
        return True
    return False


def clear_command_line(screen):
    screen.Send(chr(3))
    crt.Sleep(AFTER_CANCEL_DELAY_MS)
    wait_for_screen_idle(screen)


def wait_for_screen_idle(screen):
    checks = 0
    while checks < MAX_IDLE_CHECKS:
        if not screen.WaitForCursor(IDLE_SECONDS):
            return True
        checks += 1
    return False


def run_normal_command(screen, command):
    clear_command_line(screen)
    screen.Send(command + "\r")
    crt.Sleep(NORMAL_COMMAND_DELAY_MS)
    wait_for_screen_idle(screen)


def get_prompt(screen):
    current = screen.CurrentRow
    first = max(1, current - 12)
    for row in range(current, first - 1, -1):
        try:
            value = screen.Get(row, 0, row, screen.Columns).strip()
        except Exception:
            continue
        if value and re.search(r"[>#]\s*$", value):
            return value
    return ""


def hostname_from_prompt(prompt):
    value = re.sub(r"[>#]\s*$", "", prompt.strip()).strip()
    if value.startswith("*"):
        value = value[1:].strip()
    return value or "UNKNOWN"


def normalize_capture(text):
    value = to_text(text)
    if value.startswith(u"\ufeff"):
        value = value[1:]
    value = apply_backspaces(value)
    value = re.sub(u"\x1b\\[[0-9;?]*[A-Za-z]", u"", value)
    value = value.replace(u"\x1b", u"").replace(u"\x00", u"")
    value = value.replace(u"\n\r", u"\n").replace(u"\r\n", u"\n").replace(u"\r", u"\n")
    return value


def apply_backspaces(value):
    result = []
    for char in value:
        if char == u"\b":
            if result:
                result.pop()
        else:
            result.append(char)
    return u"".join(result)


def remove_log_prefix(line):
    return re.sub(u"^\\s*\\[[^\\]]+\\]\\s*", u"", line)


def to_text(value):
    if value is None:
        try:
            return unicode("")
        except NameError:
            return ""
    try:
        text_type = unicode
    except NameError:
        text_type = str
    if isinstance(value, text_type):
        return value
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return value.decode(encoding)
        except Exception:
            pass
    return text_type(value)


def get_file_size(path):
    return os.path.getsize(path) if os.path.exists(path) else 0


def read_file_from_offset(path, offset):
    handle = open(path, "rb")
    try:
        handle.seek(offset)
        data = handle.read()
    finally:
        handle.close()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except Exception:
            pass
    return to_text(data)


def sanitize_filename(value):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", to_text(value).strip()).strip("-._")
    return value or "UNKNOWN"


def ensure_directory(path):
    if not os.path.exists(path):
        os.makedirs(path)


def write_text(path, data):
    handle = codecs.open(path, "w", "utf-8")
    try:
        handle.write(to_text(data))
    finally:
        handle.close()


def append_text(path, data):
    handle = codecs.open(path, "a", "utf-8")
    try:
        handle.write(to_text(data))
        handle.flush()
    finally:
        handle.close()


def join_values(values):
    return u", ".join([to_text(v) for v in values])


Main()
