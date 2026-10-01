"""교육용 대화형 Python 디버거.

The Debugging Book의 "How Debuggers Work" Exercise 2 범위를 독립적으로
구현한다. 외부 패키지 없이 ``sys.settrace()``만 사용한다.
"""

from __future__ import annotations

import argparse
import builtins
import ctypes
import inspect
import linecache
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import CodeType, FrameType, TracebackType
from typing import Any, Callable, Iterable, TextIO


class DebuggerQuit(BaseException):
    """사용자가 디버깅 대상 실행을 중단했음을 나타낸다."""


@dataclass
class Breakpoint:
    """줄 또는 함수 중단점."""

    number: int
    kind: str
    filename: str | None = None
    line: int | None = None
    function_name: str | None = None
    code: CodeType | None = None
    condition: str | None = None

    def describe(self) -> str:
        if self.kind == "function":
            location = f"function {self.function_name}"
        else:
            location = f"{self.filename}:{self.line}"
        if self.condition:
            location += f" if {self.condition}"
        return f"{self.number}: {location}"


@dataclass
class Watchpoint:
    """한 코드 객체 안에서 표현식 값의 변화를 감시한다."""

    expression: str
    code: CodeType
    value: tuple[str, str]


class MiniDebugger:
    """``sys.settrace()`` 기반의 작은 대화형 디버거.

    ``input_stream``과 ``output_stream``을 바꿀 수 있어 대화 세션도 테스트할 수
    있다. 기본값은 실제 표준 입력/출력이다.
    """

    PROMPT = "(mini-debugger) "

    def __init__(
        self,
        *,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
    ) -> None:
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stdout
        self.breakpoints: list[Breakpoint] = []
        self.watchpoints: list[Watchpoint] = []
        self.command_history: list[str] = []
        self._next_breakpoint_number = 1
        self._mode = "step"
        self._resume_frame: FrameType | None = None
        self._resume_line: int | None = None
        self._until_line: int | None = None
        self._active_frame: FrameType | None = None
        self._selected_frame: FrameType | None = None
        self._selected_index = 0
        self._event = ""
        self._event_arg: Any = None
        self._enabled = False
        self._old_trace: Callable[..., Any] | None = None
        self._debugger_filename = self._normalize_filename(__file__)
        self._condition_errors_reported: set[int] = set()

    # -- lifecycle -------------------------------------------------------

    def __enter__(self) -> "MiniDebugger":
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self.stop()
        return exc_type is DebuggerQuit

    def start(self) -> None:
        """현재 스레드에서 추적을 시작한다."""
        if self._enabled:
            return
        self._enabled = True
        self._mode = "step"
        self._old_trace = sys.gettrace()
        sys.settrace(self._trace)

    def stop(self) -> None:
        """이전 추적 함수를 복구한다."""
        if not self._enabled:
            return
        sys.settrace(self._old_trace)
        self._enabled = False

    def run_script(self, script: str | os.PathLike[str], arguments: Iterable[str] = ()) -> None:
        """스크립트를 ``__main__``처럼 실행하면서 디버깅한다."""
        path = Path(script).resolve()
        source = path.read_text(encoding="utf-8")
        code = compile(source, str(path), "exec")
        namespace: dict[str, Any] = {
            "__name__": "__main__",
            "__file__": str(path),
            "__package__": None,
            "__builtins__": builtins,
        }
        old_argv = sys.argv
        sys.argv = [str(path), *arguments]
        try:
            with self:
                exec(code, namespace, namespace)
        finally:
            sys.argv = old_argv

    # -- tracing and stop decisions -------------------------------------

    def _trace(self, frame: FrameType, event: str, arg: Any) -> Callable[..., Any] | None:
        if self._normalize_filename(frame.f_code.co_filename) == self._debugger_filename:
            return self._trace

        breakpoint = self._matching_breakpoint(frame, event)
        watch_change = self._watch_change(frame)
        reason: str | None = None

        if breakpoint is not None:
            reason = f"breakpoint {breakpoint.number}"
        elif watch_change is not None:
            reason = watch_change
        elif self._mode == "step" and event == "line":
            reason = "step"
        elif self._mode == "next" and self._resume_frame is frame:
            if event == "return":
                reason = "function returned"
            elif event == "line" and frame.f_lineno != self._resume_line:
                reason = "next"
        elif self._mode == "until" and self._resume_frame is frame:
            if event == "return":
                reason = "function returned"
            elif event == "line" and self._until_line is not None and frame.f_lineno > self._until_line:
                reason = f"line > {self._until_line}"
        elif self._mode == "finish" and self._resume_frame is frame and event == "return":
            reason = "finish"

        if reason is not None:
            self._interaction(frame, event, arg, reason)
        return self._trace

    def _matching_breakpoint(self, frame: FrameType, event: str) -> Breakpoint | None:
        filename = self._normalize_filename(frame.f_code.co_filename)
        for breakpoint in self.breakpoints:
            matches = False
            if breakpoint.kind == "function":
                matches = event == "call" and (
                    frame.f_code is breakpoint.code
                    or (
                        breakpoint.code is None
                        and breakpoint.function_name is not None
                        and breakpoint.filename == filename
                        and frame.f_code.co_name == breakpoint.function_name.rsplit(".", 1)[-1]
                    )
                )
            elif event == "line":
                matches = breakpoint.filename == filename and breakpoint.line == frame.f_lineno
            if not matches:
                continue
            if breakpoint.condition is None:
                return breakpoint
            try:
                if bool(eval(breakpoint.condition, frame.f_globals, frame.f_locals)):
                    return breakpoint
            except Exception as error:  # 디버깅 대상의 잘못된 조건이 실행을 깨면 안 된다.
                if breakpoint.number not in self._condition_errors_reported:
                    self._write(
                        f"Breakpoint {breakpoint.number} condition error: "
                        f"{type(error).__name__}: {error}"
                    )
                    self._condition_errors_reported.add(breakpoint.number)
        return None

    def _watch_change(self, frame: FrameType) -> str | None:
        for watchpoint in self.watchpoints:
            if frame.f_code is not watchpoint.code:
                continue
            try:
                value = eval(watchpoint.expression, frame.f_globals, frame.f_locals)
            except (NameError, UnboundLocalError):
                continue
            except Exception:
                continue
            snapshot = self._snapshot(value)
            if snapshot != watchpoint.value:
                old = watchpoint.value[1]
                watchpoint.value = snapshot
                return f"watch {watchpoint.expression}: {old} -> {snapshot[1]}"
        return None

    def _interaction(self, frame: FrameType, event: str, arg: Any, reason: str) -> None:
        self._active_frame = frame
        self._selected_frame = frame
        self._selected_index = 0
        self._event = event
        self._event_arg = arg
        self._mode = "stopped"
        self._write(f"Stopped ({reason}) at {self._location(frame)}")
        self._show_current_line(frame)

        while self._mode == "stopped":
            command = self._read_command()
            if command is None:
                self._mode = "continue"
                break
            if not command.strip():
                command = self.command_history[-1] if self.command_history else "step"
            else:
                self.command_history.append(command)
            self._dispatch(command)

    # -- command dispatch ------------------------------------------------

    def _read_command(self) -> str | None:
        if self.input is sys.stdin:
            try:
                return input(self.PROMPT)
            except EOFError:
                return None
        self.output.write(self.PROMPT)
        self.output.flush()
        line = self.input.readline()
        return None if line == "" else line.rstrip("\n")

    def _dispatch(self, command_line: str) -> None:
        command, _, argument = command_line.strip().partition(" ")
        commands = self._commands()
        if command not in commands:
            matches = [name for name in commands if name.startswith(command)]
            if len(matches) == 1:
                command = matches[0]
            elif len(matches) > 1:
                self._write(f"Ambiguous command {command!r}: {', '.join(matches)}")
                return
            else:
                self._write(f"Unknown command {command!r}. Type 'help'.")
                return
        try:
            commands[command](argument.strip())
        except DebuggerQuit:
            raise
        except Exception as error:
            self._write(f"Command error: {type(error).__name__}: {error}")

    def _commands(self) -> dict[str, Callable[[str], None]]:
        return {
            "assign": self._cmd_assign,
            "break": self._cmd_break,
            "continue": self._cmd_continue,
            "delete": self._cmd_delete,
            "down": self._cmd_down,
            "finish": self._cmd_finish,
            "help": self._cmd_help,
            "history": self._cmd_history,
            "list": self._cmd_list,
            "locals": self._cmd_locals,
            "next": self._cmd_next,
            "print": self._cmd_print,
            "quit": self._cmd_quit,
            "step": self._cmd_step,
            "until": self._cmd_until,
            "up": self._cmd_up,
            "watch": self._cmd_watch,
            "where": self._cmd_where,
        }

    # -- commands: execution --------------------------------------------

    def _cmd_step(self, argument: str) -> None:
        """step: 다음 실행 줄로 들어간다."""
        self._require_no_argument(argument)
        self._mode = "step"

    def _cmd_continue(self, argument: str) -> None:
        """continue: 중단점이나 감시점까지 계속한다."""
        self._require_no_argument(argument)
        self._mode = "continue"

    def _cmd_next(self, argument: str) -> None:
        """next: 호출한 함수 안으로 들어가지 않고 다음 줄까지 실행한다."""
        self._require_no_argument(argument)
        self._require_active_frame()
        self._resume_frame = self._active_frame
        self._resume_line = self._active_frame.f_lineno
        self._mode = "next"

    def _cmd_until(self, argument: str) -> None:
        """until [LINE]: 현재 프레임에서 LINE보다 큰 줄까지 실행한다."""
        self._require_active_frame()
        self._resume_frame = self._active_frame
        self._until_line = int(argument) if argument else self._active_frame.f_lineno
        self._mode = "until"

    def _cmd_finish(self, argument: str) -> None:
        """finish: 현재 함수가 반환할 때까지 실행한다."""
        self._require_no_argument(argument)
        self._require_active_frame()
        self._resume_frame = self._active_frame
        self._mode = "finish"

    def _cmd_quit(self, argument: str) -> None:
        """quit: 디버깅 대상 실행을 끝낸다."""
        self._require_no_argument(argument)
        raise DebuggerQuit()

    # -- commands: inspection -------------------------------------------

    def _cmd_print(self, argument: str) -> None:
        """print EXPR: 선택한 프레임에서 Python 표현식을 평가한다."""
        if not argument:
            raise ValueError("usage: print EXPR")
        frame = self._require_selected_frame()
        result = eval(argument, frame.f_globals, frame.f_locals)
        self._write(repr(result))

    def _cmd_locals(self, argument: str) -> None:
        """locals: 선택한 프레임의 지역 변수를 출력한다."""
        self._require_no_argument(argument)
        frame = self._require_selected_frame()
        for name in sorted(frame.f_locals):
            self._write(f"{name} = {self._safe_repr(frame.f_locals[name])}")

    def _cmd_list(self, argument: str) -> None:
        """list [RADIUS]: 현재 줄 주변 소스를 출력한다."""
        radius = int(argument) if argument else 3
        frame = self._require_selected_frame()
        self._list_source(frame, radius)

    def _cmd_where(self, argument: str) -> None:
        """where: 호출 스택을 출력한다."""
        self._require_no_argument(argument)
        for index, frame in enumerate(self._stack()):
            marker = "->" if index == self._selected_index else "  "
            self._write(f"{marker} #{index} {self._location(frame)}")

    def _cmd_up(self, argument: str) -> None:
        """up: 호출자 프레임을 선택한다."""
        self._require_no_argument(argument)
        stack = self._stack()
        if self._selected_index + 1 >= len(stack):
            self._write("Already at the oldest available frame.")
            return
        self._selected_index += 1
        self._selected_frame = stack[self._selected_index]
        self._write(self._location(self._selected_frame))
        self._show_current_line(self._selected_frame)

    def _cmd_down(self, argument: str) -> None:
        """down: 피호출자 방향 프레임을 선택한다."""
        self._require_no_argument(argument)
        if self._selected_index == 0:
            self._write("Already at the newest frame.")
            return
        self._selected_index -= 1
        self._selected_frame = self._stack()[self._selected_index]
        self._write(self._location(self._selected_frame))
        self._show_current_line(self._selected_frame)

    def _cmd_assign(self, argument: str) -> None:
        """assign NAME=EXPR: 선택한 프레임의 지역 변수 값을 바꾼다."""
        name, separator, expression = argument.partition("=")
        name = name.strip()
        if not separator or not name.isidentifier() or not expression.strip():
            raise ValueError("usage: assign NAME=EXPR")
        frame = self._require_selected_frame()
        value = eval(expression, frame.f_globals, frame.f_locals)
        frame.f_locals[name] = value
        self._sync_fast_locals(frame)
        self._write(f"{name} = {self._safe_repr(value)}")

    # -- commands: breakpoints and watchpoints ---------------------------

    def _cmd_break(self, argument: str) -> None:
        """break [LOCATION [if CONDITION]]: 중단점을 표시하거나 추가한다."""
        if not argument:
            if not self.breakpoints:
                self._write("No breakpoints.")
            for breakpoint in self.breakpoints:
                self._write(breakpoint.describe())
            return

        location, condition = self._split_condition(argument)
        frame = self._require_selected_frame()
        if location.isdigit() or self._looks_like_file_line(location):
            filename, line = self._parse_line_location(location, frame)
            breakpoint = Breakpoint(
                self._next_breakpoint_number,
                "line",
                filename=filename,
                line=line,
                condition=condition,
            )
        else:
            if condition:
                raise ValueError("conditional function breakpoints are not supported")
            # 모듈 첫 줄에서는 아래에 정의된 함수가 아직 이름 공간에 없다. 이때도
            # 함수 이름을 예약해 두고 이후 ``call`` 이벤트의 ``co_name``과 맞춘다.
            try:
                target = eval(location, frame.f_globals, frame.f_locals)
            except NameError:
                if not location.isidentifier():
                    raise
                code = None
            else:
                code = self._callable_code(target)
            breakpoint = Breakpoint(
                self._next_breakpoint_number,
                "function",
                filename=(
                    self._normalize_filename(code.co_filename)
                    if code
                    else self._normalize_filename(frame.f_code.co_filename)
                ),
                line=code.co_firstlineno if code else None,
                function_name=location,
                code=code,
            )
        self.breakpoints.append(breakpoint)
        self._next_breakpoint_number += 1
        self._write(f"Breakpoint {breakpoint.describe()}")

    def _cmd_delete(self, argument: str) -> None:
        """delete TARGET: #번호·줄·함수 중단점 또는 감시식을 삭제한다."""
        if not argument:
            raise ValueError("usage: delete #NUMBER|LINE|FILE:LINE|FUNCTION|CONDITION")
        frame = self._require_selected_frame()
        deleted: list[str] = []

        if argument.startswith("#") and argument[1:].isdigit():
            number = int(argument[1:])
            numbered = [bp for bp in self.breakpoints if bp.number == number]
            self.breakpoints = [bp for bp in self.breakpoints if bp.number != number]
            deleted.extend(bp.describe() for bp in numbered)
        elif argument.isdigit():
            filename = self._normalize_filename(frame.f_code.co_filename)
            line = int(argument)
            matched = [
                bp for bp in self.breakpoints
                if bp.kind == "line" and bp.filename == filename and bp.line == line
            ]
            self.breakpoints = [bp for bp in self.breakpoints if bp not in matched]
            deleted.extend(bp.describe() for bp in matched)
        elif self._looks_like_file_line(argument):
            filename, line = self._parse_line_location(argument, frame)
            matched = [
                bp for bp in self.breakpoints
                if bp.kind == "line" and bp.filename == filename and bp.line == line
            ]
            self.breakpoints = [bp for bp in self.breakpoints if bp not in matched]
            deleted.extend(bp.describe() for bp in matched)
        else:
            matched = [
                bp for bp in self.breakpoints
                if bp.kind == "function" and bp.function_name == argument
            ]
            self.breakpoints = [bp for bp in self.breakpoints if bp not in matched]
            deleted.extend(bp.describe() for bp in matched)
            watched = [wp for wp in self.watchpoints if wp.expression == argument]
            self.watchpoints = [wp for wp in self.watchpoints if wp.expression != argument]
            deleted.extend(f"watch {wp.expression}" for wp in watched)

        if deleted:
            for item in deleted:
                self._write(f"Deleted {item}")
        else:
            self._write(f"Nothing matched {argument!r}.")

    def _cmd_watch(self, argument: str) -> None:
        """watch EXPR: 현재 함수에서 표현식 값이 바뀔 때 멈춘다."""
        if not argument:
            if not self.watchpoints:
                self._write("No watchpoints.")
            for watchpoint in self.watchpoints:
                self._write(f"watch {watchpoint.expression} = {watchpoint.value[1]}")
            return
        frame = self._require_selected_frame()
        value = eval(argument, frame.f_globals, frame.f_locals)
        self.watchpoints.append(Watchpoint(argument, frame.f_code, self._snapshot(value)))
        self._write(f"Watching {argument} = {self._safe_repr(value)}")

    # -- commands: help/history -----------------------------------------

    def _cmd_help(self, argument: str) -> None:
        """help [COMMAND]: 명령 도움말을 출력한다."""
        commands = self._commands()
        if argument:
            if argument not in commands:
                raise ValueError(f"unknown command {argument!r}")
            self._write(inspect.getdoc(commands[argument]) or argument)
            return
        self._write("Commands (unique prefixes are accepted):")
        for name in sorted(commands):
            doc = inspect.getdoc(commands[name]) or ""
            self._write(f"  {doc.splitlines()[0] if doc else name}")

    def _cmd_history(self, argument: str) -> None:
        """history: 이번 세션의 명령 기록을 출력한다."""
        self._require_no_argument(argument)
        for index, command in enumerate(self.command_history, 1):
            self._write(f"{index:>3}  {command}")

    # -- helpers ---------------------------------------------------------

    def _stack(self) -> list[FrameType]:
        frame = self._require_active_frame()
        frames: list[FrameType] = []
        while frame is not None:
            if self._normalize_filename(frame.f_code.co_filename) != self._debugger_filename:
                frames.append(frame)
            frame = frame.f_back
        return frames

    def _list_source(self, frame: FrameType, radius: int) -> None:
        if radius < 0:
            raise ValueError("radius must be >= 0")
        filename = frame.f_code.co_filename
        start = max(1, frame.f_lineno - radius)
        end = frame.f_lineno + radius
        for line_number in range(start, end + 1):
            source = linecache.getline(filename, line_number)
            if not source:
                continue
            marker = "->" if line_number == frame.f_lineno else "  "
            self._write(f"{marker} {line_number:>4} {source.rstrip()}")

    def _show_current_line(self, frame: FrameType) -> None:
        source = linecache.getline(frame.f_code.co_filename, frame.f_lineno).rstrip()
        if source:
            self._write(f"-> {frame.f_lineno:>4} {source}")

    def _location(self, frame: FrameType) -> str:
        return f"{frame.f_code.co_name} ({frame.f_code.co_filename}:{frame.f_lineno})"

    def _parse_line_location(self, location: str, frame: FrameType) -> tuple[str, int]:
        if location.isdigit():
            return self._normalize_filename(frame.f_code.co_filename), int(location)
        filename, separator, line_text = location.rpartition(":")
        if not separator or not line_text.isdigit():
            raise ValueError("location must be LINE, FILE:LINE, or FUNCTION")
        path = Path(filename)
        if not path.is_absolute():
            path = Path.cwd() / path
        return self._normalize_filename(str(path)), int(line_text)

    @staticmethod
    def _looks_like_file_line(location: str) -> bool:
        _, separator, line = location.rpartition(":")
        return bool(separator and line.isdigit())

    @staticmethod
    def _split_condition(argument: str) -> tuple[str, str | None]:
        location, separator, condition = argument.partition(" if ")
        if separator and not condition.strip():
            raise ValueError("condition is empty")
        return location.strip(), condition.strip() if separator else None

    @staticmethod
    def _callable_code(target: Any) -> CodeType:
        if inspect.ismethod(target):
            target = target.__func__
        target = inspect.unwrap(target)
        code = getattr(target, "__code__", None)
        if not isinstance(code, CodeType):
            raise TypeError("target is not a Python function")
        return code

    @staticmethod
    def _normalize_filename(filename: str) -> str:
        return os.path.normcase(os.path.abspath(filename))

    @staticmethod
    def _safe_repr(value: Any, limit: int = 200) -> str:
        try:
            result = repr(value)
        except Exception as error:
            result = f"<repr failed: {type(error).__name__}>"
        return result if len(result) <= limit else result[: limit - 3] + "..."

    @classmethod
    def _snapshot(cls, value: Any) -> tuple[str, str]:
        return type(value).__qualname__, cls._safe_repr(value, 1000)

    @staticmethod
    def _sync_fast_locals(frame: FrameType) -> None:
        """CPython의 최적화 지역 변수 배열에 ``f_locals``를 반영한다."""
        if sys.implementation.name != "cpython":
            return
        try:
            sync = ctypes.pythonapi.PyFrame_LocalsToFast
            sync.argtypes = [ctypes.py_object, ctypes.c_int]
            sync.restype = None
            sync(frame, 1)
        except (AttributeError, OSError):
            pass

    def _require_active_frame(self) -> FrameType:
        if self._active_frame is None:
            raise RuntimeError("program is not stopped")
        return self._active_frame

    def _require_selected_frame(self) -> FrameType:
        if self._selected_frame is None:
            raise RuntimeError("no frame is selected")
        return self._selected_frame

    @staticmethod
    def _require_no_argument(argument: str) -> None:
        if argument:
            raise ValueError("this command takes no arguments")

    def _write(self, message: str) -> None:
        print(message, file=self.output)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="A small educational Python debugger built with sys.settrace()."
    )
    parser.add_argument("script", help="Python script to debug")
    parser.add_argument("script_args", nargs=argparse.REMAINDER, help="arguments for the script")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    options = parser.parse_args(argv)
    debugger = MiniDebugger()
    try:
        debugger.run_script(options.script, options.script_args)
    except FileNotFoundError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

