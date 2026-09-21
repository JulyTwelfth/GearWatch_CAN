import logging
from dataclasses import dataclass, field
from unittest.mock import Mock

import pytest
import requests

from app.core.http import HttpFetchError, PoliteHttpClient


@dataclass
class FakeClock:
    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_response(
    status_code: int = 200,
    body: str = "<html>ok</html>",
    headers: dict[str, str] | None = None,
) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = body.encode("utf-8")
    response.encoding = "utf-8"
    response.headers.update(headers or {"Content-Type": "text/html; charset=utf-8"})
    return response


def make_client(
    session: Mock,
    clock: FakeClock | None = None,
    *,
    max_retries: int = 2,
    min_interval_seconds: float = 0,
    backoff_seconds: float = 0.5,
) -> tuple[PoliteHttpClient, FakeClock]:
    fake_clock = clock or FakeClock()
    return (
        PoliteHttpClient(
            session=session,
            timeout_seconds=7,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            min_interval_seconds=min_interval_seconds,
            user_agent="GearWatch-Test/1.0",
            clock=fake_clock,
            sleeper=fake_clock.sleep,
        ),
        fake_clock,
    )


def test_get_html_uses_timeout_and_identifying_headers() -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = make_response(body="<html>fixture</html>")
    client, _ = make_client(session)

    html = client.get_html("https://retailer.example/product/123")

    assert html == "<html>fixture</html>"
    session.get.assert_called_once_with(
        "https://retailer.example/product/123",
        headers={"User-Agent": "GearWatch-Test/1.0", "Accept": "text/html"},
        timeout=7,
        allow_redirects=True,
    )


def test_connection_failures_retry_with_bounded_exponential_backoff() -> None:
    session = Mock(spec=requests.Session)
    session.get.side_effect = [
        requests.Timeout("first timeout"),
        requests.ConnectionError("connection reset"),
        make_response(),
    ]
    client, clock = make_client(session)

    assert client.get_html("https://retailer.example/product") == "<html>ok</html>"
    assert session.get.call_count == 3
    assert clock.sleeps == [0.5, 1.0]


def test_exhausted_timeouts_raise_controlled_error() -> None:
    session = Mock(spec=requests.Session)
    session.get.side_effect = requests.Timeout("timeout")
    client, clock = make_client(session, max_retries=1)

    with pytest.raises(HttpFetchError, match="after 2 attempts") as caught:
        client.get_html("https://retailer.example/product")

    assert caught.value.status_code is None
    assert session.get.call_count == 2
    assert clock.sleeps == [0.5]


def test_retry_after_is_respected_but_capped() -> None:
    session = Mock(spec=requests.Session)
    session.get.side_effect = [
        make_response(503, headers={"Content-Type": "text/html", "Retry-After": "120"}),
        make_response(),
    ]
    client, clock = make_client(session)

    client.get_html("https://retailer.example/product")

    assert session.get.call_count == 2
    assert clock.sleeps == [30.0]


def test_non_retryable_http_error_fails_once_and_redacts_query(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = make_response(404)
    client, _ = make_client(session)
    caplog.set_level(logging.WARNING)

    with pytest.raises(HttpFetchError) as caught:
        client.get_html("https://retailer.example/missing?tracking=secret")

    assert caught.value.status_code == 404
    assert caught.value.url == "https://retailer.example/missing"
    assert session.get.call_count == 1
    assert all("tracking=secret" not in record.getMessage() for record in caplog.records)


def test_requests_are_rate_limited_per_host() -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = make_response()
    client, clock = make_client(session, min_interval_seconds=2.0)

    client.get_html("https://retailer.example/product/1")
    client.get_html("https://retailer.example/product/2")
    client.get_html("https://another.example/product/1")

    assert clock.sleeps == [2.0]


def test_non_html_response_is_rejected() -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = make_response(
        body='{"price": 100}', headers={"Content-Type": "application/json"}
    )
    client, _ = make_client(session)

    with pytest.raises(HttpFetchError, match="not HTML"):
        client.get_html("https://retailer.example/product")


def test_get_json_accepts_shopify_javascript_mime_and_uses_json_accept_header() -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = make_response(
        body='{"variants": []}', headers={"Content-Type": "text/javascript; charset=utf-8"}
    )
    client, _ = make_client(session)

    result = client.get_json("https://retailer.example/product.js")

    assert result == '{"variants": []}'
    session.get.assert_called_once_with(
        "https://retailer.example/product.js",
        headers={"User-Agent": "GearWatch-Test/1.0", "Accept": "application/json"},
        timeout=7,
        allow_redirects=True,
    )


def test_invalid_url_is_rejected_without_a_request() -> None:
    session = Mock(spec=requests.Session)
    client, _ = make_client(session)

    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        client.get_html("file:///local/fixture.html")

    session.get.assert_not_called()


def test_non_connection_request_error_is_wrapped_without_retry() -> None:
    session = Mock(spec=requests.Session)
    session.get.side_effect = requests.TooManyRedirects("redirect loop")
    client, _ = make_client(session)

    with pytest.raises(HttpFetchError, match="Request failed"):
        client.get_html("https://retailer.example/product")

    assert session.get.call_count == 1


def test_invalid_retry_configuration_is_rejected() -> None:
    session = Mock(spec=requests.Session)

    with pytest.raises(ValueError, match="cannot be negative"):
        PoliteHttpClient(session=session, max_retries=-1)
