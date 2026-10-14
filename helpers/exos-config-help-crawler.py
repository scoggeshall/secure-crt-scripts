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
    total_commands = 0
    total_literals = 0
    total_placeholders = 0
    total_failures = 0
    total_token_skips = 0

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
        run_normal_command(screen, "disable cli paging")

        visited = set()
        queue = collections.deque([{"command": ROOT_COMMAND, "depth": 1}])
        while queue and total_commands < MAX_COMMANDS:
            item = queue.popleft()
            command = item["command"].strip()
            depth = item["depth"]
            if command.lower() in visited:
                continue
            visited.add(command.lower())
            total_commands += 1
            append_text(output_path,
                "\n" + "=" * 100 + "\n"
                "Query: " + str(total_commands) + "\n"
                "Depth: " + str(depth) + "\n"
                "Command: " + command + " ?\n"
                + "=" * 100 + "\n")
            try:
                captured = capture_help_query(screen, session, command, output_path)
                literals, placeholders = parse_help_entries(captured)
                total_literals += len(literals)
                total_placeholders += len(placeholders)
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
                            total_token_skips += 1
                            continue
                        if child.lower() not in visited:
                            queue.append({"command": child, "depth": depth + 1})
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
            "\n" + "#" * 100 + "\nFinal Crawl Summary\n" + "#" * 100 + "\n"
            "Help commands queried: " + str(total_commands) + "\n"
            "Literal options discovered: " + str(total_literals) + "\n"
            "Value placeholders recorded: " + str(total_placeholders) + "\n"
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
        "Crawl complete.\n\nHelp commands queried: " + str(total_commands)
        + "\nLiteral options discovered: " + str(total_literals)
        + "\nValue placeholders recorded: " + str(total_placeholders)
        + "\nFailures: " + str(total_failures)
        + "\n\nOutput file:\n" + output_path,
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
