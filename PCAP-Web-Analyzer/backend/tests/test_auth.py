import auth


def test_password_hash_roundtrip():
    h = auth.hash_password("s3cret")
    assert "$" in h
    assert auth.verify_password("s3cret", h)
    assert not auth.verify_password("wrong", h)


def test_token_roundtrip():
    tok = auth.make_token("user-123")
    assert auth.verify_token(tok) == "user-123"
    assert auth.verify_token(tok + "tamper") is None
    assert auth.verify_token("garbage") is None
