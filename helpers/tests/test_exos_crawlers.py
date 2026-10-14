# Fixture-based tests for the EXOS crawlers. Run from the repository root:
#   python3 -m unittest discover -s helpers/tests -v
#
# The fixtures are SYNTHETIC approximations of EXOS "?" output; they are not
# captures from a live device. See helpers/README-exos-crawler-suite.md.
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

    def run_main(self, mgmt_text, crawl_exc=None, answer_yes=True):
        ns = self.ns
        ns["OUTPUT_ROOT"] = self.tmp
        self.dialog.answer = [v for k, v in ns.items() if k == "CONFIRMATION"][0] if "CONFIRMATION" in ns else "CONTEXTCRAWL"
        self.dialog.message_box = 6 if answer_yes else 7
        calls = {"n": 0}

        def readonly(screen, session, command, path):
            self.screen.sent.append("RO:" + command)
            return (mgmt_text if command == "show management" else SHOW_VERSION + SHOW_SWITCH), True

        def crawl(*a):
            self.screen.sent.append("CRAWL")
            if crawl_exc:
                raise crawl_exc

        ns["capture_readonly_command"] = readonly
        ns["run_crawl" if "run_crawl" in ns else "run_context_crawl"] = crawl
        try:
            ns["Main"]()
        except BaseException as exc:
            return exc
        return None

    def cmds(self):
        return [s.strip() for s in self.screen.sent if "paging" in s]

    def test_paging_enabled_restored_on_success(self):
        self.run_main(SHOW_MGMT_ENABLED)
        self.assertEqual(self.cmds(), ["disable cli paging", "enable cli paging"])

    def test_paging_restored_on_error(self):
        self.run_main(SHOW_MGMT_ENABLED, crawl_exc=RuntimeError("boom"))
        self.assertEqual(self.cmds(), ["disable cli paging", "enable cli paging"])

    def test_paging_restored_on_cancellation(self):
        exc = self.run_main(SHOW_MGMT_ENABLED, crawl_exc=KeyboardInterrupt())
        self.assertIsInstance(exc, KeyboardInterrupt)
        self.assertEqual(self.cmds(), ["disable cli paging", "enable cli paging"])

    def test_paging_already_disabled_left_alone(self):
        self.run_main(SHOW_MGMT_DISABLED)
        self.assertEqual(self.cmds(), [])
        self.assertIn("CRAWL", self.screen.sent)

    def test_unknown_state_requires_confirmation(self):
        self.run_main(u"garbage", answer_yes=False)
        self.assertEqual(self.cmds(), [])
        self.assertNotIn("CRAWL", self.screen.sent)

    def test_unknown_state_confirmed(self):
        self.run_main(u"garbage", answer_yes=True)
        self.assertEqual(self.cmds(), ["disable cli paging", "enable cli paging"])

    def test_metadata_in_header_and_failure_does_not_block(self):
        self.run_main(SHOW_MGMT_ENABLED)
        out = [f for f in os.listdir(self.tmp) if f.endswith(".txt")][0]
        with open(os.path.join(self.tmp, out), "rb") as handle:
            text = handle.read().decode("utf-8")
        self.assertIn("Platform metadata", text)

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
