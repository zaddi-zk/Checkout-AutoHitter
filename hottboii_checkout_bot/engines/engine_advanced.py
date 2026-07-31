# engines/engine_advanced.py
import time
import random
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


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def perform_checkout(
    url: str,
    shipping: Dict[str, str],
    cards: List[Dict[str, str]],
    send_update: Callable[[str], Any],
    headless: bool = True,
    proxy: Optional[str] = None,
    captcha_handler: Optional[Callable[..., Any]] = None,
) -> Dict[str, str]:
    send_update("🚀 Engine 3: Advanced multi‑strategy")
    for attempt in range(2):
        driver = None
        try:
            driver = init_driver(headless, proxy)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": random.choice(USER_AGENTS)})
            if proxy:
                send_update(f"🌐 Using proxy: {proxy}")
            try:
                from config import BURP_ENABLED, BURP_PROXY
                if BURP_ENABLED and BURP_PROXY:
                    send_update(f"🔧 Burp Suite interception active: {BURP_PROXY}")
            except Exception:
                pass
            driver.get(url)
            time.sleep(5)

            ff = SmartFormFiller(driver)

            send_update("📧📦 Filling all fields...")
            ff.fill_field("email", shipping.get("email", ""))
            ff.fill_shipping(shipping)
            ff.handle_state(shipping)

            send_update("🔄 Submitting...")
            if not ff.click_pay_button():
                try:
                    driver.find_element(By.XPATH, "//button[@type='submit']").click()
                except Exception:
                    try:
                        driver.find_element(By.CSS_SELECTOR, "form").submit()
                    except Exception:
                        pass
            time.sleep(5)

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
            send_update(f"⚠️ Attempt {attempt+1} failed: {str(e)[:80]}")
            continue
        finally:
            if driver:
                driver.quit()

    return {"status": "failed", "message": "Engine 3 exhausted all attempts."}
