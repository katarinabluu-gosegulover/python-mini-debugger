# 재제출 수정 보고서

- 수정일: 2026-10-04 (Asia/Seoul)
- 대상: `BLOG_POST.md`

## 피드백 반영 내용

1. **상태와 정지 정책 구분**
   - 실행 상태를 `PAUSED`, `RUNNING`, `TERMINATED`로 정의했다.
   - `STEP`, `CONTINUE`, `NEXT`, `UNTIL`, `FINISH`는 `RUNNING` 상태에 붙는 정지
     정책으로 분리했다.
   - 명령, `line`/`return` 이벤트, 중단점, 감시점, 프로그램 종료에 따른 전이를 명시했다.
   - 실제 구현의 `_mode`는 두 개념을 문자열 하나로 평평하게 표현한다는 점도 밝혔다.

2. **이벤트 우선순위 구체화**
   - 중단점 → 감시점 → 실행 정책 순으로 검사하는 이유를 `next` 중 하위 함수 중단점을
     놓치지 않아야 한다는 실제 사례로 설명했다.

3. **구현 문제와 설계 선택 추가**
   - `next`가 하위 함수로 들어가는 문제와 프레임 동일성 비교
   - 파일이 다른 동일 줄 번호 문제와 절대 경로 정규화
   - 함수 정의 전 함수 중단점의 `NameError`와 예약 중단점
   - 감시 표현식의 프레임 충돌과 변경 가능한 객체 스냅샷
   - `_active_frame`과 `_selected_frame` 분리
   - 조건식 오류가 대상 프로그램을 종료하지 않도록 한 처리
   - `delete LINE`과 `delete #NUMBER`의 모호성 수정

4. **테스트 과정 보강**
   - 구현 메서드 단위 테스트가 아닌 실제 임시 스크립트와 명령 스트림을 사용한 통합
     테스트가 설계를 어떻게 변경했는지 설명했다.

## 참고 구현

- [`debugger.py`](debugger.py)
- [`tests/test_debugger.py`](tests/test_debugger.py)
- [Python `sys.settrace()` 문서](https://docs.python.org/3/library/sys.html#sys.settrace)
- [The Debugging Book — Exercise 2](https://www.debuggingbook.org/html/Debugger.html#Exercise-2:-More-Commands)

