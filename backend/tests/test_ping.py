def test_ping_ok(client):
    response = client.get("/ping/")
    assert response.status_code == 200
