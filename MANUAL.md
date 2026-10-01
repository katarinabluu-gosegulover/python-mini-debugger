# Python Mini Debugger 사용자 매뉴얼

## 1. 실행 환경

- Python 3.10 이상
- 외부 패키지 없음
- Windows, macOS, Linux에서 실행 가능

Python의 `sys.settrace()`는 현재 스레드의 추적 함수를 등록하며, 추적 함수는
`call`, `line`, `return`, `exception`, `opcode` 이벤트를 받을 수 있다.[^python-settrace]
이 디버거는 그중 `call`, `line`, `return` 이벤트를 이용한다.

## 2. 시작하기

```powershell
python debugger.py 디버깅할파일.py [프로그램 인자 ...]
```

예제:

```powershell
python debugger.py examples/buggy_average.py
```

실행하면 첫 번째 실행 줄에서 멈추고 `(mini-debugger)` 프롬프트가 나타난다.

## 3. 명령 요약

명령은 구분 가능한 접두사로 줄여 쓸 수 있다. 예를 들어 `continue`는 `c`, `where`는
`wh`로 쓸 수 있다. 빈 명령을 입력하면 직전 명령을 반복하며, 첫 명령이 비어 있으면
`step`을 수행한다.

| 명령 | 사용법 | 동작 |
|---|---|---|
| `help` | `help [COMMAND]` | 전체 또는 특정 명령 도움말 |
| `step` | `step` | 다음 실행 줄로 들어감 |
| `next` | `next` | 함수 호출 안으로 들어가지 않고 현재 프레임의 다음 줄로 이동 |
| `continue` | `continue` | 중단점 또는 감시점까지 계속 실행 |
| `until` | `until [LINE]` | 현재 프레임에서 기준보다 큰 줄 번호가 나올 때까지 실행 |
| `finish` | `finish` | 현재 함수의 `return` 이벤트까지 실행 |
| `print` | `print EXPR` | 선택한 프레임에서 표현식 평가 |
| `locals` | `locals` | 선택한 프레임의 지역 변수 출력 |
| `list` | `list [RADIUS]` | 현재 줄 앞뒤 소스 출력(기본 반경 3줄) |
| `where` | `where` | 현재 호출 스택 출력 |
| `up` | `up` | 호출자 프레임 선택 |
| `down` | `down` | 더 최신(피호출자 방향) 프레임 선택 |
| `assign` | `assign NAME=EXPR` | 지역 변수 변경(주로 CPython) |
| `break` | `break [LOCATION]` | 중단점 목록 또는 추가 |
| `delete` | `delete TARGET` | 중단점 또는 감시점 삭제 |
| `watch` | `watch [EXPR]` | 감시점 목록 또는 추가 |
| `history` | `history` | 이번 세션의 명령 기록 출력 |
| `quit` | `quit` | 디버깅 대상 실행 중단 |

## 4. 중단점

### 줄 중단점

```text
break 18
break examples/buggy_average.py:18
```

첫 형식은 현재 선택 프레임의 파일 18번 줄, 둘째는 특정 파일의 18번 줄을 뜻한다.

### 함수 이름 중단점

```text
break average
break object.method
```

함수가 아직 정의되기 전이라도 단순 함수 이름을 예약할 수 있다. 정의된 Python 함수나
메서드는 실제 코드 객체를 저장해 같은 이름의 다른 함수를 구별한다. The Debugging Book의
Exercise 2는 `break FUNCTION`과 `delete FUNCTION`을 함수 중단점의 인터페이스로
제시한다.[^debugger-ex2]

### 조건부 중단점(추가 기능)

```text
break 18 if len(values) == 0
break examples/buggy_average.py:8 if result > 10
```

위치는 먼저 일치해야 하며, 해당 프레임의 전역·지역 이름으로 조건을 평가한 결과가 참일
때만 멈춘다. 조건 오류는 한 번 보고하고 대상 프로그램 실행은 계속한다.

### 조회와 삭제

```text
break                 # 목록
delete 18             # 현재 파일 18번 줄의 중단점
delete file.py:18     # 지정 파일·줄의 중단점
delete average        # 함수 중단점
delete #2             # 목록에 표시된 중단점 번호
```

## 5. 감시점

```text
watch counter
watch total / count
watch                 # 목록
delete counter
```

`watch EXPR`은 추가할 당시의 함수 코드 객체와 초깃값을 저장한다. 같은 함수의 이후 추적
이벤트에서 표현식의 타입 또는 `repr()` 값이 달라지면 멈춘다. 다른 함수에 같은 변수명이
있어도 감시하지 않으며, 이름이 잠시 존재하지 않으면 그 이벤트는 건너뛴다. 이는 Exercise
2가 요구하는 “조건의 값이 바뀌는 즉시 정지”와 존재하지 않는 변수 이름에 대한 주의를
반영한 동작이다.[^debugger-ex2]

## 6. 호출 스택과 프레임 선택

```text
where
up
print values
list
down
```

`where`의 `#0`은 실제 실행이 멈춘 최신 프레임이다. `up`과 `down`은 `print`, `locals`,
`list`, `break LINE`이 바라보는 프레임만 바꾼다. 실행 재개 명령은 실제로 멈춘 `#0`
프레임을 기준으로 한다. 프레임의 `f_back`은 호출자 프레임, `f_locals`와 `f_globals`는
각각 지역·전역 이름 공간을 가리킨다.[^python-frame]

## 7. 변수 변경

```text
assign count=10
assign message="fixed"
```

오른쪽은 선택한 프레임에서 Python 표현식으로 평가한다. CPython의 최적화 지역 변수는
단순히 `f_locals`를 수정하는 것만으로 즉시 반영되지 않을 수 있어, 구현은 CPython 내부
API `PyFrame_LocalsToFast`로 동기화를 시도한다. 따라서 다른 Python 구현에서는 변경이
보장되지 않는다.

## 8. 추천 실습

`examples/buggy_average.py`를 열고 실제 줄 번호를 확인한 뒤 실행한다.

```text
break average
continue
where
print values
next
```

관찰 예상:

1. `average()`에 전달된 `values`가 빈 목록이다.
2. `len(values)`는 `0`이다.
3. 나눗셈 줄을 실행하면 `ZeroDivisionError`가 발생한다.

이는 “빈 입력을 어떻게 처리할지 정하지 않은 결함 → 0인 분모 상태 → 외부에 보이는
예외”라는 원인-결과 사슬로 볼 수 있다. The Debugging Book은 결함(defect)이 잘못된
상태(fault)를 만들고 이것이 실패(failure)로 전파된다고 설명한다.[^intro]

## 9. 제한 사항과 주의

- 새 스레드는 자동으로 추적하지 않는다. `sys.settrace()`는 스레드별 설정이다.[^python-settrace]
- C로 구현된 내장 함수 내부의 Python 줄은 추적할 수 없다.
- `eval()`을 사용하는 `print`, `watch`, 조건부 중단점은 대상 프로그램과 같은 권한으로
  표현식을 실행한다. 신뢰할 수 없는 명령을 붙여 넣지 않는다.
- 비동기 태스크·멀티스레드·원격 디버깅·시간 여행 디버깅은 범위 밖이다.
- `repr()`이 같지만 내부 상태가 다른 객체 변경은 감시점이 놓칠 수 있다.

## 10. 참고 자료

[^intro]: [The Debugging Book — Introduction to Debugging](https://www.debuggingbook.org/html/Intro_Debugging.html)
[^debugger-ex2]: [The Debugging Book — How Debuggers Work, Exercise 2](https://www.debuggingbook.org/html/Debugger.html#Exercise-2:-More-Commands)
[^python-settrace]: [Python 표준 문서 — `sys.settrace()`](https://docs.python.org/3/library/sys.html#sys.settrace)
[^python-frame]: [Python 표준 문서 — Frame objects](https://docs.python.org/3/reference/datamodel.html#frame-objects)

