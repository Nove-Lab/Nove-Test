def count_up_to(n: int) -> list[int]:
    # Intentional off-by-one bug: should return [1, 2, ..., n] but stops at n-1.
    # This bug is the fixture's contract — do not "fix" it.
    return list(range(1, n))


def is_even(n: int) -> bool:
    return n % 2 == 0
