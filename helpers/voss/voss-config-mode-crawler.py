# $language = "python"
# $interface = "1.0"

# VOSS Configuration Mode Crawler
#
# Intended transport:
#   Serial console
#
# Purpose:
#   Enter selected VOSS configuration submodes and recursively crawl
#   the question-mark help available inside each mode.
#
# Mode navigation:
#   1. Start each profile from exact global configuration mode: (config)#
#   2. Enter the requested submode.
#   3. Crawl the configured command root with question-mark help.
#   4. Send exit until the prompt returns to exact global configuration.
#   5. Run optional cleanup commands.
#   6. Return to exact global configuration before the next profile.
#   7. Return to privileged EXEC after all profiles complete.
#
# SPBM coverage:
#   - Global SPBM syntax: spbm ?
#   - IS-IS configuration mode: router isis, then ?
#   - IS-IS SPBM instance syntax: router isis, then spbm 1 ?
#   - Interface SPBM syntax: interface ethernet 1/1, then isis spbm 1 ?
#
# The crawler never presses Enter on discovered commands. It sends:
#
#   command ?
#
# and cancels the partial command with Ctrl+C.
#
# Some profile entry commands can temporarily modify running configuration.
# Cleanup commands are attempted, but the configuration is never saved.
#
# Output:
#   C:\scripts\secure-crt\outputs\mode-help\
#
# No external dependencies.

import codecs
import collections
import datetime
import os
import re


SCRIPT_TITLE = "VOSS Configuration Mode Crawler"

OUTPUT_ROOT = r"C:\scripts\secure-crt\outputs\mode-help"

TERMINAL_LENGTH = 64


# ----------------------------------------------------------------------
# Safe/test values
# ----------------------------------------------------------------------
#
# Review these values before running the script.
#
# Existing interfaces such as VLAN 1 and Ethernet 1/1 normally allow
# mode entry without creating a new object.
#
# Loopback 99, OSPF area 0.0.0.255, BGP AS 65000, and SPBM instance 1
# are test values. Change them if they conflict with the device.
#

SAFE_VALUES = {
    "physical_interface": "1/1",
    "vlan_interface": "1",
    "loopback_interface": "99",
    "ospf_area": "0.0.0.255",
    "bgp_as": "65000",
    "spbm_instance": "1",
}


# ----------------------------------------------------------------------
# Mode profiles
# ----------------------------------------------------------------------
#
# enabled:
#   True  = crawl this profile
#   False = skip this profile
#
# entry_commands:
#   Commands executed after the script reaches exact global
#   configuration mode.
#
# crawl_root:
#   First command prefix to question-mark inside the selected mode.
#
#   ""              -> send ?
#   "spbm"          -> send spbm ?
#   "spbm 1"        -> send spbm 1 ?
#   "isis spbm 1"   -> send isis spbm 1 ?
#
# expected_prompt_patterns:
#   Regular expressions used to validate the final mode prompt.
#
# cleanup_commands:
#   Commands executed as one sequence beginning from exact global
#   configuration mode. The script returns to global configuration
#   after the sequence automatically.
#

MODE_PROFILES = [
    {
        "name": "Global SPBM Syntax",
        "enabled": True,
        "entry_commands": [],
        "crawl_root": "spbm",
        "expected_prompt_patterns": [
            r"\(config\)#$",
        ],
        "cleanup_commands": [],
    },
    {
        "name": "ISIS Router",
        "enabled": True,
        "entry_commands": [
            "router isis",
        ],
        "crawl_root": "",
        "expected_prompt_patterns": [
            r"\(config-isis[^)]*\)#$",
        ],
        "cleanup_commands": [],
    },
    {
        "name": "ISIS SPBM Instance Syntax",
        "enabled": True,
        "entry_commands": [
            "router isis",
        ],
        "crawl_root": "spbm " + SAFE_VALUES["spbm_instance"],
        "expected_prompt_patterns": [
            r"\(config-isis[^)]*\)#$",
        ],
        "cleanup_commands": [],
    },
    {
        "name": "Physical Ethernet Interface",
        "enabled": True,
        "entry_commands": [
            "interface ethernet " + SAFE_VALUES["physical_interface"],
        ],
        "crawl_root": "",
        "expected_prompt_patterns": [
            r"\(config-if[^)]*\)#$",
            r"\(config-interface[^)]*\)#$",
        ],
        "cleanup_commands": [],
    },
    {
        "name": "Physical Interface SPBM Syntax",
        "enabled": True,
        "entry_commands": [
            "interface ethernet " + SAFE_VALUES["physical_interface"],
        ],
        "crawl_root": "isis spbm " + SAFE_VALUES["spbm_instance"],
        "expected_prompt_patterns": [
            r"\(config-if[^)]*\)#$",
            r"\(config-interface[^)]*\)#$",
        ],
        "cleanup_commands": [],
    },
    {
        "name": "VLAN Interface",
        "enabled": True,
        "entry_commands": [
            "interface vlan " + SAFE_VALUES["vlan_interface"],
        ],
        "crawl_root": "",
        "expected_prompt_patterns": [
            r"\(config-if[^)]*\)#$",
            r"\(config-interface[^)]*\)#$",
        ],
        "cleanup_commands": [],
    },
    {
        "name": "OSPF Router",
        "enabled": True,
        "entry_commands": [
            "router ospf",
        ],
        "crawl_root": "",
        "expected_prompt_patterns": [
            r"\(config-ospf[^)]*\)#$",
        ],
        "cleanup_commands": [],
    },
    {
        "name": "OSPF Area",
        "enabled": True,
        "entry_commands": [
            "router ospf",
            "area " + SAFE_VALUES["ospf_area"],
        ],
        "crawl_root": "",
        "expected_prompt_patterns": [
            r"\(config-ospf-area[^)]*\)#$",
            r"\(config-area[^)]*\)#$",
        ],
        "cleanup_commands": [
            "router ospf",
            "no area " + SAFE_VALUES["ospf_area"],
        ],
    },
    {
        "name": "BGP Router",
        "enabled": True,
        "entry_commands": [
            "router bgp " + SAFE_VALUES["bgp_as"],
        ],
        "crawl_root": "",
        "expected_prompt_patterns": [
            r"\(config-bgp[^)]*\)#$",
        ],
        "cleanup_commands": [
            "no router bgp " + SAFE_VALUES["bgp_as"],
        ],
    },
    {
        "name": "Loopback Interface",
        "enabled": True,
        "entry_commands": [
            "interface loopback " + SAFE_VALUES["loopback_interface"],
        ],
        "crawl_root": "",
        "expected_prompt_patterns": [
            r"\(config-if[^)]*\)#$",
            r"\(config-interface[^)]*\)#$",
        ],
        "cleanup_commands": [
            "no interface loopback " + SAFE_VALUES["loopback_interface"],
        ],
    },
    {
        "name": "RIP Router",
        "enabled": False,
        "entry_commands": [
            "router rip",
        ],
        "crawl_root": "",
        "expected_prompt_patterns": [
            r"\(config-rip[^)]*\)#$",
        ],
        "cleanup_commands": [],
    },
]


# ----------------------------------------------------------------------
# Faster serial-console pacing
# ----------------------------------------------------------------------
#
# The crawler relies primarily on cursor-idle detection. Increase
# IDLE_SECONDS to 2 if a very slow serial session truncates output.
#

INITIAL_RENDER_DELAY_MS = 100
AFTER_CANCEL_DELAY_MS = 100
BETWEEN_QUERY_DELAY_MS = 50
NORMAL_COMMAND_DELAY_MS = 300
MODE_TRANSITION_DELAY_MS = 350

IDLE_SECONDS = 1
MAX_IDLE_CHECKS = 120


# ----------------------------------------------------------------------
# Crawl boundaries
# ----------------------------------------------------------------------

MAX_DEPTH_PER_MODE = 25
MAX_COMMANDS_PER_MODE = 10000
MAX_TOTAL_COMMANDS = 50000
MAX_MODE_EXIT_ATTEMPTS = 12


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def Main():
    tab = crt.GetScriptTab()

    if not tab.Session.Connected:
        crt.Dialog.MessageBox(
            "Not connected.\n\n"
            "Connect to the offline VOSS device over the serial console.",
            SCRIPT_TITLE
        )
        return

    screen = tab.Screen
    session = tab.Session

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
    enabled_profiles = get_enabled_profiles()

    if len(enabled_profiles) == 0:
        crt.Dialog.MessageBox(
            "No mode profiles are enabled.",
            SCRIPT_TITLE
        )
        return

    profile_preview = build_profile_preview(enabled_profiles)

    confirmation = crt.Dialog.Prompt(
        "This will enter and crawl VOSS configuration submodes.\n\n"
        "Enabled profiles:\n\n" +
        profile_preview +
        "\n\nEach profile starts and ends at exact global configuration "
        "mode: (config)#.\n\n"
        "Temporary mode-entry commands may modify the running "
        "configuration. Cleanup commands will be attempted, but the "
        "configuration will not be saved.\n\n"
        "Use this only on an offline test or decommissioned device.\n\n"
        "Type MODECRAWL to continue.",
        SCRIPT_TITLE,
        "",
        False
    )

    if confirmation is None:
        return

    if confirmation.strip().upper() != "MODECRAWL":
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
        "_mode-help.txt"
    )

    capture_directory = os.path.join(
        OUTPUT_ROOT,
        "_capture"
    )

    ensure_directory(capture_directory)

    previous_logging = session.Logging
    previous_log_file = session.LogFileName

    total_commands = 0
    total_literal_options = 0
    total_placeholders = 0
    total_failures = 0
    successful_profiles = 0
    failed_profiles = 0

    try:
        if session.Logging:
            session.Log(False)

        if not ensure_exec_mode(screen):
            crt.Dialog.MessageBox(
                "Could not reach privileged EXEC mode.",
                SCRIPT_TITLE
            )
            return

        run_normal_command(
            screen,
            "terminal length " + str(TERMINAL_LENGTH)
        )

        if not ensure_global_config_mode(screen):
            crt.Dialog.MessageBox(
                "Could not reach global configuration mode.",
                SCRIPT_TITLE
            )
            return

        write_header(
            output_path,
            exec_prompt,
            enabled_profiles
        )

        for profile_index in range(0, len(enabled_profiles)):
            if total_commands >= MAX_TOTAL_COMMANDS:
                append_text(
                    output_path,
                    "\nSTOPPED: Maximum total command count reached: " +
                    str(MAX_TOTAL_COMMANDS) +
                    "\n"
                )
                break

            profile = enabled_profiles[profile_index]

            append_profile_header(
                output_path,
                profile_index + 1,
                profile
            )

            profile_success = False

            try:
                if not ensure_global_config_mode(screen):
                    raise Exception(
                        "Could not reach exact global configuration mode "
                        "before profile entry."
                    )

                append_text(
                    output_path,
                    "Starting prompt: " + get_prompt(screen) + "\n"
                )

                mode_prompt = enter_profile(
                    screen,
                    profile
                )

                if mode_prompt == "":
                    raise Exception(
                        "No prompt was detected after profile entry."
                    )

                if not prompt_matches_profile(
                    mode_prompt,
                    profile
                ):
                    raise Exception(
                        "Unexpected prompt after profile entry: " +
                        mode_prompt
                    )

                append_text(
                    output_path,
                    "Detected profile prompt: " + mode_prompt + "\n"
                )

                results = crawl_current_profile(
                    screen,
                    session,
                    profile,
                    profile_index + 1,
                    timestamp,
                    capture_directory,
                    output_path,
                    MAX_TOTAL_COMMANDS - total_commands
                )

                total_commands += results.get("commands", 0)
                total_literal_options += results.get(
                    "literal_options",
                    0
                )
                total_placeholders += results.get(
                    "placeholders",
                    0
                )
                total_failures += results.get("failures", 0)

                profile_success = True
                successful_profiles += 1

            except Exception as exc:
                failed_profiles += 1
                total_failures += 1

                try:
                    if session.Logging:
                        session.Log(False)
                except Exception:
                    pass

                append_text(
                    output_path,
                    "\nPROFILE ERROR: " +
                    to_text(exc) +
                    "\n"
                )

            finally:
                # Always unwind the current submode before cleanup.
                returned_to_global = ensure_global_config_mode(screen)

                append_text(
                    output_path,
                    "Returned to global configuration before cleanup: " +
                    str(returned_to_global) +
                    "\n"
                )

                cleanup_ok = run_profile_cleanup(
                    screen,
                    profile,
                    output_path
                )

                append_text(
                    output_path,
                    "Cleanup result: " + str(cleanup_ok) + "\n"
                )

                # Always establish exact global configuration again before
                # the next profile begins.
                ready_for_next = ensure_global_config_mode(screen)

                append_text(
                    output_path,
                    "Ready for next profile at global configuration: " +
                    str(ready_for_next) +
                    "\n"
                )

                if not ready_for_next:
                    append_text(
                        output_path,
                        "STOPPED: Could not recover global configuration "
                        "mode after profile cleanup.\n"
                    )
                    break

                if profile_success:
                    append_text(
                        output_path,
                        "Profile completed successfully.\n"
                    )

        append_final_summary(
            output_path,
            len(enabled_profiles),
            successful_profiles,
            failed_profiles,
            total_commands,
            total_literal_options,
            total_placeholders,
            total_failures
        )

    finally:
        try:
            if session.Logging:
                session.Log(False)
        except Exception:
            pass

        leave_to_exec_mode(screen)

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
        "Configuration mode crawl complete.\n\n"
        "Mode profiles attempted: " +
        str(len(enabled_profiles)) + "\n"
        "Successful profiles: " + str(successful_profiles) + "\n"
        "Failed profiles: " + str(failed_profiles) + "\n"
        "Help commands queried: " + str(total_commands) + "\n"
        "Literal options discovered: " +
        str(total_literal_options) + "\n"
        "Placeholders recorded: " +
        str(total_placeholders) + "\n"
        "Failures: " + str(total_failures) + "\n\n"
        "Output file:\n" + output_path,
        SCRIPT_TITLE
    )


# ----------------------------------------------------------------------
# Profiles
# ----------------------------------------------------------------------


def get_enabled_profiles():
    enabled = []

    for profile in MODE_PROFILES:
        if profile.get("enabled", False):
            enabled.append(profile)

    return enabled


def build_profile_preview(profiles):
    lines = []

    for index in range(0, len(profiles)):
        profile = profiles[index]

        lines.append(
            str(index + 1) + ". " +
            profile.get("name", "Unnamed profile")
        )

        entry_commands = profile.get("entry_commands", [])

        if len(entry_commands) == 0:
            lines.append("   Entry: global configuration")
        else:
            for command in entry_commands:
                lines.append("   Entry: " + command)

        crawl_root = profile.get("crawl_root", "").strip()

        if crawl_root == "":
            lines.append("   Crawl: ?")
        else:
            lines.append("   Crawl: " + crawl_root + " ?")

        cleanup = profile.get("cleanup_commands", [])

        if len(cleanup) > 0:
            lines.append("   Cleanup:")

            for command in cleanup:
                lines.append("     " + command)

    return "\n".join(lines)


def enter_profile(screen, profile):
    if not ensure_global_config_mode(screen):
        return ""

    entry_commands = profile.get("entry_commands", [])

    for command in entry_commands:
        run_normal_command(
            screen,
            command
        )

    return get_prompt(screen)


def run_profile_cleanup(screen, profile, output_path):
    cleanup_commands = profile.get(
        "cleanup_commands",
        []
    )

    if len(cleanup_commands) == 0:
        return True

    if not ensure_global_config_mode(screen):
        append_text(
            output_path,
            "Cleanup skipped: global configuration mode unavailable.\n"
        )
        return False

    try:
        for command in cleanup_commands:
            run_normal_command(
                screen,
                command
            )

        return ensure_global_config_mode(screen)

    except Exception as exc:
        append_text(
            output_path,
            "Cleanup error: " + to_text(exc) + "\n"
        )

        ensure_global_config_mode(screen)
        return False


def prompt_matches_profile(prompt, profile):
    patterns = profile.get(
        "expected_prompt_patterns",
        []
    )

    if len(patterns) == 0:
        return is_any_configuration_prompt(prompt)

    for pattern in patterns:
        if re.search(pattern, prompt, re.I):
            return True

    return False


# ----------------------------------------------------------------------
# Crawl engine
# ----------------------------------------------------------------------


def crawl_current_profile(
    screen,
    session,
    profile,
    profile_number,
    timestamp,
    capture_directory,
    output_path,
    remaining_total_commands
):
    root_command = profile.get("crawl_root", "").strip()

    queue = collections.deque([
        {
            "command": root_command,
            "depth": 1,
        }
    ])

    visited = set()

    command_count = 0
    literal_option_count = 0
    placeholder_count = 0
    failure_count = 0

    while len(queue) > 0:
        if command_count >= MAX_COMMANDS_PER_MODE:
            append_text(
                output_path,
                "\nPROFILE STOPPED: Maximum commands per profile reached: " +
                str(MAX_COMMANDS_PER_MODE) +
                "\n"
            )
            break

        if command_count >= remaining_total_commands:
            append_text(
                output_path,
                "\nPROFILE STOPPED: Maximum total command limit reached.\n"
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
            timestamp + "_profile" +
            str(profile_number).zfill(3) +
            "_query" +
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

            literal_options = parse_literal_options(
                captured
            )

            placeholders = parse_placeholders(
                captured
            )

            literal_option_count += len(literal_options)
            placeholder_count += len(placeholders)

            append_query_section(
                output_path,
                profile.get("name", "Unnamed profile"),
                command_count,
                depth,
                command,
                captured,
                literal_options,
                placeholders,
                ""
            )

            if depth < MAX_DEPTH_PER_MODE:
                for option in literal_options:
                    child_command = join_command(
                        command,
                        option
                    )

                    child_key = child_command.lower()

                    if child_key not in visited:
                        queue.append(
                            {
                                "command": child_command,
                                "depth": depth + 1,
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
                profile.get("name", "Unnamed profile"),
                command_count,
                depth,
                command,
                "",
                [],
                [],
                to_text(exc)
            )

            clear_command_line(screen)

        finally:
            delete_file_if_present(capture_path)

    return {
        "commands": command_count,
        "literal_options": literal_option_count,
        "placeholders": placeholder_count,
        "failures": failure_count,
    }


def capture_help_query(
    screen,
    session,
    command,
    capture_path
):
    delete_file_if_present(capture_path)

    session.LogFileName = capture_path
    session.Log(True, False, False)

    if command == "":
        query = "?"
    else:
        query = command + " ?"

    screen.Send(query)

    crt.Sleep(INITIAL_RENDER_DELAY_MS)
    wait_for_screen_idle(screen)

    # Cancel the partial command without executing it.
    screen.Send(chr(3))
    crt.Sleep(AFTER_CANCEL_DELAY_MS)

    # Stopping logging flushes the temporary capture file. A second full
    # idle wait is intentionally avoided to reduce per-query runtime.
    session.Log(False)

    crt.Sleep(BETWEEN_QUERY_DELAY_MS)

    captured = read_text_file(capture_path)

    return normalize_capture(captured)


# ----------------------------------------------------------------------
# Mode navigation
# ----------------------------------------------------------------------


def ensure_global_config_mode(screen):
    """
    Reach exact global configuration mode: (config)#.

    Preferred path:
      - From a configuration submode, send exit until (config)#.
      - From privileged EXEC, send configure terminal.

    Fallback path:
      - Use Ctrl+Z to reach EXEC.
      - Re-enter configure terminal.
    """

    clear_command_line(screen)

    prompt = get_prompt(screen)

    if is_global_configuration_prompt(prompt):
        return True

    attempts = 0

    while (
        is_configuration_submode_prompt(prompt) and
        attempts < MAX_MODE_EXIT_ATTEMPTS
    ):
        screen.Send("exit\r")
        crt.Sleep(MODE_TRANSITION_DELAY_MS)
        wait_for_screen_idle(screen)

        prompt = get_prompt(screen)

        if is_global_configuration_prompt(prompt):
            return True

        attempts += 1

    # If exit reached EXEC, re-enter global configuration.
    if is_privileged_exec_prompt(prompt):
        run_normal_command(
            screen,
            "configure terminal"
        )

        return is_global_configuration_prompt(
            get_prompt(screen)
        )

    # Fallback from an unexpected or stubborn configuration prompt.
    if is_any_configuration_prompt(prompt):
        screen.Send(chr(26))
        crt.Sleep(MODE_TRANSITION_DELAY_MS)
        wait_for_screen_idle(screen)

        prompt = get_prompt(screen)

    if not is_privileged_exec_prompt(prompt):
        clear_command_line(screen)
        screen.Send("end\r")
        crt.Sleep(MODE_TRANSITION_DELAY_MS)
        wait_for_screen_idle(screen)

        prompt = get_prompt(screen)

    if is_privileged_exec_prompt(prompt):
        run_normal_command(
            screen,
            "configure terminal"
        )

        return is_global_configuration_prompt(
            get_prompt(screen)
        )

    return False


def ensure_exec_mode(screen):
    """
    Reach privileged EXEC mode without saving configuration.
    """

    clear_command_line(screen)

    prompt = get_prompt(screen)

    if is_privileged_exec_prompt(prompt):
        return True

    if is_any_configuration_prompt(prompt):
        screen.Send("end\r")
        crt.Sleep(MODE_TRANSITION_DELAY_MS)
        wait_for_screen_idle(screen)

        prompt = get_prompt(screen)

    if is_privileged_exec_prompt(prompt):
        return True

    if is_any_configuration_prompt(prompt):
        screen.Send(chr(26))
        crt.Sleep(MODE_TRANSITION_DELAY_MS)
        wait_for_screen_idle(screen)

        prompt = get_prompt(screen)

    return is_privileged_exec_prompt(prompt)


def leave_to_exec_mode(screen):
    clear_command_line(screen)

    prompt = get_prompt(screen)

    if is_privileged_exec_prompt(prompt):
        return True

    if is_any_configuration_prompt(prompt):
        screen.Send("end\r")
        crt.Sleep(MODE_TRANSITION_DELAY_MS)
        wait_for_screen_idle(screen)

        prompt = get_prompt(screen)

    if is_any_configuration_prompt(prompt):
        screen.Send(chr(26))
        crt.Sleep(MODE_TRANSITION_DELAY_MS)
        wait_for_screen_idle(screen)

        prompt = get_prompt(screen)

    return is_privileged_exec_prompt(prompt)


def run_normal_command(screen, command):
    clear_command_line(screen)

    screen.Send(command + "\r")

    crt.Sleep(NORMAL_COMMAND_DELAY_MS)
    wait_for_screen_idle(screen)


def clear_command_line(screen):
    screen.Send(chr(3))
    crt.Sleep(AFTER_CANCEL_DELAY_MS)


def wait_for_screen_idle(screen):
    checks = 0

    while checks < MAX_IDLE_CHECKS:
        if not screen.WaitForCursor(IDLE_SECONDS):
            return True

        checks += 1

    return False


# ----------------------------------------------------------------------
# Prompt handling
# ----------------------------------------------------------------------


def is_global_configuration_prompt(prompt):
    return re.search(
        r"\(config\)#$",
        prompt.strip(),
        re.I
    ) is not None


def is_configuration_submode_prompt(prompt):
    if not is_any_configuration_prompt(prompt):
        return False

    return not is_global_configuration_prompt(prompt)


def is_any_configuration_prompt(prompt):
    return re.search(
        r"\(config[^)]*\)#$",
        prompt.strip(),
        re.I
    ) is not None


def is_privileged_exec_prompt(prompt):
    value = prompt.strip()

    if not value.endswith("#"):
        return False

    return not is_any_configuration_prompt(value)


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


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------


def parse_literal_options(text):
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


# ----------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------


def append_profile_header(path, profile_number, profile):
    lines = []

    lines.append("\n")
    lines.append("#" * 110 + "\n")
    lines.append(
        "Profile " + str(profile_number) + ": " +
        profile.get("name", "Unnamed profile") +
        "\n"
    )

    entry_commands = profile.get("entry_commands", [])

    if len(entry_commands) == 0:
        lines.append("Entry: global configuration\n")
    else:
        lines.append("Entry commands:\n")

        for command in entry_commands:
            lines.append("  " + command + "\n")

    crawl_root = profile.get("crawl_root", "").strip()

    if crawl_root == "":
        lines.append("Crawl root: ?\n")
    else:
        lines.append("Crawl root: " + crawl_root + " ?\n")

    cleanup_commands = profile.get(
        "cleanup_commands",
        []
    )

    if len(cleanup_commands) > 0:
        lines.append("Cleanup commands:\n")

        for command in cleanup_commands:
            lines.append("  " + command + "\n")

    lines.append("#" * 110 + "\n")

    append_text(
        path,
        join_lines(lines)
    )


def append_query_section(
    path,
    profile_name,
    query_number,
    depth,
    command,
    captured,
    literal_options,
    placeholders,
    error
):
    lines = []

    if command == "":
        displayed_command = "?"
    else:
        displayed_command = command + " ?"

    lines.append("\n")
    lines.append("=" * 110 + "\n")
    lines.append("Profile: " + profile_name + "\n")
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
        join_lines(lines)
    )


def write_header(path, exec_prompt, profiles):
    lines = []

    lines.append("VOSS Configuration Mode Help Crawl\n")
    lines.append(
        "Generated: " +
        datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ) +
        "\n"
    )
    lines.append("Transport: Serial console\n")
    lines.append("Initial EXEC prompt: " + exec_prompt + "\n")
    lines.append(
        "Profiles enabled: " +
        str(len(profiles)) +
        "\n"
    )
    lines.append(
        "Maximum depth per profile: " +
        str(MAX_DEPTH_PER_MODE) +
        "\n"
    )
    lines.append(
        "Maximum commands per profile: " +
        str(MAX_COMMANDS_PER_MODE) +
        "\n"
    )
    lines.append(
        "Maximum total commands: " +
        str(MAX_TOTAL_COMMANDS) +
        "\n"
    )
    lines.append(
        "Capture method: SecureCRT native session logging\n"
    )
    lines.append(
        "Each profile begins and ends at exact global configuration "
        "mode.\n"
    )
    lines.append(
        "Literal keywords are followed automatically. Dynamic values "
        "are recorded but not invented.\n"
    )
    lines.append(
        "Temporary configuration is not saved.\n"
    )
    lines.append("\n")

    write_text(
        path,
        join_lines(lines)
    )


def append_final_summary(
    path,
    attempted_profiles,
    successful_profiles,
    failed_profiles,
    commands,
    literals,
    placeholders,
    failures
):
    lines = []

    lines.append("\n")
    lines.append("#" * 110 + "\n")
    lines.append("Final Crawl Summary\n")
    lines.append("#" * 110 + "\n")
    lines.append(
        "Profiles attempted: " +
        str(attempted_profiles) +
        "\n"
    )
    lines.append(
        "Successful profiles: " +
        str(successful_profiles) +
        "\n"
    )
    lines.append(
        "Failed profiles: " +
        str(failed_profiles) +
        "\n"
    )
    lines.append(
        "Help commands queried: " +
        str(commands) +
        "\n"
    )
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
        "Failures: " +
        str(failures) +
        "\n"
    )

    append_text(
        path,
        join_lines(lines)
    )


# ----------------------------------------------------------------------
# Text and file helpers
# ----------------------------------------------------------------------


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

    if value.startswith(u"\ufeff"):
        value = value[1:]

    value = apply_backspaces(value)

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
    return re.sub(
        u"^\\s*\\[[^\\]]+\\]\\s*",
        u"",
        line
    )


def join_text_values(values):
    converted = []

    for value in values:
        converted.append(to_text(value))

    return u", ".join(converted)


def join_lines(lines):
    converted = []

    for line in lines:
        converted.append(to_text(line))

    return u"".join(converted)


def read_text_file(path):
    if not os.path.exists(path):
        return to_text("")

    handle = open(path, "rb")

    try:
        data = handle.read()
    finally:
        handle.close()

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
