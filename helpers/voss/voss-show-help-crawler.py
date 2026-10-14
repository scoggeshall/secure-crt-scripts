# $language = "python"
# $interface = "1.0"

# VOSS Recursive Show Help Crawler
#
# Uses SecureCRT native session logging instead of Screen.ReadString()
# to capture VOSS question-mark help.
#
# Recursively runs:
#
#   show ?
#   show access-policy ?
#   show alarm ?
#   show ip ?
#   show ip ospf ?
#   ...
#
# Literal lowercase CLI keywords are followed automatically.
#
# Dynamic values are logged but not followed:
#
#   <1-4094>
#   WORD
#   IP-ADDRESS
#   PORT
#
# Output:
#
#   C:\scripts\secure-crt\outputs\show-help\
#
# Active tab only.
# Read-only CLI help commands.

import codecs
import datetime
import os
import re


SCRIPT_TITLE = "VOSS Show Help Crawler"

OUTPUT_ROOT = r"C:\scripts\secure-crt\outputs\show-help"

TERMINAL_LENGTH = 64

# Wait until the cursor has not moved for this many seconds.
IDLE_SECONDS = 1

# Maximum number of cursor-movement checks for a single command.
MAX_IDLE_CHECKS = 300

# Additional delays around each command.
INITIAL_RENDER_DELAY_MS = 750
AFTER_CANCEL_DELAY_MS = 500
BETWEEN_COMMAND_DELAY_MS = 750

# Safety boundaries.
MAX_DEPTH = 25
MAX_COMMANDS = 10000


def Main():
    tab = crt.GetScriptTab()

    if not tab.Session.Connected:
        crt.Dialog.MessageBox(
            "Not connected.",
            SCRIPT_TITLE
        )
        return

    screen = tab.Screen

    # Native session logging will capture the displayed output.
    # Screen synchronization is deliberately disabled so ReadString/
    # WaitForString buffering cannot consume the help output.
    screen.Synchronous = False
    screen.IgnoreEscape = True

    clear_command_line(screen)

    prompt = get_prompt(screen)

    if prompt == "":
        crt.Dialog.MessageBox(
            "Could not detect the VOSS prompt.",
            SCRIPT_TITLE
        )
        return

    hostname = hostname_from_prompt(prompt)

    confirmation = crt.Dialog.Prompt(
        "This will recursively crawl the VOSS show-command help tree.\n\n"
        "Examples:\n"
        "show ?\n"
        "show ip ?\n"
        "show ip ospf ?\n"
        "show vlan ?\n\n"
        "Every literal CLI option discovered will be queried.\n"
        "Dynamic values such as <1-4094> and WORD will only be logged.\n\n"
        "Maximum commands: " + str(MAX_COMMANDS) + "\n\n"
        "Type CRAWL to continue.",
        SCRIPT_TITLE,
        "",
        False
    )

    if confirmation is None:
        return

    if confirmation.strip().upper() != "CRAWL":
        crt.Dialog.MessageBox(
            "Canceled.",
            SCRIPT_TITLE
        )
        return

    ensure_directory(OUTPUT_ROOT)

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    log_path = os.path.join(
        OUTPUT_ROOT,
        timestamp + "_" +
        sanitize_filename(hostname) +
        "_show-help.txt"
    )

    session = tab.Session

    previous_logging = session.Logging
    previous_log_file = session.LogFileName

    command_count = 0
    literal_count = 0
    placeholder_count = 0
    failed_count = 0

    try:
        # Temporarily stop any existing session logging.
        if session.Logging:
            session.Log(False)

        session.LogFileName = log_path

        write_log_header(
            log_path,
            prompt
        )

        # VOSS supports 8 through 64, not terminal length 0.
        send_enter_command(
            screen,
            "terminal length " + str(TERMINAL_LENGTH)
        )

        queue = [
            {
                "command": "show",
                "depth": 1,
            }
        ]

        visited = {}

        while len(queue) > 0:
            if command_count >= MAX_COMMANDS:
                append_text(
                    log_path,
                    "\n"
                    "STOPPED: Maximum command limit reached: " +
                    str(MAX_COMMANDS) +
                    "\n"
                )
                break

            item = queue.pop(0)

            command = item.get("command", "").strip()
            depth = item.get("depth", 1)

            if command == "":
                continue

            command_key = command.lower()

            if command_key in visited:
                continue

            visited[command_key] = True
            command_count += 1

            section_header = build_section_header(
                command,
                depth,
                command_count
            )

            append_text(
                log_path,
                section_header
            )

            capture_start = get_file_size(log_path)

            try:
                # Start normal displayed-text logging in append mode.
                session.Log(True, True, False)

                run_question_mark_command(
                    screen,
                    command
                )

                # Stopping logging flushes the output and releases the file.
                session.Log(False)

                captured = read_file_from_offset(
                    log_path,
                    capture_start
                )

                cleaned = normalize_log_text(captured)

                literal_options = parse_literal_options(cleaned)
                placeholders = parse_placeholders(cleaned)

                literal_count += len(literal_options)
                placeholder_count += len(placeholders)

                append_parse_results(
                    log_path,
                    literal_options,
                    placeholders,
                    cleaned
                )

                if depth < MAX_DEPTH:
                    for option in literal_options:
                        child_command = command + " " + option
                        child_key = child_command.lower()

                        if child_key not in visited:
                            queue.append(
                                {
                                    "command": child_command,
                                    "depth": depth + 1,
                                }
                            )

            except Exception as exc:
                failed_count += 1

                if session.Logging:
                    session.Log(False)

                append_text(
                    log_path,
                    "\n"
                    "PARSER ERROR: " +
                    str(exc) +
                    "\n\n"
                )

                clear_command_line(screen)

        append_summary(
            log_path,
            command_count,
            literal_count,
            placeholder_count,
            failed_count
        )

    finally:
        # Always stop the crawler log before restoring prior settings.
        try:
            if session.Logging:
                session.Log(False)
        except Exception:
            pass

        try:
            session.LogFileName = previous_log_file
        except Exception:
            pass

        # Resume the user's previous logging session when applicable.
        if previous_logging and previous_log_file != "":
            try:
                session.Log(True, True, False)
            except Exception:
                pass

    crt.Dialog.MessageBox(
        "Show help crawl complete.\n\n"
        "Commands queried: " + str(command_count) + "\n"
        "Literal options discovered: " + str(literal_count) + "\n"
        "Placeholders recorded: " + str(placeholder_count) + "\n"
        "Failures: " + str(failed_count) + "\n\n"
        "Log file:\n" + log_path,
        SCRIPT_TITLE
    )


def run_question_mark_command(screen, command):
    """
    VOSS displays question-mark help without needing Enter.

    The partial command may remain on the command line after help is
    displayed. Ctrl+C clears it without executing the command.
    """

    clear_command_line(screen)

    screen.Send(command + " ?")

    # Allow the first portion of output to begin arriving.
    crt.Sleep(INITIAL_RENDER_DELAY_MS)

    # Wait until serial output has stopped moving for IDLE_SECONDS.
    wait_for_screen_idle(screen)

    # Cancel the partial command without executing it.
    screen.Send(chr(3))

    crt.Sleep(AFTER_CANCEL_DELAY_MS)

    wait_for_screen_idle(screen)

    crt.Sleep(BETWEEN_COMMAND_DELAY_MS)


def send_enter_command(screen, command):
    clear_command_line(screen)

    screen.Send(command + "\r")

    crt.Sleep(INITIAL_RENDER_DELAY_MS)

    wait_for_screen_idle(screen)

    crt.Sleep(BETWEEN_COMMAND_DELAY_MS)


def clear_command_line(screen):
    """
    Ctrl+C is used instead of Enter.

    Enter could execute a partial command such as:

        show

    and produce an incomplete-command error.
    """

    screen.Send(chr(3))

    crt.Sleep(AFTER_CANCEL_DELAY_MS)

    wait_for_screen_idle(screen)


def wait_for_screen_idle(screen):
    """
    Continue waiting while the terminal cursor is moving.

    This is preferable to one fixed sleep because this script is expected
    to run over serial connections where large help pages can take several
    seconds to arrive.
    """

    checks = 0

    while checks < MAX_IDLE_CHECKS:
        moved = screen.WaitForCursor(IDLE_SECONDS)

        if not moved:
            return

        checks += 1


def parse_literal_options(text):
    """
    Follow lowercase literal VOSS keywords.

    Accepted:

        access-policy              Show access policy configurations
        alarm                      Show alarm information
        ip                         Show IP commands
        ospf                       Show OSPF commands
        default                    Use default value

    Not followed:

        <1-4094>                   VLAN identifier
        WORD                       Name
        IP-ADDRESS                 IP address
        <cr>
    """

    options = []

    for original_line in normalize_log_text(text).split("\n"):
        line = remove_log_prefix(original_line)

        if line.strip() == "":
            continue

        match = re.match(
            r"^\s{2,}([a-z][a-z0-9_.:/-]*)\s{2,}\S.*$",
            line
        )

        if not match:
            continue

        option = match.group(1).strip()

        if option not in options:
            options.append(option)

    return options


def parse_placeholders(text):
    placeholders = []

    for original_line in normalize_log_text(text).split("\n"):
        line = remove_log_prefix(original_line)

        if line.strip() == "":
            continue

        match = re.match(
            r"^\s{2,}(\S+)\s{2,}\S.*$",
            line
        )

        if not match:
            continue

        token = match.group(1).strip()

        if is_literal_keyword(token):
            continue

        if is_placeholder(token):
            if token not in placeholders:
                placeholders.append(token)

    return placeholders


def is_literal_keyword(token):
    return re.match(
        r"^[a-z][a-z0-9_.:/-]*$",
        token
    ) is not None


def is_placeholder(token):
    if token == "":
        return False

    if token.startswith("<"):
        return True

    if token.startswith("["):
        return True

    if token.startswith("{"):
        return True

    if token.startswith("|"):
        return True

    # Uppercase VOSS tokens generally represent user-supplied values.
    if token.upper() == token and re.search(r"[A-Z]", token):
        return True

    return False


def remove_log_prefix(line):
    """
    Remove optional SecureCRT timestamp prefixes such as:

        [2026-07-14 08:45:10]

    This allows parsing to work even when line timestamps are configured
    in the current SecureCRT session.
    """

    return re.sub(
        r"^\s*\[[^\]]+\]\s*",
        "",
        line
    )


def normalize_log_text(text):
    if text is None:
        return ""

    value = str(text)

    value = re.sub(
        r"\x1b\[[0-9;?]*[A-Za-z]",
        "",
        value
    )

    value = value.replace("\x1b", "")
    value = value.replace("\n\r", "\n")
    value = value.replace("\r\n", "\n")
    value = value.replace("\r", "\n")

    return value


def build_section_header(command, depth, number):
    lines = []

    lines.append("\n")
    lines.append("=" * 100 + "\n")
    lines.append("Query Number: " + str(number) + "\n")
    lines.append("Depth: " + str(depth) + "\n")
    lines.append("Command: " + command + " ?\n")
    lines.append("=" * 100 + "\n")

    return "".join(lines)


def append_parse_results(path, literals, placeholders, captured):
    lines = []

    lines.append("\n")
    lines.append("-" * 100 + "\n")
    lines.append("Parser Results\n")
    lines.append("-" * 100 + "\n")
    lines.append(
        "Captured characters: " +
        str(len(captured)) +
        "\n"
    )
    lines.append(
        "Literal children: " +
        str(len(literals)) +
        "\n"
    )
    lines.append(
        "Value placeholders: " +
        str(len(placeholders)) +
        "\n"
    )

    if len(literals) > 0:
        lines.append(
            "Children: " +
            ", ".join(literals) +
            "\n"
        )

    if len(placeholders) > 0:
        lines.append(
            "Placeholders: " +
            ", ".join(placeholders) +
            "\n"
        )

    lines.append("\n")

    append_text(
        path,
        "".join(lines)
    )


def write_log_header(path, prompt):
    lines = []

    lines.append("VOSS Recursive Show Help Crawl\n")
    lines.append(
        "Generated: " +
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") +
        "\n"
    )
    lines.append("Prompt: " + prompt + "\n")
    lines.append("Maximum depth: " + str(MAX_DEPTH) + "\n")
    lines.append("Maximum commands: " + str(MAX_COMMANDS) + "\n")
    lines.append("Capture method: SecureCRT native session logging\n")
    lines.append("\n")

    write_text(
        path,
        "".join(lines)
    )


def append_summary(
    path,
    commands,
    literals,
    placeholders,
    failures
):
    lines = []

    lines.append("\n")
    lines.append("=" * 100 + "\n")
    lines.append("Crawl Summary\n")
    lines.append("=" * 100 + "\n")
    lines.append("Commands queried: " + str(commands) + "\n")
    lines.append(
        "Literal options discovered: " +
        str(literals) +
        "\n"
    )
    lines.append(
        "Value placeholders recorded: " +
        str(placeholders) +
        "\n"
    )
    lines.append("Failures: " + str(failures) + "\n")

    append_text(
        path,
        "".join(lines)
    )


def get_prompt(screen):
    row = screen.CurrentRow
    column = screen.CurrentColumn - 1

    if column < 1:
        column = 1

    value = screen.Get(
        row,
        0,
        row,
        column
    )

    return value.strip()


def hostname_from_prompt(prompt):
    value = prompt.strip()

    if value.endswith("#") or value.endswith(">"):
        value = value[:-1]

    value = value.strip()

    if value == "":
        return "UNKNOWN"

    return value


def get_file_size(path):
    if not os.path.exists(path):
        return 0

    return os.path.getsize(path)


def read_file_from_offset(path, offset):
    handle = open(path, "rb")

    try:
        handle.seek(offset)
        data = handle.read()
    finally:
        handle.close()

    try:
        return data.decode("utf-8")
    except Exception:
        pass

    try:
        return data.decode("cp1252")
    except Exception:
        pass

    return data.decode("latin-1", "replace")


def sanitize_filename(value):
    value = str(value).strip()

    value = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "-",
        value
    )

    value = value.strip("-._")

    if value == "":
        return "UNKNOWN"

    return value


def ensure_directory(path):
    if not os.path.exists(path):
        os.makedirs(path)


def write_text(path, data):
    handle = codecs.open(
        path,
        "w",
        "utf-8"
    )

    try:
        handle.write(data)
    finally:
        handle.close()


def append_text(path, data):
    handle = codecs.open(
        path,
        "a",
        "utf-8"
    )

    try:
        handle.write(data)
        handle.flush()
    finally:
        handle.close()


Main()