from sqlalchemy import select
from app.models.import_staging import ImportStaging
from app.repositories.user import UserRepository


async def test_import_staging_persists_jsonb(db):
    user_repo = UserRepository(db)
    user = await user_repo.create(
        name="Importer", email="importer@example.com", google_id="google-importer"
    )
    row = ImportStaging(
        created_by=user.id,
        filename="discs.xlsx",
        status="pending",
        rows=[{"row_number": 4, "model": "Teebird"}],
        plan={"counts": {"created": 1}},
    )
    db.add(row)
    await db.flush()
    fetched = (await db.execute(select(ImportStaging))).scalar_one()
    assert fetched.status == "pending"
    assert fetched.rows[0]["model"] == "Teebird"
    assert fetched.plan["counts"]["created"] == 1
    assert fetched.created_at is not None
