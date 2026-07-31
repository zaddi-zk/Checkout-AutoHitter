# engines/humanize.py
"""Human-like browser behavior: character-by-character typing, scrolling,
mouse events and randomized pauses, so automated checkouts look organic."""
import random
import time

from selenium.webdriver.remote.webelement import WebElement


def pause(min_seconds: float = 1.0, max_seconds: float = 2.5) -> None:
    """Sleep a random number of seconds between min and max."""
    time.sleep(random.uniform(min_seconds, max_seconds))


def type_human(
    element: WebElement,
    text: str,
    key_delay: tuple = (0.025, 0.09),
) -> bool:
    """Type text into an element one character at a time with jitter.

    Focuses the field, clears it, then types with realistic per-key delays
    and occasional micro-pauses. Returns True on success.
    """
    if not text:
        return True
    lo, hi = key_delay
    try:
        try:
            element.click()
        except Exception:
            pass
        try:
            element.clear()
        except Exception:
            pass
        for i, ch in enumerate(text):
            element.send_keys(ch)
            time.sleep(random.uniform(lo, hi))
            if i > 0 and i % 5 == 0:
                time.sleep(random.uniform(0.04, 0.16))
        return True
    except Exception:
        return False


def scroll_to(driver, element: WebElement, block: str = "center") -> bool:
    """Smooth-scroll an element into view, like a user looking for it."""
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({behavior:'smooth', block: arguments[1]});",
            element,
            block,
        )
        time.sleep(random.uniform(0.4, 0.9))
        return True
    except Exception:
        return False


def hover_and_click(driver, element: WebElement) -> bool:
    """Scroll to an element, emit mouse-move/down/up events near it, then click.

    Uses the native click() with a JS fallback if the element is covered.
    """
    if not scroll_to(driver, element):
        return False
    try:
        rect = element.rect
        x = int(rect.get("x", 0)) + int(rect.get("width", 0)) // 2 + random.randint(-6, 6)
        y = int(rect.get("y", 0)) + int(rect.get("height", 0)) // 2 + random.randint(-6, 6)
        driver.execute_script(
            "window.dispatchEvent(new MouseEvent('mousemove',{clientX:arguments[0],clientY:arguments[1],bubbles:true}));"
            "window.dispatchEvent(new MouseEvent('mousemove',{clientX:arguments[0]+arguments[2],clientY:arguments[1]+arguments[3],bubbles:true}));"
            "window.dispatchEvent(new MouseEvent('mousedown',{clientX:arguments[0],clientY:arguments[1],bubbles:true}));"
            "window.dispatchEvent(new MouseEvent('mouseup',{clientX:arguments[0],clientY:arguments[1],bubbles:true}));",
            x,
            y,
            random.randint(2, 20),
            random.randint(-10, 10),
        )
        time.sleep(random.uniform(0.1, 0.35))
    except Exception:
        pass
    try:
        element.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False


def human_scroll(driver, steps: int = None) -> None:
    """Scroll the page in a few randomized increments (up and down)."""
    steps = steps or random.randint(2, 5)
    for _ in range(steps):
        dy = random.randint(150, 450) * random.choice([1, 1, -1])
        try:
            driver.execute_script("window.scrollBy(0, arguments[0]);", dy)
        except Exception:
            pass
        time.sleep(random.uniform(0.15, 0.45))


def human_delay_between_actions() -> None:
    """A short 'thinking time' between major checkout steps."""
    pause(1.2, 3.2)
