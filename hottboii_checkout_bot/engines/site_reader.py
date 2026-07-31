# engines/site_reader.py
"""Reads the current page and finds the RIGHT action for the current step.

Instead of guessing, this module:
  - collects every visible, enabled clickable element (buttons, links, submits),
  - scores each against a phase-specific phrase catalog ("continue to payment",
    "place order", ...) with fuzzy matching,
  - avoids dangerous buttons ("cancel", "remove", "continue shopping", ...),
  - clicks with human-like motion,
  - and reports real error messages so the engine can recover and continue.
"""
import re
import time
from typing import Any, Callable, Dict, List, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

CLICKABLE_SELECTORS = [
    "button",
    "a",
    "input[type='submit']",
    "input[type='button']",
    "[role='button']",
]

# Never click things that abandon or break the checkout.
DANGEROUS_PATTERNS = [
    "cancel", "close", "back", "return to", "go back", "never mind",
    "remove", "delete", "clear cart", "remove item", "edit", "update",
    "sign out", "log out", "logout", "forgot", "decline", "reject",
    "continue shopping", "add to cart", "skip for now", "privacy",
    "terms of service", "refund",
]

# Phase catalog: (phrase, base_score). Longer/more specific phrases win.
ACTION_CATALOG: Dict[str, List[tuple]] = {
    "shipping": [
        ("continue to shipping", 100),
        ("continue to payment", 98),
        ("continue to delivery", 96),
        ("deliver to this address", 94),
        ("ship to this address", 94),
        ("use this address", 92),
        ("save and continue", 88),
        ("continue", 85),
        ("next", 78),
        ("proceed", 74),
        ("checkout", 70),
        ("submit", 66),
    ],
    "payment": [
        ("complete order", 100),
        ("place your order", 100),
        ("place order", 99),
        ("pay now", 98),
        ("complete your order", 96),
        ("confirm and pay", 94),
        ("pay securely", 93),
        ("complete payment", 92),
        ("confirm order", 92),
        ("submit payment", 90),
        ("pay & order", 90),
        ("submit order", 89),
        ("order now", 86),
        ("buy now", 82),
        ("purchase", 78),
        ("pay", 65),
    ],
    "verify": [
        ("verify", 100),
        ("confirm", 96),
        ("continue", 92),
        ("submit", 88),
        ("authenticate", 88),
        ("ok", 70),
    ],
}

ERROR_PHRASES = [
    "declined", "payment failed", "unable to process", "couldn't process",
    "not authorized", "does not match", "invalid", "insufficient funds",
    "rejected", "try again", "enter a valid", "verification failed",
    "transaction failed", "card was declined", "please check",
]

ERROR_SELECTORS = [
    "[role='alert']",
    "[class*='error' i]",
    "[class*='alert' i]",
    "[class*='notification' i]",
    "p[class*='error' i]",
    "div[class*='error' i]",
    "span[class*='error' i]",
]


def _normalize(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text or "")
    return re.sub(r"\s+", " ", text).strip().lower()


def _el_text(el: WebElement) -> str:
    try:
        return (el.text or "").strip()
    except Exception:
        return ""


def _score(text: str, catalog: List[tuple]) -> int:
    t = _normalize(text)
    if not t:
        return 0
    best = 0
    tw = set(t.split())
    for phrase, base in catalog:
        p = _normalize(phrase)
        if not p:
            continue
        if t == p:
            best = max(best, base)
        elif t.startswith(p):
            best = max(best, base - 10)
        elif p in t:
            best = max(best, base - 20)
        else:
            pw = set(p.split())
            if pw and pw <= tw:
                best = max(best, base - 35)
    return best


def is_dangerous(text: str) -> bool:
    t = _normalize(text)
    for pat in DANGEROUS_PATTERNS:
        if pat in t:
            return True
    return False


def _collect_in_context(driver) -> List[Dict[str, Any]]:
    """Collect visible, enabled clickable elements in the current frame."""
    candidates: List[Dict[str, Any]] = []
    for sel in CLICKABLE_SELECTORS:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
        except Exception:
            continue
        for el in els:
            try:
                if not el.is_displayed() or not el.is_enabled():
                    continue
            except Exception:
                continue
            tag = ""
            text = ""
            try:
                tag = (el.tag_name or "").lower()
                text = _el_text(el)
                if not text and tag == "input":
                    text = (el.get_attribute("value") or "") or ""
                if not text:
                    text = (el.get_attribute("aria-label") or "") or ""
                if not text:
                    text = (el.get_attribute("title") or "") or ""
            except Exception:
                continue
            if not text:
                continue
            candidates.append({"el": el, "text": text, "tag": tag})
    return candidates


def _all_candidates(driver, include_iframes: bool = True) -> List[Dict[str, Any]]:
    """Collect candidates from the main document and (optionally) every iframe."""
    try:
        driver.switch_to.default_content()
    except Exception:
        pass

    cands = _collect_in_context(driver)

    if include_iframes:
        iframes = []
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
        except Exception:
            pass
        for frame in iframes:
            try:
                driver.switch_to.frame(frame)
            except Exception:
                continue
            try:
                inner = _collect_in_context(driver)
                if inner:
                    cands.extend(inner)
            except Exception:
                pass
            try:
                driver.switch_to.default_content()
            except Exception:
                pass

    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    return cands


def find_action_button(
    driver,
    phase: str,
    include_iframes: bool = True,
    min_score: int = 60,
) -> Optional[WebElement]:
    """Return the best-matching action element for the phase, or None."""
    catalog = ACTION_CATALOG.get(phase)
    if not catalog:
        return None

    best_el: Optional[WebElement] = None
    best_score = 0

    for c in _all_candidates(driver, include_iframes):
        if is_dangerous(c["text"]):
            continue
        s = _score(c["text"], catalog)
        if s > best_score:
            best_score = s
            best_el = c["el"]

    if best_score < min_score:
        return None
    return best_el


def click_action(
    driver,
    phase: str,
    send_update: Callable[[str], Any],
    include_iframes: bool = True,
    human: bool = True,
) -> bool:
    """Find and click the right button for the phase. Returns True if clicked."""
    from .humanize import hover_and_click

    btn = find_action_button(driver, phase, include_iframes)
    if btn is None:
        return False

    send_update(f"🖱️ Clicking: \"{_el_text(btn)[:60]}\"")
    if human:
        try:
            from config import HUMANIZE
            if not HUMANIZE:
                human = False
        except Exception:
            pass
    if human:
        return hover_and_click(driver, btn)
    try:
        btn.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", btn)
            return True
        except Exception:
            return False


def click_submit_fallback(driver) -> bool:
    """Fallback: submit any visible form or click the first submit button."""
    try:
        submits = driver.find_elements(By.XPATH, "//button[@type='submit'] | //input[@type='submit']")
        for el in submits:
            try:
                if el.is_displayed():
                    el.click()
                    return True
            except Exception:
                continue
    except Exception:
        pass
    try:
        forms = driver.find_elements(By.CSS_SELECTOR, "form")
        for form in forms:
            try:
                form.submit()
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def detect_error_message(driver, max_len: int = 200) -> Optional[str]:
    """Return the first visible error text on the page, or None."""
    texts: List[str] = []

    try:
        driver.switch_to.default_content()
    except Exception:
        pass

    for sel in ERROR_SELECTORS:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
        except Exception:
            continue
        for el in els:
            try:
                if not el.is_displayed():
                    continue
                t = _el_text(el)
                if t:
                    texts.append(t)
            except Exception:
                continue

    if not texts:
        return None

    low = " ".join(_normalize(t) for t in texts)
    for phrase in ERROR_PHRASES:
        if phrase in low:
            for t in texts:
                if phrase in _normalize(t):
                    return re.sub(r"\s+", " ", t)[:max_len]
    return re.sub(r"\s+", " ", texts[0])[:max_len]


def page_contains(driver, phrases: List[str]) -> bool:
    try:
        src = (driver.page_source or "").lower()
    except Exception:
        return False
    return any(p.lower() in src for p in phrases)


def wait_ready(driver, timeout: float = 30.0) -> bool:
    """Wait until the document is fully loaded (readyState == complete)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            state = driver.execute_script("return document.readyState")
            if state == "complete":
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False
