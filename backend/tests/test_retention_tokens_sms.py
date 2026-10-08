"""OBS-011 / GDPR-007 (audyt 2026-09-28): retencja wygasłych tokenów, historii SMS i błędów JS.
Stare rekordy znikają, świeże i AKTYWNE (ważny refresh token = zalogowana sesja) zostają."""
import datetime

from sqlalchemy import select

from app import retention
from app.models import (ClientError, Company, Container, PasswordResetToken, RefreshToken,
                        SmsMessage, User, utcnow)


def test_purge_old_tokens_sms_client_errors(db_session):
    db = db_session
    now = utcnow()
    days = datetime.timedelta(days=1)
    uid = db.scalars(select(User)).first().id
    c = Container(company_id=db.scalars(select(Company)).first().id, container_no="RETN1234567")
    db.add(c)
    db.flush()
    db.add_all([
        RefreshToken(user_id=uid, jti="old", expires_at=now - 40 * days, revoked=True),
        RefreshToken(user_id=uid, jti="active", expires_at=now + 10 * days,
                     created_at=now - 400 * days),
        # odwołany, ale jeszcze nie wygasły — potrzebny do wykrycia ponownego użycia
        RefreshToken(user_id=uid, jti="revoked-live", expires_at=now + 5 * days, revoked=True),
        PasswordResetToken(user_id=uid, token_hash="old", expires_at=now - 40 * days),
        PasswordResetToken(user_id=uid, token_hash="fresh", expires_at=now + days / 24),
        SmsMessage(container_id=c.id, phone="600100200", created_at=now - 91 * days),
        SmsMessage(container_id=c.id, phone="600100201", created_at=now - 10 * days),
        ClientError(message="stary", created_at=now - 31 * days),
        ClientError(message="swiezy", created_at=now - days),
    ])
    db.commit()

    for fn in (retention.purge_expired_tokens, retention.purge_sms_messages,
               retention.purge_client_errors):
        fn(db)
    db.expire_all()

    assert sorted(db.scalars(select(RefreshToken.jti)).all()) == ["active", "revoked-live"]
    assert db.scalars(select(PasswordResetToken.token_hash)).all() == ["fresh"]
    assert db.scalars(select(SmsMessage.phone)).all() == ["600100201"]
    assert db.scalars(select(ClientError.message)).all() == ["swiezy"]


def test_retention_wired_into_daily_job():
    from app.jobs import build_jobs
    job = next(j for j in build_jobs() if j.name == "applog_retention")
    names = {f.__name__ for f in job.fns}
    assert {"purge_expired_tokens", "purge_sms_messages", "purge_client_errors"} <= names
