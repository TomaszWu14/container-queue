"""Mailer awizacji: wybór backendu, retry z backoffem, Graph sendMail, szablony PL/EN, log maili."""
import pytest

from app import avizo_workflow as wf
from app import mailer
from app.database import SessionLocal
from app.models import (AvizoItem, AvizoMailLog, AvizoRequest, AvizoStatus, Company, Container,
                        Forwarder)


def _mail(**kw):
    return mailer.Mail(to=["fw@example.com"], subject="S", html="<p>h</p>", text="t", **kw)


def test_backend_selection(monkeypatch):
    s = mailer.settings
    monkeypatch.setattr(s, "mail_backend", "")
    monkeypatch.setattr(s, "smtp_host", "")
    assert isinstance(mailer.get_sender(), mailer.ConsoleMailSender)
    monkeypatch.setattr(s, "smtp_host", "smtp.example.com")
    assert isinstance(mailer.get_sender(), mailer.SmtpMailSender)
    monkeypatch.setattr(s, "mail_backend", "graph")
    assert isinstance(mailer.get_sender(), mailer.GraphMailSender)
    monkeypatch.setattr(s, "mail_backend", "console")
    assert mailer.get_sender() is mailer.get_sender()   # jeden outbox



def test_console_on_production_fails_hard(monkeypatch):
    """Prod bez poczty: błąd → log maili „failed”, nie ciche „sent”."""
    monkeypatch.setattr(mailer.settings, "environment", "production")
    monkeypatch.setattr(mailer, "_sleep", lambda s: None)
    attempts, error = mailer.send_with_retry(mailer.ConsoleMailSender(), _mail())
    assert "nie jest skonfigurowana" in error

class Flaky:
    name = "flaky"

    def __init__(self, fails):
        self.fails, self.calls = fails, 0

    def send(self, mail):
        self.calls += 1
        if self.calls <= self.fails:
            raise ConnectionError("smtp down")


def test_retry_backoff(monkeypatch):
    slept = []
    monkeypatch.setattr(mailer, "_sleep", slept.append)
    assert mailer.send_with_retry(Flaky(2), _mail()) == (3, "")
    assert slept == [1, 4]
    slept.clear()
    attempts, error = mailer.send_with_retry(Flaky(99), _mail())
    assert attempts == 4 and "smtp down" in error and slept == [1, 4, 16]


def test_graph_sendmail_payload(monkeypatch):
    s = mailer.settings
    for key, val in (("ms_tenant_id", "t"), ("ms_client_id", "c"), ("ms_client_secret", "x"),
                     ("mail_sender", "awizacje@firma.pl")):
        monkeypatch.setattr(s, key, val)

    class App:
        def acquire_token_for_client(self, scopes):
            assert scopes == mailer.GRAPH_SCOPE
            return {"access_token": "AT"}

    monkeypatch.setattr(mailer, "_graph_app", App())
    calls = []

    class Resp:
        def __init__(self, code):
            self.status_code, self.text = code, "err"

    def post(url, headers, json, timeout):
        calls.append((url, headers, json))
        return Resp(202 if len(calls) == 1 else 403)

    monkeypatch.setattr(mailer.httpx, "post", post)
    mailer.GraphMailSender().send(_mail(cc=["cc@firma.pl"], reply_to="op@firma.pl"))
    url, headers, body = calls[0]
    assert url == "https://graph.microsoft.com/v1.0/users/awizacje@firma.pl/sendMail"
    assert headers["Authorization"] == "Bearer AT"
    msg = body["message"]
    assert msg["toRecipients"][0]["emailAddress"]["address"] == "fw@example.com"
    assert msg["ccRecipients"][0]["emailAddress"]["address"] == "cc@firma.pl"
    assert msg["replyTo"][0]["emailAddress"]["address"] == "op@firma.pl"
    with pytest.raises(RuntimeError, match="403"):
        mailer.GraphMailSender().send(_mail())


def test_graph_without_config_raises(monkeypatch):
    monkeypatch.setattr(mailer.settings, "ms_client_secret", "")
    with pytest.raises(RuntimeError, match="nie jest skonfigurowany"):
        mailer.GraphMailSender().send(_mail())


def _request(db, lang="pl"):
    co = db.query(Company).first()
    co.avizo_cc = "log1@firma.pl; log2@firma.pl"
    fw = db.query(Forwarder).first()
    fw.email = "fw@example.com"
    c = Container(container_no=f"MAIL{lang.upper()}0000001", company_id=co.id, vessel="EVER X")
    db.add(c)
    db.flush()
    req = AvizoRequest(token=f"mail-{lang}", company_id=co.id, forwarder_id=fw.id,
                       status=AvizoStatus.REJECTED, language=lang,
                       reject_comment="<script>alert(1)</script> zły termin")
    db.add(req)
    db.flush()
    db.add(AvizoItem(request_id=req.id, container_id=c.id))
    db.flush()
    db.refresh(req)
    return req


@pytest.mark.parametrize("lang,word", [("pl", "Komentarz"), ("en", "Comment")])
def test_templates_language_cc_and_escaping(client, lang, word):
    with SessionLocal() as db:
        req = _request(db, lang)
        mail = wf.build_mail(db, req, "rejected", "RAWTOKEN", "https://app.example", None)
        assert mail.to == ["fw@example.com"]
        assert mail.cc == ["log1@firma.pl", "log2@firma.pl"]
        assert word in mail.html and word in mail.text
        assert "https://app.example/avizo/RAWTOKEN" in mail.html
        assert "<script>" not in mail.html and "&lt;script&gt;" in mail.html
        assert f"MAIL{lang.upper()}0000001" in mail.text
        stage2 = wf.build_mail(db, req, "stage2", "RAW2", "https://app.example/", None)
        assert "https://app.example/avizo/driver/RAW2" in stage2.html


def test_deliver_logs_sent_and_failed(client, monkeypatch):
    with SessionLocal() as db:
        req = _request(db)
        db.commit()
        req_id = req.id
    monkeypatch.setattr(mailer.settings, "mail_backend", "console")
    wf.deliver(req_id, "stage1", _mail())
    monkeypatch.setattr(mailer, "get_sender", lambda: Flaky(99))
    monkeypatch.setattr(mailer, "_sleep", lambda s: None)
    wf.deliver(req_id, "stage2", _mail())
    with SessionLocal() as db:
        logs = db.query(AvizoMailLog).filter_by(request_id=req_id).order_by(AvizoMailLog.id).all()
        assert [(l.stage, l.status, l.backend, l.attempts) for l in logs] == [
            (1, "sent", "console", 1), (2, "failed", "flaky", 4)]
        assert "smtp down" in logs[1].error


def test_console_sender_prints_body_only_in_dev(monkeypatch, capsys, caplog):
    # audyt OBS-004: na stagingu (instancja po HTTP) treść maila z linkiem-tokenem trafiała do logów
    from app.config import settings
    mail = mailer.Mail(to=["a@example.com"], subject="Awizacja", html="<p>x</p>",
                       text="Link: /avizo/TAJNYTOKEN123")
    monkeypatch.setattr(settings, "environment", "staging")
    mailer.ConsoleMailSender().send(mail)
    out = capsys.readouterr().out + caplog.text
    assert "TAJNYTOKEN123" not in out and "a@example.com" not in out and "Awizacja" in caplog.text
    monkeypatch.setattr(settings, "environment", "dev")
    mailer.ConsoleMailSender().send(mail)
    assert "TAJNYTOKEN123" in capsys.readouterr().out   # dev/E2E: link dalej widoczny
