from __future__ import annotations

from socket import timeout as SocketTimeout
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

DEFAULT_AISWEB_BASE_URL = "http://aisweb.decea.gov.br/api/"


class AiswebClientError(RuntimeError):
    """Raised when the AISWEB upstream request cannot be completed safely."""


def build_aisweb_met_url(*, base_url: str, api_key: str, api_pass: str, icao_code: str) -> str:
    return build_aisweb_area_url(
        base_url=base_url,
        api_key=api_key,
        api_pass=api_pass,
        area="met",
        icao_code=icao_code,
    )


def build_aisweb_area_url(*, base_url: str, api_key: str, api_pass: str, area: str, icao_code: str) -> str:
    base = (base_url or DEFAULT_AISWEB_BASE_URL).strip() or DEFAULT_AISWEB_BASE_URL
    separator = "&" if "?" in base and not base.endswith(("?", "&")) else ""
    if "?" not in base:
        separator = "?"
    params = urlencode(
        {
            "apiKey": api_key,
            "apiPass": api_pass,
            "area": area,
            "icaoCode": icao_code,
        }
    )
    return f"{base}{separator}{params}"


def fetch_aisweb_area(
    *,
    api_key: str,
    api_pass: str,
    base_url: str,
    area: str,
    icao_code: str,
    timeout_seconds: float = 8.0,
) -> str:
    url = build_aisweb_area_url(
        base_url=base_url,
        api_key=api_key,
        api_pass=api_pass,
        area=area,
        icao_code=icao_code,
    )
    request = Request(
        url,
        headers={
            "Accept": "application/xml,text/xml,text/plain;q=0.9,*/*;q=0.8",
            "User-Agent": "BrasilVida-Operacional/1.0",
        },
        method="GET",
    )
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(request, timeout=max(1.0, float(timeout_seconds))) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        raise AiswebClientError(f"AISWEB respondeu HTTP {exc.code}.") from exc
    except (URLError, SocketTimeout, TimeoutError, OSError) as exc:
        raise AiswebClientError("Falha de rede ou timeout ao consultar AISWEB.") from exc


def fetch_aisweb_met(
    *,
    api_key: str,
    api_pass: str,
    base_url: str,
    icao_code: str,
    timeout_seconds: float = 8.0,
) -> str:
    return fetch_aisweb_area(
        api_key=api_key,
        api_pass=api_pass,
        base_url=base_url,
        area="met",
        icao_code=icao_code,
        timeout_seconds=timeout_seconds,
    )


def fetch_aisweb_notams(
    *,
    api_key: str,
    api_pass: str,
    base_url: str,
    icao_code: str,
    timeout_seconds: float = 8.0,
) -> str:
    return fetch_aisweb_area(
        api_key=api_key,
        api_pass=api_pass,
        base_url=base_url,
        area="notam",
        icao_code=icao_code,
        timeout_seconds=timeout_seconds,
    )
