# $language = "python"
# $interface = "1.0"

# VOSS Configuration Help Crawler
#
# Intended transport:
#   Serial console
#
# Operation:
#   1. Enters configure terminal.
#   2. Sends ? at the global configuration prompt.
#   3. Parses all literal command keywords.
#   4. Recursively sends:
#
#        command ?
#        command child ?
#        command child grandchild ?
#
#   5. Records dynamic placeholders but does not invent values.
#   6. Cancels every partial command with Ctrl+C.
#   7. Returns to privileged EXEC mode when finished.
#
# No discovered configuration command is executed.
#
# Output:
#   C:\scripts\secure-crt\outputs\config-help\
#
# No external dependencies.

import codecs
import collections
import datetime
import os
import re


SCRIPT_TITLE = "VOSS Configuration Help Crawler"

OUTPUT_ROOT = r"C:\scripts\secure-crt\outputs\config-help"

TERMINAL_LENGTH = 64

# Faster serial-console pacing.
#
# The crawler primarily relies on cursor-idle detection rather than
# long fixed sleeps. Increase IDLE_SECONDS to 2 for very slow serial
# connections, such as 9600 baud.
INITIAL_RENDER_DELAY_MS = 100
AFTER_CANCEL_DELAY_MS = 75
BETWEEN_COMMAND_DELAY_MS = 50
NORMAL_COMMAND_DELAY_MS = 250

# A help query is considered complete after the cursor has not moved
# for this many seconds.
IDLE_SECONDS = 1

# Allows up to approximately two minutes of continuously moving output
# before the script gives up waiting for one query.
MAX_IDLE_CHECKS = 60

# Safety limits.
MAX_DEPTH = 25
MAX_COMMANDS = 20000

# Prevent unusually long command paths even if an unexpected CLI grammar
# does not match the repeatable-choice detector.
MAX_COMMAND_TOKENS = 24

# Repeatable-choice detection is intentionally limited to reasonably sized
# option groups. This avoids treating large command namespaces such as the
# root global-configuration list as an unordered choice list.
MIN_REPEATABLE_CHOICES = 2
MAX_REPEATABLE_CHOICES = 32


def Main():
    tab = crt.GetScriptTab()

    if not tab.Session.Connected:
        crt.Dialog.MessageBox(
            "Not connected.\n\nConnect to the VOSS serial console first.",
            SCRIPT_TITLE
        )
        return

    screen = tab.Screen
    session = tab.Session

    # Native SecureCRT session logging captures VOSS question-mark output
    # more reliably than Screen.ReadString().
    screen.Synchronous = False
    screen.IgnoreEscape = True

    clear_command_line(screen)
    crt.Sleep(NORMAL_COMMAND_DELAY_MS)

    exec_prompt = get_prompt(screen)

    if exec_prompt == "":
        crt.Dialog.MessageBox(
            "Could not detect the VOSS command prompt.",
            SCRIPT_TITLE
        )
        return

    hostname = hostname_from_prompt(exec_prompt)

    confirmation = crt.Dialog.Prompt(
        "This will crawl the VOSS configuration-command help tree.\n\n"
        "The script will:\n"
        "  1. Enter configure terminal\n"
        "  2. Send ? at the configuration prompt\n"
        "  3. Follow every literal keyword it discovers\n"
        "  4. Record placeholders such as <1-4094> and WORD\n"
        "  5. Cancel every partial command with Ctrl+C\n"
        "  6. Return to privileged EXEC mode when finished\n\n"
        "No discovered configuration command will be executed.\n\n"
        "Repeatable option lists are detected so alternate orderings do "
        "not expand into thousands of help queries.\n\n"
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

    output_path = os.path.join(
        OUTPUT_ROOT,
        timestamp + "_" +
        sanitize_filename(hostname) +
        "_config-help.txt"
    )

    capture_directory = os.path.join(
        OUTPUT_ROOT,
        "_capture"
    )

    ensure_directory(capture_directory)

    previous_logging = session.Logging
    previous_log_file = session.LogFileName

    command_count = 0
    literal_option_count = 0
    placeholder_count = 0
    failure_count = 0
    permutation_skip_count = 0
    token_limit_skip_count = 0

    config_mode_entered = False

    try:
        if session.Logging:
            session.Log(False)

        run_normal_command(
            screen,
            "terminal length " + str(TERMINAL_LENGTH)
        )

        run_normal_command(
            screen,
            "configure terminal"
        )

        config_prompt = get_prompt(screen)

        if not is_configuration_prompt(config_prompt):
            crt.Dialog.MessageBox(
                "The switch did not appear to enter configuration mode.\n\n"
                "Detected prompt:\n" + config_prompt,
                SCRIPT_TITLE
            )
            return

        config_mode_entered = True

        write_header(
            output_path,
            exec_prompt,
            config_prompt
        )

        queue = collections.deque([
            {
                "command": "",
                "depth": 1,
                "parent_command": "",
                "parent_options": [],
                "selected_option": "",
            }
        ])

        visited = set()

        while len(queue) > 0:
            if command_count >= MAX_COMMANDS:
                append_text(
                    output_path,
                    "\nSTOPPED: Maximum command count reached: " +
                    str(MAX_COMMANDS) +
                    "\n"
                )
                break

            item = queue.popleft()

            command = item.get("command", "").strip()
            depth = item.get("depth", 1)

            command_key = command.lower()

            if command_key in visited:
                continue

            visited.add(command_key)
            command_count += 1

            capture_path = os.path.join(
                capture_directory,
                timestamp + "_" +
                str(command_count).zfill(6) +
                ".txt"
            )

            try:
                captured = capture_help_query(
                    screen,
                    session,
                    command,
                    capture_path
                )

                literal_options = parse_literal_options(captured)
                placeholders = parse_placeholders(captured)

                guarded_options = detect_repeatable_options(
                    item,
                    literal_options
                )

                literal_option_count += len(literal_options)
                placeholder_count += len(placeholders)

                append_query_section(
                    output_path,
                    command_count,
                    depth,
                    command,
                    captured,
                    literal_options,
                    placeholders,
                    guarded_options,
                    ""
                )

                if depth < MAX_DEPTH:
                    for option in literal_options:
                        if option in guarded_options:
                            permutation_skip_count += 1
                            continue

                        child_command = join_command(
                            command,
                            option
                        )

                        if count_command_tokens(child_command) > MAX_COMMAND_TOKENS:
                            token_limit_skip_count += 1
                            continue

                        child_key = child_command.lower()

                        if child_key not in visited:
                            queue.append(
                                {
                                    "command": child_command,
                                    "depth": depth + 1,
                                    "parent_command": command,
                                    "parent_options": list(literal_options),
                                    "selected_option": option,
                                }
                            )

            except Exception as exc:
                failure_count += 1

                try:
                    if session.Logging:
                        session.Log(False)
                except Exception:
                    pass

                append_query_section(
                    output_path,
                    command_count,
                    depth,
                    command,
                    "",
                    [],
                    [],
                    [],
                    to_text(exc)
                )

                clear_command_line(screen)

            finally:
                delete_file_if_present(capture_path)

        append_summary(
            output_path,
            command_count,
            literal_option_count,
            placeholder_count,
            permutation_skip_count,
            token_limit_skip_count,
            failure_count
        )

    finally:
        try:
            if session.Logging:
                session.Log(False)
        except Exception:
            pass

        if config_mode_entered:
            leave_configuration_mode(screen)

        try:
            session.LogFileName = previous_log_file
        except Exception:
            pass

        if previous_logging and previous_log_file != "":
            try:
                session.Log(True, True, False)
            except Exception:
                pass

        remove_directory_if_empty(capture_directory)

    crt.Dialog.MessageBox(
        "Configuration help crawl complete.\n\n"
        "Commands queried: " + str(command_count) + "\n"
        "Literal options discovered: " + str(literal_option_count) + "\n"
        "Placeholders recorded: " + str(placeholder_count) + "\n"
        "Repeatable branches skipped: " +
        str(permutation_skip_count) + "\n"
        "Token-limit branches skipped: " +
        str(token_limit_skip_count) + "\n"
        "Failures: " + str(failure_count) + "\n\n"
        "Output file:\n" + output_path,
        SCRIPT_TITLE
    )


def capture_help_query(screen, session, command, capture_path):
    """
    Capture one VOSS question-mark query with native SecureCRT logging.

    Root configuration prompt:

        ?

    Discovered command paths:

        vlan ?
        vlan create ?
        router ospf ?

    The command is not executed with Enter. Ctrl+C cancels the partial
    command after the help text finishes displaying.
    """

    delete_file_if_present(capture_path)

    session.LogFileName = capture_path
    session.Log(True, False, False)

    if command == "":
        query = "?"
    else:
        query = command + " ?"

    screen.Send(query)

    # Allow output to begin, then rely on cursor-idle detection.
    crt.Sleep(INITIAL_RENDER_DELAY_MS)
    wait_for_screen_idle(screen)

    # Cancel the partial configuration command without executing it.
    screen.Send(chr(3))

    crt.Sleep(AFTER_CANCEL_DELAY_MS)
    wait_for_screen_idle(screen)

    # Stopping logging flushes the temporary capture file.
    session.Log(False)

    crt.Sleep(BETWEEN_COMMAND_DELAY_MS)

    captured = read_text_file(capture_path)

    return normalize_capture(captured)


def run_normal_command(screen, command):
    clear_command_line(screen)

    screen.Send(command + "\r")

    crt.Sleep(NORMAL_COMMAND_DELAY_MS)
    wait_for_screen_idle(screen)


def clear_command_line(screen):
    """
    Cancel anything currently typed without executing it.
    """

    screen.Send(chr(3))
    crt.Sleep(AFTER_CANCEL_DELAY_MS)


def wait_for_screen_idle(screen):
    """
    Wait until no cursor movement is detected for IDLE_SECONDS.

    Long serial output is supported because every detected cursor
    movement starts another idle check.
    """

    checks = 0

    while checks < MAX_IDLE_CHECKS:
        if not screen.WaitForCursor(IDLE_SECONDS):
            return True

        checks += 1

    return False


def leave_configuration_mode(screen):
    """
    Prefer end. If the prompt remains in configuration mode, send exit
    repeatedly as a fallback.
    """

    clear_command_line(screen)

    screen.Send("end\r")

    crt.Sleep(NORMAL_COMMAND_DELAY_MS)
    wait_for_screen_idle(screen)

    prompt = get_prompt(screen)
    attempts = 0

    while is_configuration_prompt(prompt) and attempts < 10:
        screen.Send("exit\r")

        crt.Sleep(NORMAL_COMMAND_DELAY_MS)
        wait_for_screen_idle(screen)

        prompt = get_prompt(screen)
        attempts += 1


def parse_literal_options(text):
    """
    Parse lowercase literal VOSS command keywords.

    Followed:

        vlan                       Configure VLAN information
        router                     Configure routing
        spanning-tree              Configure spanning tree
        no                         Negate a command
        default                    Restore a default

    Recorded but not followed:

        <1-4094>
        WORD
        IP-ADDRESS
        PORT
        <cr>
    """

    options = []

    for original_line in normalize_capture(text).split(u"\n"):
        line = remove_log_prefix(original_line)

        if line.strip() == u"":
            continue

        match = re.match(
            u"^\\s{2,}([a-z][a-z0-9_.:/-]*)\\s{2,}\\S.*$",
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

    for original_line in normalize_capture(text).split(u"\n"):
        line = remove_log_prefix(original_line)

        if line.strip() == u"":
            continue

        match = re.match(
            u"^\\s{2,}(\\S+)\\s{2,}\\S.*$",
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
        u"^[a-z][a-z0-9_.:/-]*$",
        token
    ) is not None


def is_placeholder(token):
    if token == u"":
        return False

    if token.startswith(u"<"):
        return True

    if token.startswith(u"["):
        return True

    if token.startswith(u"{"):
        return True

    if token.startswith(u"|"):
        return True

    if token.upper() == token and re.search(u"[A-Z]", token):
        return True

    return False


def join_command(parent, child):
    if parent == "":
        return child

    return parent + " " + child


def count_command_tokens(command):
    if command.strip() == "":
        return 0

    return len(command.split())


def detect_repeatable_options(item, literal_options):
    """
    Detect unordered or repeatable option lists without relying on a
    command-specific name such as encryption-type.

    Example:

        feature ?
          option-a
          option-b
          option-c

        feature option-a ?
          option-b
          option-c

    The second help state mostly repeats choices from the direct parent.
    Continuing into option-b and option-c would create alternate orderings
    of the same set. Those repeated siblings are returned as guarded options.

    Important safeguards:

      * The root global-configuration namespace is never classified as a
        repeatable list because parent_command is empty.
      * Only reasonably sized parent option groups are considered.
      * New child keywords that were not offered by the parent remain
        eligible for normal crawling.
    """

    parent_command = item.get("parent_command", "").strip()
    parent_options = item.get("parent_options", [])
    selected_option = item.get("selected_option", "").strip()

    if parent_command == "":
        return []

    if len(parent_options) < MIN_REPEATABLE_CHOICES:
        return []

    if len(parent_options) > MAX_REPEATABLE_CHOICES:
        return []

    parent_set = set([option.lower() for option in parent_options])
    current_set = set([option.lower() for option in literal_options])

    if selected_option.lower() not in parent_set:
        return []

    repeated_set = current_set.intersection(parent_set)

    if len(repeated_set) == 0:
        return []

    # Strong signal: every current literal is one of the original siblings.
    all_current_are_parent_choices = current_set.issubset(parent_set)

    # Mixed help states can contain both remaining sibling choices and one or
    # more genuinely new subcommands. Treat it as repeatable when at least
    # half of both sets overlap. Cross multiplication avoids float behavior
    # differences between SecureCRT Python runtimes.
    overlap_is_dominant = (
        len(repeated_set) * 2 >= len(parent_set) and
        len(repeated_set) * 2 >= len(current_set)
    )

    if not all_current_are_parent_choices and not overlap_is_dominant:
        return []

    guarded = []

    for option in literal_options:
        if option.lower() in repeated_set:
            guarded.append(option)

    return guarded


def append_query_section(
    path,
    query_number,
    depth,
    command,
    captured,
    literal_options,
    placeholders,
    guarded_options,
    error
):
    lines = []

    if command == "":
        displayed_command = "?"
    else:
        displayed_command = command + " ?"

    lines.append("\n")
    lines.append("=" * 110 + "\n")
    lines.append("Query Number: " + str(query_number) + "\n")
    lines.append("Depth: " + str(depth) + "\n")
    lines.append("Command: " + displayed_command + "\n")
    lines.append(
        "Captured characters: " +
        str(len(captured)) +
        "\n"
    )
    lines.append(
        "Literal children: " +
        str(len(literal_options)) +
        "\n"
    )
    lines.append(
        "Value placeholders: " +
        str(len(placeholders)) +
        "\n"
    )

    if len(literal_options) > 0:
        lines.append(
            "Children: " +
            join_text_values(literal_options) +
            "\n"
        )

    if len(placeholders) > 0:
        lines.append(
            "Placeholders: " +
            join_text_values(placeholders) +
            "\n"
        )

    if len(guarded_options) > 0:
        lines.append(
            "Permutation guard skipped: " +
            join_text_values(guarded_options) +
            "\n"
        )

    if error != "":
        lines.append("ERROR: " + error + "\n")

    lines.append("=" * 110 + "\n")

    if error != "":
        lines.append("[Query failed]\n")
    elif captured.strip() == u"":
        lines.append("[No output captured]\n")
    else:
        lines.append(captured.strip() + u"\n")

    append_text(
        path,
        u"".join([to_text(value) for value in lines])
    )


def write_header(path, exec_prompt, config_prompt):
    lines = []

    lines.append("VOSS Configuration Help Crawl\n")
    lines.append(
        "Generated: " +
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") +
        "\n"
    )
    lines.append("Transport: Serial console\n")
    lines.append("Initial EXEC prompt: " + exec_prompt + "\n")
    lines.append("Configuration prompt: " + config_prompt + "\n")
    lines.append("Maximum depth: " + str(MAX_DEPTH) + "\n")
    lines.append("Maximum commands: " + str(MAX_COMMANDS) + "\n")
    lines.append("Maximum command tokens: " + str(MAX_COMMAND_TOKENS) + "\n")
    lines.append("Repeatable-choice protection: enabled\n")
    lines.append(
        "Capture method: SecureCRT native session logging\n"
    )
    lines.append(
        "Note: Literal keywords are followed. Dynamic values are recorded "
        "but are not populated automatically.\n"
    )
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
    permutation_skips,
    token_limit_skips,
    failures
):
    lines = []

    lines.append("\n")
    lines.append("=" * 110 + "\n")
    lines.append("Crawl Summary\n")
    lines.append("=" * 110 + "\n")
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
    lines.append(
        "Repeatable branches skipped: " +
        str(permutation_skips) +
        "\n"
    )
    lines.append(
        "Token-limit branches skipped: " +
        str(token_limit_skips) +
        "\n"
    )
    lines.append("Failures: " + str(failures) + "\n")

    append_text(
        path,
        "".join(lines)
    )


def is_configuration_prompt(prompt):
    lower = prompt.lower()

    if "(config" in lower:
        return True

    return False


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

    value = re.sub(
        r"\(config[^)]*\)$",
        "",
        value,
        flags=re.I
    )

    value = value.strip()

    if value == "":
        return "UNKNOWN"

    return value


def to_text(value):
    """
    Return Unicode safely under SecureCRT Python 2 or Python 3.

    SecureCRT session logs may begin with a UTF-8 BOM. Avoid calling
    str() directly on decoded Unicode because Python 2 may attempt an
    ASCII conversion.
    """

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

    try:
        return value.decode("utf-8-sig")
    except Exception:
        pass

    try:
        return value.decode("cp1252")
    except Exception:
        pass

    try:
        return value.decode("latin-1", "replace")
    except Exception:
        return text_type(value)


def normalize_capture(text):
    if text is None:
        return to_text("")

    value = to_text(text)

    # Remove an optional UTF-8 byte-order mark.
    if value.startswith(u"\ufeff"):
        value = value[1:]

    value = apply_backspaces(value)

    # Remove common ANSI terminal escape sequences.
    value = re.sub(
        u"\x1b\\[[0-9;?]*[A-Za-z]",
        u"",
        value
    )

    value = value.replace(u"\x1b", u"")
    value = value.replace(u"\x00", u"")
    value = value.replace(u"\n\r", u"\n")
    value = value.replace(u"\r\n", u"\n")
    value = value.replace(u"\r", u"\n")

    return value


def apply_backspaces(value):
    result = []

    for character in value:
        if character == u"\b":
            if len(result) > 0:
                result.pop()
        else:
            result.append(character)

    return u"".join(result)


def remove_log_prefix(line):
    # Supports optional SecureCRT timestamp prefixes.
    return re.sub(
        u"^\\s*\\[[^\\]]+\\]\\s*",
        u"",
        line
    )


def join_text_values(values):
    text_values = []

    for value in values:
        text_values.append(to_text(value))

    return u", ".join(text_values)


def read_text_file(path):
    if not os.path.exists(path):
        return to_text("")

    handle = open(path, "rb")

    try:
        data = handle.read()
    finally:
        handle.close()

    # utf-8-sig removes SecureCRT's optional UTF-8 BOM.
    try:
        return data.decode("utf-8-sig")
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
        handle.write(to_text(data))
    finally:
        handle.close()


def append_text(path, data):
    handle = codecs.open(
        path,
        "a",
        "utf-8"
    )

    try:
        handle.write(to_text(data))
        handle.flush()
    finally:
        handle.close()


def delete_file_if_present(path):
    if not os.path.exists(path):
        return

    try:
        os.remove(path)
    except Exception:
        pass


def remove_directory_if_empty(path):
    if not os.path.isdir(path):
        return

    try:
        if len(os.listdir(path)) == 0:
            os.rmdir(path)
    except Exception:
        pass


Main()