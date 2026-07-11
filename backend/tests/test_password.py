from app.auth.password import hash_password, verify_password


def test_argon2id_password_hashing() -> None:
    password_hash = hash_password("correct horse battery staple")
    assert password_hash.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("incorrect", password_hash)
