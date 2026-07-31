import time
from typing import Any, Callable, Dict, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


def normalize_proxy(proxy: str) -> str:
    proxy = proxy.strip()
    if proxy.startswith("https://"):
        proxy = "http://" + proxy[8:]
    if not proxy.startswith("http://"):
        proxy = "http://" + proxy
    return proxy


def init_driver(headless: bool, proxy: Optional[str] = None) -> webdriver.Chrome:
    options: Any = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors")
    options.add_argument("--disable-web-security")
    options.add_argument("--allow-running-insecure-content")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    try:
        from config import BURP_ENABLED, BURP_PROXY
        if BURP_ENABLED and BURP_PROXY:
            options.add_argument(f"--proxy-server={BURP_PROXY}")
        elif proxy:
            options.add_argument(f"--proxy-server={normalize_proxy(proxy)}")
    except Exception:
        if proxy:
            options.add_argument(f"--proxy-server={normalize_proxy(proxy)}")

    if headless:
        options.add_argument("--headless")
        options.add_argument("--window-size=1920,1080")

    driver: Any = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
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


def wait_for_captcha(
    driver: webdriver.Chrome,
    send_update: Callable[[str], Any],
    captcha_handler: Optional[Callable[..., Any]] = None,
    max_wait_seconds: Optional[float] = None,
    api_key: str = "",
    captcha_solve_timeout_seconds: float = 60.0,
) -> bool:
    """Detect CAPTCHA and solve automatically using azapi.ai (when api_key is set).

    If api_key is missing, falls back to `captcha_handler` (manual debug/UI) if provided.
    """

    # Fallback: if api_key is empty, try loading from config
    if not api_key:
        try:
            from config import CAPTCHA_API_KEY as _key
            api_key = _key or ""
        except ImportError:
            pass

    start = time.time()

    while True:
        if _captcha_signals_present(driver):
            send_update("🧩 CAPTCHA detected! Solving automatically...")

            solution: Optional[str] = None
            api_was_set = bool(api_key)
            if api_key:
                solution = solve_captcha_with_azapi(driver, api_key, timeout_seconds=captcha_solve_timeout_seconds)

            if solution:
                # Fill solution into likely input fields
                from selenium.webdriver.common.keys import Keys

                filled = False
                input_selectors = [
                    "input[name*='captcha' i]",
                    "input[id*='captcha' i]",
                    "textarea[name*='captcha' i]",
                    "input[aria-label*='captcha' i]",
                    "input[placeholder*='captcha' i]",
                ]

                for css in input_selectors:
                    try:
                        inp = driver.find_element(By.CSS_SELECTOR, css)
                        if inp and inp.is_displayed():
                            inp.clear()
                            inp.send_keys(solution)
                            filled = True
                            break
                    except Exception:
                        continue

                if not filled:
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
                                    filled = True
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass

                if filled:
                    # Submit
                    submitted = False
                    for submit_sel in [
                        "button[type='submit']",
                        "input[type='submit']",
                        "button[id*='submit' i]",
                    ]:
                        try:
                            btn = driver.find_element(By.CSS_SELECTOR, submit_sel)
                            if btn and btn.is_displayed() and btn.is_enabled():
                                btn.click()
                                submitted = True
                                break
                        except Exception:
                            continue

                    if not submitted:
                        try:
                            body = driver.switch_to.active_element
                            body.send_keys(Keys.ENTER)
                        except Exception:
                            pass

                send_update("✅ CAPTCHA solution submitted (azapi).")
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

            if api_was_set:
                send_update("⚠️ CAPTCHA solver failed — API key may be invalid or low balance")
            else:
                send_update("⚠️ CAPTCHA API key not set — add CAPTCHA_API_KEY to .env")
            return True

        if max_wait_seconds is None:
            return False

        if time.time() - start >= max_wait_seconds:
            return False

        time.sleep(1)


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


def handle_verification_code(driver: webdriver.Chrome, send_update: Callable[[str], Any], shipping: Dict[str, str]) -> bool:
    """Handle OTP/ZIP verification after payment submission. Returns True if handled."""
    import time
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    zip_val = shipping.get("zip", "84020")

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
        if len(code_inputs) == 5:
            for i, digit in enumerate(zip_val[:5]):
                try:
                    code_inputs[i].clear()
                    code_inputs[i].send_keys(digit)
                except Exception:
                    pass
        else:
            try:
                code_inputs[0].clear()
                code_inputs[0].send_keys(zip_val)
            except Exception:
                pass
        _click_button(driver, ["Continue", "Verify", "Confirm"])
        time.sleep(3)
        return True

    return False


def _click_button(driver: webdriver.Chrome, texts: list) -> bool:
    """Find and click a button by its visible text. Returns True if clicked."""
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

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
    import time
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
    import time
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    deadline = time.time() + timeout
    send_update("⏳ Waiting for payment page to load...")

    while time.time() < deadline:
        current_url = (driver.current_url or "").lower()

        if "payment" in current_url or "checkout" in current_url:
            pass

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
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

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
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

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
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

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
                elif maxlen >= 15 and number:
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

