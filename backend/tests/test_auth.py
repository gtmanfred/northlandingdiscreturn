from app.services.auth import create_access_token, decode_access_token


async def test_create_and_decode_token():
    token = create_access_token("user-123")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"


async def test_get_current_user_invalid_token(client):
    response = await client.get("/users/me", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


async def test_get_current_user_no_token(client):
    response = await client.get("/users/me")
    assert response.status_code in (401, 403)  # HTTPBearer returns 403 or 401 when no credentials
