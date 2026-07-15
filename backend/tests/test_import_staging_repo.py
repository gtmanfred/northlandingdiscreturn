import uuid
from sqlalchemy import select
from app.repositories.import_staging import ImportStagingRepository
from app.repositories.user import UserRepository
from app.models.import_staging import ImportStaging


async def test_create_pending_and_get(db):
    repo = ImportStagingRepository(db)
    user_repo = UserRepository(db)
    admin = await user_repo.create(
        name="Admin One", email="admin1@example.com", google_id="google-admin1"
    )
    s = await repo.create_pending(
        created_by=admin.id, filename="a.xlsx", rows=[{"x": 1}], plan={"counts": {}},
    )
    fetched = await repo.get(s.id)
    assert fetched is not None
    assert fetched.status == "pending"
    assert fetched.filename == "a.xlsx"


async def test_create_pending_cancels_prior_pending_for_same_admin(db):
    repo = ImportStagingRepository(db)
    user_repo = UserRepository(db)
    admin = await user_repo.create(
        name="Admin Two", email="admin2@example.com", google_id="google-admin2"
    )
    first = await repo.create_pending(created_by=admin.id, filename="1.xlsx", rows=[], plan={})
    await repo.create_pending(created_by=admin.id, filename="2.xlsx", rows=[], plan={})
    refreshed = await repo.get(first.id)
    assert refreshed.status == "canceled"


async def test_create_pending_leaves_other_admins_alone(db):
    repo = ImportStagingRepository(db)
    user_repo = UserRepository(db)
    a = await user_repo.create(
        name="Admin Three", email="admin3@example.com", google_id="google-admin3"
    )
    b = await user_repo.create(
        name="Admin Four", email="admin4@example.com", google_id="google-admin4"
    )
    first = await repo.create_pending(created_by=a.id, filename="a.xlsx", rows=[], plan={})
    await repo.create_pending(created_by=b.id, filename="b.xlsx", rows=[], plan={})
    assert (await repo.get(first.id)).status == "pending"


async def test_set_status(db):
    repo = ImportStagingRepository(db)
    user_repo = UserRepository(db)
    admin = await user_repo.create(
        name="Admin Five", email="admin5@example.com", google_id="google-admin5"
    )
    s = await repo.create_pending(created_by=admin.id, filename="a.xlsx", rows=[], plan={})
    await repo.set_status(s, "applied")
    assert (await repo.get(s.id)).status == "applied"
