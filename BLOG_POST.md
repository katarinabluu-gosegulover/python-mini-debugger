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

## 5. “멈춤”은 상태 기계다

명령을 구현하면서 가장 중요했던 설계는 단순한 `if` 모음이 아니라 실행 모드를 분리하는
것이었다.

```text
step      : 다음 line 이벤트에서 정지
continue  : 중단점/감시점에서만 정지
next      : 현재 프레임의 다음 line 또는 return에서 정지
until     : 현재 프레임에서 기준보다 큰 line 또는 return에서 정지
finish    : 현재 프레임의 return에서 정지
```

`next`가 특히 흥미롭다. 호출한 함수의 이벤트는 계속 들어오지만, 저장해 둔 현재 프레임과
이벤트의 프레임이 다르면 무시한다. 같은 프레임이 다시 `line` 이벤트를 보낼 때 멈추므로
함수 호출 전체를 건너뛴 것처럼 보인다. 반대로 `step`은 하위 함수의 첫 `line` 이벤트도
받아들인다. 이는 Exercise 2가 설명하는 두 명령의 차이와 같다.[^debugger-ex2]

중단점과 감시점은 모드보다 우선한다. 따라서 `next` 중에 호출된 함수 안에 명시적
중단점이 있으면 그곳에서 멈춘다. 사용자가 지정한 관찰 지점을 실행 명령이 가려서는 안
된다고 판단했기 때문이다.

## 6. 줄 중단점과 함수 중단점

줄 중단점은 정규화한 절대 파일 경로와 줄 번호 쌍으로 저장했다.

```python
event == "line" and filename == bp.filename and frame.f_lineno == bp.line
```

함수 중단점은 가능하면 함수의 `__code__` 객체를 저장하고 `call` 이벤트의
`frame.f_code`와 동일성 비교를 한다. 같은 이름의 함수가 여러 모듈에 있어도 구별할 수
있다. 다만 모듈 첫 줄에서는 아래쪽 함수가 아직 정의되지 않았으므로, 이때는 현재 파일과
함수 이름을 예약하고 나중의 `call` 이벤트와 맞춘다.

## 7. 감시점과 “값이 바뀌었다”의 정의

Exercise 2는 `watch CONDITION`의 값이 바뀌면 멈추라고 요구한다.[^debugger-ex2] 여기에는
두 가지 설계 문제가 있다.

첫째, 다른 함수에 들어가면 같은 이름이 없거나 전혀 다른 뜻일 수 있다. 그래서 감시점을
등록한 함수의 코드 객체도 함께 저장하고 같은 함수에서만 평가했다.

둘째, 객체는 제자리에서 변경될 수 있다. 객체 참조만 저장하면 이전 값도 함께 바뀌어
비교가 무의미하다. 이 구현은 교육용 절충으로 `(타입 이름, repr 값)` 스냅샷을 저장한다.
목록의 내용 변화는 잡을 수 있지만 `repr()`에 상태를 드러내지 않는 객체는 놓칠 수 있다.

## 8. 추가 기능: 조건부 중단점

구현 전에 `FEATURE_SPEC.md`에 다음 인터페이스를 먼저 정했다.

```text
break LINE if CONDITION
break FILE:LINE if CONDITION
```

위치가 일치했을 때만 해당 프레임에서 조건식을 평가한다. 반복문에서 `i == 1000`인 순간만
멈추는 식으로 사용할 수 있다. 조건식 오류가 대상 프로그램을 망가뜨리지 않도록 오류는 한
번만 표시하고 실행을 이어 간다.

이 기능을 고른 이유는 조건부 중단점이 단순 편의 기능을 넘어 `f_globals`, `f_locals`,
`eval()`이 실제 디버거 안에서 연결되는 모습을 잘 보여 주기 때문이다.

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

## 10. 테스트하면서 방향을 다시 의심한 지점

첫 구현에서는 `delete 15`를 “15번 중단점”으로 먼저 해석했다. 하지만 책의 기본
디버거 흐름과 사용자의 기대를 다시 검토하니 숫자만 썼을 때는 “현재 파일 15번 줄”이 더
자연스러웠다. 최종 인터페이스는 다음처럼 모호성을 없앴다.

```text
delete 15    # 15번 줄
delete #2    # 중단점 번호 2
```

또한 함수가 정의되기 전 `break function_name`이 실패하는 테스트를 보고, 함수 이름을 미리
예약하는 동작을 추가했다. 디버거는 프로그램을 관찰하는 도구이므로 첫 줄에서 앞으로 정의될
함수에 중단점을 걸 수 있어야 실제 사용성이 높다.

테스트는 단위 메서드만 호출하지 않고 임시 `.py` 파일을 만들고 명령 입력 스트림을
주입한다. `step/print`, 줄·조건부·함수 중단점, `next/where/up/down/finish`, `watch`,
`until`, `assign`, 중단점 삭제를 포함한 8개 통합 테스트로 CLI 핵심 동작을 검증했다.

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

