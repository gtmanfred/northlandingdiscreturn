# backend/tests/test_sms_opt_out.py
from app.repositories.sms_opt_out import SMSOptOutRepository


async def test_opt_out_then_is_opted_out(db):
    repo = SMSOptOutRepository(db)
    assert await repo.is_opted_out("+15551234567") is False
    await repo.opt_out("+15551234567")
    assert await repo.is_opted_out("+15551234567") is True


async def test_opt_out_is_idempotent(db):
    repo = SMSOptOutRepository(db)
    await repo.opt_out("+15551234567")
    await repo.opt_out("+15551234567")
    assert await repo.is_opted_out("+15551234567") is True


async def test_opt_in_removes_opt_out(db):
    repo = SMSOptOutRepository(db)
    await repo.opt_out("+15551234567")
    await repo.opt_in("+15551234567")
    assert await repo.is_opted_out("+15551234567") is False


async def test_opt_in_on_unknown_number_is_noop(db):
    repo = SMSOptOutRepository(db)
    await repo.opt_in("+15550000000")  # no error
    assert await repo.is_opted_out("+15550000000") is False
