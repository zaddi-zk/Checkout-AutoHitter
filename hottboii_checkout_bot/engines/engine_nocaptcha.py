# engines/engine_nocaptcha.py
import time
from typing import Any, Callable, Dict, List, Optional
from selenium.webdriver.common.by import By
from .engine_base import (
    init_driver, check_success, wait_for_captcha,
    switch_to_payment_iframe, handle_verification_code,
    wait_for_success, wait_for_payment_page,
    fill_card_on_platform, detect_payment_platform
)
from .field_finder import SmartFormFiller
from .threeds_bypass import handle_threeds_challenge
from config import CAPTCHA_API_KEY


def perform_checkout(
    url: str,
    shipping: Dict[str, str],
    cards: List[Dict[str, str]],
    send_update: Callable[[str], Any],
    headless: bool = True,
    proxy: Optional[str] = None,
    captcha_handler: Optional[Callable[..., Any]] = None,
) -> Dict[str, str]:
    driver = None
    try:
        send_update("🚀 Engine 2: No‑CAPTCHA (fast)")
        driver = init_driver(headless, proxy)
        if proxy:
            send_update(f"🌐 Using proxy: {proxy}")
        try:
            from config import BURP_ENABLED, BURP_PROXY
            if BURP_ENABLED and BURP_PROXY:
                send_update(f"🔧 Burp Suite interception active: {BURP_PROXY}")
        except Exception:
            pass
        driver.get(url)
        time.sleep(3)

        ff = SmartFormFiller(driver)

        send_update("📦 Filling shipping...")
        ff.fill_shipping(shipping)
        ff.handle_state(shipping)

        send_update("🔄 Submitting shipping...")
        if not ff.click_pay_button():
            try:
                driver.find_element(By.CSS_SELECTOR, "form").submit()
            except Exception:
                pass
        time.sleep(3)

        wait_for_captcha(driver, send_update, captcha_handler=captcha_handler, max_wait_seconds=5, api_key=CAPTCHA_API_KEY)

        wait_for_payment_page(driver, send_update)

        for idx, card in enumerate(cards, 1):
            send_update(f"💳 Card {idx}/{len(cards)}")
            try:
                fill_card_on_platform(driver, card, shipping)

                if ff.click_pay_button():
                    time.sleep(5)
                else:
                    time.sleep(3)

                wait_for_captcha(driver, send_update, captcha_handler=captcha_handler, max_wait_seconds=5, api_key=CAPTCHA_API_KEY)

                handle_threeds_challenge(driver, send_update, card)
                handle_verification_code(driver, send_update, shipping)

                if wait_for_success(driver, send_update, max_wait=30):
                    return {"status": "success", "message": "Order confirmed."}
            except Exception:
                continue

        return {"status": "failed", "message": "All cards declined."}
    except Exception as e:
        return {"status": "failed", "message": str(e)}
    finally:
        if driver:
            driver.quit()
            send_update("🧹 Engine 2 closed.")
