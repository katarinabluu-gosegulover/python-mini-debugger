"""디버거 연습용: 빈 목록 처리 버그가 있는 평균 계산기."""


def total(values: list[float]) -> float:
    result = 0.0
    for value in values:
        result += value
    return result


def average(values: list[float]) -> float:
    # 의도적으로 남겨 둔 버그: 빈 목록이면 ZeroDivisionError가 발생한다.
    return total(values) / len(values)


def main() -> None:
    samples: list[float] = []
    print(average(samples))


if __name__ == "__main__":
    main()

