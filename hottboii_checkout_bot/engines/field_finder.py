# engines/field_finder.py
"""
Universal form filler — handles ANY website layout using keyword-based field
classification, pattern detection, label scanning, and smart select handling.
"""
import re
import time
from typing import Any, Dict, List, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import StaleElementReferenceException

STATE_MAP = {
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

STATE_KEYWORDS = list(STATE_MAP.keys()) + list(STATE_MAP.values())

FIELD_KEYWORDS = {
    "email": ["email", "e-mail", "mail"],
    "firstName": ["first name", "firstname", "fname", "given name"],
    "lastName": ["last name", "lastname", "lname", "family name", "surname"],
    "address1": ["address", "address1", "address line 1", "street", "street address", "shipping address"],
    "address2": ["address2", "address line 2", "apt", "suite", "unit"],
    "city": ["city", "town", "locality"],
    "state": ["state", "province", "region", "prefecture", "county"],
    "zip": ["zip", "postal", "postcode", "post code", "zip code"],
    "phone": ["phone", "telephone", "tel", "mobile", "cell", "phone number"],
    "company": ["company", "organization", "business"],
    "country": ["country"],
    "number": ["card number", "cardnumber", "cc-number", "ccnumber", "card no", "credit card"],
    "expiry": ["expiry", "expiration", "exp date", "exp-date", "expiry date", "valid thru", "valid through"],
    "cvv": ["cvv", "cvc", "security code", "card code", "cvv2", "cvc2", "ccv", "secure code"],
}

CARD_NUMBER_PATTERN = re.compile(r'^[\d\s-]{12,23}$')
EXPIRY_PATTERN = re.compile(r'^(0?[1-9]|1[0-2])\s*[/\s]\s*\d{2,4}$')
CVV_PATTERN = re.compile(r'^\d{3,4}$')


class SmartFormFiller:
    def __init__(self, driver):
        self.driver = driver

    def _get_field_text(self, el: WebElement) -> str:
        """Get all identifying text for a field: label, placeholder, name, id, aria-label."""
        texts = []
        try:
            tid = (el.get_attribute("id") or "").strip()
            if tid:
                label = self._find_label_by_id(tid)
                if label:
                    texts.append(label)
        except Exception:
            pass
        for attr in ["placeholder", "aria-label", "name", "id", "class", "title"]:
            try:
                v = (el.get_attribute(attr) or "").strip().lower()
                if v:
                    texts.append(v)
            except Exception:
                pass
        return " ".join(texts)

    def _find_label_by_id(self, elem_id: str) -> str:
        """Find label text using `for` attribute."""
        try:
            lbl = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{elem_id}']")
            return (lbl.text or "").strip().lower()
        except Exception:
            pass
        try:
            parent = self.driver.find_element(By.XPATH, f"//label[@for='{elem_id}']")
            return (parent.text or "").strip().lower()
        except Exception:
            pass
        return ""

    def _scan_all_labels(self) -> Dict[str, str]:
        """Scan ALL labels and map them to their input field IDs."""
        mapping = {}
        try:
            labels = self.driver.find_elements(By.TAG_NAME, "label")
            for lbl in labels:
                try:
                    text = (lbl.text or "").strip().lower()
                    for_id = (lbl.get_attribute("for") or "").strip()
                    if text and for_id:
                        mapping[for_id] = text
                except Exception:
                    continue
        except Exception:
            pass
        return mapping

    def classify_field(self, el: WebElement) -> Optional[str]:
        """Classify a form field into one of our known types."""
        text = self._get_field_text(el)
        if not text:
            try:
                text = (el.get_attribute("type") or "").strip().lower()
            except Exception:
                pass
        if not text:
            return None

        # Type-based classification
        try:
            input_type = (el.get_attribute("type") or "").strip().lower()
            if input_type == "email":
                return "email"
            if input_type == "tel":
                return "phone"
        except Exception:
            pass

        for field_type, keywords in FIELD_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return field_type
        return None

    def find_field_by_classification(self, target_type: str) -> Optional[WebElement]:
        """Find a field by its classified type using all available strategies."""
        # Strategy 1: Try all inputs and classify them
        try:
            all_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='checkbox']):not([type='radio'])")
            for inp in all_inputs:
                try:
                    if inp.is_displayed() and self.classify_field(inp) == target_type:
                        return inp
                except StaleElementReferenceException:
                    continue
        except Exception:
            pass

        # Strategy 2: Direct attribute matching
        keywords = FIELD_KEYWORDS.get(target_type, [target_type])
        for kw in keywords:
            for attr in ["name", "id", "placeholder", "aria-label"]:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, f"input[{attr}*='{kw}' i]")
                    if el.is_displayed():
                        return el
                except Exception:
                    continue

        # Strategy 3: Label-based detection
        label_map = self._scan_all_labels()
        for for_id, label_text in label_map.items():
            for kw in keywords:
                if kw in label_text:
                    try:
                        el = self.driver.find_element(By.ID, for_id)
                        if el.is_displayed():
                            return el
                    except Exception:
                        continue

        # Strategy 4: XPath with label nearby (case-insensitive via full alphabet translate)
        _up = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        _low = 'abcdefghijklmnopqrstuvwxyz'
        for kw in keywords:
            kwl = kw.lower()
            xpaths = [
                f"//label[contains(translate(text(),'{_up}','{_low}'),'{kwl}')]/following::input[1]",
                f"//label[contains(translate(text(),'{_up}','{_low}'),'{kwl}')]/..//input",
                f"//*[contains(translate(@placeholder,'{_up}','{_low}'),'{kwl}')]",
                f"//*[contains(translate(@aria-label,'{_up}','{_low}'),'{kwl}')]",
                f"//input[contains(translate(@name,'{_up}','{_low}'),'{kwl}')]",
            ]
            for xp in xpaths:
                try:
                    el = self.driver.find_element(By.XPATH, xp)
                    if el.is_displayed():
                        return el
                except Exception:
                    continue

        return None

    def find_select_by_classification(self, target_type: str) -> Optional[WebElement]:
        """Find a <select> element for state/province/etc."""
        keywords = FIELD_KEYWORDS.get(target_type, [target_type])
        try:
            selects = self.driver.find_elements(By.TAG_NAME, "select")
            for sel in selects:
                try:
                    if not sel.is_displayed():
                        continue
                    text = self._get_field_text(sel)
                    for kw in keywords:
                        if kw in text:
                            return sel
                except Exception:
                    continue
        except Exception:
            pass

        for kw in keywords:
            for attr in ["name", "id"]:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, f"select[{attr}*='{kw}' i]")
                    if el.is_displayed():
                        return el
                except Exception:
                    continue
        return None

    def fill_input(self, el: WebElement, value: str, human: bool = True) -> bool:
        """Fill a single input field with the value.

        Prefers human-like character-by-character typing (anti-bot), verifies
        the resulting value, and falls back to JS force-set if the field did
        not accept the typed text (prevents value duplication).
        """
        if not el:
            return False
        try:
            if not el.is_displayed():
                return False
        except Exception:
            return False

        try:
            el.click()
        except Exception:
            pass
        try:
            el.clear()
        except Exception:
            pass

        if human:
            try:
                from config import HUMANIZE
                if not HUMANIZE:
                    human = False
            except Exception:
                pass

        if human:
            from .humanize import type_human
            if type_human(el, value):
                try:
                    if (el.get_attribute("value") or "") == value:
                        return True
                except Exception:
                    pass
                # Field didn't keep the text — force-set via JS.
                try:
                    self.driver.execute_script(
                        "arguments[0].value = arguments[1];"
                        "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                        "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                        el,
                        value,
                    )
                    return True
                except Exception:
                    pass

        try:
            el.send_keys(value)
            return True
        except Exception:
            pass

        # Last resort: JS force-set
        try:
            self.driver.execute_script(
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                el,
                value,
            )
            return True
        except Exception:
            pass

        return False


    def fill_select(self, el: WebElement, value: str) -> bool:
        """Fill a <select> dropdown — try by visible text, then by value, then by index."""
        if not el:
            return False
        try:
            select = Select(el)
            # Try by visible text (full name or abbreviation)
            try:
                select.select_by_visible_text(value)
                return True
            except Exception:
                pass
            try:
                select.select_by_visible_text(value.lower())
                return True
            except Exception:
                pass
            # Try by value
            try:
                select.select_by_value(value)
                return True
            except Exception:
                pass
            try:
                select.select_by_value(value.lower())
                return True
            except Exception:
                pass
            # Try matching option text
            for opt in select.options:
                opt_text = (opt.text or "").strip().lower()
                if opt_text == value.lower() or opt_text == STATE_MAP.get(value.lower(), "").lower():
                    opt.click()
                    return True
            # Fallback: partial match
            for opt in select.options:
                opt_text = (opt.text or "").strip().lower()
                if value.lower() in opt_text or opt_text in value.lower():
                    opt.click()
                    return True
        except Exception:
            pass
        return False

    def fill_field(self, field_type: str, value: str) -> bool:
        """Fill a field by type — tries input first, then select."""
        if not value:
            return False
        el = self.find_field_by_classification(field_type)
        if el:
            if self.fill_input(el, value):
                return True
        sel = self.find_select_by_classification(field_type)
        if sel:
            if self.fill_select(sel, value):
                return True
        return False

    def fill_shipping(self, shipping: Dict[str, str]):
        """Fill all shipping fields using classified detection."""
        name = shipping.get("full_name", "")
        first = name.split()[0] if name else ""
        last = " ".join(name.split()[1:]) if name else ""

        fields = [
            ("email", shipping.get("email", "")),
            ("firstName", first),
            ("lastName", last),
            ("address1", shipping.get("address", "")),
            ("city", shipping.get("city", "")),
            ("state", shipping.get("state", "")),
            ("zip", shipping.get("zip", "")),
            ("phone", shipping.get("phone", "")),
            # Always default to USA country if a country field exists
            ("country", shipping.get("country", "USA") or "USA"),

        ]
        for ftype, val in fields:
            if val:
                self.fill_field(ftype, val)

    def find_card_fields_enhanced(self) -> Dict[str, Optional[WebElement]]:
        """Enhanced card field finder that works on nested iframes and common checkout providers."""
        result = {"number": None, "expiry": None, "cvv": None}

        # 1. Search in the current document context.
        self._search_card_fields_in_context(result)

        # 2. If any field is still missing, scan iframe contexts.
        iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
        for frame in iframes:
            try:
                self.driver.switch_to.frame(frame)
                self._search_card_fields_in_context(result)
                self.driver.switch_to.default_content()
                if all(result.values()):
                    break
            except Exception:
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass

        # 3. Fallback selectors for common Stripe / Shopify / Payment fields.
        if not result["number"]:
            number_selectors = [
                "input[data-elements-stable-field-name='cardNumber']",
                "input[name='cardnumber']",
                "input[autocomplete='cc-number']",
                "input[placeholder*='Card Number']",
                "input[aria-label*='Card Number']",
            ]
            for sel in number_selectors:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    if el.is_displayed():
                        result["number"] = el
                        break
                except Exception:
                    pass

        if not result["expiry"]:
            expiry_selectors = [
                "input[data-elements-stable-field-name='cardExpiry']",
                "input[name='expiry']",
                "input[autocomplete='cc-exp']",
                "input[placeholder*='MM / YY']",
                "input[aria-label*='Expiration']",
            ]
            for sel in expiry_selectors:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    if el.is_displayed():
                        result["expiry"] = el
                        break
                except Exception:
                    pass

        if not result["cvv"]:
            cvv_selectors = [
                "input[data-elements-stable-field-name='cardCvc']",
                "input[name='cvc']",
                "input[autocomplete='cc-csc']",
                "input[placeholder*='CVV']",
                "input[aria-label*='CVV']",
            ]
            for sel in cvv_selectors:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    if el.is_displayed():
                        result["cvv"] = el
                        break
                except Exception:
                    pass

        return result

    def _search_card_fields_in_context(self, result: Dict[str, Optional[WebElement]]):
        """Search for card fields in the current frame context."""
        inputs = []
        try:
            inputs = self.driver.find_elements(
                By.CSS_SELECTOR,
                "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='checkbox']):not([type='radio'])"
            )
            inputs = [i for i in inputs if i.is_displayed()]
        except Exception:
            pass

        for inp in inputs:
            try:
                v = (inp.get_attribute("value") or "").strip()
                if v:
                    continue
                text = self._get_field_text(inp)
                maxlen = 0
                try:
                    maxlen = int(inp.get_attribute("maxlength") or 0)
                except Exception:
                    pass

                if not result["number"]:
                    if maxlen >= 15 or "card" in text or "number" in text:
                        result["number"] = inp
                        continue
                if not result["expiry"]:
                    if maxlen <= 7 and ("expir" in text or "valid" in text or "mm/yy" in text):
                        result["expiry"] = inp
                        continue
                if not result["cvv"]:
                    if maxlen <= 4 and ("cvv" in text or "cvc" in text or "security" in text):
                        result["cvv"] = inp
                        continue
            except Exception:
                continue

    def find_card_fields(self) -> Dict[str, Optional[WebElement]]:
        return self.find_card_fields_enhanced()

    def click_pay_button_with_retry(self, max_attempts: int = 5) -> bool:
        """Find and click the pay button with retries and iframe fallback."""
        for attempt in range(max_attempts):
            try:
                btn = self.find_pay_button()
                if btn:
                    self.driver.execute_script("arguments[0].click();", btn)
                    return True

                for frame in self.driver.find_elements(By.TAG_NAME, "iframe"):
                    try:
                        self.driver.switch_to.frame(frame)
                        btn = self.find_pay_button()
                        if btn:
                            self.driver.execute_script("arguments[0].click();", btn)
                            self.driver.switch_to.default_content()
                            return True
                        self.driver.switch_to.default_content()
                    except Exception:
                        try:
                            self.driver.switch_to.default_content()
                        except Exception:
                            pass
                time.sleep(0.5)
            except Exception:
                pass
        return False

    def _search_card_fields_in_iframes(self, result: Dict[str, Optional[WebElement]]):
        """Search inside all iframes for card fields."""
        iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
        for frame in iframes:
            try:
                self.driver.switch_to.frame(frame)
                inner = self.find_card_fields()
                for k in result:
                    if not result[k] and inner.get(k):
                        result[k] = inner[k]
                self.driver.switch_to.default_content()
                if all(result.values()):
                    break
            except Exception:
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass

    def fill_card(self, card: Dict[str, str]):
        """Fill all card fields — number, expiry, CVV."""
        fields = self.find_card_fields()

        number = card.get("number", "").strip()
        exp_month = card.get("exp_month", "").strip()
        exp_year = card.get("exp_year", "").strip()
        cvv = card.get("cvv", "").strip()

        # Build expiry in every possible format
        if len(exp_year) == 4:
            expiry_vals = [
                f"{exp_month}/{exp_year[2:]}",
                f"{exp_month}/{exp_year}",
                f"{exp_month}/{exp_year[-2:]}",
            ]
        else:
            expiry_vals = [f"{exp_month}/{exp_year}"]

        if fields["number"] and number:
            self.fill_input(fields["number"], number)

        if fields["expiry"]:
            for ev in expiry_vals:
                if self.fill_input(fields["expiry"], ev):
                    break

        if fields["cvv"] and cvv:
            self.fill_input(fields["cvv"], cvv)

    def reset_card_fields(self):
        """Clear card fields so the next card can be filled (error recovery)."""
        try:
            fields = self.find_card_fields()
        except Exception:
            fields = {}
        for el in fields.values():
            if not el:
                continue
            try:
                el.clear()
            except Exception:
                pass
            try:
                self.driver.execute_script("arguments[0].value = '';", el)
            except Exception:
                pass
        try:
            self.driver.switch_to.default_content()
        except Exception:
            pass

    def find_pay_button(self) -> Optional[WebElement]:
        """Find ANY clickable submit/pay element using exhaustive search."""
        _up = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        _low = 'abcdefghijklmnopqrstuvwxyz'
        pay_keywords = [
            "pay", "submit", "place order", "place your order", "confirm", "complete",
            "checkout", "purchase", "buy", "order", "continue to payment", "pay now",
            "pay securely", "complete order", "confirm order", "confirm payment",
        ]

        # 1. Try buttons and submit inputs with matching text
        for kw in pay_keywords:
            kwl = kw.lower()
            xpaths = [
                f"//button[contains(translate(text(),'{_up}','{_low}'),'{kwl}')]",
                f"//button[@type='submit'][contains(translate(text(),'{_up}','{_low}'),'{kwl}')]",
                f"//input[@type='submit'][contains(translate(@value,'{_up}','{_low}'),'{kwl}')]",
                f"//a[contains(translate(text(),'{_up}','{_low}'),'{kwl}')]",
                f"//*[@role='button'][contains(translate(text(),'{_up}','{_low}'),'{kwl}')]",
                f"//span[contains(translate(text(),'{_up}','{_low}'),'{kwl}')]/..",
            ]
            for xp in xpaths:
                try:
                    els = self.driver.find_elements(By.XPATH, xp)
                    for el in els:
                        try:
                            if el.is_displayed():
                                return el
                        except Exception:
                            continue
                except Exception:
                    continue

        # 2. Any submit button inside a form
        try:
            submits = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
            for el in submits:
                try:
                    if el.is_displayed():
                        return el
                except Exception:
                    continue
        except Exception:
            pass

        # 3. First button inside the last form (likely the payment form)
        try:
            forms = self.driver.find_elements(By.TAG_NAME, "form")
            if forms:
                last_form = forms[-1]
                buttons = last_form.find_elements(By.CSS_SELECTOR, "button, input[type='submit'], a[role='button']")
                for btn in buttons:
                    try:
                        if btn.is_displayed():
                            return btn
                    except Exception:
                        continue
        except Exception:
            pass

        # 4. Any visible button on the page
        try:
            all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in all_buttons:
                try:
                    if btn.is_displayed():
                        return btn
                except Exception:
                    continue
        except Exception:
            pass

        return None

    def click_pay_button(self) -> bool:
        """Find and click the pay button, with JS fallback."""
        btn = self.find_pay_button()
        if btn is None:
            return False
        try:
            btn.click()
            return True
        except Exception:
            pass
        try:
            self.driver.execute_script("arguments[0].click();", btn)
            return True
        except Exception:
            pass
        return False

    def handle_state(self, shipping: Dict[str, str]):
        """Smart state/province handling — fills both input and select."""
        state = shipping.get("state", "").strip()
        if not state:
            return

        # Normalize: full name -> abbreviation
        state_lower = state.lower()
        if state_lower in STATE_MAP:
            state_abbr = STATE_MAP[state_lower]
        elif state.upper() in STATE_MAP.values():
            state_abbr = state.upper()
            state_lower = {v: k for k, v in STATE_MAP.items()}.get(state_abbr, state_lower)
        else:
            state_abbr = state
            state_lower = state_lower

        # Try filling as input
        inp = self.find_field_by_classification("state")
        if inp:
            if self.fill_input(inp, state_abbr):
                return

        # Try filling as select
        sel = self.find_select_by_classification("state")
        if sel:
            success = False
            try:
                s = Select(sel)
                for attempt in [state_abbr, state_lower, state.title(), state_abbr.lower()]:
                    try:
                        s.select_by_visible_text(attempt)
                        success = True
                        break
                    except Exception:
                        pass
                if not success:
                    try:
                        s.select_by_value(state_abbr)
                        success = True
                    except Exception:
                        pass
                if not success:
                    try:
                        s.select_by_value(state_lower)
                        success = True
                    except Exception:
                        pass
            except Exception:
                pass
            return
