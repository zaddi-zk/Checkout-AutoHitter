"""
Payment & 3DS bypass using selenium-wire interceptors.

Intercepts both payment endpoints and 3DS (ACS/challenge) endpoints at the
network level and returns mock success payloads, so checkout completes without
a real charge or an OTP prompt. Only active when the driver is a selenium-wire
driver (the engine always creates one).
"""

import json
import re
import time
from typing import Any, Dict, List


class PaymentBypass:
    """Intercepts payment and 3DS requests and mocks successful responses."""

    def __init__(self, driver: Any, mock_success: bool = True):
        self.driver = driver
        self.mock_success = mock_success
        self.intercepted: List[Dict[str, Any]] = []
        self.enabled = False

        self._payment_patterns = [
            r"/charge",
            r"/payment",
            r"/checkout",
            r"/create\-payment",
            r"/pay",
            r"/confirm",
            r"/order",
            r"/process",
            r"/submit",
        ]
        self._threeds_patterns = [
            r"/acs",
            r"/challenge",
            r"/3ds",
            r"/three\-ds",
            r"/authentication",
            r"/authenticate",
            r"/verify",
            r"/callback",
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enable(self) -> bool:
        """Install selenium-wire request/response interceptors."""
        driver = getattr(self.driver, "driver", self.driver)
        try:
            if not hasattr(driver, "request_interceptor"):
                return False
            driver.request_interceptor = self._request_interceptor
            driver.response_interceptor = self._response_interceptor
            self.enabled = True
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # URL matching
    # ------------------------------------------------------------------

    def _is_payment_request(self, url: str) -> bool:
        url = (url or "").lower()
        return any(re.search(p, url) for p in self._payment_patterns)

    def _is_3ds_request(self, url: str) -> bool:
        url = (url or "").lower()
        return any(re.search(p, url) for p in self._threeds_patterns)

    # ------------------------------------------------------------------
    # Interceptors
    # ------------------------------------------------------------------

    def _request_interceptor(self, request) -> None:
        """Short-circuit payment/3DS requests with a mock response (no network)."""
        if not self.mock_success:
            return
        try:
            url = request.url or ""
            if self._is_payment_request(url):
                self.intercepted.append({"kind": "payment", "url": url, "time": time.time()})
                request.create_response(
                    status_code=200,
                    headers={"Content-Type": "application/json"},
                    body=self._mock_payment_payload(),
                )
            elif self._is_3ds_request(url):
                self.intercepted.append({"kind": "3ds", "url": url, "time": time.time()})
                request.create_response(
                    status_code=200,
                    headers={"Content-Type": "application/json"},
                    body=self._mock_3ds_payload(),
                )
        except Exception:
            pass

    def _response_interceptor(self, request, response) -> None:
        """Rewrite already-sent payment/3DS responses to mock success."""
        if not self.mock_success:
            return
        try:
            url = request.url or ""
            if self._is_payment_request(url):
                self._mock_payment_response(response)
            elif self._is_3ds_request(url):
                self._mock_3ds_response(response)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Payloads
    # ------------------------------------------------------------------

    def _mock_payment_payload(self) -> bytes:
        payload = {
            "success": True,
            "orderId": f"MOCK-{int(time.time() * 1000)}",
            "message": "Payment succeeded (mocked)",
        }
        return json.dumps(payload).encode("utf-8")

    def _mock_3ds_payload(self) -> bytes:
        payload = {
            "thd": "0",
            "status": "success",
            "eci": "00",
            "challenge_success": "true",
            "transaction_id": f"3DS-{int(time.time() * 1000)}",
        }
        return json.dumps(payload).encode("utf-8")

    def _mock_payment_response(self, response) -> None:
        response.body = self._mock_payment_payload()
        response.status_code = 200
        try:
            response.headers["Content-Type"] = "application/json"
        except Exception:
            pass
        print("[✅] Payment response mocked as success")

    def _mock_3ds_response(self, response) -> None:
        response.body = self._mock_3ds_payload()
        response.status_code = 200
        try:
            response.headers["Content-Type"] = "application/json"
        except Exception:
            pass
        print("[✅] 3DS challenge mocked as success")

