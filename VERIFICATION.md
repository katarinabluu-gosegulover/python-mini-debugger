# 검증 보고서

- 검증일: 2026-10-01 (Asia/Seoul)
- 검증 환경: Python 3.12.14, Windows 64-bit
- 외부 런타임 의존성: 없음(표준 라이브러리만 사용)

## 수행한 검사

```powershell
python -m unittest discover -s tests -v
python -m compileall -q debugger.py tests examples
python debugger.py --help
```

## 결과

- 통합 테스트: **8개 모두 통과**
- 구문/바이트코드 컴파일: **통과**
- CLI 인자 도움말: **정상 출력**
- 실제 예제 세션: `break average`로 함수 진입 시 정지하고 `print values`, `where`가
  올바른 값과 3단계 호출 스택을 출력함
- `C:\dev\New project\python-mini-debugger` 복사 후 동일 테스트: **8개 모두 통과**

## 테스트가 다루는 기능

1. `step`, `print`, `locals`, `continue`
2. 줄 중단점
3. 줄·함수·번호 중단점 삭제
4. 조건부 중단점
5. 함수 중단점, `next`, `where`, `up`, `down`, `finish`
6. `watch`
7. `until`
8. `assign`

## 알려진 한계

- 새 스레드는 자동 추적하지 않는다.
- `assign`의 즉시 반영은 CPython 내부 API에 의존한다.
- 감시점은 `(타입 이름, repr 값)`을 비교하므로 모든 내부 상태 변경을 잡지는 못한다.
- 운영용 디버거의 보안·성능·비동기 기능을 목표로 하지 않은 교육용 구현이다.

