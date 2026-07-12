from app.security import hash_password, verify_password


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("correct-horse-battery")
    second = hash_password("correct-horse-battery")

    assert first != second
    assert "correct-horse-battery" not in first
    assert verify_password("correct-horse-battery", first)
    assert not verify_password("wrong-password", first)


def test_password_hash_rejects_short_password():
    try:
        hash_password("short")
    except ValueError as exc:
        assert "8 characters" in str(exc)
    else:
        raise AssertionError("short password was accepted")
