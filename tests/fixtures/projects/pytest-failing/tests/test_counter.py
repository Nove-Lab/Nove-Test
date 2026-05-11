from pytest_failing.counter import count_up_to, is_even


def test_count_up_to_includes_endpoint() -> None:
    # Exposes the intentional off-by-one bug in count_up_to.
    # Expected to FAIL: count_up_to(5) returns [1,2,3,4] instead of [1,2,3,4,5].
    assert count_up_to(5) == [1, 2, 3, 4, 5]


def test_count_up_to_starts_at_one() -> None:
    result = count_up_to(5)
    assert result[0] == 1


def test_is_even_true() -> None:
    assert is_even(4) is True


def test_is_even_false() -> None:
    assert is_even(7) is False
