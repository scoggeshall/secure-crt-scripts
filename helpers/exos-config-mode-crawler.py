# $language = "python"
# $interface = "1.0"

import codecs
import collections
import datetime
import os
import re

SCRIPT_TITLE = "EXOS Configuration Context Crawler"
OUTPUT_LEAF = 'exos-context-help'
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
IDYES = 6
METADATA_COMMANDS = ['show version', 'show switch']


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
        "Example values (used only inside ? help queries, never executed):\n" + "\n".join(preview) + "\n\n"
        "Roots: " + ", ".join(CONTEXT_ROOTS) + "\n"
        "No discovered configuration command is executed.\n\nType CONTEXTCRAWL to continue.",
        SCRIPT_TITLE, "", False)
    if answer is None or answer.strip().upper() != "CONTEXTCRAWL":
        return

    output_root = resolve_output_root(OUTPUT_LEAF)
    ensure_directory(output_root)
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = os.path.join(output_root, timestamp + "_" + sanitize_filename(hostname_from_prompt(prompt)) + "_context-help.txt")
    previous_logging = session.Logging
    previous_log_file = session.LogFileName
    stats = new_stats()
    paging = new_paging_state()

    try:
        if session.Logging:
            session.Log(False)
        lines = [
            "EXOS / Switch Engine Configuration Context Crawl\n",
            "Generated: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n",
            "Prompt: " + prompt + "\n",
            "Roots: " + ", ".join(CONTEXT_ROOTS) + "\n",
            "Maximum depth/root: " + str(MAX_DEPTH_PER_ROOT) + "\n",
            "Maximum commands/root: " + str(MAX_COMMANDS_PER_ROOT) + "\n",
            "Maximum total commands: " + str(MAX_TOTAL_COMMANDS) + "\n",
            "Maximum command tokens: " + str(MAX_COMMAND_TOKENS) + "\n",
            "Maximum placeholder branches/query: " + str(MAX_PLACEHOLDER_BRANCHES_PER_QUERY) + "\n\n"
            "Example values are used only in question-mark help queries; no discovered command is executed.\n\nBaseline values:\n"
        ]
        for key in sorted(BASELINE_VALUES.keys()):
            lines.append("  " + key + ": " + BASELINE_VALUES[key] + "\n")
        lines.append("\n")
        write_text(output_path, "".join(lines))
        proceed = prepare_paging(screen, session, output_path, paging, stats)
        append_text(output_path, "CLI paging: " + paging["note"] + "\n\n")
        if proceed:
            stats["metadata_failures"] = collect_platform_metadata(screen, session, output_path)
            run_context_crawl(screen, session, output_path, stats)
        else:
            append_text(output_path, "Crawl not run (see CLI paging note above).\n")
        restore_paging(screen, session, output_path, paging, stats)

        append_text(output_path,
            "\n" + "#" * 110 + "\nFinal Crawl Summary\n" + "#" * 110 + "\n"
            "Help commands queried: " + str(stats["queries"]) + "\n"
            "Literal options discovered: " + str(stats["literals"]) + "\n"
            "Placeholders discovered: " + str(stats["placeholders"]) + "\n"
            "Placeholder examples resolved: " + str(stats["resolved"]) + "\n"
            "Unresolved placeholders: " + str(stats["unresolved"]) + "\n"
            "Incomplete queries (timeouts): " + str(stats["incomplete"]) + "\n"
            "Error responses: " + str(stats["errors"]) + "\n"
            "Duplicate commands not re-queued: " + str(stats["duplicates"]) + "\n"
            "Token-limit branches skipped: " + str(stats["token_skips"]) + "\n"
            "Metadata query failures: " + str(stats["metadata_failures"]) + "\n"
            "Failures: " + str(stats["failures"]) + "\n"
        "Paging failures: " + str(len(stats["paging_failures"])) + "\n"
        + "".join(["  " + m + "\n" for m in stats["paging_failures"]]))
    finally:
        try:
            if session.Logging:
                session.Log(False)
        except Exception:
            pass
        try:
            restore_paging(screen, session, output_path, paging, stats)
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
        "Configuration context crawl complete.\n\nHelp commands queried: " + str(stats["queries"])
        + "\nLiteral options discovered: " + str(stats["literals"])
        + "\nPlaceholders discovered: " + str(stats["placeholders"])
        + "\nPlaceholder examples resolved: " + str(stats["resolved"])
        + "\nIncomplete queries (timeouts): " + str(stats["incomplete"])
        + "\nError responses: " + str(stats["errors"])
        + "\nFailures: " + str(stats["failures"])
        + paging_failure_text(stats)
        + "\n\nOutput file:\n" + output_path,
        SCRIPT_TITLE)


def paging_failure_text(stats):
    if not stats["paging_failures"]:
        return ""
    return "\n\nPAGING PROBLEMS (check CLI paging manually):\n" + "\n".join(stats["paging_failures"])


def new_stats():
    return {"queries": 0, "literals": 0, "placeholders": 0, "resolved": 0,
            "unresolved": 0, "failures": 0, "token_skips": 0, "incomplete": 0,
            "errors": 0, "duplicates": 0, "metadata_failures": 0, "paging_failures": []}


def run_context_crawl(screen, session, output_path, stats):
    visited = set()
    queued = set()
    for root_index in range(len(CONTEXT_ROOTS)):
        if stats["queries"] >= MAX_TOTAL_COMMANDS:
            break
        root = CONTEXT_ROOTS[root_index]
        append_text(output_path, "\n" + "#" * 110 + "\nContext Root " + str(root_index + 1) + ": " + root + "\n" + "#" * 110 + "\n")
        queue = collections.deque()
        enqueue_command(queue, queued, root, 1)
        root_count = 0
        while queue:
            if root_count >= MAX_COMMANDS_PER_ROOT or stats["queries"] >= MAX_TOTAL_COMMANDS:
                break
            item = queue.popleft()
            command = item["command"].strip()
            if command.lower() in visited:
                stats["duplicates"] += 1
                continue
            visited.add(command.lower())
            root_count += 1
            process_context_query(screen, session, output_path, root, root_count, command, item["depth"], queue, queued, stats)


def process_context_query(screen, session, output_path, root, root_count, command, depth, queue, queued, stats):
    stats["queries"] += 1
    append_text(output_path, "\n" + "=" * 110 + "\nRoot: " + root + "\nQuery: " + str(root_count) + "\nTotal Query: " + str(stats["queries"]) + "\nDepth: " + str(depth) + "\nCommand: " + command + " ?\n" + "=" * 110 + "\n")
    try:
        captured, complete = capture_help_query(screen, session, command, output_path)
        if not complete:
            stats["incomplete"] += 1
            append_text(output_path,
                "\nINCOMPLETE QUERY: screen did not become idle within the time limit.\n"
                "Output was not parsed and no child commands were queued.\n")
            return
        if classify_help_response(captured) == "error":
            stats["errors"] += 1
            append_text(output_path,
                "\nERROR RESPONSE: the device rejected this help query.\n"
                "Output was not parsed and no child commands were queued.\n")
            return
        literals, placeholders = parse_help_entries(captured)
        stats["literals"] += len(literals)
        stats["placeholders"] += len(placeholders)
        resolved = []
        unresolved = []
        for placeholder in placeholders:
            value = resolve_placeholder(placeholder, command)
            if value:
                resolved.append((placeholder, value))
            else:
                unresolved.append(placeholder)
        stats["resolved"] += len(resolved)
        stats["unresolved"] += len(unresolved)
        result = ["\nParser Results\n", "Literal children: " + str(len(literals)) + "\n", "Value placeholders: " + str(len(placeholders)) + "\n"]
        if literals:
            result.append("Children: " + join_values(literals) + "\n")
        if placeholders:
            result.append("Placeholders: " + join_values(placeholders) + "\n")
        if resolved:
            result.append("Resolved examples (used only in ? help queries):\n")
            for placeholder, value in resolved:
                result.append("  " + to_text(placeholder) + " -> " + value + "\n")
        if unresolved:
            result.append("Unresolved placeholders: " + join_values(unresolved) + "\n")
        append_text(output_path, "".join(result))
        if depth < MAX_DEPTH_PER_ROOT:
            for option in literals:
                child = command + " " + option
                if len(child.split()) > MAX_COMMAND_TOKENS:
                    stats["token_skips"] += 1
                    continue
                if not enqueue_command(queue, queued, child, depth + 1):
                    stats["duplicates"] += 1
            used = 0
            for placeholder, value in resolved:
                if used >= MAX_PLACEHOLDER_BRANCHES_PER_QUERY:
                    break
                child = command + " " + value
                if len(child.split()) > MAX_COMMAND_TOKENS:
                    stats["token_skips"] += 1
                    continue
                if enqueue_command(queue, queued, child, depth + 1):
                    used += 1
                else:
                    stats["duplicates"] += 1
    except Exception as exc:
        stats["failures"] += 1
        try:
            if session.Logging:
                session.Log(False)
        except Exception:
            pass
        append_text(output_path, "\nERROR: " + to_text(exc) + "\n")
        clear_command_line(screen)


# ---- Shared helpers (identical in all three EXOS crawlers) ----

def start_capture(session, output_path):
    session.LogFileName = output_path
    session.Log(True, True, False)


def capture_help_query(screen, session, command, output_path):
    """Send 'command ?' (never Enter), cancel with Ctrl+C.
    Returns (text, complete). complete is False if the screen never went idle."""
    clear_command_line(screen)
    start = get_file_size(output_path)
    start_capture(session, output_path)
    complete = True
    try:
        screen.Send(command + " ?")
        crt.Sleep(INITIAL_RENDER_DELAY_MS)
        if not wait_for_screen_idle(screen):
            complete = False
        screen.Send(chr(3))
        crt.Sleep(AFTER_CANCEL_DELAY_MS)
        if not wait_for_screen_idle(screen):
            complete = False
    finally:
        session.Log(False)
    crt.Sleep(BETWEEN_QUERY_DELAY_MS)
    return normalize_capture(read_file_from_offset(output_path, start)), complete


class PromptLostError(Exception):
    pass


def ensure_usable_prompt(screen):
    """Cancel any partial input and confirm a CLI prompt is visible and idle."""
    clear_command_line(screen)
    return get_prompt(screen) != ""


def capture_readonly_command(screen, session, command, output_path):
    """Run one read-only command. Returns (text, complete).
    On a timeout the command is canceled with Ctrl+C and the prompt is
    confirmed; PromptLostError is raised if the CLI is not usable again."""
    if not ensure_usable_prompt(screen):
        raise PromptLostError("No usable CLI prompt before: " + command)
    start = get_file_size(output_path)
    start_capture(session, output_path)
    complete = True
    try:
        screen.Send(command + "\r")
        crt.Sleep(NORMAL_COMMAND_DELAY_MS)
        if not wait_for_screen_idle(screen):
            complete = False
            screen.Send(chr(3))
            crt.Sleep(AFTER_CANCEL_DELAY_MS)
            wait_for_screen_idle(screen)
    finally:
        session.Log(False)
    crt.Sleep(BETWEEN_QUERY_DELAY_MS)
    text = normalize_capture(read_file_from_offset(output_path, start))
    if not complete and not ensure_usable_prompt(screen):
        raise PromptLostError("CLI prompt not recovered after timeout: " + command)
    return text, complete


def resolve_output_root(leaf):
    """Output directory: $EXOS_CRAWLER_OUTPUT_ROOT/<leaf> if set, otherwise
    <home>/Documents/SecureCRT-Outputs/<leaf>."""
    override = os.environ.get("EXOS_CRAWLER_OUTPUT_ROOT", "").strip()
    if override:
        base = override
    else:
        base = os.path.join(os.path.expanduser("~"), "Documents", "SecureCRT-Outputs")
    return os.path.join(base, leaf)


def classify_help_response(text):
    """Return 'error' for EXOS rejection text, otherwise 'ok'."""
    for original in normalize_capture(text).split(u"\n"):
        stripped = remove_log_prefix(original).strip()
        if stripped.startswith(u"%%") or stripped.startswith(u"%"):
            return "error"
        if re.search(u"(?i)(invalid input|ambiguous command|incomplete command|unknown command)", stripped):
            if not stripped.endswith(u"?"):
                return "error"
    return "ok"


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
        if re.match(u"^\\*?\\s*\\S+\\s[#>]\\s", stripped):
            continue

        match = re.match(u"^\\s*([^\\s]+)\\s{2,}\\S.*$", line)
        if not match:
            continue
        token = match.group(1).strip().strip(u",")
        if is_end_marker(token):
            continue
        if is_literal(token):
            if token not in literals:
                literals.append(token)
        elif is_placeholder(token):
            if token not in placeholders:
                placeholders.append(token)
    return literals, placeholders


def is_end_marker(token):
    return token.lower() == u"<cr>"


def is_literal(token):
    return re.match(u"^[a-z][a-z0-9_.:/-]*$", token) is not None and u"_" not in token


def is_placeholder(token):
    if token.startswith((u"<", u"[", u"{", u"|")):
        return True
    if u"_" in token:
        return True
    if re.search(u"[A-Z]", token):
        return True
    return False


def enqueue_command(queue, queued, command, depth):
    """Queue a command once. Returns False if it was already queued."""
    key = command.strip().lower()
    if key in queued:
        return False
    queued.add(key)
    queue.append({"command": command.strip(), "depth": depth})
    return True


def parse_paging_state(text):
    """Return True (enabled), False (disabled) or None (not found)."""
    for original in normalize_capture(text).split(u"\n"):
        line = remove_log_prefix(original)
        match = re.match(u"(?i)^\\s*CLI\\s+paging\\s*:\\s*(enabled|disabled)", line)
        if match:
            return match.group(1).lower() == u"enabled"
    return None


def new_paging_state():
    return {"restore_command": None, "restored": False, "note": ""}


def set_paging(screen, session, output_path, command):
    """Run a paging command. Returns (ok, detail); never raises for CLI problems."""
    try:
        text, complete = capture_readonly_command(screen, session, command, output_path)
    except Exception as exc:
        return False, to_text(exc)
    if not complete:
        return False, "timed out"
    if classify_help_response(text) == "error":
        return False, "device returned an error"
    return True, "ok"


def prepare_paging(screen, session, output_path, paging, stats):
    """Detect the CLI paging state and disable paging if needed.
    Returns True if the crawl may proceed. paging["restore_command"] is set
    BEFORE the disable attempt so cleanup always knows paging may have changed."""
    try:
        text, complete = capture_readonly_command(screen, session, "show management", output_path)
        state = parse_paging_state(text) if complete else None
    except Exception as exc:
        state = None
        stats["paging_failures"].append("Paging state query failed: " + to_text(exc))
    if state is False:
        paging["note"] = "already disabled; left unchanged"
        return True
    if state is True:
        paging["note"] = "was enabled; disabled for the crawl and will be re-enabled"
    else:
        answer = crt.Dialog.MessageBox(
            "The script could not read the current CLI paging state from 'show management'.\n\n"
            "To continue it must run 'disable cli paging'. Afterward it will run "
            "'enable cli paging' (the EXOS default), even if paging was previously disabled.\n\n"
            "Continue?",
            SCRIPT_TITLE, 32 | 4)
        if answer != IDYES:
            paging["note"] = "state unknown; user declined; paging not changed"
            return False
        paging["note"] = "state could not be detected; user confirmed; will be set to enabled afterward"
    paging["restore_command"] = "enable cli paging"
    ok, detail = set_paging(screen, session, output_path, "disable cli paging")
    if not ok:
        stats["paging_failures"].append("Disable paging failed: " + detail)
        paging["note"] += "; DISABLE FAILED (" + detail + "); crawl skipped"
        return False
    return True


def restore_paging(screen, session, output_path, paging, stats):
    """Restore paging once. Failures are counted and written to the output file."""
    if paging["restored"] or not paging["restore_command"]:
        return True
    paging["restored"] = True
    ok, detail = set_paging(screen, session, output_path, paging["restore_command"])
    if ok:
        append_text(output_path, "\nCLI paging restore: '" + paging["restore_command"] + "' succeeded.\n")
        return True
    message = "Restore paging failed ('" + paging["restore_command"] + "'): " + detail
    stats["paging_failures"].append(message)
    try:
        append_text(output_path, "\nCLI paging restore: FAILED. " + message + "\nCheck and restore the CLI paging setting manually.\n")
    except Exception:
        pass
    return False


def parse_platform_metadata(version_text, switch_text):
    """Return a list of (label, value) from show version / show switch output."""
    items = []
    combined = normalize_capture(version_text) + u"\n" + normalize_capture(switch_text)
    match = re.search(u"(?i)(ExtremeXOS|Switch Engine)\\s+version\\s+(\\S+)", combined)
    if match:
        items.append(("EXOS version", match.group(1) + u" " + match.group(2)))
    for label, pattern in (("System type", u"(?im)^\\s*System Type\\s*:\\s*(.+?)\\s*$"),
                           ("Boot ROM", u"(?im)^\\s*BootROM\\s*:\\s*(.+?)\\s*$"),
                           ("Hardware (show version)", u"(?im)^\\s*(?:Switch|Chassis)\\s*:\\s*(.+?)\\s*$")):
        match = re.search(pattern, combined)
        if match:
            items.append((label, match.group(1)))
    return items


def collect_platform_metadata(screen, session, output_path):
    """Append read-only platform metadata to the output. Returns failure count."""
    failures = 0
    texts = []
    lines = ["Platform metadata (read-only: " + ", ".join(METADATA_COMMANDS) + ")\n"]
    for command in METADATA_COMMANDS:
        try:
            text, complete = capture_readonly_command(screen, session, command, output_path)
            if not complete:
                failures += 1
                lines.append("  Metadata query incomplete (timeout): " + command + "\n")
                text = u""
            texts.append(text)
        except Exception as exc:
            failures += 1
            lines.append("  Metadata query failed: " + command + ": " + to_text(exc) + "\n")
            texts.append(u"")
            try:
                if session.Logging:
                    session.Log(False)
            except Exception:
                pass
            if isinstance(exc, PromptLostError):
                lines.append("  Remaining metadata queries skipped: CLI prompt not usable.\n")
                break
    while len(texts) < 2:
        texts.append(u"")
    items = parse_platform_metadata(texts[0], texts[1])
    if not items:
        failures += 1
        lines.append("  No EXOS version or platform information could be parsed.\n")
    for label, value in items:
        lines.append("  " + label + ": " + to_text(value) + "\n")
    append_text(output_path, "\nMetadata raw capture ends above.\n" + "".join(lines) + "\n")
    return failures


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
