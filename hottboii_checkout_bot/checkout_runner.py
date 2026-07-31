# checkout_runner.py
from typing import Any, Callable, Dict, List, Optional

from engines import engine_captcha, engine_nocaptcha, engine_advanced
from engines.proxy_manager import get_working_proxy
import time

ENGINES = [
    ("No-CAPTCHA (fast)", engine_nocaptcha.perform_checkout),
    ("Advanced multi-strategy", engine_advanced.perform_checkout),
    ("Captcha-ready", engine_captcha.perform_checkout),
]


def run_checkout_with_fallback(
    url: str,
    shipping: Dict[str, str],
    cards: List[Dict[str, str]],
    send_update: Callable[[str], Any],
    headless: bool = True,
    captcha_handler: Optional[Callable[..., Any]] = None,
) -> Dict[str, str]:

    results = []

    for name, engine_func in ENGINES:
        proxy = get_working_proxy()
        strategy = [("direct", None)]
        if proxy:
            strategy.insert(0, ("proxy", proxy))
            send_update(f"🌐 Proxy acquired: {proxy}")

        for mode, px in strategy:
            label = f"{name} {'🌐' if mode == 'proxy' else '🔌 direct'}"
            send_update(f"🔄 Trying {label}...")
            try:
                result = engine_func(
                    url, shipping, cards, send_update, headless, px, captcha_handler
                )
                results.append({"engine": name, "mode": mode, "result": result})

                msg = result.get("message", "Unknown error")[:150]
                if result.get("status") == "success":
                    send_update(f"✅ {label} reported success, verifying truth...")
                else:
                    send_update(f"❌ {label} failed: {msg}")

                if "SSL_PROTOCOL" in msg or "ssl_protocol" in msg:
                    send_update("↩️ SSL error — retrying without proxy...")
                    break
            except Exception as e:
                err_str = str(e)[:150]
                results.append({"engine": name, "mode": mode, "result": {"status": "failed", "message": err_str}})
                send_update(f"⚠️ {label} error: {err_str}")
                if "SSL_PROTOCOL" in err_str or "ssl_protocol" in err_str:
                    send_update("↩️ SSL error — retrying without proxy...")
                    break
            time.sleep(1)

        time.sleep(2)

    successes = [r for r in results if r["result"].get("status") == "success"]

    if successes:
        send_update(f"\n📊 FINAL VERDICT: {len(successes)}/{len(ENGINES)} engines reported order confirmation")
        for s in successes:
            send_update(f"  ✅ {s['engine']} ({s['mode']})")
        return {"status": "success", "message": "Order confirmed — verified across engines."}

    send_update("\n📊 FINAL VERDICT: No engine confirmed the order")
    last_msg = results[-1]["result"].get("message", "Unknown error") if results else "All engines failed."
    return {"status": "failed", "message": last_msg}
