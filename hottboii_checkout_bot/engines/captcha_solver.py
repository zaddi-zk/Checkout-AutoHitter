# engines/captcha_solver.py
"""Real CAPTCHA solving via the 2Captcha API.

Supports reCAPTCHA v2, hCaptcha, Cloudflare Turnstile, FunCaptcha (Arkose)
and legacy image CAPTCHAs. The classic 2Captcha flow is:

    submit  -> GET https://2captcha.com/in.php   -> {"status":1,"request":captcha_id}
    poll    -> GET https://2captcha.com/res.php?action=get -> {"status":1,"request":token}
"""

import re
import time
import logging

import requests
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)

IN_URL = "https://2captcha.com/in.php"
RES_URL = "https://2captcha.com/res.php"

AZAPI_IN_URL = "https://api.azapi.ai/captcha/solve"
AZAPI_RES_URL = "https://api.azapi.ai/captcha/result"

_PROVIDER_MARKERS = {
    "recaptcha": ["g-recaptcha", "recaptcha", "google.com/recaptcha"],
    "hcaptcha": ["hcaptcha", "h-captcha"],
    "turnstile": ["cf-turnstile", "challenges.cloudflare.com", "turnstile"],
    "funcaptcha": ["funcaptcha", "arkose", "tile-api.one"],
}


def detect_captcha_provider(driver) -> str:
    """Return which CAPTCHA provider is present on the page, or ''."""
    page_src = ""
    try:
        page_src = (driver.page_source or "").lower()
    except Exception:
        pass

    for provider, markers in _PROVIDER_MARKERS.items():
        if any(m in page_src for m in markers):
            return provider

    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
    except Exception:
        iframes = []
    for frame in iframes:
        try:
            src = (frame.get_attribute("src") or "").lower()
        except Exception:
            continue
        for provider, markers in _PROVIDER_MARKERS.items():
            if any(m in src for m in markers):
                return provider
    return ""


def extract_sitekey(driver, provider: str) -> str:
    """Pull the sitekey out of the page DOM for a given provider."""
    page_src = ""
    try:
        page_src = driver.page_source or ""
    except Exception:
        pass

    if provider == "recaptcha":
        patterns = [
            r'data-sitekey\s*=\s*["\']([^"\']{20,})["\']',
            r'googlekey\s*[=:]\s*["\']([^"\']{20,})["\']',
            r'[?&]k\s*=\s*([A-Za-z0-9_-]{20,})',
        ]
    elif provider in ("hcaptcha", "turnstile"):
        patterns = [
            r'data-sitekey\s*=\s*["\']([^"\']{20,})["\']',
            r'sitekey\s*[=:]\s*["\']([^"\']{20,})["\']',
            r'sitekey\s*[=:]\s*([A-Za-z0-9_-]{20,})',
        ]
    elif provider == "funcaptcha":
        patterns = [
            r'data-pkey\s*=\s*["\']([^"\']{10,})["\']',
            r'public_key\s*[=:]\s*["\']([^"\']{10,})["\']',
            r'pkey\s*[=:]\s*["\']([^"\']{10,})["\']',
        ]
    else:
        return ""

    for pat in patterns:
        m = re.search(pat, page_src)
        if m:
            return m.group(1).strip()
    return ""


def _page_url(driver) -> str:
    try:
        return driver.current_url or ""
    except Exception:
        return ""


def _submit(api_key: str, payload: dict) -> str:
    payload = dict(payload)
    payload.update({"key": api_key, "json": 1})
    try:
        resp = requests.get(IN_URL, params=payload, timeout=20)
        data = resp.json()
    except Exception:
        return ""
    if data.get("status") != 1:
        return ""
    return str(data.get("request", ""))


def _poll(api_key: str, captcha_id: str, timeout: float = 90.0) -> str:
    if not captcha_id:
        return ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(5)
        try:
            resp = requests.get(
                RES_URL,
                params={"key": api_key, "action": "get", "id": captcha_id, "json": 1},
                timeout=20,
            )
            data = resp.json()
            if data.get("status") == 1:
                return str(data.get("request", ""))
        except Exception:
            continue
    return ""


def solve_recaptcha_v2(driver, sitekey: str, page_url: str, api_key: str, timeout: float = 90.0) -> str:
    captcha_id = _submit(api_key, {"method": "userrecaptcha", "googlekey": sitekey, "pageurl": page_url})
    return _poll(api_key, captcha_id, timeout)


def solve_hcaptcha(driver, sitekey: str, page_url: str, api_key: str, timeout: float = 90.0) -> str:
    captcha_id = _submit(api_key, {"method": "hcaptcha", "sitekey": sitekey, "pageurl": page_url})
    return _poll(api_key, captcha_id, timeout)


def solve_turnstile(driver, sitekey: str, page_url: str, api_key: str, timeout: float = 90.0) -> str:
    captcha_id = _submit(api_key, {"method": "turnstile", "sitekey": sitekey, "pageurl": page_url})
    return _poll(api_key, captcha_id, timeout)


def solve_fun_captcha(driver, pkey: str, page_url: str, api_key: str, timeout: float = 90.0) -> str:
    captcha_id = _submit(
        api_key,
        {"method": "funcaptcha", "publickey": pkey, "pageurl": page_url},
    )
    return _poll(api_key, captcha_id, timeout)


def solve_image_captcha_2captcha(screenshot_b64: str, api_key: str, timeout: float = 90.0) -> str:
    captcha_id = _submit(api_key, {"method": "base64", "body": screenshot_b64})
    return _poll(api_key, captcha_id, timeout)


def solve_image_captcha_azapi(screenshot_b64: str, api_key: str, timeout: float = 60.0) -> str:
    try:
        resp = requests.post(
            AZAPI_IN_URL,
            data={"method": "base64", "body": screenshot_b64, "key": api_key, "json": 1},
            timeout=20,
        )
        data = resp.json()
        if data.get("status") != 1:
            return ""
        captcha_id = str(data.get("request", ""))
        if not captcha_id:
            return ""
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(5)
            res = requests.get(
                AZAPI_RES_URL,
                params={"key": api_key, "id": captcha_id, "json": 1},
                timeout=20,
            )
            result = res.json()
            if result.get("status") == 1:
                return str(result.get("request", ""))
    except Exception:
        pass
    return ""


def inject_token(driver, token: str, provider: str) -> bool:
    """Inject a solved token into the page's hidden response fields."""
    if not token:
        return False

    if provider == "recaptcha":
        js = """
        var t = arguments[0];
        var els = document.querySelectorAll(
            'textarea[id^="g-recaptcha-response"], textarea[name="g-recaptcha-response"], ' +
            'input[name="g-recaptcha-response"]'
        );
        for (var i = 0; i < els.length; i++) {
            els[i].value = t;
            els[i].innerHTML = t;
            els[i].dispatchEvent(new Event('input', {bubbles:true}));
            els[i].dispatchEvent(new Event('change', {bubbles:true}));
        }
        """
    elif provider == "hcaptcha":
        js = """
        var t = arguments[0];
        var els = document.querySelectorAll(
            'textarea[name="h-captcha-response"], input[name="h-captcha-response"]'
        );
        for (var i = 0; i < els.length; i++) {
            els[i].value = t;
            els[i].innerHTML = t;
            els[i].dispatchEvent(new Event('input', {bubbles:true}));
            els[i].dispatchEvent(new Event('change', {bubbles:true}));
        }
        """
    elif provider == "turnstile":
        js = """
        var t = arguments[0];
        var els = document.querySelectorAll(
            'input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]'
        );
        for (var i = 0; i < els.length; i++) {
            els[i].value = t;
            els[i].dispatchEvent(new Event('input', {bubbles:true}));
            els[i].dispatchEvent(new Event('change', {bubbles:true}));
        }
        """
    else:
        js = None

    if not js:
        return False

    try:
        driver.execute_script(js, token)
        time.sleep(0.5)
        return True
    except Exception:
        return False


def solve_captcha(
    driver,
    api_key: str,
    provider_hint: str = "",
    timeout: float = 90.0,
) -> bool:
    """Detect, solve and inject the CAPTCHA currently on the page.

    Returns True if a token was solved and injected, False otherwise.
    """
    if not api_key:
        return False

    provider = provider_hint or detect_captcha_provider(driver)
    if not provider:
        return False

    page_url = _page_url(driver)
    sitekey = extract_sitekey(driver, provider)

    if provider == "image":
        try:
            screenshot = driver.get_screenshot_as_base64()
        except Exception:
            screenshot = None
        if not screenshot:
            return False
        token = solve_image_captcha_2captcha(screenshot, api_key, timeout)
        if not token:
            token = solve_image_captcha_azapi(screenshot, api_key, timeout)
    else:
        if not sitekey:
            return False
        if provider == "recaptcha":
            token = solve_recaptcha_v2(driver, sitekey, page_url, api_key, timeout)
        elif provider == "hcaptcha":
            token = solve_hcaptcha(driver, sitekey, page_url, api_key, timeout)
        elif provider == "turnstile":
            token = solve_turnstile(driver, sitekey, page_url, api_key, timeout)
        elif provider == "funcaptcha":
            token = solve_fun_captcha(driver, sitekey, page_url, api_key, timeout)
        else:
            return False

    if not token:
        return False
    return inject_token(driver, token, provider)
