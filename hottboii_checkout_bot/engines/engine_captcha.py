# engines/engine_captcha.py
from typing import Any, Callable, Dict, List, Optional

from .engine_base import perform_checkout_core


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
    send_update("🚀 Engine 1: Captcha-ready")
    return perform_checkout_core(
        url, shipping, cards, send_update,
        headless=headless,
        proxy=proxy,
        captcha_handler=captcha_handler,
        strategy="captcha",
        max_runtime_seconds=max_runtime_seconds,
    )
