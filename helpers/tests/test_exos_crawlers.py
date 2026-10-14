# Fixture-based tests for the EXOS crawlers. Run from the repository root:
#   python3 -m unittest discover -s helpers/tests -v
#
# ALL fixtures and the fake SecureCRT/CLI objects here are SYNTHETIC. They are
# not captures from a live EXOS device and do not validate real EXOS output or
# the SecureCRT runtime. See helpers/README-exos-crawler-suite.md.
import collections
import os
import shutil
import tempfile
import unittest

HELPERS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = ["exos-show-help-crawler.py", "exos-config-help-crawler.py", "exos-config-mode-crawler.py"]

HELP_FIXTURE = u"""X460G2.1 # show vlan ?
  <vlan_name>          Specify a VLAN name
  <vlanid>             Specify a VLAN tag
  detail               Display detailed information
  stpd                 Show VLANs in an STPD
  VR-NAME              Virtual router
  ports                Show ports
  vlanName             Camel-case dynamic value
  <cr>                 Execute the command
* X460G2.1 # show vlan
X460G2.1 # """

ERROR_FIXTURE = u"X460G2.1 # show bogus ?\r\n%% Invalid input detected at '^' marker.\r\n"
SHOW_MGMT_ENABLED = u"CLI Paging             : Enabled (this session only)\r\nCLI scripting          : Disabled\r\n"
SHOW_MGMT_DISABLED = u"CLI paging: Disabled\r\n"
SHOW_VERSION = (u"Switch      : 800482-00-04 1340G-01234 Rev 4.0 BootROM: 2.0.1.5   IMG: 31.7.1.4\r\n"
                u"Image   : ExtremeXOS version 31.7.1.4 by release-manager\r\n")
SHOW_SWITCH = u"System Type:      X460G2-24p-10G4\r\n"


class FakeScreen(object):
    Columns = 120
    CurrentRow = 1

    def __init__(self, idle=True):
        self.sent = []
        self.idle = idle
        self.Synchronous = True
        self.IgnoreEscape = False

    def Send(self, text):
        self.sent.append(text)

    def WaitForCursor(self, seconds):
        return not self.idle  # False means the screen went idle

    def Get(self, r1, c1, r2, c2):
        return "X460G2.1 # "


class FakeSession(object):
    Connected = True
    Logging = False
    LogFileName = ""

    def Log(self, *args):
        pass


class FakeDialog(object):
    def __init__(self, answer="OK", message_box=6):
        self.answer = answer
        self.message_box = message_box
        self.boxes = []

    def Prompt(self, *args):
        return self.answer

    def MessageBox(self, text, title="", flags=0):
        self.boxes.append(text)
        return self.message_box


class FakeCrt(object):
    def __init__(self, screen, dialog):
        self.screen = screen
        self.session = FakeSession()
        self.Dialog = dialog

    def GetScriptTab(self):
        tab = type("Tab", (), {})()
        tab.Screen = self.screen
        tab.Session = self.session
        return tab

    def Sleep(self, ms):
        pass


def load(name, fake_crt=None):
    with open(os.path.join(HELPERS, name)) as handle:
        source = handle.read()
    assert source.rstrip().endswith("Main()")
    source = source.rstrip()[:-len("Main()")]
    ns = {"crt": fake_crt or FakeCrt(FakeScreen(), FakeDialog())}
    exec(compile(source, name, "exec"), ns)
    return ns


class AllScripts(object):
    script = None

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "out.txt")
        self.screen = FakeScreen()
        self.dialog = FakeDialog(answer=None)
        self.crt = FakeCrt(self.screen, self.dialog)
        self.ns = load(self.script, self.crt)

    def tearDown(self):
        os.environ.pop("EXOS_CRAWLER_OUTPUT_ROOT", None)
        shutil.rmtree(self.tmp)

    def read(self):
        with open(self.out, "rb") as handle:
            return handle.read().decode("utf-8")

    # ---- parser classification ----
    def test_parse_classification(self):
        literals, placeholders = self.ns["parse_help_entries"](HELP_FIXTURE)
        self.assertEqual(literals, ["detail", "stpd", "ports"])
        self.assertEqual(placeholders, ["<vlan_name>", "<vlanid>", "VR-NAME", "vlanName"])

    def test_end_marker_and_prompt_lines_ignored(self):
        literals, placeholders = self.ns["parse_help_entries"](HELP_FIXTURE)
        self.assertNotIn("<cr>", placeholders)
        self.assertFalse([x for x in literals if x.startswith("*")])

    def test_empty_and_garbage_output(self):
        for text in (u"", u"\r\n\r\n", u"random single line"):
            self.assertEqual(self.ns["parse_help_entries"](text), ([], []))

    def test_error_response_classified(self):
        self.assertEqual(self.ns["classify_help_response"](ERROR_FIXTURE), "error")
        self.assertEqual(self.ns["classify_help_response"](u"Incomplete command"), "error")
        self.assertEqual(self.ns["classify_help_response"](HELP_FIXTURE), "ok")

    def test_ansi_and_log_prefix_normalized(self):
        text = u"[2026-01-01 00:00:00]   detail      Show detail\x1b[0m\r\n"
        self.assertEqual(self.ns["parse_help_entries"](text), (["detail"], []))

    # ---- duplicate queue prevention ----
    def test_enqueue_dedupes_case_insensitively(self):
        queue, queued = collections.deque(), set()
        enqueue = self.ns["enqueue_command"]
        self.assertTrue(enqueue(queue, queued, "show vlan", 2))
        self.assertFalse(enqueue(queue, queued, "SHOW VLAN ", 3))
        self.assertEqual(len(queue), 1)

    # ---- timeouts ----
    def test_incomplete_query_not_parsed_or_enqueued(self):
        ns = self.ns
        ns["append_text"](self.out, "")
        ns["capture_help_query"] = lambda *a: (HELP_FIXTURE, False)
        queue, queued, stats = collections.deque(), set(), ns["new_stats"]()
        self._process(queue, queued, stats)
        self.assertEqual(stats["incomplete"], 1)
        self.assertEqual(len(queue), 0)
        self.assertEqual(stats["literals"], 0)
        self.assertIn("INCOMPLETE QUERY", self.read())

    def test_error_response_not_enqueued(self):
        ns = self.ns
        ns["capture_help_query"] = lambda *a: (ERROR_FIXTURE, True)
        queue, queued, stats = collections.deque(), set(), ns["new_stats"]()
        self._process(queue, queued, stats)
        self.assertEqual(stats["errors"], 1)
        self.assertEqual(len(queue), 0)

    def test_complete_query_enqueues_children_once(self):
        ns = self.ns
        ns["capture_help_query"] = lambda *a: (HELP_FIXTURE, True)
        queue, queued, stats = collections.deque(), set(), ns["new_stats"]()
        self._process(queue, queued, stats)
        self._process(queue, queued, stats)
        commands = [q["command"] for q in queue]
        self.assertEqual(len(commands), len(set(c.lower() for c in commands)))
        self.assertTrue([c for c in commands if c.lower().endswith(" vlan detail")])
        self.assertTrue(stats["duplicates"] >= 1)

    def test_capture_reports_timeout_and_sends_only_question_mark(self):
        ns = self.ns
        ns["MAX_IDLE_CHECKS"] = 2
        self.screen.idle = False  # cursor never goes idle
        open(self.out, "wb").close()
        text, complete = ns["capture_help_query"](self.screen, self.crt.session, "show vlan", self.out)
        self.assertFalse(complete)
        self.assertIn("show vlan ?", self.screen.sent)
        self.assertFalse([s for s in self.screen.sent if "\r" in s])

    def test_capture_complete_when_idle(self):
        open(self.out, "wb").close()
        text, complete = self.ns["capture_help_query"](self.screen, self.crt.session, "show vlan", self.out)
        self.assertTrue(complete)

    # ---- paging state / metadata ----
    def test_parse_paging_state(self):
        p = self.ns["parse_paging_state"]
        self.assertIs(p(SHOW_MGMT_ENABLED), True)
        self.assertIs(p(SHOW_MGMT_DISABLED), False)
        self.assertIsNone(p(u"nothing useful"))

    def test_parse_platform_metadata(self):
        items = dict(self.ns["parse_platform_metadata"](SHOW_VERSION, SHOW_SWITCH))
        self.assertEqual(items["EXOS version"], "ExtremeXOS 31.7.1.4")
        self.assertEqual(items["System type"], "X460G2-24p-10G4")

    # ---- paging lifecycle (scripted fake CLI; synthetic, not EXOS output) ----
    def run_main(self, mgmt_text, responses=None, crawl_exc=None, answer_yes=True):
        """Run Main() with capture_readonly_command and the crawl replaced by
        recorders. responses maps a command to "timeout" or an Exception to raise."""
        ns = self.ns
        responses = responses or {}
        self.order = []
        self.dialog.answer = ns.get("CONFIRMATION", "CONTEXTCRAWL")
        self.dialog.message_box = 6 if answer_yes else 7
        os.environ["EXOS_CRAWLER_OUTPUT_ROOT"] = self.tmp

        def readonly(screen, session, command, path):
            self.order.append(command)
            outcome = responses.get(command)
            if isinstance(outcome, BaseException):
                raise outcome
            if outcome == "timeout":
                return u"", False
            if command == "show management":
                return mgmt_text, True
            return SHOW_VERSION + SHOW_SWITCH, True

        def crawl(*a):
            self.order.append("CRAWL")
            if crawl_exc:
                raise crawl_exc

        ns["capture_readonly_command"] = readonly
        ns["run_crawl" if "run_crawl" in ns else "run_context_crawl"] = crawl
        try:
            ns["Main"]()
        except BaseException as exc:
            return exc
        return None

    def output_text(self):
        found = []
        for root, dirs, files in os.walk(self.tmp):
            found += [os.path.join(root, f) for f in files if f.endswith(".txt") and f != "out.txt"]
        self.assertEqual(len(found), 1)
        with open(found[0], "rb") as handle:
            return handle.read().decode("utf-8")

    def final_dialog(self):
        return self.dialog.boxes[-1]

    FULL_ORDER = ["show management", "disable cli paging", "show version",
                  "show switch", "CRAWL", "enable cli paging"]

    def test_command_order_paging_before_metadata(self):
        self.assertIsNone(self.run_main(SHOW_MGMT_ENABLED))
        self.assertEqual(self.order, self.FULL_ORDER)
        self.assertIn("Platform metadata", self.output_text())
        self.assertNotIn("PAGING PROBLEMS", self.final_dialog())

    def test_restored_on_crawl_error(self):
        exc = self.run_main(SHOW_MGMT_ENABLED, crawl_exc=RuntimeError("boom"))
        self.assertIsInstance(exc, RuntimeError)
        self.assertEqual(self.order[-1], "enable cli paging")
        self.assertEqual(self.order.count("enable cli paging"), 1)

    def test_restored_on_cancellation(self):
        exc = self.run_main(SHOW_MGMT_ENABLED, crawl_exc=KeyboardInterrupt())
        self.assertIsInstance(exc, KeyboardInterrupt)
        self.assertEqual(self.order[-1], "enable cli paging")
        self.assertEqual(self.order.count("enable cli paging"), 1)

    def test_already_disabled_left_alone(self):
        self.run_main(SHOW_MGMT_DISABLED)
        self.assertEqual(self.order, ["show management", "show version", "show switch", "CRAWL"])

    def test_unknown_state_declined_changes_nothing(self):
        self.run_main(u"garbage", answer_yes=False)
        self.assertEqual(self.order, ["show management"])
        self.assertIn("could not read the current CLI paging state", self.dialog.boxes[0])

    def test_unknown_state_confirmed(self):
        self.run_main(u"garbage", answer_yes=True)
        self.assertEqual(self.order, self.FULL_ORDER)
        self.assertIn("could not read the current CLI paging state", self.dialog.boxes[0])

    def test_disable_timeout_skips_crawl_but_still_restores(self):
        self.run_main(SHOW_MGMT_ENABLED, responses={"disable cli paging": "timeout"})
        self.assertNotIn("CRAWL", self.order)
        self.assertNotIn("show version", self.order)
        self.assertEqual(self.order[-1], "enable cli paging")
        self.assertIn("Disable paging failed", self.output_text())
        self.assertIn("PAGING PROBLEMS", self.final_dialog())
        self.assertIn("Disable paging failed", self.final_dialog())

    def test_disable_exception_still_attempts_restore(self):
        self.run_main(SHOW_MGMT_ENABLED, responses={"disable cli paging": self.ns["PromptLostError"]("lost")})
        self.assertNotIn("CRAWL", self.order)
        self.assertEqual(self.order[-1], "enable cli paging")
        self.assertIn("Disable paging failed", self.final_dialog())

    def test_restore_failure_visible_in_file_summary_and_dialog(self):
        self.run_main(SHOW_MGMT_ENABLED, responses={"enable cli paging": "timeout"})
        text = self.output_text()
        self.assertIn("CLI paging restore: FAILED", text)
        self.assertIn("Paging failures: 1", text)
        self.assertIn("Restore paging failed", self.final_dialog())

    def test_restore_exception_visible(self):
        self.run_main(SHOW_MGMT_ENABLED, responses={"enable cli paging": RuntimeError("x")})
        self.assertIn("Restore paging failed", self.final_dialog())
        self.assertIn("Restore paging failed", self.output_text())

    def test_restore_failure_after_crawl_error_recorded_in_file(self):
        self.run_main(SHOW_MGMT_ENABLED, responses={"enable cli paging": "timeout"}, crawl_exc=RuntimeError("boom"))
        self.assertIn("CLI paging restore: FAILED", self.output_text())

    def test_set_paging_reports_status(self):
        ns = self.ns
        ns["capture_readonly_command"] = lambda *a: (u"", True)
        self.assertEqual(ns["set_paging"](None, None, self.out, "disable cli paging"), (True, "ok"))
        ns["capture_readonly_command"] = lambda *a: (u"", False)
        self.assertFalse(ns["set_paging"](None, None, self.out, "disable cli paging")[0])
        ns["capture_readonly_command"] = lambda *a: (ERROR_FIXTURE, True)
        self.assertFalse(ns["set_paging"](None, None, self.out, "disable cli paging")[0])

    def test_restore_command_set_before_disable_attempt(self):
        ns = self.ns
        paging = ns["new_paging_state"]()
        stats = ns["new_stats"]()
        seen = {}

        def readonly(screen, session, command, path):
            if command == "show management":
                return SHOW_MGMT_ENABLED, True
            seen["restore"] = paging["restore_command"]
            raise RuntimeError("disable blew up")

        ns["capture_readonly_command"] = readonly
        self.assertFalse(ns["prepare_paging"](self.screen, self.crt.session, self.out, paging, stats))
        self.assertEqual(seen["restore"], "enable cli paging")
        self.assertEqual(len(stats["paging_failures"]), 1)

    # ---- read-only command timeout ----
    def test_readonly_timeout_cancels_and_confirms_prompt(self):
        self.screen.idle = False
        self.ns["MAX_IDLE_CHECKS"] = 1
        open(self.out, "wb").close()
        text, complete = self.ns["capture_readonly_command"](self.screen, self.crt.session, "show version", self.out)
        self.assertFalse(complete)
        sent = self.screen.sent
        self.assertLess(sent.index("show version\r"), len(sent) - 1 - sent[::-1].index(chr(3)))

    def test_readonly_timeout_prompt_not_recovered_raises(self):
        self.screen.idle = False
        self.ns["MAX_IDLE_CHECKS"] = 1
        open(self.out, "wb").close()
        calls = {"n": 0}
        original = self.screen.Get

        def get(*a):
            calls["n"] += 1
            return original(*a) if calls["n"] <= 1 else ""
        self.screen.Get = get
        with self.assertRaises(self.ns["PromptLostError"]):
            self.ns["capture_readonly_command"](self.screen, self.crt.session, "show version", self.out)

    def test_no_prompt_blocks_next_command(self):
        self.screen.Get = lambda *a: ""
        open(self.out, "wb").close()
        with self.assertRaises(self.ns["PromptLostError"]):
            self.ns["capture_readonly_command"](self.screen, self.crt.session, "show version", self.out)
        self.assertNotIn("show version\r", self.screen.sent)

    def test_metadata_stops_after_prompt_lost(self):
        ns = self.ns
        calls = []

        def readonly(screen, session, command, path):
            calls.append(command)
            raise ns["PromptLostError"]("lost")
        ns["capture_readonly_command"] = readonly
        open(self.out, "wb").close()
        ns["collect_platform_metadata"](self.screen, self.crt.session, self.out)
        self.assertEqual(calls, ["show version"])

    # ---- prompt loss propagation ----
    def stale_prompt_screen(self):
        """Prompt visible on an earlier row, pager text on the cursor row."""
        self.screen.CurrentRow = 5

        def get(r1, c1, r2, c2):
            return "X460G2.1 # " if r1 < 5 else " --More--"
        self.screen.Get = get

    def test_get_prompt_is_fooled_but_current_prompt_is_not(self):
        self.stale_prompt_screen()
        self.assertNotEqual(self.ns["get_prompt"](self.screen), "")
        self.assertEqual(self.ns["get_current_prompt"](self.screen), "")
        self.assertFalse(self.ns["ensure_usable_prompt"](self.screen))

    def test_stale_prompt_above_pager_is_not_recovery(self):
        self.stale_prompt_screen()
        self.screen.idle = False
        self.ns["MAX_IDLE_CHECKS"] = 1
        open(self.out, "wb").close()
        with self.assertRaises(self.ns["PromptLostError"]):
            self.ns["capture_readonly_command"](self.screen, self.crt.session, "show version", self.out)

    def test_help_query_refuses_to_send_without_prompt(self):
        self.stale_prompt_screen()
        open(self.out, "wb").close()
        before = len(self.screen.sent)
        with self.assertRaises(self.ns["PromptLostError"]):
            self.ns["capture_help_query"](self.screen, self.crt.session, "show vlan", self.out)
        self.assertNotIn("show vlan ?", self.screen.sent[before:])

    def test_help_query_timeout_without_prompt_recovery_raises(self):
        self.screen.idle = False
        self.ns["MAX_IDLE_CHECKS"] = 1
        open(self.out, "wb").close()
        original = self.screen.Get
        calls = {"n": 0}

        def get(*a):
            calls["n"] += 1
            return original(*a) if calls["n"] <= 1 else " --More--"
        self.screen.Get = get
        with self.assertRaises(self.ns["PromptLostError"]) as ctx:
            self.ns["capture_help_query"](self.screen, self.crt.session, "show vlan", self.out)
        self.assertTrue(ctx.exception.timed_out)

    def test_prompt_lost_in_crawl_stops_queries(self):
        ns = self.ns
        calls = []

        def capture(*a):
            calls.append(a[2])
            if len(calls) == 2:
                raise ns["PromptLostError"]("lost", True)
            return HELP_FIXTURE, True
        ns["capture_help_query"] = capture
        queue, queued, stats = collections.deque(), set(), ns["new_stats"]()
        self._process(queue, queued, stats)
        self._process(queue, queued, stats)
        self.assertTrue(stats["prompt_lost"])
        self.assertEqual(stats["incomplete"], 1)
        self.assertIn("PROMPT LOST", self.read())
        crawl = ns["run_crawl"] if "run_crawl" in ns else ns["run_context_crawl"]
        calls_before = len(calls)
        crawl(self.screen, self.crt.session, self.out, stats)
        self.assertEqual(len(calls), calls_before)

    def test_metadata_prompt_loss_skips_crawl(self):
        self.run_main(SHOW_MGMT_ENABLED, responses={"show version": self.ns["PromptLostError"]("lost")})
        self.assertNotIn("CRAWL", self.order)
        self.assertEqual(self.order[-1], "enable cli paging")
        text = self.output_text()
        self.assertIn("Crawl not run: CLI prompt lost during metadata collection", text)
        self.assertIn("Status: Crawl SKIPPED", text)
        self.assertIn("Crawl SKIPPED", self.final_dialog())
        self.assertNotIn("Crawl complete", self.final_dialog())

    # ---- final status ----
    def test_status_completed(self):
        self.run_main(SHOW_MGMT_ENABLED)
        self.assertIn("Crawl complete", self.final_dialog())
        self.assertIn("Status: Crawl complete", self.output_text())

    def test_status_skipped_when_disable_fails(self):
        self.run_main(SHOW_MGMT_ENABLED, responses={"disable cli paging": "timeout"})
        self.assertIn("Crawl SKIPPED", self.final_dialog())
        self.assertNotIn("Crawl complete", self.final_dialog())

    def test_status_skipped_when_user_declines(self):
        self.run_main(u"garbage", answer_yes=False)
        self.assertIn("Crawl SKIPPED", self.final_dialog())
        self.assertNotIn("Crawl complete", self.final_dialog())
        self.assertIn("Status: Crawl SKIPPED", self.output_text())

    def test_status_stopped_early_text(self):
        stats = self.ns["new_stats"]()
        stats["prompt_lost"] = True
        self.assertIn("STOPPED EARLY", self.ns["crawl_status_text"](stats))

    # ---- output location ----
    def test_output_root_default_is_portable(self):
        os.environ.pop("EXOS_CRAWLER_OUTPUT_ROOT", None)
        root = self.ns["resolve_output_root"]("leaf")
        self.assertTrue(root.startswith(os.path.expanduser("~")))
        self.assertIn("Documents", root)
        self.assertFalse(":" in root.replace(os.path.expanduser("~"), ""))

    def test_output_root_override(self):
        os.environ["EXOS_CRAWLER_OUTPUT_ROOT"] = self.tmp
        self.assertEqual(self.ns["resolve_output_root"]("leaf"), os.path.join(self.tmp, "leaf"))

    def test_no_hardcoded_drive_path_in_script(self):
        with open(os.path.join(HELPERS, self.script)) as handle:
            self.assertNotIn("C:\\", handle.read())

    def test_metadata_query_failure_recorded(self):
        ns = self.ns

        def boom(*a):
            raise RuntimeError("no response")
        ns["capture_readonly_command"] = boom
        open(self.out, "wb").close()
        failures = ns["collect_platform_metadata"](self.screen, self.crt.session, self.out)
        self.assertEqual(failures, 3)
        self.assertIn("Metadata query failed", self.read())


class ShowTests(AllScripts, unittest.TestCase):
    script = SCRIPTS[0]

    def _process(self, queue, queued, stats):
        self.ns["process_help_query"](self.screen, self.crt.session, self.out, "show vlan", 2, queue, queued, stats)


class ConfigTests(AllScripts, unittest.TestCase):
    script = SCRIPTS[1]

    def _process(self, queue, queued, stats):
        self.ns["process_help_query"](self.screen, self.crt.session, self.out, "configure vlan", 2, queue, queued, stats)


class ContextTests(AllScripts, unittest.TestCase):
    script = SCRIPTS[2]

    def _process(self, queue, queued, stats):
        self.ns["process_context_query"](self.screen, self.crt.session, self.out, "configure", 1, "configure vlan", 2, queue, queued, stats)

    def test_placeholder_examples_only_queried_with_question_mark(self):
        ns = self.ns
        queue, queued, stats = collections.deque(), set(), ns["new_stats"]()
        ns["capture_help_query"] = lambda *a: (u"  <vlan_name>   VLAN name\n  <port>   ports\n", True)
        self._process(queue, queued, stats)
        self.assertEqual([q["command"] for q in queue], ["configure vlan Default", "configure vlan 1:1"])
        self.assertEqual(self.screen.sent, [])  # nothing is sent by the processor itself

    def test_resolve_placeholder(self):
        r = self.ns["resolve_placeholder"]
        self.assertEqual(r("<vlan_name>", "configure vlan"), "Default")
        self.assertEqual(r("<1-4094>", "x"), "1")
        self.assertEqual(r("<unknown_thing>", "x"), "")

    def test_cross_root_dedupe(self):
        ns = self.ns
        queued = set()
        a, b = collections.deque(), collections.deque()
        self.assertTrue(ns["enqueue_command"](a, queued, "configure vlan", 2))
        self.assertFalse(ns["enqueue_command"](b, queued, "configure vlan", 2))


if __name__ == "__main__":
    unittest.main()
