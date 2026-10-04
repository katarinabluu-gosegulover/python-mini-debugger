# `sys.settrace()`로 나만의 Python 디버거 만들기

> 게시 상태: **게시 전 원고**  
> 게시 후 URL: `여기에 공개 블로그 URL을 입력하세요`

디버거는 마법처럼 프로그램을 멈추는 도구가 아니다. Python 인터프리터가 보내는 실행
이벤트를 받고, 현재 실행 프레임을 관찰한 다음, 사용자의 명령이 올 때까지 실행을 보류하는
프로그램이다. 이 글에서는 The Debugging Book의 세 챕터를 읽고 `sys.settrace()`만으로
작은 대화형 디버거를 만든 과정을 정리한다.

## 1. 디버깅을 먼저 정의하기

「Introduction to Debugging」은 문제의 흐름을 다음처럼 구분한다.

```text
사람의 실수(mistake)
        ↓
코드의 결함(defect)
        ↓
실행 상태의 잘못(fault)
        ↓
외부에서 관찰되는 실패(failure)
```

핵심은 실패가 보이는 마지막 줄만 고치는 것이 아니라, 올바른 상태가 처음 잘못된 상태로
변한 지점을 찾아야 한다는 것이다. 또 수정 전 진단에는 “왜 이 코드가 실패를 만들었는가”
(인과성)와 “왜 이 코드가 올바르지 않은가”(부정확성)가 함께 있어야 한다.[^intro]

이 관점은 디버거의 역할도 명확하게 해 준다. 디버거는 자동으로 답을 주는 도구라기보다,
원인-결과 사슬의 중간 상태를 관찰하고 가설을 실험하게 해 주는 도구다.

## 2. Python 실행을 관찰하는 열쇠: `sys.settrace()`

Python은 `sys.settrace(trace_function)`으로 현재 스레드에 추적 함수를 설치할 수 있다.
추적 함수는 다음 세 인자를 받는다.[^python-settrace]

```python
def trace(frame, event, arg):
    ...
    return trace
```

- `frame`: 지금 실행 중인 프레임
- `event`: `call`, `line`, `return`, `exception`, `opcode` 중 하나
- `arg`: 이벤트별 부가 값. 예를 들어 `return`이면 반환값

`call` 이벤트에서 반환한 함수가 그 새 스코프의 로컬 추적 함수가 된다. `line` 이벤트는
새 소스 줄을 실행하기 직전에 발생하고, 반복문의 조건을 다시 실행할 때 같은 줄에서 다시
발생할 수도 있다.[^python-settrace] 이 프로젝트는 `call`, `line`, `return`으로 함수
중단점, 한 줄 실행, 함수 종료까지 실행을 구현했다.

가장 작은 추적기는 다음과 같은 모양이다.

```python
import sys

def trace(frame, event, arg):
    print(event, frame.f_code.co_name, frame.f_lineno)
    return trace

sys.settrace(trace)
target_function()
sys.settrace(None)
```

The Debugging Book의 「Tracing Executions」도 실행 관찰을 대화형 디버깅의 전제 조건으로
설명하고, 중단점은 코드 위치에 대한 조건, 감시점은 상태 변화에 대한 이벤트라고
구분한다.[^tracer]

## 3. 프레임 안에는 무엇이 있을까

프레임 객체는 함수 호출 하나의 실행 상태다. 구현에서 주로 사용한 속성은 다음과 같다.

| 속성 | 사용처 |
|---|---|
| `f_code.co_name` | 현재 함수 이름, 함수 중단점 |
| `f_code.co_filename` | 소스 파일 식별 |
| `f_lineno` | 현재 줄과 줄 중단점 |
| `f_locals` | 지역 변수 출력과 표현식 평가 |
| `f_globals` | 전역 이름을 포함한 표현식 평가 |
| `f_back` | 호출자 방향으로 스택 탐색 |

Python 데이터 모델 문서도 `f_back`을 호출자 방향의 이전 프레임으로, `f_locals`와
`f_globals`를 지역·전역 이름 검색에 쓰는 매핑으로 정의한다.[^python-frame]

이 정보만 있으면 `print x + 1`은 아래처럼 구현할 수 있다.

```python
result = eval(expression, frame.f_globals, frame.f_locals)
print(repr(result))
```

여기서 `eval()`은 단순 파서가 아니라 실제 Python 코드를 실행한다. 따라서 디버거 명령도
대상 프로그램과 같은 권한을 갖는다. 편리하지만 신뢰할 수 없는 표현식을 실행하면 안 된다.

## 4. 컨텍스트 매니저로 추적 수명 관리하기

디버거를 다음처럼 쓰면 추적 시작과 종료 범위가 명확하다.

```python
with MiniDebugger():
    target_function()
```

`with` 문은 `__enter__()`가 성공하면 블록이 어떻게 끝나더라도 `__exit__()`을 호출하도록
정의되어 있다.[^python-with] 구현에서는 `__enter__()`에서 기존 추적 함수를 저장하고 새
추적 함수를 설치하며, `__exit__()`에서 원래 값을 복구한다.

CLI에서는 대상 파일을 읽고 `compile()`한 뒤 별도의 `__main__` 이름 공간에서 `exec()`한다.
그러면 새로 실행되는 모듈 프레임부터 추적 이벤트를 받을 수 있다.

## 5. “멈춤”을 상태와 정지 정책으로 나누기

초안에서는 이 구조를 단순히 “멈춤은 상태 기계다”라고 표현했지만, 정확히는 **실행
상태(phase)**와 **실행 중 적용할 정지 정책(policy)**을 구분해야 한다.

실행 상태는 다음 세 가지다.

| 실행 상태 | 의미 |
|---|---|
| `PAUSED` | 대상 실행을 멈추고 사용자 명령을 기다리는 상태 |
| `RUNNING` | 대상 코드를 실행하면서 추적 이벤트를 검사하는 상태 |
| `TERMINATED` | `quit`을 입력했거나 대상 프로그램이 끝난 상태 |

`RUNNING`에는 “다음에 어떤 조건에서 `PAUSED`로 돌아갈 것인가”를 나타내는 정지 정책이
하나 붙는다.

| 정지 정책 | `PAUSED`로 돌아가는 조건 |
|---|---|
| `STEP` | 다음 `line` 이벤트 |
| `CONTINUE` | 중단점 일치 또는 감시값 변경 |
| `NEXT` | 명령을 입력한 프레임의 다음 `line` 또는 그 프레임의 `return` |
| `UNTIL` | 같은 프레임에서 기준보다 큰 줄의 `line` 또는 `return` |
| `FINISH` | 명령을 입력한 프레임의 `return` |

이를 전이로 쓰면 다음과 같다.

```text
초기화 ──> RUNNING(STEP) ── 첫 line ──> PAUSED

PAUSED ── step 명령 ───────> RUNNING(STEP)
PAUSED ── continue 명령 ───> RUNNING(CONTINUE)
PAUSED ── next 명령 ───────> RUNNING(NEXT, 현재 frame)
PAUSED ── until 명령 ──────> RUNNING(UNTIL, 현재 frame, 기준 line)
PAUSED ── finish 명령 ─────> RUNNING(FINISH, 현재 frame)

RUNNING ── 정책의 정지 조건 충족 ──> PAUSED
RUNNING ── 중단점/감시점 충족 ─────> PAUSED
PAUSED  ── quit 명령 ──────────────> TERMINATED
RUNNING ── 대상 프로그램 종료 ─────> TERMINATED
```

실제 코드에서는 별도의 `phase`와 `policy` 열거형을 두지 않고 `_mode` 문자열 하나에
`stopped`, `step`, `continue`, `next`, `until`, `finish`를 저장했다. 즉, 구현은 두 개념을
한 변수로 평평하게 표현하지만, 동작을 이해할 때는 `PAUSED/RUNNING/TERMINATED`와
`STEP~FINISH`를 서로 다른 수준으로 보는 편이 정확하다.

### 실제 문제 1: `next`가 `step`처럼 동작할 수 있었다

**문제:** `sys.settrace()`는 호출된 함수에서도 `call`과 `line` 이벤트를 보낸다. 따라서
단순히 “다음 `line`에서 멈춘다”로 구현하면 `next`도 호출한 함수 내부로 들어가 `step`과
같아진다.[^python-settrace]

**선택:** `next` 명령을 입력한 시점의 프레임을 `_resume_frame`에 저장하고, 이후 이벤트의
`frame is _resume_frame`이 참인 경우에만 줄 정지 조건을 검사했다. 하위 함수에서 발생한
이벤트는 추적하되 `next`의 정지 조건으로는 사용하지 않는다.

**결과:** 하위 함수에 별도 중단점이 없으면 호출 전체를 건너뛰고 호출자 프레임의 다음 줄에서
멈춘다. 반대로 `step`은 프레임을 제한하지 않으므로 하위 함수의 첫 실행 줄에서 멈춘다. 이는
Exercise 2가 설명하는 두 명령의 차이와 같다.[^debugger-ex2]

### 실제 문제 2: `next`가 명시적 중단점까지 무시하면 안 됐다

**문제:** 정지 정책만 먼저 검사하면 `NEXT`나 `FINISH` 실행 중 하위 함수의 중단점과
감시점을 지나칠 수 있다.

**선택:** 추적 이벤트 하나를 처리할 때 다음 순서로 검사했다.

```text
1. 중단점이 일치하는가?
2. 감시값이 변했는가?
3. 현재 정지 정책의 조건이 만족됐는가?
4. 모두 아니면 RUNNING을 유지한다.
```

**결과:** `next`로 호출을 건너뛰는 중이어도 사용자가 하위 함수에 직접 설정한 중단점이
있으면 그곳에서 `PAUSED`로 전이한다. 이것이 이 구현에서 말하는 “이벤트 우선순위”의 실제
의미다.

## 6. 줄 중단점과 함수 중단점

### 실제 문제 3: 줄 번호만으로는 중단점을 식별할 수 없었다

**문제:** 여러 파일에 같은 줄 번호가 존재하므로 `18`만 저장하면 다른 모듈의 18번 줄에서도
멈춘다. Windows에서는 경로의 대소문자와 상대 경로도 비교를 어렵게 한다.

**선택:** 줄 중단점을 정규화한 절대 파일 경로와 줄 번호 쌍으로 저장했다.

```python
event == "line" and filename == bp.filename and frame.f_lineno == bp.line
```

### 실제 문제 4: 첫 줄에서는 아래쪽 함수가 아직 정의되지 않았다

**문제:** 디버거가 모듈 첫 줄에서 멈췄을 때 `break average`를 실행하면 `average`의 `def`가
아직 실행되지 않아 `eval("average")`가 `NameError`를 냈다. 실제 통합 테스트도 이 문제로
처음 실패했다.

**선택:** 함수가 이미 정의됐다면 함수의 `__code__` 객체를 저장하고 `call` 이벤트의
`frame.f_code`와 동일성 비교를 한다. 아직 정의되지 않은 단순 함수 이름이라면 현재 파일과
함수 이름을 예약해 두고, 이후 같은 파일의 `call` 이벤트에서 `co_name`을 비교한다.

**결과:** 정의된 함수는 코드 객체로 정확히 구별하고, 모듈 첫 줄에서도 앞으로 정의될 함수에
중단점을 예약할 수 있게 됐다. 파일까지 함께 비교하므로 다른 모듈의 동명 함수에서 잘못
멈추는 경우도 줄였다.

## 7. 감시점과 “값이 바뀌었다”의 정의

Exercise 2는 `watch CONDITION`의 값이 바뀌면 멈추라고 요구한다.[^debugger-ex2] 여기에는
두 가지 설계 문제가 있다.

### 실제 문제 5: 하위 함수에서 같은 이름이 다른 값을 가졌다

**문제:** `watch counter`를 모든 프레임에서 평가하면 하위 함수에 들어갈 때 `counter`가
없어지거나, 우연히 같은 이름의 다른 지역 변수를 만나 값이 바뀐 것으로 판단할 수 있다.

**선택:** 감시점을 등록할 때 표현식뿐 아니라 현재 함수의 코드 객체도 함께 저장하고, 같은
코드 객체의 프레임에서만 표현식을 다시 평가했다. 이름이 아직 만들어지지 않은 이벤트는
중단하지 않고 건너뛴다.

### 실제 문제 6: 변경 가능한 객체는 참조만 저장해서 비교할 수 없었다

**문제:** 이전 목록 객체 자체를 저장한 뒤 같은 목록과 비교하면 `append()` 후에도 저장된
참조가 동일한 객체를 가리킨다. “이전 값”이 보존되지 않는 셈이다.

**선택:** 교육용 구현의 복잡도를 제한하기 위해 `(타입 이름, repr 값)`을 문자열 스냅샷으로
저장했다. 깊은 복사보다 실패 가능성이 낮고 대부분의 기본 컨테이너 변경을 관찰할 수 있다.

**한계:** `repr()`에 내부 상태를 표시하지 않는 사용자 객체의 변경은 놓칠 수 있다. 따라서
이 선택은 완전한 객체 변경 감지가 아니라 작은 디버거에 맞춘 명시적인 절충이다.

### 실제 문제 7: 살펴보는 프레임과 실행을 재개할 프레임이 달랐다

**문제:** `up`으로 호출자 프레임을 선택한 뒤 `print`와 `list`를 실행할 수 있어야 하지만,
그 상태에서 `next`가 선택된 호출자 프레임을 기준으로 실행되면 실제 정지 위치와 실행 제어가
섞인다.

**선택:** 실제 실행이 멈춘 `_active_frame`과 사용자가 스택 탐색으로 고른
`_selected_frame`을 따로 저장했다. `print`, `locals`, `list`는 선택 프레임을 사용하고,
`step`, `next`, `until`, `finish`는 실제 정지 프레임을 기준으로 재개한다.

**결과:** `up/down`은 관찰 대상을 바꿀 뿐 프로그램 카운터나 재개 위치는 바꾸지 않는다.
프레임 객체의 `f_back`을 따라 호출자 방향 스택을 만드는 구조와도 역할이 분리됐다.[^python-frame]

## 8. 추가 기능: 조건부 중단점

구현 전에 `FEATURE_SPEC.md`에 다음 인터페이스를 먼저 정했다.

```text
break LINE if CONDITION
break FILE:LINE if CONDITION
```

**문제:** 일반 줄 중단점은 반복문의 모든 반복에서 멈추므로 특정 상태만 확인하기 번거로웠다.

**선택:** 먼저 파일과 줄이 일치하는지 확인한 뒤 해당 프레임의 `f_globals`와 `f_locals`로
조건식을 평가한다. 예를 들어 `i == 1000`인 반복에서만 멈출 수 있다. 조건식의 변수 이름이
틀렸다고 해서 대상 프로그램까지 종료되는 것은 과도하다고 판단해, 평가 오류는 중단점별로
한 번만 출력하고 실행을 이어 가도록 했다.

**결과:** 조건부 중단점은 단순 편의 기능을 넘어 `f_globals`, `f_locals`, `eval()`이 실제
디버거 안에서 어떻게 연결되는지를 보여 주는 학습 기능이 됐다.

## 9. Python 문법과 표준 라이브러리에서 배운 것

### 데이터 클래스

`@dataclass`로 `Breakpoint`, `Watchpoint` 같은 데이터 중심 객체의 생성자와 표현을 간결하게
만들었다. 실행 제어 로직과 저장 데이터가 분리되어 명령 목록 출력과 삭제가 쉬워졌다.

### 타입 힌트와 유니온

`FrameType | None`, `list[Breakpoint]` 같은 Python 3.10+ 표기를 사용했다. 타입 힌트는
런타임 제약이 아니라, “정지 전에는 프레임이 없을 수 있다” 같은 상태를 코드에 드러내는
문서 역할을 했다.

### 예외 계층

`quit`은 `DebuggerQuit(BaseException)`을 발생시켜 대상 실행을 즉시 빠져나온다.
`Exception`이 아니라 `BaseException`을 상속한 것은 대상 코드의 흔한
`except Exception:`에 실수로 잡히지 않게 하기 위해서다. 컨텍스트 매니저의 `__exit__()`은
이 예외만 억제하고 추적 함수를 복구한다.

### `linecache`

현재 줄과 주변 소스는 `linecache.getline()`으로 읽는다. Python이 이미 읽은 소스를
캐시하므로 매 정지마다 파일 전체를 직접 열 필요가 없다.

### 지역 변수 쓰기의 함정

`frame.f_locals[name] = value`가 항상 실행 중인 빠른 지역 변수에 바로 반영되는 것은 아니다.
이 프로젝트의 `assign`은 CPython 내부 함수 `PyFrame_LocalsToFast`를 `ctypes`로 호출해
동기화를 시도한다. 즉, 이 명령은 Python 언어 전체가 보장하는 기능이 아니라 CPython에
의존한다. 읽기와 쓰기의 이 차이는 프레임을 단순 딕셔너리로 생각하면 놓치기 쉽다.

## 10. 테스트가 바꾼 인터페이스

### `delete 15`는 줄 번호인가, 중단점 번호인가

**문제:** 첫 구현에서는 `delete 15`를 “15번 중단점”으로 먼저 해석했다. 하지만 줄
중단점을 `break 15`로 설정했는데 삭제할 때 같은 숫자가 다른 뜻이 되는 것은 일관성이
없었다.

**수정:** 숫자만 쓰면 현재 파일의 줄 번호, 번호 앞에 `#`을 붙이면 중단점 식별자로
정의했다.

```text
delete 15    # 15번 줄
delete #2    # 중단점 번호 2
```

### 구현 메서드 테스트만으로는 부족했다

**문제:** 명령 메서드를 각각 호출하는 테스트만으로는 “모듈 첫 줄에는 함수 이름이 아직
없다”거나 `next` 중 하위 함수 이벤트가 들어오는 문제를 재현하기 어렵다.

**수정:** 임시 `.py` 파일을 실제로 `compile()`·`exec()`하고 명령 입력 스트림을 주입하는
통합 테스트를 만들었다. `step/print`, 줄·조건부·함수 중단점,
`next/where/up/down/finish`, `watch`, `until`, `assign`, 중단점 삭제를 포함한 8개 테스트를
검증했다. 이 과정에서 함수 정의 전 `break function_name` 실패가 발견되어 앞에서 설명한
예약 방식이 추가됐다.

## 11. 남은 한계와 다음 단계

- `sys.settrace()`는 스레드별이므로 멀티스레드 지원에는 각 스레드 등록이 필요하다.[^python-settrace]
- 감시점 스냅샷은 완전한 객체 변경 탐지가 아니다.
- 비동기 태스크 전환을 별도로 시각화하지 않는다.
- 예외 발생 시 자동 정지 명령은 아직 없다.
- 시간 여행 디버깅은 Exercise 3의 별도 주제다.[^debugger]

다음 확장으로는 `catch EXCEPTION`, 중단점 활성화/비활성화, 명령 파일 저장, 추적 결과를
JSON으로 내보내는 기능이 적합하다. 다만 기능을 더하기 전에 이벤트 우선순위와 프레임 수명,
스레드 정책을 먼저 명세해야 한다.

## 12. 실행해 보기

```powershell
python debugger.py examples/buggy_average.py
```

```text
(mini-debugger) break average
(mini-debugger) continue
(mini-debugger) where
(mini-debugger) print values
(mini-debugger) next
```

전체 명령은 `MANUAL.md`, 코드는 `debugger.py`, 테스트는 `tests/test_debugger.py`에 있다.

## 참고 자료

[^intro]: [The Debugging Book — Introduction to Debugging](https://www.debuggingbook.org/html/Intro_Debugging.html)
[^tracer]: [The Debugging Book — Tracing Executions](https://www.debuggingbook.org/html/Tracer.html)
[^debugger]: [The Debugging Book — How Debuggers Work](https://www.debuggingbook.org/html/Debugger.html)
[^debugger-ex2]: [The Debugging Book — How Debuggers Work, Exercise 2](https://www.debuggingbook.org/html/Debugger.html#Exercise-2:-More-Commands)
[^python-settrace]: [Python 표준 문서 — `sys.settrace()`](https://docs.python.org/3/library/sys.html#sys.settrace)
[^python-frame]: [Python 표준 문서 — Frame objects](https://docs.python.org/3/reference/datamodel.html#frame-objects)
[^python-with]: [Python 언어 참조 — `with` 문](https://docs.python.org/3/reference/compound_stmts.html#the-with-statement)

