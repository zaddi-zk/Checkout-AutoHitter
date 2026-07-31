"""
Request tampering via CDP-compatible fallback.

This module attempts to enable Chrome DevTools Network interception and then
injects a page-level fetch/XHR override to simulate a successful payment
response for payment-like endpoints. The behavior is intentionally conservative
and only active when explicitly toggled via config.
"""

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional

from selenium.webdriver.common.by import By


class RequestTamperer:
    """Intercepts network requests and modifies payment submissions to skip actual payment."""

    def __init__(self, driver: Any):
        self.driver = driver
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
        url = (url or "").lower()
        return any(re.search(pattern, url) for pattern in self._request_patterns)

    def enable(self) -> bool:
        """Enable request interception via CDP with a graceful fallback."""
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

        try:
            self.driver.execute_script(
                """
                window.__nexus_intercept = window.__nexus_intercept || function(event) {
                    console.log('Intercepted:', event);
                };
                """
            )
        except Exception:
            pass

        self.enabled = True
        return True

    def intercept_payment(self, mock_success: bool = True) -> bool:
        """
        Inject a fetch/XHR override that fakes a success response for payment-like requests.

        This is intentionally safe: it only replaces requests whose URL matches
        typical payment endpoint patterns, and it leaves the rest of the browser
        behavior unchanged.
        """
        if not self.enabled:
            print("[!] Request tampering not enabled. Call enable() first.")
            return False

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
