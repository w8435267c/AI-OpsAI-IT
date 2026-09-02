from django.test import SimpleTestCase


class HealthLiveTests(SimpleTestCase):
    def test_live_endpoint_returns_success(self):
        response = self.client.get("/health/live")

        self.assertEqual(response.status_code, 200)

    def test_live_endpoint_returns_expected_payload(self):
        response = self.client.get("/health/live")

        self.assertEqual(response.json(), {"status": "ok", "service": "opsai-it"})

    def test_live_endpoint_rejects_non_get_requests(self):
        response = self.client.post("/health/live")

        self.assertEqual(response.status_code, 405)
