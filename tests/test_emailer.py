import smtplib

from src import config, emailer


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.sent, self.started, self.logged = [], False, None
        FakeSMTP.instances.append(self)

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, context=None): self.started = True
    def login(self, u, p): self.logged = (u, p)
    def send_message(self, m): self.sent.append(m)


def _enable(monkeypatch, port=587):
    FakeSMTP.instances = []
    monkeypatch.setattr(config, "SMTP_ENABLED", True)
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(config, "SMTP_PORT", port)
    monkeypatch.setattr(config, "SMTP_USER", "u")
    monkeypatch.setattr(config, "SMTP_PASSWORD", "p")
    monkeypatch.setattr(config, "SMTP_FROM", "Gym <noreply@example.test>")
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)


def test_disabled_smtp_returns_false(monkeypatch):
    monkeypatch.setattr(config, "SMTP_ENABLED", False)
    assert emailer.send_email("a@b.it", "s", "b") is False


def test_send_uses_starttls_and_login(monkeypatch):
    _enable(monkeypatch)
    assert emailer.send_email("a@b.it", "Oggetto", "Corpo") is True
    smtp = FakeSMTP.instances[0]
    assert smtp.started and smtp.logged == ("u", "p")
    assert smtp.sent[0]["To"] == "a@b.it" and smtp.sent[0]["Subject"] == "Oggetto"


def test_failure_never_raises(monkeypatch):
    _enable(monkeypatch)
    def boom(*a, **k): raise OSError("rete giù")
    monkeypatch.setattr(smtplib, "SMTP", boom)
    assert emailer.send_email("a@b.it", "s", "b") is False


def test_newsletter_has_unsubscribe_headers_and_footer(monkeypatch):
    _enable(monkeypatch)
    assert emailer.send_newsletter_email("a@b.it", 7, "Novità", "Ciao") is True
    msg = FakeSMTP.instances[0].sent[0]
    assert "/unsubscribe?u=7&t=" in msg["List-Unsubscribe"]
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "/unsubscribe?u=7&t=" in msg.get_content()


def test_verification_and_reset_links(monkeypatch):
    _enable(monkeypatch)
    emailer.send_verification_email("a@b.it", "TOK1")
    emailer.send_password_reset_email("a@b.it", "TOK2")
    assert "https://gym.example.test/#verify=TOK1" in FakeSMTP.instances[0].sent[0].get_content()
    assert "https://gym.example.test/#reset=TOK2" in FakeSMTP.instances[1].sent[0].get_content()
