import http.client
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard.server import DashboardError, Handler, JOBS, ROOT, ThreadingHTTPServer, _run_job, build_command


class Dashboard(unittest.TestCase):
    def test_analysis_tasks_map_to_fixed_tools(self):
        cases = {
            "scanner-daily": ("trader-scanner", "scan.py"),
            "scanner-orb": ("trader-scanner", "scan.py"),
            "news": ("trader-news", "news.py"),
            "entry": ("trader-entry", "entry.py"),
            "exit-plan": ("trader-exit", "exit.py"),
            "timemachine": ("trader-timemachine", "timemachine.py"),
            "budget": ("trader-budget", "size.py"),
            "risk": ("trader-risk", "check.py"),
            "tickets": ("trader-broker", "ticket.py"),
            "alerts-check": ("trader-alerts", "alerts.py"),
            "alerts-clock": ("trader-alerts", "alerts.py"),
            "alerts-list": ("trader-alerts", "alerts.py"),
            "analyst": ("trader-analyst", "facts.py"),
            "pelosi": ("trader-pelosi", "ptr.py"),
        }
        for task, expected in cases.items():
            with self.subTest(task=task):
                command = build_command({"task": task, "symbol": "TSLA"})
                self.assertEqual(command[1], str(ROOT / expected[0] / expected[1]))
                self.assertTrue(Path(command[0]).name.lower().startswith("python"))

    def test_ticker_arguments_are_normalized_and_checked(self):
        command = build_command({"task": "entry", "symbol": " tsla "})
        self.assertIn("TSLA", command)
        with self.assertRaises(DashboardError):
            build_command({"task": "news", "symbol": "TSLA; whoami"})

    def test_unknown_and_non_string_tasks_are_rejected(self):
        for payload in ({"task": "anything"}, {"task": []}, []):
            with self.subTest(payload=payload):
                with self.assertRaises(DashboardError):
                    build_command(payload)

    def test_broker_route_is_read_only(self):
        command = build_command({"task": "tickets"})
        self.assertEqual(command[2:], ["show"])
        self.assertNotIn("approve", command)
        self.assertNotIn("result", command)
        self.assertNotIn("flatten", command)

    def test_nonzero_tool_exit_keeps_its_output_without_claiming_success(self):
        from types import SimpleNamespace

        with patch("dashboard.server.subprocess.run", return_value=SimpleNamespace(
            returncode=1, stdout="NYSE closed.", stderr=""
        )):
            JOBS["nonzero-test"] = {"status": "queued"}
            _run_job("nonzero-test", ["unused"])
        self.assertEqual(JOBS["nonzero-test"]["status"], "finished")
        self.assertEqual(JOBS["nonzero-test"]["output"], "NYSE closed.")


class DashboardHTTP(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_dashboard_origin_can_queue_only_allowlisted_task(self):
        with patch("dashboard.server.POOL.submit") as submit:
            connection = http.client.HTTPConnection("127.0.0.1", self.port)
            body = json.dumps({"task": "tickets"})
            connection.request(
                "POST",
                "/api/run",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Origin": "http://127.0.0.1:%d" % self.port,
                },
            )
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
        self.assertEqual(response.status, 202)
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(submit.call_count, 1)

    def test_cross_origin_task_request_is_rejected(self):
        with patch("dashboard.server.POOL.submit") as submit:
            connection = http.client.HTTPConnection("127.0.0.1", self.port)
            body = json.dumps({"task": "tickets"})
            connection.request(
                "POST",
                "/api/run",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Origin": "http://evil.example",
                },
            )
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
        self.assertEqual(response.status, 403)
        self.assertIn("local dashboard", payload["error"])
        submit.assert_not_called()

    def test_duplicate_task_input_is_rejected_while_queued(self):
        with patch("dashboard.server.POOL.submit") as submit:
            responses = []
            for _ in range(2):
                connection = http.client.HTTPConnection("127.0.0.1", self.port)
                connection.request(
                    "POST",
                    "/api/run",
                    body=json.dumps({"task": "alerts-clock"}),
                    headers={
                        "Content-Type": "application/json",
                        "Origin": "http://127.0.0.1:%d" % self.port,
                    },
                )
                response = connection.getresponse()
                responses.append(response.status)
                response.read()
                connection.close()
        self.assertEqual(responses, [202, 409])
        self.assertEqual(submit.call_count, 1)


if __name__ == "__main__":
    unittest.main()
