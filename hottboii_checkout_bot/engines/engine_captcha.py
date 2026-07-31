# engines/engine_captcha.py
import time
from typing import Any, Callable, Dict, List, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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
    max_runtime_seconds: int = 120,
) -> Dict[str, str]:
    driver = None
    start_time = time.time()

    def check_timeout():
        if time.time() - start_time > max_runtime_seconds:
            raise TimeoutError(f"Engine timed out after {max_runtime_seconds} seconds")

    try:
        send_update("🚀 Engine 1: Captcha‑ready")
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
        check_timeout()
        time.sleep(2)

        ff = SmartFormFiller(driver)

        check_timeout()
        send_update("📧 Filling email...")
        ff.fill_field("email", shipping.get("email", ""))

        send_update("📦 Filling shipping...")
        ff.fill_shipping(shipping)
        ff.handle_state(shipping)

        check_timeout()
        send_update("🔄 Submitting shipping...")
        if not ff.click_pay_button():
            try:
                btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Continue')]")))
                btn.click()
            except Exception:
                try:
                    driver.find_element(By.CSS_SELECTOR, "form").submit()
                except Exception:
                    pass
        time.sleep(2)

        elapsed = time.time() - start_time
        remaining = max(0.1, max_runtime_seconds - elapsed)
        wait_for_captcha(
            driver, send_update,
            captcha_handler=captcha_handler,
            max_wait_seconds=remaining,
            api_key=CAPTCHA_API_KEY,
        )

        check_timeout()
        send_update("💳 Processing payment...")
        wait_for_payment_page(driver, send_update)

        for idx, card in enumerate(cards, 1):
            check_timeout()
            send_update(f"💳 Attempting card {idx}/{len(cards)}...")
            try:
                fill_card_on_platform(driver, card, shipping)

                if ff.click_pay_button():
                    time.sleep(5)
                else:
                    time.sleep(3)

                if not handle_threeds_challenge(driver, send_update, card):
                    send_update("⚠️ 3DS bypass failed, checking if order still succeeded...")
                time.sleep(2)

                handle_verification_code(driver, send_update, shipping)

                if wait_for_success(driver, send_update, max_wait=30):
                    send_update("✅ Checkout successful!")
                    return {"status": "success", "message": "Order confirmed."}

                send_update(f"❌ Card {idx} failed.")
            except Exception as e:
                send_update(f"⚠️ Card {idx} error: {str(e)[:80]}")
                continue

        return {"status": "failed", "message": "All cards declined."}
    except Exception as e:
        return {"status": "failed", "message": str(e)}
    finally:
        if driver:
            driver.quit()
            send_update("🧹 Engine 1 closed.")
