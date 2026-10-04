# Python Mini Debugger

`sys.settrace()`로 직접 만든 교육용 대화형 Python 디버거다. The Debugging Book의
「How Debuggers Work」Exercise 2에서 요구하는 명령을 모두 구현했고, 추가 기능으로
조건부 중단점을 넣었다.

## 빠른 시작

Python 3.10 이상에서 외부 패키지 없이 실행된다.

```powershell
python debugger.py examples/buggy_average.py
```

첫 정지 후 아래처럼 입력해 볼 수 있다.

```text
(mini-debugger) break average
(mini-debugger) continue
(mini-debugger) where
(mini-debugger) print values
(mini-debugger) next
```

전체 사용법은 [MANUAL.md](MANUAL.md), 구현에서 배운 내용은
[게시된 블로그 글](https://katarinabluu-gosegulover.github.io/Hercent.github.io/posts/my-python-debugger/), 추가 기능의 구현 전 명세는
[FEATURE_SPEC.md](FEATURE_SPEC.md), 실행 검증 결과는 [VERIFICATION.md](VERIFICATION.md)에서
볼 수 있다. 피드백에 따른 블로그 보완 내역은 [REVISION_NOTES.md](REVISION_NOTES.md)에
정리했다.

## 구현 범위

- 기본: `step`, `continue`, `print`, `locals`, `list`, 줄 중단점, `delete`, `quit`
- Exercise 1: `assign`
- Exercise 2: 함수 중단점, `next`, `where`, `up`, `down`, `until`, `finish`, `watch`
- 추가 기능: `break LINE if CONDITION` 조건부 중단점
- 편의 기능: 고유 명령 접두사와 `history`

## 테스트

```powershell
python -m unittest discover -s tests -v
```

테스트는 실제 임시 Python 스크립트를 실행하고 명령 입력을 주입하는 통합 테스트다.

## 구조

```text
python-mini-debugger/
├── debugger.py                 # 디버거와 CLI
├── MANUAL.md                   # 사용자 매뉴얼
├── FEATURE_SPEC.md             # 구현 전 추가 기능 명세
├── VERIFICATION.md             # 테스트 및 실행 검증 보고서
├── REVISION_NOTES.md           # 피드백 반영 및 재제출 보고서
├── examples/
│   └── buggy_average.py        # 실습용 버그 프로그램
└── tests/
    └── test_debugger.py        # 통합 테스트 8개
```

## 참고 자료

- [The Debugging Book — Introduction to Debugging](https://www.debuggingbook.org/html/Intro_Debugging.html)
- [The Debugging Book — Tracing Executions](https://www.debuggingbook.org/html/Tracer.html)
- [The Debugging Book — How Debuggers Work](https://www.debuggingbook.org/html/Debugger.html)
- [Python 문서 — `sys.settrace()`](https://docs.python.org/3/library/sys.html#sys.settrace)
- [Python 문서 — 프레임 객체](https://docs.python.org/3/reference/datamodel.html#frame-objects)

## 제한 사항

이 프로젝트는 동작 원리를 학습하기 위한 디버거다. `sys.settrace()`가 현재 스레드에
설치되므로 새 스레드는 자동 추적하지 않으며, `assign`은 CPython의
`PyFrame_LocalsToFast`를 사용하는 구현 의존 기능이다. 운영 환경에서는 `pdb` 같은
검증된 도구를 권장한다.

