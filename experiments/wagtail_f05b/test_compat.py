"""独立 F05A 配置进程下，新服务仍必须拒绝。"""

from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from experiments.wagtail_f05a.tests import snapshot

from . import tests as eligibility_tests
from .services import ApprovalRejected, approve_review


class OriginalConfigTests(TestCase):
    login = eligibility_tests.EligibilityTests.login
    data = eligibility_tests.EligibilityTests.data
    url = eligibility_tests.EligibilityTests.url
    post_submit = eligibility_tests.EligibilityTests.post_submit
    setUp = eligibility_tests.EligibilityTests.setUp
    tearDown = eligibility_tests.EligibilityTests.tearDown

    def test_service_is_disabled_in_f05a(self):
        before = snapshot()
        with self.assertRaises(ApprovalRejected) as error:
            approve_review(self.ts_id, self.reviewer)
        self.assertEqual(error.exception.code, "configuration_disabled")
        self.assertEqual(snapshot(), before)

    def test_http_routes_and_button_absent_in_f05a(self):
        self.login("super")
        before = snapshot()
        for name in ("f05b_review", "f05b_approve"):
            with self.assertRaises(NoReverseMatch):
                reverse(name, args=[self.ts_id])
        response = self.client.post(
            f"/cms/f05b/tasks/{self.ts_id}/approve/",
            {
                "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            },
        )
        self.assertEqual(response.status_code, 404)
        page = self.client.get(self.url("list"))
        self.assertNotContains(page, "审核并批准")
        self.assertEqual(snapshot(), before)
