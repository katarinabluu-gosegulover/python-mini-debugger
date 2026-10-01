# 추가 기능 사전 명세: 조건부 중단점

> 이 문서는 구현 전에 명령 이름·사용법·동작을 확정하기 위한 명세다.

## 선택한 기능

일반 줄 중단점에 Python 조건식을 붙이는 **조건부 중단점**을 추가한다.

## 명령 이름과 사용법

```text
break LINE if CONDITION
break FILE:LINE if CONDITION
```

예:

```text
break 24 if total < 0
break examples/buggy_average.py:18 if len(values) == 0
```

## 동작

1. 실행 위치가 지정한 파일·줄에 도달한다.
2. 그 프레임의 전역 변수와 지역 변수를 사용해 `CONDITION`을 평가한다.
3. 결과가 참일 때만 실행을 멈춘다.
4. 결과가 거짓이면 계속 실행한다.
5. 조건 평가 중 예외가 나면 프로그램을 중단하지 않고 오류를 한 번 알린 뒤 계속 실행한다.

## 선택 근거

반복문에서 특정 반복만 관찰할 수 있어 `until`·`watch`와 다른 실용성이 있고, 프레임의
`f_globals`/`f_locals`가 표현식 평가에 어떻게 쓰이는지 직접 학습할 수 있다.

## 수용 기준

- 조건이 거짓인 동안 정지하지 않는다.
- 조건이 처음 참이 된 줄에서 정지한다.
- `delete LINE` 또는 `delete FILE:LINE`으로 삭제할 수 있다.
- `break` 목록에 조건식이 함께 표시된다.

