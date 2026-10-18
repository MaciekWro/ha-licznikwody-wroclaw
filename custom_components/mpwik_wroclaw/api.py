"""Klient API eBOK MPWiK Wrocław (https://ebok.mpwik.wroc.pl).

Moduł nie zależy od Home Assistant - można go używać samodzielnie (patrz tools/mpwik_fetch.py).

Logowanie w eBOK wymaga tokenu Google reCAPTCHA, więc klient nie loguje się sam.
Korzysta z ciasteczek sesji skopiowanych z przeglądarki (nagłówek ``Cookie``)
i podtrzymuje sesję okresowymi zapytaniami.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from http.cookies import SimpleCookie
from typing import Any

import aiohttp
from yarl import URL

BASE_URL = "https://ebok.mpwik.wroc.pl"
API_URL = f"{BASE_URL}/frontend-api/v1"

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
    ),
    "Referer": f"{BASE_URL}/trust/zuzycie-wody",
}


class MpwikError(Exception):
    """Ogólny błąd komunikacji z eBOK."""


class MpwikAuthError(MpwikError):
    """Sesja wygasła lub ciasteczko jest nieprawidłowe."""


@dataclass(slots=True)
class Odczyt:
    """Pojedynczy odczyt (godzinowy lub dobowy)."""

    licznik: str
    data: datetime  # czas lokalny (Europe/Warsaw), bez strefy - tak zwraca API
    wskazanie: float | None
    zuzycie: float | None
    typ: str | None

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Odczyt:
        return cls(
            licznik=raw.get("licznik", ""),
            data=datetime.fromisoformat(raw["data"]),
            wskazanie=_float(raw.get("wskazanie")),
            zuzycie=_float(raw.get("zuzycie")),
            typ=raw.get("typ"),
        )


def _float(value: Any) -> float | None:
    return None if value is None else float(value)


def parse_cookie(cookie: str) -> dict[str, str]:
    """Zamienia wklejony nagłówek Cookie (albo samą wartość JSESSIONID) na słownik."""
    cookie = cookie.strip()
    if cookie.lower().startswith("cookie:"):
        cookie = cookie[7:].strip()
    if "=" not in cookie:
        return {"JSESSIONID": cookie}
    parsed = SimpleCookie()
    parsed.load(cookie)
    return {key: morsel.value for key, morsel in parsed.items()}


def punkt_do_url(numer_punktu: str) -> str:
    """Numer punktu '0670/5550' -> '0670-5550' (tak jak robi to frontend eBOK)."""
    return numer_punktu.replace("/", "-")


class MpwikClient:
    """Asynchroniczny klient eBOK MPWiK Wrocław."""

    def __init__(self, session: aiohttp.ClientSession, cookie: str) -> None:
        self._session = session
        session.cookie_jar.update_cookies(parse_cookie(cookie), URL(BASE_URL))

    def cookie_header(self) -> str:
        """Aktualne ciasteczka (serwer może je odświeżać) jako nagłówek Cookie."""
        cookies = self._session.cookie_jar.filter_cookies(URL(BASE_URL))
        return "; ".join(f"{key}={morsel.value}" for key, morsel in cookies.items())

    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        try:
            async with self._session.get(
                f"{API_URL}{path}",
                params=params,
                headers=_HEADERS,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (401, 403) or resp.status in (301, 302, 303):
                    raise MpwikAuthError(f"Brak autoryzacji ({resp.status}) dla {path}")
                if resp.status != 200:
                    text = await resp.text()
                    raise MpwikError(f"HTTP {resp.status} dla {path}: {text[:200]}")
                if "json" not in resp.headers.get("Content-Type", ""):
                    # np. strona blokady Imperva albo przekierowanie na logowanie
                    raise MpwikAuthError(f"Nieoczekiwana odpowiedź (nie JSON) dla {path}")
                return await resp.json()
        except aiohttp.ClientError as err:
            raise MpwikError(f"Błąd połączenia: {err}") from err
        except TimeoutError as err:
            raise MpwikError("Przekroczono czas oczekiwania na eBOK") from err

    async def session_info(self) -> dict[str, Any]:
        """Informacje o sesji. Rzuca MpwikAuthError, jeśli sesja nie jest zalogowana.

        Wywołanie podtrzymuje też sesję przy życiu.
        """
        info = await self._get("/session/info")
        if not info.get("user_login"):
            raise MpwikAuthError("Sesja nie jest zalogowana (wygasła lub złe ciasteczko)")
        return info

    async def punkty_sieci(self, podmiot: str) -> list[dict[str, Any]]:
        data = await self._get(f"/podmioty/{podmiot}/punkty-sieci", {"status": "AKTYWNE"})
        return data.get("punkty", [])

    async def liczniki(self, podmiot: str, punkt: str) -> list[dict[str, Any]]:
        data = await self._get(
            f"/podmioty/{podmiot}/punkty-sieci/{punkt_do_url(punkt)}/liczniki",
            {"status": "AKTYWNE"},
        )
        return data.get("liczniki", [])

    async def odczyty_godzinowe(self, podmiot: str, punkt: str, dzien: date) -> list[Odczyt]:
        """Odczyty godzinowe z jednego dnia (API nie przyjmuje dłuższych zakresów).

        Każdy odczyt ma czas KOŃCA godziny, a ``zuzycie`` to zużycie w tej godzinie.
        Odpowiedź zawiera też odczyt z godz. 23:00 dnia poprzedniego.
        Dane pojawiają się zwykle z 2-3 dniowym opóźnieniem.
        """
        data = await self._get(
            f"/podmioty/{podmiot}/punkty-sieci/{punkt_do_url(punkt)}/odczyty/godzinowe",
            _zakres(dzien, dzien),
        )
        return [Odczyt.from_json(o) for o in data.get("odczyty", [])]

    async def odczyty_dobowe(
        self, podmiot: str, punkt: str, od: date, do: date
    ) -> list[Odczyt]:
        data = await self._get(
            f"/podmioty/{podmiot}/punkty-sieci/{punkt_do_url(punkt)}/odczyty/dobowe",
            _zakres(od, do),
        )
        return [Odczyt.from_json(o) for o in data.get("odczyty", [])]


def _zakres(od: date, do: date) -> dict[str, str]:
    return {
        "dataOd": datetime.combine(od, time.min).isoformat(timespec="seconds"),
        "dataDo": datetime.combine(do, time(23, 59, 59)).isoformat(timespec="seconds"),
    }
