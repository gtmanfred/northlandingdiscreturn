import io
import uuid
import openpyxl
from datetime import date as _date
from sqlalchemy import select
from app.services.auth import create_access_token
from app.repositories.user import UserRepository
from app.models.disc import Disc
from app.models.pickup_event import SMSJob


def admin_headers(user_id: uuid.UUID) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


async def make_admin(db, email="admin@example.com", google_id="g-admin"):
    repo = UserRepository(db)
    user = await repo.create(name="Admin", email=email, google_id=google_id)
    user.is_admin = True
    await db.commit()
    return user


def _sheet(data_rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Current"
    ws.append(["North Landing Discs Database"])
    ws.append(["Sorted by ...", None, None, None, None, None, "Code: ..."])
    ws.append(["Name", "Phone", "Mfr", "Model", "Color", "Other",
               "Code", "Date found", "Date retuned", "Date contacted"])
    for r in data_rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _files(content):
    return {"file": ("discs.xlsx", content,
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


async def test_preview_returns_plan_and_writes_nothing(client, db):
    admin = await make_admin(db)
    content = _sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", "note",
         None, _date(2026, 6, 6), None, None],
    ])
    resp = await client.post("/discs/import/preview", files=_files(content),
                             headers=admin_headers(admin.id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"]["counts"]["created"] == 1
    assert body["staging_id"]
    # no discs created by preview
    discs = (await db.execute(select(Disc))).scalars().all()
    assert len(discs) == 0


async def test_preview_bad_file_422(client, db):
    admin = await make_admin(db)
    wb = openpyxl.Workbook()
    wb.active.title = "Other"
    buf = io.BytesIO()
    wb.save(buf)
    resp = await client.post("/discs/import/preview", files=_files(buf.getvalue()),
                             headers=admin_headers(admin.id))
    assert resp.status_code == 422


async def test_apply_commits_and_enqueues_sms(client, db):
    admin = await make_admin(db)
    content = _sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", "note",
         None, _date(2026, 6, 6), None, None],
    ])
    preview = await client.post("/discs/import/preview", files=_files(content),
                                headers=admin_headers(admin.id))
    staging_id = preview.json()["staging_id"]
    resp = await client.post(f"/discs/import/{staging_id}/apply",
                             headers=admin_headers(admin.id))
    assert resp.status_code == 200
    assert resp.json()["created"] == 1
    discs = (await db.execute(select(Disc))).scalars().all()
    assert len(discs) == 1
    jobs = (await db.execute(select(SMSJob))).scalars().all()
    assert len(jobs) == 2  # welcome + heads-up


async def test_apply_twice_is_409(client, db):
    admin = await make_admin(db)
    content = _sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", "note",
         None, _date(2026, 6, 6), None, None],
    ])
    staging_id = (await client.post("/discs/import/preview", files=_files(content),
                                    headers=admin_headers(admin.id))).json()["staging_id"]
    await client.post(f"/discs/import/{staging_id}/apply", headers=admin_headers(admin.id))
    again = await client.post(f"/discs/import/{staging_id}/apply",
                              headers=admin_headers(admin.id))
    assert again.status_code == 409


async def test_apply_unknown_id_404(client, db):
    admin = await make_admin(db)
    resp = await client.post(f"/discs/import/{uuid.uuid4()}/apply",
                             headers=admin_headers(admin.id))
    assert resp.status_code == 404


async def test_cancel_marks_canceled(client, db):
    admin = await make_admin(db)
    content = _sheet([
        ["Jane Doe", "404-951-8881", "Discraft", "Heat", "purple", "note",
         None, _date(2026, 6, 6), None, None],
    ])
    staging_id = (await client.post("/discs/import/preview", files=_files(content),
                                    headers=admin_headers(admin.id))).json()["staging_id"]
    resp = await client.post(f"/discs/import/{staging_id}/cancel",
                             headers=admin_headers(admin.id))
    assert resp.status_code == 200
    # applying a canceled import is rejected
    apply = await client.post(f"/discs/import/{staging_id}/apply",
                              headers=admin_headers(admin.id))
    assert apply.status_code == 409
