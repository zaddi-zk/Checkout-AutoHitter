# engines/stealth.py
"""Free, dependency-free browser stealth via Chrome DevTools Protocol.

Injects a patch that removes the navigator.webdriver marker and spoofs common
fingerprints (plugins, languages, permissions, chrome runtime) on every new
document, so stores are less likely to challenge the session with a CAPTCHA.
"""
import logging

logger = logging.getLogger(__name__)

STEALTH_SCRIPT = r"""
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'plugins', {
      get: () => [1, 2, 3, 4, 5],
    });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'permissions', {
      get: () => ({ query: () => Promise.resolve({ state: 'denied' }) }),
    });
  } catch (e) {}
  try {
    window.chrome = window.chrome || { runtime: {} };
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
  } catch (e) {}
})();
"""


def apply_stealth(driver) -> None:
    """Apply stealth patches to a freshly-created Chrome driver.

    Injects on-new-document via CDP so the patch also applies to iframes and
    after navigations, then patches the current page directly.
    """
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": STEALTH_SCRIPT},
        )
        driver.execute_script(STEALTH_SCRIPT)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Stealth patch skipped: %s", exc)
