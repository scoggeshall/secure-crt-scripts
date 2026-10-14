# $language = "python"
# $interface = "1.0"

# VOSS Baseline Build + Verification Discovery Crawler
#
# Intended use:
#   OFFLINE / LAB / DECOMMISSIONED VOSS / Fabric Engine switch.
#
# Purpose:
#   1. Build a small disposable configuration modeled after the production
#      baseline.
#   2. Return to privileged EXEC mode.
#   3. Explore targeted "show ... ?" trees for the features that were built.
#   4. Resolve safe show-command placeholders with the same baseline values.
#   5. Execute read-only show commands when the help tree reaches <cr>.
#   6. Record the command syntax and actual operational output together.
#   7. Attempt cleanup of the disposable objects.
#
# IMPORTANT:
#   This script intentionally changes RUNNING configuration.
#   It NEVER runs "save config".
#   Do not run it on a production switch.
#
# Output:
#   C:\scripts\secure-crt\outputs\baseline-verification\
#
# No external dependencies.

import codecs
import collections
import datetime
import os
import re


SCRIPT_TITLE = "VOSS Baseline Verification Discovery"
OUTPUT_ROOT = r"C:\scripts\secure-crt\outputs\baseline-verification"

TERMINAL_LENGTH = 64

INITIAL_RENDER_DELAY_MS = 150
AFTER_CANCEL_DELAY_MS = 100
BETWEEN_QUERY_DELAY_MS = 75
NORMAL_COMMAND_DELAY_MS = 350
MODE_TRANSITION_DELAY_MS = 400

IDLE_SECONDS = 1
MAX_IDLE_CHECKS = 180

MAX_SHOW_DEPTH = 6
MAX_SHOW_COMMANDS_PER_FEATURE = 300
MAX_TOTAL_SHOW_COMMANDS = 2500
MAX_COMMAND_TOKENS = 18
MAX_PLACEHOLDER_BRANCHES_PER_QUERY = 3

# Physical-port / MLT testing is intentionally disabled by default because
# changing a real port is more disruptive than creating disposable L3 objects.
ENABLE_PHYSICAL_MLT_TEST = False


# ----------------------------------------------------------------------
# Disposable baseline values
# ----------------------------------------------------------------------
#
# These values are intentionally documentation/test ranges and high VLAN IDs.
# Review them before every run.
#

BASELINE = {
    "loopback_id": "99",
    "loopback_ip": "192.0.2.99",

    "ospf_area": "0.0.0.255",

    "client_vlan_id": "3901",
    "client_vlan_name": "CRAWL-CLIENT",
    "client_gateway": "198.51.100.1",
    "client_mask": "255.255.255.0",

    "transit_vlan_id": "3902",
    "transit_vlan_name": "CRAWL-TRANSIT",
    "transit_ip": "198.51.101.1",
    "transit_mask": "255.255.255.252",

    "multicast_vlan_id": "3903",
    "multicast_vlan_name": "CRAWL-MCAST",
    "multicast_ip": "198.51.102.1",
    "multicast_mask": "255.255.255.0",

    "dhcp_server_1": "192.0.2.10",
    "dhcp_server_2": "192.0.2.11",

    "pim_rp": "192.0.2.254",
    "multicast_group": "239.255.0.0/16",

    "acl_id": "3901",
    "acl_ace": "10",

    "mlt_id": "99",
    "lacp_key": "99",
    "port_1": "1/1",
    "port_2": "1/2",
}


# ----------------------------------------------------------------------
# Baseline configuration sections
# ----------------------------------------------------------------------


def build_configuration_sections():
    b = BASELINE

    sections = [
        {
            "name": "IPv4 Routing",
            "commands": [
                "ip routing",
            ],
        },
        {
            "name": "OSPF Process",
            "commands": [
                "router ospf enable",
                "router ospf",
                "router-id " + b["loopback_ip"],
                "area " + b["ospf_area"],
                "exit",
            ],
        },
        {
            "name": "Loopback",
            "commands": [
                "interface loopback " + b["loopback_id"],
                "ip address " + b["loopback_id"] + " " +
                b["loopback_ip"] + "/32",
                "ip area " + b["loopback_id"] + " " + b["ospf_area"],
                "ip ospf " + b["loopback_id"],
                "exit",
            ],
        },
        {
            "name": "Client VLAN",
            "commands": [
                "vlan create " + b["client_vlan_id"] +
                ' name "' + b["client_vlan_name"] +
                '" type port-mstprstp 0',

                "interface vlan " + b["client_vlan_id"],
                "ip address " + b["client_gateway"] + " " + b["client_mask"],
                "ip dhcp-relay",
                "ip ospf area " + b["ospf_area"],
                "ip ospf network passive",
                "ip ospf enable",
                "exit",
            ],
        },
        {
            "name": "DHCP Relay",
            "commands": [
                "ip dhcp-relay fwd-path " +
                b["client_gateway"] + " " + b["dhcp_server_1"],
                "ip dhcp-relay fwd-path " +
                b["client_gateway"] + " " + b["dhcp_server_1"] + " enable",
                "ip dhcp-relay fwd-path " +
                b["client_gateway"] + " " + b["dhcp_server_1"] +
                " mode bootp_dhcp",

                "ip dhcp-relay fwd-path " +
                b["client_gateway"] + " " + b["dhcp_server_2"],
                "ip dhcp-relay fwd-path " +
                b["client_gateway"] + " " + b["dhcp_server_2"] + " enable",
                "ip dhcp-relay fwd-path " +
                b["client_gateway"] + " " + b["dhcp_server_2"] +
                " mode bootp_dhcp",
            ],
        },
        {
            "name": "Transit VLAN",
            "commands": [
                "vlan create " + b["transit_vlan_id"] +
                ' name "' + b["transit_vlan_name"] +
                '" type port-mstprstp 0',

                "interface vlan " + b["transit_vlan_id"],
                "ip address " + b["transit_ip"] + " " + b["transit_mask"],
                "ip ospf area " + b["ospf_area"],
                "ip ospf network broadcast",
                "ip ospf enable",
                "ip pim enable",
                "exit",
            ],
        },
        {
            "name": "PIM",
            "commands": [
                "ip pim enable",
                "ip pim mode sparse",
                "ip pim static-rp " + b["multicast_group"] + " " + b["pim_rp"],
            ],
        },
        {
            "name": "Multicast VLAN",
            "commands": [
                "vlan create " + b["multicast_vlan_id"] +
                ' name "' + b["multicast_vlan_name"] +
                '" type port-mstprstp 0',

                "interface vlan " + b["multicast_vlan_id"],
                "ip address " + b["multicast_ip"] + " " + b["multicast_mask"],
                "ip pim enable",
                "exit",
            ],
        },
        {
            "name": "Test ACL",
            "commands": [
                "filter acl " + b["acl_id"] +
                ' type inVlan name "CRAWL-ACL"',
                "filter acl ace " + b["acl_id"] + " " + b["acl_ace"] +
                ' name "CRAWL-PERMIT"',
                "filter acl ace action " + b["acl_id"] + " " +
                b["acl_ace"] + " permit",
                "filter acl ace ethernet " + b["acl_id"] + " " +
                b["acl_ace"] + " ether-type eq ip",
                "filter acl ace " + b["acl_id"] + " " +
                b["acl_ace"] + " enable",
            ],
        },
    ]

    if ENABLE_PHYSICAL_MLT_TEST:
        sections.append(
            {
                "name": "Physical MLT and LACP",
                "commands": [
                    "interface gigabitEthernet " +
                    b["port_1"] + "," + b["port_2"],
                    "no auto-sense enable",
                    "no lacp enable",
                    "encapsulation dot1q",
                    "default-vlan-id 0",
                    "no shutdown",
                    "exit",

                    "mlt " + b["mlt_id"],
                    "mlt " + b["mlt_id"] + ' name "CRAWL-MLT"',
                    "mlt " + b["mlt_id"] + " encapsulation dot1q",
                    "mlt " + b["mlt_id"] + " vlan " + b["client_vlan_id"],
                    "mlt " + b["mlt_id"] + " vlan " + b["multicast_vlan_id"],
                    "mlt " + b["mlt_id"] + " enable",

                    "lacp enable",

                    "interface mlt " + b["mlt_id"],
                    "lacp key " + b["lacp_key"],
                    "lacp enable",
                    "exit",
                ],
            }
        )

    return sections


# ----------------------------------------------------------------------
# Verification discovery seeds
# ----------------------------------------------------------------------
#
# These are deliberately broad. The actual device parser decides what exists.
# The crawler uses ? beneath each seed and executes only completed show paths.
#

SHOW_FEATURES = [
    {
        "name": "System / Running Configuration",
        "roots": [
            "show running-config",
            "show sys-info",
        ],
    },
    {
        "name": "VLANs",
        "roots": [
            "show vlan",
        ],
    },
    {
        "name": "Interfaces",
        "roots": [
            "show interfaces",
            "show ip interface",
        ],
    },
    {
        "name": "OSPF",
        "roots": [
            "show ip ospf",
        ],
    },
    {
        "name": "DHCP Relay",
        "roots": [
            "show ip dhcp-relay",
        ],
    },
    {
        "name": "PIM",
        "roots": [
            "show ip pim",
        ],
    },
    {
        "name": "ACL / Filters",
        "roots": [
            "show filter",
        ],
    },
    {
        "name": "MLT",
        "roots": [
            "show mlt",
        ],
        "enabled": ENABLE_PHYSICAL_MLT_TEST,
    },
    {
        "name": "LACP",
        "roots": [
            "show lacp",
        ],
        "enabled": ENABLE_PHYSICAL_MLT_TEST,
    },
]


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def Main():
    tab = crt.GetScriptTab()

    if not tab.Session.Connected:
        crt.Dialog.MessageBox(
            "Not connected.\n\n"
            "Connect to an OFFLINE/LAB VOSS device first.",
            SCRIPT_TITLE
        )
        return

    screen = tab.Screen
    session = tab.Session

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

    preview = build_confirmation_preview()

    confirmation = crt.Dialog.Prompt(
        "WARNING: THIS SCRIPT MODIFIES RUNNING CONFIGURATION.\n\n"
        "Use only on an offline, lab, or decommissioned VOSS switch.\n\n"
        "The script will:\n"
        "  1. Build disposable baseline objects\n"
        "  2. Never save the configuration\n"
        "  3. Explore targeted show-command syntax\n"
        "  4. Execute completed read-only show commands\n"
        "  5. Attempt cleanup\n\n"
        + preview +
        "\n\nType BUILDVERIFY to continue.",
        SCRIPT_TITLE,
        "",
        False
    )

    if confirmation is None:
        return

    if confirmation.strip().upper() != "BUILDVERIFY":
        crt.Dialog.MessageBox("Canceled.", SCRIPT_TITLE)
        return

    ensure_directory(OUTPUT_ROOT)

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    output_path = os.path.join(
        OUTPUT_ROOT,
        timestamp + "_" +
        sanitize_filename(hostname) +
        "_baseline-verification.txt"
    )

    previous_logging = session.Logging
    previous_log_file = session.LogFileName

    config_failures = 0
    show_help_queries = 0
    show_commands_executed = 0
    show_failures = 0
    cleanup_failures = 0

    try:
        if session.Logging:
            session.Log(False)

        write_header(output_path, prompt)

        if not ensure_exec_mode(screen):
            raise Exception("Could not reach privileged EXEC mode.")

        capture_enter_command(
            screen,
            session,
            "terminal length " + str(TERMINAL_LENGTH),
            output_path,
            "SESSION PREPARATION"
        )

        if not ensure_global_config_mode(screen):
            raise Exception("Could not reach global configuration mode.")

        sections = build_configuration_sections()

        for section in sections:
            append_text(
                output_path,
                "\n" + "#" * 110 + "\n"
                "CONFIGURE: " + section["name"] + "\n"
                + "#" * 110 + "\n"
            )

            for command in section["commands"]:
                output = capture_enter_command(
                    screen,
                    session,
                    command,
                    output_path,
                    "CONFIG"
                )

                if output_indicates_error(output):
                    config_failures += 1

                    append_text(
                        output_path,
                        "CONFIG RESULT: POSSIBLE ERROR\n"
                    )

                else:
                    append_text(
                        output_path,
                        "CONFIG RESULT: ACCEPTED/NO PARSED ERROR\n"
                    )

        if not ensure_exec_mode(screen):
            raise Exception(
                "Configuration was applied, but privileged EXEC mode "
                "could not be restored for verification."
            )

        append_text(
            output_path,
            "\n" + "#" * 110 + "\n"
            "VERIFICATION DISCOVERY\n"
            + "#" * 110 + "\n"
        )

        for feature in SHOW_FEATURES:
            if feature.get("enabled", True) is False:
                continue

            results = crawl_show_feature(
                screen,
                session,
                feature,
                output_path,
                MAX_TOTAL_SHOW_COMMANDS - show_help_queries
            )

            show_help_queries += results["help_queries"]
            show_commands_executed += results["executed"]
            show_failures += results["failures"]

            if show_help_queries >= MAX_TOTAL_SHOW_COMMANDS:
                append_text(
                    output_path,
                    "\nSTOPPED: Maximum total show-help queries reached.\n"
                )
                break

        append_text(
            output_path,
            "\n" + "#" * 110 + "\n"
            "CLEANUP\n"
            + "#" * 110 + "\n"
        )

        cleanup_failures = cleanup_disposable_configuration(
            screen,
            session,
            output_path
        )

        append_final_summary(
            output_path,
            config_failures,
            show_help_queries,
            show_commands_executed,
            show_failures,
            cleanup_failures
        )

    except Exception as exc:
        append_text(
            output_path,
            "\nFATAL ERROR: " + to_text(exc) + "\n"
        )

        try:
            if session.Logging:
                session.Log(False)
        except Exception:
            pass

        try:
            cleanup_failures += cleanup_disposable_configuration(
                screen,
                session,
                output_path
            )
        except Exception:
            cleanup_failures += 1

    finally:
        try:
            if session.Logging:
                session.Log(False)
        except Exception:
            pass

        ensure_exec_mode(screen)

        try:
            session.LogFileName = previous_log_file
        except Exception:
            pass

        if previous_logging and previous_log_file != "":
            try:
                session.Log(True, True, False)
            except Exception:
                pass

    crt.Dialog.MessageBox(
        "Baseline verification discovery complete.\n\n"
        "Configuration commands with possible errors: " +
        str(config_failures) + "\n"
        "Show help queries: " + str(show_help_queries) + "\n"
        "Completed show commands executed: " +
        str(show_commands_executed) + "\n"
        "Show failures: " + str(show_failures) + "\n"
        "Cleanup failures: " + str(cleanup_failures) + "\n\n"
        "The configuration was NOT saved.\n\n"
        "Output file:\n" + output_path,
        SCRIPT_TITLE
    )


# ----------------------------------------------------------------------
# Show discovery
# ----------------------------------------------------------------------


def crawl_show_feature(
    screen,
    session,
    feature,
    output_path,
    remaining_total
):
    append_text(
        output_path,
        "\n" + "=" * 110 + "\n"
        "VERIFY FEATURE: " + feature["name"] + "\n"
        + "=" * 110 + "\n"
    )

    queue = collections.deque()

    for root in feature.get("roots", []):
        queue.append(
            {
                "command": root,
                "depth": 1,
            }
        )

    visited_help = set()
    executed = set()

    help_queries = 0
    execute_count = 0
    failures = 0

    while len(queue) > 0:
        if help_queries >= MAX_SHOW_COMMANDS_PER_FEATURE:
            append_text(
                output_path,
                "FEATURE STATUS: PARTIAL - feature query limit reached.\n"
            )
            break

        if help_queries >= remaining_total:
            break

        item = queue.popleft()

        command = item["command"].strip()
        depth = item["depth"]
        key = command.lower()

        if key in visited_help:
            continue

        visited_help.add(key)
        help_queries += 1

        try:
            captured = capture_question_mark(
                screen,
                session,
                command,
                output_path
            )

            parsed = parse_help(captured)

            append_show_help_result(
                output_path,
                feature["name"],
                help_queries,
                depth,
                command,
                parsed
            )

            if parsed["has_cr"] and key not in executed:
                executed.add(key)

                actual_output = capture_enter_command(
                    screen,
                    session,
                    command,
                    output_path,
                    "SHOW EXECUTE"
                )

                execute_count += 1

                append_text(
                    output_path,
                    "EXECUTED SHOW COMMAND: " + command + "\n"
                )

                if output_indicates_error(actual_output):
                    failures += 1
                    append_text(
                        output_path,
                        "SHOW RESULT: POSSIBLE ERROR\n"
                    )
                else:
                    append_text(
                        output_path,
                        "SHOW RESULT: COMPLETED\n"
                    )

            if depth >= MAX_SHOW_DEPTH:
                continue

            for literal in parsed["literals"]:
                child = join_command(command, literal)

                if count_tokens(child) > MAX_COMMAND_TOKENS:
                    continue

                if child.lower() not in visited_help:
                    queue.append(
                        {
                            "command": child,
                            "depth": depth + 1,
                        }
                    )

            placeholder_branches = 0

            for placeholder in parsed["placeholders"]:
                if placeholder_branches >= MAX_PLACEHOLDER_BRANCHES_PER_QUERY:
                    break

                value = resolve_show_placeholder(
                    placeholder,
                    command,
                    feature["name"]
                )

                if value == "":
                    continue

                child = join_command(command, value)

                if count_tokens(child) > MAX_COMMAND_TOKENS:
                    continue

                if child.lower() not in visited_help:
                    queue.append(
                        {
                            "command": child,
                            "depth": depth + 1,
                        }
                    )

                    placeholder_branches += 1

        except Exception as exc:
            failures += 1

            append_text(
                output_path,
                "SHOW DISCOVERY ERROR: " + to_text(exc) + "\n"
            )

            clear_command_line(screen)

    return {
        "help_queries": help_queries,
        "executed": execute_count,
        "failures": failures,
    }


def resolve_show_placeholder(token, command, feature_name):
    value = normalize_placeholder(token)
    command_lower = command.lower()
    feature_lower = feature_name.lower()

    numeric = numeric_range_example(value)

    if numeric != "":
        # Prefer actual configured IDs when the context is identifiable.
        if "vlan" in command_lower or "vlan" in feature_lower:
            return BASELINE["client_vlan_id"]

        if "mlt" in command_lower or "mlt" in feature_lower:
            return BASELINE["mlt_id"]

        if "filter" in command_lower or "acl" in feature_lower:
            return BASELINE["acl_id"]

        return numeric

    if "vlan" in value:
        return BASELINE["client_vlan_id"]

    if "interface" in value or "port" in value:
        return BASELINE["port_1"]

    if "mlt" in value:
        return BASELINE["mlt_id"]

    if "acl" in value or "filter" in value:
        return BASELINE["acl_id"]

    if "area" in value:
        return BASELINE["ospf_area"]

    if "vrid" in value:
        return "1"

    if "ip" in value or "address" in value:
        if "ospf" in command_lower:
            return BASELINE["loopback_ip"]

        if "dhcp" in command_lower:
            return BASELINE["client_gateway"]

        if "pim" in command_lower:
            return BASELINE["pim_rp"]

        return BASELINE["loopback_ip"]

    if "word" in value or "name" in value:
        if "vlan" in command_lower:
            return BASELINE["client_vlan_name"]

    return ""


# ----------------------------------------------------------------------
# Help parsing
# ----------------------------------------------------------------------


def parse_help(text):
    literals = []
    placeholders = []
    enumerated = []
    formatted = []
    has_cr = False

    for original_line in normalize_capture(text).split(u"\n"):
        line = remove_log_prefix(original_line)
        stripped = line.strip()

        if stripped == u"":
            continue

        if stripped == u"<cr>" or stripped.startswith(u"<cr>"):
            has_cr = True
            continue

        if re.search(u"[>#]\\s*$", stripped):
            continue

        if stripped.endswith(u"?"):
            continue

        match = re.match(
            u"^\\s{2,}(\\S+(?:\\s+\\S+){0,5}?)\\s{2,}\\S.*$",
            line
        )

        if not match:
            continue

        token = match.group(1).strip()

        first = token.split()[0]

        if is_literal(first):
            if first not in literals:
                literals.append(first)
            continue

        if is_enumerated(first):
            if first not in enumerated:
                enumerated.append(first)
            continue

        if is_placeholder(first):
            if first not in placeholders:
                placeholders.append(first)
            continue

        if looks_formatted_value(token):
            if token not in formatted:
                formatted.append(token)

    return {
        "literals": literals,
        "placeholders": placeholders,
        "enumerated": enumerated,
        "formatted": formatted,
        "has_cr": has_cr,
    }


def is_literal(token):
    return re.match(
        u"^[a-z][a-z0-9_.:/-]*$",
        token
    ) is not None


def is_enumerated(token):
    if re.match(u"^0x[0-9A-Fa-f]+$", token):
        return True

    if re.match(u"^[0-9]+$", token):
        return True

    return False


def is_placeholder(token):
    if token.startswith((u"<", u"{", u"[", u"|")):
        return True

    if token.upper() == token and re.search(u"[A-Z]", token):
        return True

    if re.match(u"^WORD<[^>]+>$", token, re.I):
        return True

    return False


def looks_formatted_value(token):
    if u"xxxx" in token.lower():
        return True

    if re.search(u"x\\.x", token.lower()):
        return True

    if u"...xxxx" in token.lower():
        return True

    return False


def append_show_help_result(
    path,
    feature_name,
    number,
    depth,
    command,
    parsed
):
    lines = []

    lines.append("\n")
    lines.append("-" * 110 + "\n")
    lines.append("Feature: " + feature_name + "\n")
    lines.append("Help Query: " + str(number) + "\n")
    lines.append("Depth: " + str(depth) + "\n")
    lines.append("Command: " + command + " ?\n")
    lines.append("Complete command (<cr>): " + str(parsed["has_cr"]) + "\n")

    if len(parsed["literals"]) > 0:
        lines.append(
            "Literal children: " +
            join_values(parsed["literals"]) +
            "\n"
        )

    if len(parsed["placeholders"]) > 0:
        lines.append(
            "Placeholders: " +
            join_values(parsed["placeholders"]) +
            "\n"
        )

    if len(parsed["enumerated"]) > 0:
        lines.append(
            "Enumerated values: " +
            join_values(parsed["enumerated"]) +
            "\n"
        )

    if len(parsed["formatted"]) > 0:
        lines.append(
            "Formatted values: " +
            join_values(parsed["formatted"]) +
            "\n"
        )

    append_text(path, u"".join(lines))


# ----------------------------------------------------------------------
# Cleanup
# ----------------------------------------------------------------------


def cleanup_disposable_configuration(screen, session, output_path):
    failures = 0
    b = BASELINE

    if not ensure_global_config_mode(screen):
        append_text(
            output_path,
            "Cleanup failed: could not reach global configuration mode.\n"
        )
        return 1

    cleanup_groups = []

    if ENABLE_PHYSICAL_MLT_TEST:
        cleanup_groups.extend(
            [
                "no mlt " + b["mlt_id"],
            ]
        )

    cleanup_groups.extend(
        [
            "no filter acl " + b["acl_id"],

            "vlan delete " + b["multicast_vlan_id"],
            "vlan delete " + b["transit_vlan_id"],
            "vlan delete " + b["client_vlan_id"],

            "no interface loopback " + b["loopback_id"],

            "router ospf",
            "no area " + b["ospf_area"],
            "exit",
        ]
    )

    for command in cleanup_groups:
        output = capture_enter_command(
            screen,
            session,
            command,
            output_path,
            "CLEANUP"
        )

        if output_indicates_error(output):
            failures += 1

            append_text(
                output_path,
                "CLEANUP RESULT: POSSIBLE ERROR\n"
            )

        else:
            append_text(
                output_path,
                "CLEANUP RESULT: ACCEPTED/NO PARSED ERROR\n"
            )

    ensure_exec_mode(screen)

    return failures


# ----------------------------------------------------------------------
# Command capture and mode handling
# ----------------------------------------------------------------------


def capture_question_mark(screen, session, command, output_path):
    clear_command_line(screen)

    append_text(
        output_path,
        "\nHELP QUERY: " + command + " ?\n"
    )

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

    return normalize_capture(
        read_file_from_offset(output_path, start)
    )


def capture_enter_command(
    screen,
    session,
    command,
    output_path,
    phase
):
    clear_command_line(screen)

    append_text(
        output_path,
        "\n[" + phase + "] " + command + "\n"
    )

    start = get_file_size(output_path)

    session.LogFileName = output_path
    session.Log(True, True, False)

    screen.Send(command + "\r")

    crt.Sleep(NORMAL_COMMAND_DELAY_MS)
    wait_for_screen_idle(screen)

    session.Log(False)

    return normalize_capture(
        read_file_from_offset(output_path, start)
    )


def ensure_exec_mode(screen):
    clear_command_line(screen)

    prompt = get_prompt(screen)

    if is_privileged_exec(prompt):
        return True

    if is_config_prompt(prompt):
        screen.Send("end\r")
        crt.Sleep(MODE_TRANSITION_DELAY_MS)
        wait_for_screen_idle(screen)

        prompt = get_prompt(screen)

    if is_privileged_exec(prompt):
        return True

    if is_user_exec(prompt):
        screen.Send("enable\r")
        crt.Sleep(MODE_TRANSITION_DELAY_MS)
        wait_for_screen_idle(screen)

        prompt = get_prompt(screen)

    return is_privileged_exec(prompt)


def ensure_global_config_mode(screen):
    clear_command_line(screen)

    prompt = get_prompt(screen)

    if is_global_config(prompt):
        return True

    attempts = 0

    while is_config_submode(prompt) and attempts < 15:
        screen.Send("exit\r")
        crt.Sleep(MODE_TRANSITION_DELAY_MS)
        wait_for_screen_idle(screen)

        prompt = get_prompt(screen)

        if is_global_config(prompt):
            return True

        attempts += 1

    if is_privileged_exec(prompt):
        screen.Send("configure terminal\r")
        crt.Sleep(MODE_TRANSITION_DELAY_MS)
        wait_for_screen_idle(screen)

        return is_global_config(get_prompt(screen))

    if is_user_exec(prompt):
        screen.Send("enable\r")
        crt.Sleep(MODE_TRANSITION_DELAY_MS)
        wait_for_screen_idle(screen)

        if is_privileged_exec(get_prompt(screen)):
            screen.Send("configure terminal\r")
            crt.Sleep(MODE_TRANSITION_DELAY_MS)
            wait_for_screen_idle(screen)

            return is_global_config(get_prompt(screen))

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


def is_user_exec(prompt):
    value = prompt.strip()

    if not value.endswith(">"):
        return False

    return "(config" not in value.lower()


def is_privileged_exec(prompt):
    value = prompt.strip()

    if not value.endswith("#"):
        return False

    return "(config" not in value.lower()


def is_config_prompt(prompt):
    return re.search(
        r"\(config[^)]*\)#$",
        prompt.strip(),
        re.I
    ) is not None


def is_global_config(prompt):
    return re.search(
        r"\(config\)#$",
        prompt.strip(),
        re.I
    ) is not None


def is_config_submode(prompt):
    return (
        is_config_prompt(prompt) and
        not is_global_config(prompt)
    )


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
# Misc helpers
# ----------------------------------------------------------------------


def output_indicates_error(text):
    value = normalize_capture(text).lower()

    markers = [
        "% invalid input",
        "invalid input detected",
        "% incomplete command",
        "error:",
        "failed",
        "does not exist",
        "not found",
    ]

    for marker in markers:
        if marker in value:
            return True

    return False


def normalize_placeholder(token):
    value = to_text(token).strip()
    value = value.strip("<>{}[]|")
    return value.lower()


def numeric_range_example(value):
    match = re.match(r"^(\d+)-(\d+)$", value)

    if not match:
        return ""

    low = int(match.group(1))
    high = int(match.group(2))

    if low <= 1 <= high:
        return "1"

    return str(low)


def join_command(parent, child):
    if parent.strip() == "":
        return child

    return parent.strip() + " " + child


def count_tokens(command):
    return len(command.strip().split())


def normalize_capture(text):
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
        return data.decode("utf-8-sig")
    except Exception:
        pass

    try:
        return data.decode("cp1252")
    except Exception:
        pass

    return data.decode("latin-1", "replace")


def sanitize_filename(value):
    value = to_text(value).strip()

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
    return u", ".join([to_text(value) for value in values])


def build_confirmation_preview():
    b = BASELINE

    lines = []

    lines.append("Disposable values:\n")
    lines.append(
        "  Loopback: " + b["loopback_id"] +
        " / " + b["loopback_ip"] + "/32\n"
    )
    lines.append(
        "  Client VLAN: " + b["client_vlan_id"] +
        " (" + b["client_vlan_name"] + ")\n"
    )
    lines.append(
        "  Transit VLAN: " + b["transit_vlan_id"] +
        " (" + b["transit_vlan_name"] + ")\n"
    )
    lines.append(
        "  Multicast VLAN: " + b["multicast_vlan_id"] +
        " (" + b["multicast_vlan_name"] + ")\n"
    )
    lines.append(
        "  OSPF area: " + b["ospf_area"] + "\n"
    )
    lines.append(
        "  ACL: " + b["acl_id"] + "\n"
    )
    lines.append(
        "  Physical/MLT test enabled: " +
        str(ENABLE_PHYSICAL_MLT_TEST) + "\n"
    )

    return "".join(lines)


def write_header(path, prompt):
    lines = []

    lines.append("VOSS Baseline Build + Verification Discovery\n")
    lines.append(
        "Generated: " +
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") +
        "\n"
    )
    lines.append("Initial prompt: " + prompt + "\n")
    lines.append("Configuration saved: NO\n")
    lines.append(
        "Physical/MLT test enabled: " +
        str(ENABLE_PHYSICAL_MLT_TEST) +
        "\n"
    )
    lines.append("\n")

    write_text(path, "".join(lines))


def append_final_summary(
    path,
    config_failures,
    help_queries,
    executed,
    show_failures,
    cleanup_failures
):
    lines = []

    lines.append("\n")
    lines.append("#" * 110 + "\n")
    lines.append("FINAL SUMMARY\n")
    lines.append("#" * 110 + "\n")
    lines.append(
        "Configuration commands with possible errors: " +
        str(config_failures) +
        "\n"
    )
    lines.append(
        "Show help queries: " +
        str(help_queries) +
        "\n"
    )
    lines.append(
        "Completed show commands executed: " +
        str(executed) +
        "\n"
    )
    lines.append(
        "Show failures: " +
        str(show_failures) +
        "\n"
    )
    lines.append(
        "Cleanup failures: " +
        str(cleanup_failures) +
        "\n"
    )
    lines.append("Configuration saved: NO\n")

    append_text(path, "".join(lines))


Main()
