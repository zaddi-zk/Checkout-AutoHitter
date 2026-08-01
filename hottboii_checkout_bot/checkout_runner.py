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

    # Proxy is opt-in (USE_PROXY=true). Random public proxies are never used
    # unless explicitly configured, because they break checkout reliability.
    proxy = get_working_proxy()
    strategies = [("direct", None)]
    if proxy:
        strategies.insert(0, ("proxy", proxy))
        send_update(f"🌐 Proxy acquired: {proxy}")

    results = []

    for name, engine_func in ENGINES:
        for mode, px in strategies:
            label = f"{name} {'🌐' if mode == 'proxy' else '🔌 direct'}"
            send_update(f"🔄 Trying {label}...")
            try:
                result = engine_func(
                    url, shipping, cards, send_update, headless, px, captcha_handler,
                )
                results.append({"engine": name, "mode": mode, "result": result})

                msg = result.get("message", "Unknown error")[:150]
                if result.get("status") == "success":
                    send_update(f"✅ {label} confirmed the order!")
                    return {
                        "status": "success",
                        "message": f"Order confirmed via {name} ({mode}).",
                    }
                else:
                    send_update(f"❌ {label} failed: {msg}")
            except Exception as e:
                err_str = str(e)[:150]
                results.append({"engine": name, "mode": mode, "result": {"status": "failed", "message": err_str}})
                send_update(f"⚠️ {label} error: {err_str}")
            time.sleep(1)

        time.sleep(2)

    send_update("\n📊 FINAL VERDICT: No engine confirmed the order")
    last_msg = results[-1]["result"].get("message", "Unknown error") if results else "All engines failed."
    return {"status": "failed", "message": last_msg}
