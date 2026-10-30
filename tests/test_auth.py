from src import auth


def test_hash_and_verify():
    h = auth.hash_password("segretissima-1")
    assert h.startswith("scrypt$") and "segretissima" not in h
    assert auth.verify_password("segretissima-1", h)
    assert not auth.verify_password("sbagliata", h)
    assert auth.hash_password("segretissima-1") != h  # sale casuale


def test_verify_rejects_garbage_hash():
    assert not auth.verify_password("x", "non-un-hash")
    assert not auth.verify_password("x", auth.DUMMY_PASSWORD_HASH)


def test_normalize_email():
    assert auth.normalize_email("  Mario@Example.COM ") == "mario@example.com"
    for bad in ("", "senza-chiocciola", "a@b", "a b@c.it", "x" * 260 + "@a.it"):
        assert auth.normalize_email(bad) is None


def test_validate_password():
    assert auth.validate_password("breve") is not None
    assert auth.validate_password("a" * 500) is not None
    assert auth.validate_password("mario@example.com", "mario@example.com") is not None
    assert auth.validate_password("una-password-valida") is None


def test_unsubscribe_signature():
    sig = auth.unsubscribe_signature(5)
    assert auth.verify_unsubscribe_signature(5, sig)
    assert not auth.verify_unsubscribe_signature(6, sig)
    assert not auth.verify_unsubscribe_signature(5, "")
    assert auth.unsubscribe_url(5).startswith("https://gym.example.test/unsubscribe?u=5&t=")


def test_rate_limiter():
    rl = auth.RateLimiter(2, 60)
    assert rl.blocked("k") == 0
    rl.add("k"); rl.add("k")
    assert rl.blocked("k") > 0
    assert rl.blocked("altro") == 0
    rl.clear("k")
    assert rl.blocked("k") == 0
