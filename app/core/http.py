import logging
import threading
import time
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class HttpFetchError(RuntimeError):
    def __init__(self, message: str, *, url: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code


def _safe_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


class PoliteHttpClient:
    """Small synchronous HTTP client with bounded retries and per-host pacing."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        backoff_seconds: float | None = None,
        min_interval_seconds: float | None = None,
        user_agent: str | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        settings = get_settings()
        self._session = session or requests.Session()
        self._owns_session = session is None
        self._timeout_seconds = (
            settings.http_timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        self._max_retries = settings.http_max_retries if max_retries is None else max_retries
        self._backoff_seconds = (
            settings.http_backoff_seconds if backoff_seconds is None else backoff_seconds
        )
        self._min_interval_seconds = (
            settings.http_min_interval_seconds
            if min_interval_seconds is None
            else min_interval_seconds
        )
        self._user_agent = user_agent or settings.http_user_agent
        self._clock = clock
        self._sleeper = sleeper
        self._host_last_request: dict[str, float] = {}
        self._rate_limit_lock = threading.Lock()

        if self._timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self._max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self._backoff_seconds < 0 or self._min_interval_seconds < 0:
            raise ValueError("HTTP delays cannot be negative")

    def get_html(self, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("URL must use HTTP or HTTPS and include a host")

        safe_url = _safe_url(url)
        total_attempts = self._max_retries + 1
        for attempt in range(total_attempts):
            self._wait_for_host(parsed.netloc.casefold())
            try:
                response = self._session.get(
                    url,
                    headers={"User-Agent": self._user_agent, "Accept": "text/html"},
                    timeout=self._timeout_seconds,
                    allow_redirects=True,
                )
            except (requests.Timeout, requests.ConnectionError) as error:
                if attempt == self._max_retries:
                    logger.error(
                        "HTTP request failed after retries",
                        extra={"url": safe_url, "attempts": total_attempts},
                    )
                    raise HttpFetchError(
                        f"Request failed after {total_attempts} attempts",
                        url=safe_url,
                    ) from error
                self._sleep_before_retry(attempt, retry_after=None)
                continue
            except requests.RequestException as error:
                logger.error(
                    "HTTP request failed without retry",
                    extra={"url": safe_url, "error_type": type(error).__name__},
                )
                raise HttpFetchError("Request failed", url=safe_url) from error

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt == self._max_retries:
                    logger.error(
                        "HTTP request returned a retryable error after retries",
                        extra={
                            "url": safe_url,
                            "status_code": response.status_code,
                            "attempts": total_attempts,
                        },
                    )
                    raise HttpFetchError(
                        f"Request returned HTTP {response.status_code} "
                        f"after {total_attempts} attempts",
                        url=safe_url,
                        status_code=response.status_code,
                    )
                self._sleep_before_retry(
                    attempt,
                    retry_after=self._parse_retry_after(response.headers.get("Retry-After")),
                )
                continue

            if response.status_code >= 400:
                logger.warning(
                    "HTTP request returned a non-retryable error",
                    extra={"url": safe_url, "status_code": response.status_code},
                )
                raise HttpFetchError(
                    f"Request returned HTTP {response.status_code}",
                    url=safe_url,
                    status_code=response.status_code,
                )

            content_type = response.headers.get("Content-Type", "").casefold()
            if content_type and not any(
                allowed in content_type for allowed in ("text/html", "application/xhtml+xml")
            ):
                raise HttpFetchError(
                    "Response is not HTML",
                    url=safe_url,
                    status_code=response.status_code,
                )

            logger.info(
                "HTTP request succeeded",
                extra={"url": safe_url, "status_code": response.status_code},
            )
            return response.text

        raise AssertionError("retry loop ended unexpectedly")

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def __enter__(self) -> "PoliteHttpClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _wait_for_host(self, host: str) -> None:
        with self._rate_limit_lock:
            now = self._clock()
            previous = self._host_last_request.get(host)
            if previous is not None:
                wait_seconds = self._min_interval_seconds - (now - previous)
                if wait_seconds > 0:
                    logger.debug(
                        "Rate limiting retailer host",
                        extra={"host": host, "wait_seconds": wait_seconds},
                    )
                    self._sleeper(wait_seconds)
                    now = self._clock()
            self._host_last_request[host] = now

    def _sleep_before_retry(self, attempt: int, retry_after: float | None) -> None:
        exponential_delay = self._backoff_seconds * (2**attempt)
        delay = max(exponential_delay, retry_after or 0.0)
        if delay > 0:
            self._sleeper(delay)

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            seconds = float(value)
        except ValueError:
            return None
        return max(0.0, min(seconds, 30.0))
