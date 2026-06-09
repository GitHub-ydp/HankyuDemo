"""测试辅助：注册并取 Bearer 头。"""


def register(client, email, password="pw123456", name="Tester"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": name},
    )


def login_headers(client, email, password="pw123456"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}
