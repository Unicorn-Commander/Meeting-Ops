
def test_health_endpoints(client):
    response = client.get("/health")
    assert response.status_code == 200

    response = client.get("/api/status")
    assert response.status_code == 200
