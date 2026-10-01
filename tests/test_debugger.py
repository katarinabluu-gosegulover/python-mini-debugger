"""MiniDebugger의 사용자 관점 통합 테스트."""

from __future__ import annotations

import io
import tempfile
import textwrap
import unittest
from pathlib import Path

from debugger import MiniDebugger


class DebuggerSessionTests(unittest.TestCase):
    def run_session(self, source: str, commands: str) -> str:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "target.py"
            script.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
            output = io.StringIO()
            debugger = MiniDebugger(
                input_stream=io.StringIO(textwrap.dedent(commands).lstrip()),
                output_stream=output,
            )
            debugger.run_script(script)
            return output.getvalue()

    def test_step_print_locals_and_continue(self) -> None:
        output = self.run_session(
            """
            x = 2
            y = x + 3
            result = y * 2
            """,
            """
            step
            print x
            locals
            continue
            """,
        )
        self.assertIn("2", output)
        self.assertIn("x = 2", output)

    def test_line_breakpoint_and_continue(self) -> None:
        output = self.run_session(
            """
            x = 1
            x += 1
            x += 1
            """,
            """
            break 3
            continue
            print x
            continue
            """,
        )
        self.assertIn("Stopped (breakpoint 1)", output)
        self.assertIn("2", output)

    def test_delete_line_function_and_numbered_breakpoints(self) -> None:
        output = self.run_session(
            """
            def worker():
                return 1

            result = worker()
            """,
            """
            break 4
            break worker
            delete 4
            delete worker
            break 4
            delete #3
            break
            continue
            """,
        )
        self.assertIn("Deleted 1:", output)
        self.assertIn("Deleted 2: function worker", output)
        self.assertIn("Deleted 3:", output)
        self.assertIn("No breakpoints.", output)

    def test_conditional_breakpoint(self) -> None:
        output = self.run_session(
            """
            total = 0
            for i in range(4):
                total += i
            result = total
            """,
            """
            break 3 if i == 2
            continue
            print i
            continue
            """,
        )
        self.assertIn("if i == 2", output)
        self.assertIn("Stopped (breakpoint 1)", output)
        self.assertIn("(mini-debugger) 2", output)

    def test_function_breakpoint_next_where_up_down_and_finish(self) -> None:
        output = self.run_session(
            """
            def add_one(value):
                result = value + 1
                return result

            def outer():
                base = 4
                answer = add_one(base)
                return answer

            final = outer()
            """,
            """
            break outer
            continue
            next
            next
            where
            step
            where
            up
            print base
            down
            finish
            continue
            """,
        )
        self.assertIn("function outer", output)
        self.assertIn("#0", output)
        self.assertIn("#1", output)
        self.assertIn("4", output)
        self.assertIn("Stopped (finish)", output)

    def test_watchpoint(self) -> None:
        output = self.run_session(
            """
            counter = 0
            counter += 1
            counter += 1
            """,
            """
            step
            watch counter
            continue
            print counter
            continue
            continue
            """,
        )
        self.assertIn("Watching counter = 0", output)
        self.assertIn("watch counter: 0 -> 1", output)

    def test_until(self) -> None:
        output = self.run_session(
            """
            value = 0
            for i in range(3):
                value += i
            final = value
            """,
            """
            until 3
            print value
            continue
            """,
        )
        self.assertIn("Stopped (line > 3)", output)
        self.assertIn("3", output)

    def test_assign_changes_fast_local(self) -> None:
        output = self.run_session(
            """
            def compute():
                value = 1
                marker = value
                return value

            result = compute()
            """,
            """
            break compute
            continue
            step
            assign value=40
            next
            print value
            continue
            """,
        )
        self.assertIn("value = 40", output)


if __name__ == "__main__":
    unittest.main()

