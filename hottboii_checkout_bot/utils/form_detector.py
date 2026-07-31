# utils/form_detector.py
import time
from typing import Dict, List, Optional, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


FIELD_STRATEGIES: Dict[str, List[Tuple[str, str]]] = {
    "email": [
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.CSS_SELECTOR, "input[autocomplete='email']"),
        (By.CSS_SELECTOR, "input[name*='email' i]"),
        (By.CSS_SELECTOR, "input[id*='email' i]"),
        (By.CSS_SELECTOR, "input[placeholder*='email' i]"),
        (By.CSS_SELECTOR, "input[aria-label*='email' i]"),
        (By.XPATH, "//input[translate(@placeholder,'EMAIL','email')='email']"),
        (By.NAME, "email"),
        (By.ID, "email"),
    ],
    "first_name": [
        (By.CSS_SELECTOR, "input[autocomplete='given-name']"),
        (By.CSS_SELECTOR, "input[name*='first' i]"),
        (By.CSS_SELECTOR, "input[id*='first' i]"),
        (By.CSS_SELECTOR, "input[placeholder*='first' i]"),
        (By.CSS_SELECTOR, "input[aria-label*='first' i]"),
        (By.NAME, "firstName"),
        (By.NAME, "firstname"),
        (By.NAME, "first_name"),
        (By.ID, "firstName"),
        (By.ID, "firstname"),
    ],
    "last_name": [
        (By.CSS_SELECTOR, "input[autocomplete='family-name']"),
        (By.CSS_SELECTOR, "input[name*='last' i]"),
        (By.CSS_SELECTOR, "input[id*='last' i]"),
        (By.CSS_SELECTOR, "input[placeholder*='last' i]"),
        (By.CSS_SELECTOR, "input[aria-label*='last' i]"),
        (By.NAME, "lastName"),
        (By.NAME, "lastname"),
        (By.NAME, "last_name"),
        (By.ID, "lastName"),
        (By.ID, "lastname"),
    ],
    "full_name": [
        (By.CSS_SELECTOR, "input[autocomplete='name']"),
        (By.CSS_SELECTOR, "input[name*='name' i]"),
        (By.CSS_SELECTOR, "input[id*='name' i]"),
        (By.CSS_SELECTOR, "input[placeholder*='name' i]"),
        (By.CSS_SELECTOR, "input[aria-label*='name' i]"),
        (By.NAME, "name"),
        (By.NAME, "fullName"),
        (By.NAME, "full_name"),
        (By.ID, "name"),
    ],
    "address1": [
        (By.CSS_SELECTOR, "input[autocomplete='address-line1']"),
        (By.CSS_SELECTOR, "input[name*='address' i]"),
        (By.CSS_SELECTOR, "input[id*='address' i]"),
        (By.CSS_SELECTOR, "input[placeholder*='address' i]"),
        (By.CSS_SELECTOR, "input[aria-label*='address' i]"),
        (By.NAME, "address1"),
        (By.NAME, "address"),
        (By.NAME, "shipping_address"),
        (By.ID, "address1"),
        (By.ID, "address"),
    ],
    "address2": [
        (By.CSS_SELECTOR, "input[autocomplete='address-line2']"),
        (By.CSS_SELECTOR, "input[name*='address2' i]"),
        (By.CSS_SELECTOR, "input[id*='address2' i]"),
        (By.CSS_SELECTOR, "input[placeholder*='apt' i]"),
        (By.CSS_SELECTOR, "input[aria-label*='apt' i]"),
        (By.NAME, "address2"),
        (By.ID, "address2"),
    ],
    "city": [
        (By.CSS_SELECTOR, "input[autocomplete='address-level2']"),
        (By.CSS_SELECTOR, "input[name*='city' i]"),
        (By.CSS_SELECTOR, "input[id*='city' i]"),
        (By.CSS_SELECTOR, "input[placeholder*='city' i]"),
        (By.CSS_SELECTOR, "input[aria-label*='city' i]"),
        (By.NAME, "city"),
        (By.ID, "city"),
    ],
    "state": [
        (By.CSS_SELECTOR, "select[autocomplete='address-level1']"),
        (By.CSS_SELECTOR, "input[autocomplete='address-level1']"),
        (By.CSS_SELECTOR, "select[name*='state' i]"),
        (By.CSS_SELECTOR, "input[name*='state' i]"),
        (By.CSS_SELECTOR, "select[id*='state' i]"),
        (By.CSS_SELECTOR, "input[id*='state' i]"),
        (By.CSS_SELECTOR, "select[placeholder*='state' i]"),
        (By.CSS_SELECTOR, "input[placeholder*='state' i]"),
        (By.NAME, "state"),
        (By.NAME, "province"),
        (By.NAME, "region"),
        (By.ID, "state"),
        (By.ID, "province"),
        (By.ID, "region"),
    ],
    "zip": [
        (By.CSS_SELECTOR, "input[autocomplete='postal-code']"),
        (By.CSS_SELECTOR, "input[name*='zip' i]"),
        (By.CSS_SELECTOR, "input[name*='postal' i]"),
        (By.CSS_SELECTOR, "input[name*='postcode' i]"),
        (By.CSS_SELECTOR, "input[id*='zip' i]"),
        (By.CSS_SELECTOR, "input[id*='postal' i]"),
        (By.CSS_SELECTOR, "input[placeholder*='zip' i]"),
        (By.CSS_SELECTOR, "input[placeholder*='postal' i]"),
        (By.CSS_SELECTOR, "input[aria-label*='zip' i]"),
        (By.CSS_SELECTOR, "input[aria-label*='postal' i]"),
        (By.NAME, "postalCode"),
        (By.NAME, "postal_code"),
        (By.NAME, "zip"),
        (By.NAME, "postcode"),
        (By.ID, "zip"),
        (By.ID, "postalCode"),
        (By.ID, "postcode"),
    ],
    "phone": [
        (By.CSS_SELECTOR, "input[type='tel']"),
        (By.CSS_SELECTOR, "input[autocomplete='tel']"),
        (By.CSS_SELECTOR, "input[name*='phone' i]"),
        (By.CSS_SELECTOR, "input[id*='phone' i]"),
        (By.CSS_SELECTOR, "input[placeholder*='phone' i]"),
        (By.CSS_SELECTOR, "input[aria-label*='phone' i]"),
        (By.NAME, "phone"),
        (By.NAME, "tel"),
        (By.NAME, "telephone"),
        (By.ID, "phone"),
    ],
}

STATE_ABBR_MAP = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}

BUTTON_TEXTS = [
    "Continue", "Continue to shipping", "Continue to payment",
    "Pay", "Pay now", "Submit", "Submit order",
    "Place order", "Place Order", "Complete order", "Complete Order",
    "Confirm", "Confirm order", "Confirm payment",
    "Purchase", "Buy now", "Checkout", "Order now",
    "Proceed", "Proceed to checkout", "Next",
    "Continue to review", "Review order", "Complete purchase",
]


def find_field(driver: WebDriver, field_type: str, timeout: float = 5) -> Optional[WebElement]:
    """Find a form field using multiple strategies. Tries each until one works."""
    strategies = FIELD_STRATEGIES.get(field_type)
    if not strategies:
        return None
    for by, selector in strategies:
        try:
            elem = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            if elem.is_displayed():
                return elem
        except Exception:
            continue
    return None


def fill_field(driver: WebDriver, field_type: str, value: str, timeout: float = 3) -> bool:
    """Find a field and fill it. Returns True if successful."""
    if not value:
        return False
    elem = find_field(driver, field_type, timeout)
    if elem is None:
        return False
    try:
        elem.clear()
        elem.send_keys(value)
        return True
    except Exception:
        return False


def fill_state(driver: WebDriver, state_value: str) -> bool:
    """Fill state/province — handles both <select> dropdowns and <input> text fields."""
    if not state_value:
        return False

    state_clean = state_value.strip().lower()
    abbr = STATE_ABBR_MAP.get(state_clean, state_value.upper()[:2])

    elem = find_field(driver, "state", timeout=3)
    if elem is None:
        return False

    tag = elem.tag_name.lower()
    try:
        if tag == "select":
            select = Select(elem)
            options = [o.text.strip().lower() for o in select.options]
            values = [o.get_attribute("value").strip().lower() for o in select.options]

            for candidate in [state_clean, abbr.lower(), abbr]:
                for i, opt_text in enumerate(options):
                    if candidate in opt_text or opt_text in candidate:
                        select.select_by_index(i)
                        return True
                for i, opt_val in enumerate(values):
                    if candidate == opt_val:
                        select.select_by_index(i)
                        return True

            if abbr.lower() in values:
                select.select_by_value(abbr.lower())
                return True
            if abbr in values:
                select.select_by_value(abbr)
                return True

            return False
        else:
            elem.clear()
            elem.send_keys(abbr if len(state_clean) > 2 else state_value.strip().upper())
            return True
    except Exception:
        return False


def find_and_click_button(driver: WebDriver, timeout: float = 5) -> bool:
    """Find a submit/pay button using multiple strategies. Returns True if clicked."""
    for text in BUTTON_TEXTS:
        try:
            btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[contains(text(), '{text}')]"))
            )
            btn.click()
            return True
        except Exception:
            pass
        try:
            btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.XPATH, f"//input[@type='submit' and contains(@value, '{text}')]"))
            )
            btn.click()
            return True
        except Exception:
            pass
        try:
            btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.XPATH, f"//a[contains(text(), '{text}')]"))
            )
            btn.click()
            return True
        except Exception:
            pass
        try:
            btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, f"button, input[type='submit'], a.btn, a.button"))
            )
            driver.execute_script("arguments[0].click();", btn)
            return True
        except Exception:
            pass

    try:
        form = driver.find_element(By.CSS_SELECTOR, "form")
        driver.execute_script("arguments[0].submit();", form)
        return True
    except Exception:
        pass

    return False


def fill_shipping_fields(driver: WebDriver, shipping: Dict[str, str]) -> Dict[str, bool]:
    """Fill all shipping fields. Returns a dict of what was filled."""
    results = {}

    results["email"] = fill_field(driver, "email", shipping.get("email", ""))

    full_name = shipping.get("full_name", "")
    if full_name:
        parts = full_name.split()
        first = parts[0]
        last = " ".join(parts[1:]) if len(parts) > 1 else ""
        results["first_name"] = fill_field(driver, "first_name", first)
        results["last_name"] = fill_field(driver, "last_name", last)
        if not results["first_name"] and not results["last_name"]:
            results["full_name"] = fill_field(driver, "full_name", full_name)

    results["address1"] = fill_field(driver, "address1", shipping.get("address", ""))
    results["address2"] = fill_field(driver, "address2", shipping.get("address2", ""))

    if not results["address1"]:
        address_full = shipping.get("address", "")
        if address_full:
            results["address1"] = fill_field(driver, "address1", address_full)

    results["city"] = fill_field(driver, "city", shipping.get("city", ""))
    results["state"] = fill_state(driver, shipping.get("state", ""))
    results["zip"] = fill_field(driver, "zip", shipping.get("zip", ""))
    results["phone"] = fill_field(driver, "phone", shipping.get("phone", ""))

    return results


def switch_to_card_iframe(driver: WebDriver) -> bool:
    """Find and switch to the iframe containing credit card fields. Returns True if found."""
    driver.switch_to.default_content()

    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for iframe in iframes:
        try:
            driver.switch_to.frame(iframe)
            card_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='tel'], input[aria-label*='card' i], input[placeholder*='card' i], input[name*='card' i], input[id*='card' i], input[autocomplete='cc-number']")
            if card_inputs:
                return True
            driver.switch_to.default_content()
        except Exception:
            driver.switch_to.default_content()
            continue

    for iframe in iframes:
        try:
            src = iframe.get_attribute("src") or ""
            if "stripe" in src.lower() or "shopify" in src.lower() or "card" in src.lower():
                driver.switch_to.frame(iframe)
                return True
            driver.switch_to.default_content()
        except Exception:
            driver.switch_to.default_content()
            continue

    return False


def fill_card_fields(driver: WebDriver, card: Dict[str, str]) -> bool:
    """Fill credit card fields — handles iframes and direct inputs."""
    in_iframe = switch_to_card_iframe(driver)

    card_strategies = [
        ("number", [
            (By.CSS_SELECTOR, "input[autocomplete='cc-number']"),
            (By.CSS_SELECTOR, "input[aria-label*='card number' i]"),
            (By.CSS_SELECTOR, "input[placeholder*='card number' i]"),
            (By.CSS_SELECTOR, "input[name*='number' i]"),
            (By.CSS_SELECTOR, "input[id*='number' i]"),
            (By.CSS_SELECTOR, "input[inputmode='numeric']"),
            (By.NAME, "number"),
            (By.NAME, "cardnumber"),
            (By.NAME, "cardNumber"),
            (By.ID, "number"),
            (By.ID, "cardNumber"),
        ]),
        ("expiry", [
            (By.CSS_SELECTOR, "input[autocomplete='cc-exp']"),
            (By.CSS_SELECTOR, "input[aria-label*='expir' i]"),
            (By.CSS_SELECTOR, "input[placeholder*='expir' i]"),
            (By.CSS_SELECTOR, "input[name*='expir' i]"),
            (By.CSS_SELECTOR, "input[id*='expir' i]"),
            (By.CSS_SELECTOR, "input[inputmode='numeric']"),
            (By.NAME, "expiry"),
            (By.NAME, "expdate"),
            (By.NAME, "expiryDate"),
            (By.NAME, "exp-date"),
            (By.ID, "expiry"),
            (By.ID, "exp-date"),
        ]),
        ("cvv", [
            (By.CSS_SELECTOR, "input[autocomplete='cc-csc']"),
            (By.CSS_SELECTOR, "input[aria-label*='cvv' i]"),
            (By.CSS_SELECTOR, "input[aria-label*='cvc' i]"),
            (By.CSS_SELECTOR, "input[aria-label*='security' i]"),
            (By.CSS_SELECTOR, "input[placeholder*='cvv' i]"),
            (By.CSS_SELECTOR, "input[placeholder*='cvc' i]"),
            (By.CSS_SELECTOR, "input[placeholder*='security' i]"),
            (By.CSS_SELECTOR, "input[name*='cvv' i]"),
            (By.CSS_SELECTOR, "input[name*='cvc' i]"),
            (By.CSS_SELECTOR, "input[id*='cvv' i]"),
            (By.CSS_SELECTOR, "input[id*='cvc' i]"),
            (By.CSS_SELECTOR, "input[name*='security' i]"),
            (By.NAME, "cvv"),
            (By.NAME, "cvc"),
            (By.NAME, "securityCode"),
            (By.ID, "cvv"),
            (By.ID, "cvc"),
        ]),
    ]

    card_num = card.get("number", "")
    exp_month = card.get("exp_month", "")
    exp_year = card.get("exp_year", "")
    exp_formatted = f"{exp_month}/{exp_year}" if exp_month and exp_year else ""
    cvv = card.get("cvv", "")

    all_filled = True
    for field_type, strategies in card_strategies:
        if field_type == "number" and card_num:
            val = card_num
        elif field_type == "expiry" and exp_formatted:
            val = exp_formatted
        elif field_type == "cvv" and cvv:
            val = cvv
        else:
            continue

        filled = False
        for by, selector in strategies:
            try:
                elem = driver.find_element(by, selector)
                if elem.is_displayed():
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                        time.sleep(0.3)
                        elem.click()
                        elem.clear()
                        elem.send_keys(val)
                        filled = True
                        break
                    except Exception:
                        continue
            except Exception:
                continue

        if not filled:
            all_filled = False

    if in_iframe:
        driver.switch_to.default_content()

    return all_filled


def click_pay_button(driver: WebDriver) -> bool:
    """Find and click the pay/submit button. Returns True if clicked."""
    if in_iframe := is_in_iframe_context(driver):
        driver.switch_to.default_content()

    result = find_and_click_button(driver)

    if in_iframe:
        driver.switch_to.default_content()

    return result


def is_in_iframe_context(driver: WebDriver) -> bool:
    try:
        parent = driver.execute_script("return window.frameElement;")
        return parent is not None
    except Exception:
        return False
