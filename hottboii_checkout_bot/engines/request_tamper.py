"""
Request tampering – selenium-wire payment interception + JS fallback.

Primary path uses selenium-wire's driver-level request/response interceptors to
mock a successful payment response for payment-like endpoints. When the driver
is a plain Selenium driver (or selenium-wire is unavailable), a page-level
fetch/XHR override is injected as a fallback. Behavior is intentionally
conservative and only active when explicitly toggled via config.
"""

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional

from selenium.webdriver.common.by import By


def looks_like_payment_request(url: str) -> bool:
    """Check if a URL matches typical payment endpoint patterns."""
    url = (url or "").lower()
    patterns = [
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
    return any(re.search(pattern, url) for pattern in patterns)


class RequestTamperer:
    """Intercepts network requests and mocks payment submissions to skip actual payment."""

    def __init__(self, driver: Any, mock_success: bool = True):
        self.driver = driver
        self.mock_success = mock_success
        self.intercepted_requests: List[Dict[str, Any]] = []
        self.enabled = False
        self._request_patterns = [
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

    def _looks_like_payment_request(self, url: str) -> bool:
        return looks_like_payment_request(url)

    def _mock_payload(self, prefix: str) -> bytes:
        payload = {
            "success": True,
            "orderId": f"{prefix}-{int(time.time() * 1000)}",
            "message": "Payment succeeded (mocked)",
        }
        return json.dumps(payload).encode("utf-8")

    # ------------------------------------------------------------------
    # selenium-wire path
    # ------------------------------------------------------------------

    def enable(self) -> bool:
        """Enable interception via selenium-wire (if available) or CDP fallback."""
        wire_ok = self.enable_wire_interception()
        if wire_ok:
            return True
        try:
            self.driver.execute_cdp_cmd("Network.enable", {})
        except Exception:
            pass
        try:
            self.driver.execute_cdp_cmd(
                "Network.setRequestInterception",
                {"patterns": [{"urlPattern": "*"}]},
            )
        except Exception:
            pass
        self.enabled = True
        return True

    def enable_wire_interception(self) -> bool:
        """Install selenium-wire request/response interceptors."""
        driver = getattr(self.driver, "driver", self.driver)
        try:
            if not hasattr(driver, "request_interceptor"):
                return False
        except Exception:
            return False

        try:
            driver.request_interceptor = self._wire_request_interceptor
            driver.response_interceptor = self._wire_response_interceptor
            self.enabled = True
            return True
        except Exception:
            return False

    def _wire_request_interceptor(self, request) -> None:
        """Log payment-like outgoing requests (selenium-wire)."""
        try:
            url = request.url or ""
            if self._looks_like_payment_request(url):
                self.intercepted_requests.append(
                    {"url": url, "method": getattr(request, "method", "?"), "time": time.time()}
                )
        except Exception:
            pass

    def _wire_response_interceptor(self, request, response) -> None:
        """Replace payment responses with a mock success payload (selenium-wire)."""
        if not self.mock_success:
            return
        try:
            url = request.url or ""
            if not self._looks_like_payment_request(url):
                return
            body = self._mock_payload("WIRE")
            response.body = body
            response.status_code = 200
            try:
                response.headers["Content-Type"] = "application/json"
            except Exception:
                pass
            try:
                response.headers["Access-Control-Allow-Origin"] = "*"
            except Exception:
                pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # JS fetch/XHR fallback (plain Selenium drivers)
    # ------------------------------------------------------------------

    def intercept_payment(self, mock_success: bool = True) -> bool:
        """
        Inject a fetch/XHR override that fakes a success response for payment-like requests.

        This is intentionally safe: it only replaces requests whose URL matches
        typical payment endpoint patterns, and it leaves the rest of the browser
        behavior unchanged. For selenium-wire drivers this is a no-op (the wire
        interceptors already handle it).
        """
        if not self.enabled:
            print("[!] Request tampering not enabled. Call enable() first.")
            return False

        driver = getattr(self.driver, "driver", self.driver)
        if hasattr(driver, "response_interceptor"):
            return True  # selenium-wire path already active

        js = """
        (function() {
            const paymentPatterns = %s;
            const orderId = 'MOCK-' + Date.now();

            const looksLikePayment = function(url) {
                const value = (url || '').toLowerCase();
                return paymentPatterns.some(function(pattern) {
                    return new RegExp(pattern, 'i').test(value);
                });
            };

            const mockPayload = function(prefix) {
                return JSON.stringify({
                    success: true,
                    orderId: prefix + '-' + Date.now(),
                    message: 'Payment succeeded (mocked)'
                });
            };

            if (!window.__requestTamperPatched) {
                const origFetch = window.fetch;
                window.fetch = function(url, options) {
                    if (looksLikePayment(String(url || ''))) {
                        window.__requestTamperLastUrl = String(url || '');
                        console.log('[RequestTamper] Intercepted fetch payment request:', url);
                        if (%s) {
                            return Promise.resolve(new Response(mockPayload('FETCH'), {
                                status: 200,
                                statusText: 'OK',
                                headers: { 'Content-Type': 'application/json' }
                            }));
                        }
                    }
                    return origFetch.apply(this, arguments);
                };

                const origXHR = window.XMLHttpRequest;
                window.XMLHttpRequest = function() {
                    const xhr = new origXHR();
                    const origOpen = xhr.open;
                    const origSend = xhr.send;

                    xhr.open = function(method, url, async, user, password) {
                        this.__tamperUrl = String(url || '');
                        this.__tamperMethod = String(method || 'GET');
                        return origOpen.apply(this, arguments);
                    };

                    xhr.send = function(body) {
                        if (looksLikePayment(this.__tamperUrl || '')) {
                            window.__requestTamperLastUrl = this.__tamperUrl;
                            console.log('[RequestTamper] Intercepted XHR payment request:', this.__tamperUrl);
                            if (%s) {
                                const onReady = function() {
                                    this.readyState = 4;
                                    this.status = 200;
                                    this.statusText = 'OK';
                                    this.responseText = mockPayload('XHR');
                                    this.response = this.responseText;
                                    if (typeof this.onreadystatechange === 'function') {
                                        this.onreadystatechange(new ProgressEvent('readystatechange'));
                                    }
                                    if (typeof this.onload === 'function') {
                                        this.onload(new ProgressEvent('load'));
                                    }
                                }.bind(this);
                                window.setTimeout(onReady, 0);
                                return;
                            }
                        }
                        return origSend.apply(this, arguments);
                    };
                    return xhr;
                };

                window.__requestTamperPatched = true;
            }
        })();
        """ % (
            json.dumps(self._request_patterns),
            str(bool(mock_success)).lower(),
            str(bool(mock_success)).lower(),
        )

        try:
            self.driver.execute_script(js)
            print("[+] Payment request interception injected (fetch & XHR).")
            return True
        except Exception as e:
            print(f"[!] Failed to inject interception: {e}")
            return False

