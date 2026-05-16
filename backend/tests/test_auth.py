from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("secret-pass-1")
    assert verify_password("secret-pass-1", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip():
    token = create_access_token(user_id="507f1f77bcf86cd799439011", email="u@example.com", name="User")
    payload = decode_access_token(token)
    assert payload["sub"] == "507f1f77bcf86cd799439011"
    assert payload["email"] == "u@example.com"
