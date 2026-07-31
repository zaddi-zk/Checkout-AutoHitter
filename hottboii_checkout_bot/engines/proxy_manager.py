import time
import random
import re
import threading
import logging
import socket
import requests

logger = logging.getLogger(__name__)

PROXY_SOURCES = [
    "https://free-proxy-list.net/",
    "https://www.sslproxies.org/",
]

def _dns_ok(hostname="api.telegram.org", timeout=1):
    try:
        socket.setdefaulttimeout(timeout)
        socket.gethostbyname(hostname)
        return True
    except Exception:
        return False

class ProxyManager:
    def __init__(self, cache_ttl: int = 600, max_working: int = 3, sample_size: int = 50):
        self.cache_ttl = cache_ttl
        self.max_working = max_working
        self.sample_size = sample_size
        self.proxy_pool = []
        self.last_refresh = 0.0
        self.last_attempt = 0.0
        self.fail_count = 0
        self.lock = threading.Lock()
        self._worker_thread = threading.Thread(target=self._background_loop, daemon=True)
        self._worker_thread.start()

    def get_proxy(self):
        with self.lock:
            if self.proxy_pool:
                return random.choice(self.proxy_pool)
            return None

    def _scrape_sources(self):
        scraped = set()
        for url in PROXY_SOURCES:
            try:
                resp = requests.get(url, timeout=3)
                if resp.status_code != 200:
                    continue
                pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{2,5})'
                for ip, port in re.findall(pattern, resp.text):
                    scraped.add(f"http://{ip}:{port}")
            except Exception as e:
                logger.debug(f"Proxy scrape failed for {url}: {e}")
        return list(scraped)

    def _validate_proxy(self, proxy_str: str) -> bool:
        proxies = {"http": proxy_str, "https": proxy_str}
        try:
            res = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=3)
            if res.status_code != 200:
                return False
            geo = requests.get(
                "https://ip-api.com/json/?fields=status,country",
                proxies=proxies, timeout=3,
            )
            if geo.status_code != 200:
                return False
            data = geo.json()
            if data.get("status") != "success":
                return False
            return str(data.get("country", "")).lower() in ("united states", "usa", "us")
        except Exception:
            return False

    def _refresh_pool(self):
        self.last_attempt = time.time()
        logger.debug("Refreshing proxy pool...")
        start = time.time()
        raw = self._scrape_sources()
        if not raw:
            return
        sampled = random.sample(raw, min(len(raw), self.sample_size))
        valid = []
        for proxy in sampled:
            if time.time() - start > 10:
                logger.debug("Global 10s deadline reached during proxy validation.")
                break
            if self._validate_proxy(proxy):
                valid.append(proxy)
                if len(valid) >= self.max_working:
                    break
        if valid:
            with self.lock:
                self.proxy_pool = valid
                self.last_refresh = time.time()
            logger.info(f"Pool updated: {len(valid)} active proxies.")
        else:
            logger.debug("No valid proxies found in this cycle.")

    def _background_loop(self):
        if not _dns_ok():
            logger.warning("DNS resolution failing — proxy scraping disabled until network recovers.")
            time.sleep(30)
        if _dns_ok():
            self._refresh_pool()
        while True:
            if not self.proxy_pool:
                self.fail_count += 1
                backoff = min(60 * (2 ** min(self.fail_count, 5)), 600)
                logger.debug(f"Proxy pool empty, retrying in {backoff}s (fail_count={self.fail_count})")
                time.sleep(backoff)
                if _dns_ok():
                    self._refresh_pool()
                continue
            time.sleep(60)
            if time.time() - self.last_attempt > self.cache_ttl:
                if _dns_ok():
                    try:
                        self._refresh_pool()
                        self.fail_count = 0
                    except Exception as e:
                        logger.error(f"Background proxy refresh error: {e}")
                        self.fail_count += 1
                else:
                    logger.debug("Skipping proxy refresh — DNS resolution failing.")

_manager = ProxyManager()


def get_working_proxy():
    """Return a configured proxy, or None.

    Proxies are strictly opt-in. Set USE_PROXY=true and either:
      - PROXY_URL      -> a single fixed proxy is used directly, or
      - (optional pool) -> the ProxyManager scrapes/validates proxies.
    """
    try:
        from config import USE_PROXY, PROXY_URL
    except Exception:
        USE_PROXY, PROXY_URL = False, ""

    if not USE_PROXY:
        return None

    if PROXY_URL and PROXY_URL.strip():
        return PROXY_URL.strip()

    proxy = _manager.get_proxy()
    return proxy if proxy else None
