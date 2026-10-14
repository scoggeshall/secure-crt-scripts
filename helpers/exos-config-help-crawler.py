# $language = "python"
# $interface = "1.0"

# EXOS Configuration Help Crawler
#
# EXOS / Switch Engine uses a flat CLI. This crawler starts at one command
# root, recursively queries question-mark help, and follows literal options.
# Dynamic values are recorded but never invented or entered.
#
# Help queries are canceled with Ctrl+C. No discovered command is executed.

import codecs
import collections
import datetime
import os
import re

SCRIPT_TITLE = 'EXOS Configuration Help Crawler'
OUTPUT_ROOT = 'C:\\scripts\\secure-crt\\outputs\\exos-config-help'
ROOT_COMMAND = 'configure'
OUTPUT_SUFFIX = 'config-help.txt'
OUTPUT_TITLE = 'EXOS / Switch Engine Configuration Help Crawl'
CONFIRMATION = 'CONFIGCRAWL'
PROMPT_TEXT = 'This recursively discovers EXOS/Switch Engine global configuration syntax.\n\nEXOS has a flat CLI, so the crawler starts at configure ? and follows literal branches.\nDiscovered configuration commands are queried with ? and canceled with Ctrl+C; they are not executed.\n\nType CONFIGCRAWL to continue.'

IDLE_SECONDS = 1
MAX_IDLE_CHECKS = 180
INITIAL_RENDER_DELAY_MS = 150
AFTER_CANCEL_DELAY_MS = 100
BETWEEN_QUERY_DELAY_MS = 50
NORMAL_COMMAND_DELAY_MS = 300
MAX_DEPTH = 25
MAX_COMMANDS = 20000
MAX_COMMAND_TOKENS = 24
IDYES = 6
METADATA_COMMANDS = ['show version', 'show switch']


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

    answer = crt.Dialog.Prompt(
        PROMPT_TEXT,
        SCRIPT_TITLE, "", False)
    if answer is None or answer.strip().upper() != CONFIRMATION:
        return

    ensure_directory(OUTPUT_ROOT)
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = os.path.join(
        OUTPUT_ROOT,
        timestamp + "_" + sanitize_filename(hostname_from_prompt(prompt)) + "_" + OUTPUT_SUFFIX)
    previous_logging = session.Logging
    previous_log_file = session.LogFileName
    stats = new_stats()
    restore_command = None

    try:
        if session.Logging:
            session.Log(False)
        write_text(output_path,
            OUTPUT_TITLE + "\n"
            "Generated: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n"
            "Prompt: " + prompt + "\n"
            "Root: " + ROOT_COMMAND + "\n"
            "Maximum depth: " + str(MAX_DEPTH) + "\n"
            "Maximum help queries: " + str(MAX_COMMANDS) + "\n"
            "Maximum command tokens: " + str(MAX_COMMAND_TOKENS) + "\n\n"
            "Discovered commands are only queried with question-mark help and canceled with Ctrl+C.\n"
            "No discovered command is executed.\n\n")
        stats["metadata_failures"] = collect_platform_metadata(screen, session, output_path)

        proceed, restore_command, paging_note = prepare_paging(screen, session, output_path)
        append_text(output_path, "CLI paging: " + paging_note + "\n\n")
        if proceed:
            run_crawl(screen, session, output_path, stats)
        else:
            append_text(output_path, "Crawl canceled by user before paging was changed.\n")

        append_summary(output_path, stats)
    finally:
        try:
            if session.Logging:
                session.Log(False)
        except Exception:
            pass
        try:
            restore_paging(screen, restore_command)
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
        "Crawl complete.\n\nHelp commands queried: " + str(stats["queries"])
        + "\nLiteral options discovered: " + str(stats["literals"])
        + "\nValue placeholders recorded: " + str(stats["placeholders"])
        + "\nIncomplete queries (timeouts): " + str(stats["incomplete"])
        + "\nError responses: " + str(stats["errors"])
        + "\nFailures: " + str(stats["failures"])
        + "\n\nOutput file:\n" + output_path,
        SCRIPT_TITLE)


def new_stats():
    return {"queries": 0, "literals": 0, "placeholders": 0, "failures": 0,
            "token_skips": 0, "incomplete": 0, "errors": 0, "duplicates": 0,
            "metadata_failures": 0}


def run_crawl(screen, session, output_path, stats):
    visited = set()
    queued = set()
    queue = collections.deque()
    enqueue_command(queue, queued, ROOT_COMMAND, 1)
    while queue and stats["queries"] < MAX_COMMANDS:
        item = queue.popleft()
        command = item["command"].strip()
        if command.lower() in visited:
            stats["duplicates"] += 1
            continue
        visited.add(command.lower())
        process_help_query(screen, session, output_path, command, item["depth"], queue, queued, stats)


def process_help_query(screen, session, output_path, command, depth, queue, queued, stats):
    stats["queries"] += 1
    append_text(output_path,
        "\n" + "=" * 100 + "\n"
        "Query: " + str(stats["queries"]) + "\n"
        "Depth: " + str(depth) + "\n"
        "Command: " + command + " ?\n"
        + "=" * 100 + "\n")
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
        result = ["\nParser Results\n",
                  "Literal children: " + str(len(literals)) + "\n",
                  "Value placeholders: " + str(len(placeholders)) + "\n"]
        if literals:
            result.append("Children: " + join_values(literals) + "\n")
        if placeholders:
            result.append("Placeholders (recorded, not populated): " + join_values(placeholders) + "\n")
        append_text(output_path, "".join(result))

        if depth < MAX_DEPTH:
            for option in literals:
                child = command + " " + option
                if len(child.split()) > MAX_COMMAND_TOKENS:
                    stats["token_skips"] += 1
                    continue
                if not enqueue_command(queue, queued, child, depth + 1):
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


def append_summary(output_path, stats):
    append_text(output_path,
        "\n" + "#" * 100 + "\nFinal Crawl Summary\n" + "#" * 100 + "\n"
        "Help commands queried: " + str(stats["queries"]) + "\n"
        "Literal options discovered: " + str(stats["literals"]) + "\n"
        "Value placeholders recorded: " + str(stats["placeholders"]) + "\n"
        "Incomplete queries (timeouts): " + str(stats["incomplete"]) + "\n"
        "Error responses: " + str(stats["errors"]) + "\n"
        "Duplicate commands not re-queued: " + str(stats["duplicates"]) + "\n"
        "Token-limit branches skipped: " + str(stats["token_skips"]) + "\n"
        "Metadata query failures: " + str(stats["metadata_failures"]) + "\n"
        "Failures: " + str(stats["failures"]) + "\n")


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


def capture_readonly_command(screen, session, command, output_path):
    """Run one read-only show command. Returns (text, complete)."""
    clear_command_line(screen)
    start = get_file_size(output_path)
    start_capture(session, output_path)
    complete = True
    try:
        screen.Send(command + "\r")
        crt.Sleep(NORMAL_COMMAND_DELAY_MS)
        if not wait_for_screen_idle(screen):
            complete = False
    finally:
        session.Log(False)
    crt.Sleep(BETWEEN_QUERY_DELAY_MS)
    return normalize_capture(read_file_from_offset(output_path, start)), complete


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


def prepare_paging(screen, session, output_path):
    """Detect the current CLI paging state, then disable paging if needed.
    Returns (proceed, restore_command, note). restore_command is None when the
    original state needs no restoration."""
    text, complete = capture_readonly_command(screen, session, "show management", output_path)
    state = parse_paging_state(text) if complete else None
    if state is False:
        return True, None, "already disabled; left unchanged"
    if state is True:
        restore = "enable cli paging"
        note = "was enabled; disabled for the crawl and will be re-enabled"
    else:
        answer = crt.Dialog.MessageBox(
            "The script could not read the current CLI paging state from 'show management'.\n\n"
            "To continue it must run 'disable cli paging'. Afterward it will run "
            "'enable cli paging' (the EXOS default), even if paging was previously disabled.\n\n"
            "Continue?",
            SCRIPT_TITLE, 32 | 4)
        if answer != IDYES:
            return False, None, "state unknown; user declined; paging not changed"
        restore = "enable cli paging"
        note = "state could not be detected; user confirmed; will be set to enabled afterward"
    run_normal_command(screen, "disable cli paging")
    return True, restore, note


def restore_paging(screen, restore_command):
    if restore_command:
        run_normal_command(screen, restore_command)


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
    items = parse_platform_metadata(texts[0] if texts else u"", texts[1] if len(texts) > 1 else u"")
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
