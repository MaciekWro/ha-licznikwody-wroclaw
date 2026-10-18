"""Koordynator: podtrzymanie sesji, pobieranie danych i import statystyk godzinowych."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util, slugify
from homeassistant.util.unit_conversion import VolumeConverter

from .api import MpwikAuthError, MpwikClient, MpwikError, parse_cookie
from .const import (
    CONF_ADRES,
    CONF_BACKFILL_DAYS,
    CONF_COOKIE,
    CONF_PODMIOT,
    CONF_PUNKT,
    DATA_DELAY_DAYS,
    DEFAULT_BACKFILL_DAYS,
    DOMAIN,
    FETCH_INTERVAL,
    KEEPALIVE_INTERVAL,
    TIMEZONE,
)

_LOGGER = logging.getLogger(__name__)
_TZ = ZoneInfo(TIMEZONE)
# Ciasteczka, których zmiana oznacza nową sesję i warto ją zapisać w konfiguracji.
_SESSION_COOKIES = ("JSESSIONID", "SERVERG1")


@dataclass
class MpwikData:
    """Ostatnie znane wartości dla sensorów."""

    stan_wodomierza: float | None = None
    stan_wodomierza_czas: datetime | None = None
    # koniec godziny ostatniego odczytu i zużycie w tej godzinie
    ostatnia_godzina: datetime | None = None
    zuzycie_godzinowe: float | None = None
    # zużycie od początku doby (eBOK: od 23:00 dnia poprzedniego) do ostatniego odczytu
    zuzycie_dzienne: float | None = None
    zuzycie_dzienne_dzien: date | None = None
    licznik: str | None = None


class MpwikCoordinator(DataUpdateCoordinator[MpwikData]):
    """Co 5 min podtrzymuje sesję, co godzinę pobiera dane."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: MpwikClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=KEEPALIVE_INTERVAL,
        )
        self.client = client
        self.podmiot: str = entry.data[CONF_PODMIOT]
        self.punkt: str = entry.data[CONF_PUNKT]
        self.statistic_id = f"{DOMAIN}:{slugify(f'{self.podmiot}_{self.punkt}')}"
        self._last_fetch: datetime | None = None
        self._data = MpwikData()

    async def _async_update_data(self) -> MpwikData:
        try:
            await self.client.session_info()
            now = dt_util.utcnow()
            if self._last_fetch is None or now - self._last_fetch >= FETCH_INTERVAL:
                await self._fetch()
                self._last_fetch = now
        except MpwikAuthError as err:
            raise ConfigEntryAuthFailed(
                "Sesja eBOK wygasła - wklej nowe ciasteczko z przeglądarki"
            ) from err
        except MpwikError as err:
            raise UpdateFailed(str(err)) from err
        self._persist_cookie()
        return self._data

    def _persist_cookie(self) -> None:
        """Zapisuje odświeżone przez serwer ciasteczka sesji, by przetrwały restart HA."""
        current = self.client.cookie_header()
        stored = self.config_entry.data[CONF_COOKIE]
        old, new = parse_cookie(stored), parse_cookie(current) if current else {}
        if any(new.get(k) and new.get(k) != old.get(k) for k in _SESSION_COOKIES):
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, CONF_COOKIE: current}
            )

    async def _fetch(self) -> None:
        await self._import_hourly(dt_util.now(_TZ).date())

    async def _import_hourly(self, today: date) -> None:
        """Dopisuje nowe godziny do statystyk zewnętrznych (panel Energia -> Woda).

        Przy okazji aktualizuje wartości sensorów. Zużycie dzienne liczymy z odczytów
        godzinowych (do godziny ostatniego odczytu), bo ostatni wpis endpointu dobowego
        bywa zerowy. Doba w eBOK trwa od 23:00 dnia poprzedniego do 23:00.
        """
        last = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, self.statistic_id, True, {"sum"}
        )
        if rows := last.get(self.statistic_id):
            last_start: datetime | None = dt_util.utc_from_timestamp(rows[0]["start"])
            total = rows[0]["sum"] or 0.0
            # o dzień wcześniej, żeby po restarcie odtworzyć zużycie dzienne
            day = (last_start + timedelta(hours=1)).astimezone(_TZ).date() - timedelta(days=1)
        else:
            last_start = None
            total = 0.0
            backfill = self.config_entry.data.get(CONF_BACKFILL_DAYS, DEFAULT_BACKFILL_DAYS)
            day = today - timedelta(days=backfill)

        stats: list[StatisticData] = []
        prev_end: datetime | None = None
        while day <= today:
            odczyty = await self.client.odczyty_godzinowe(self.podmiot, self.punkt, day)
            if not odczyty and (today - day).days < DATA_DELAY_DAYS:
                break  # dane z tego dnia jeszcze nie dotarły - spróbujemy później
            # pierwszy odczyt to 23:00 dnia poprzedniego - należy do poprzedniej doby
            doba = [o for o in odczyty if o.data.date() == day and o.zuzycie is not None]
            if doba:
                self._data.zuzycie_dzienne = round(sum(o.zuzycie for o in doba), 3)
                self._data.zuzycie_dzienne_dzien = day
            for o in odczyty:
                end = _to_utc(o.data)
                if prev_end and end <= prev_end:
                    # zmiana czasu z letniego na zimowy: ta sama godzina lokalna drugi raz
                    end = o.data.replace(tzinfo=_TZ, fold=1).astimezone(UTC)
                    if end <= prev_end:
                        continue  # duplikat (np. 23:00 dnia poprzedniego)
                prev_end = end
                if o.zuzycie is None:
                    continue
                self._data.ostatnia_godzina = end
                self._data.zuzycie_godzinowe = o.zuzycie
                self._data.licznik = o.licznik or self._data.licznik
                if o.wskazanie is not None:
                    self._data.stan_wodomierza = o.wskazanie
                    self._data.stan_wodomierza_czas = end
                start = end - timedelta(hours=1)
                if last_start and start <= last_start:
                    continue  # już zaimportowane
                total = round(total + o.zuzycie, 3)
                stats.append(StatisticData(start=start, state=o.wskazanie, sum=total))
            day += timedelta(days=1)
            await asyncio.sleep(0.3)  # nie zasypujemy eBOK zapytaniami przy backfillu

        if not stats:
            return
        _LOGGER.debug("Import %d godzin do %s", len(stats), self.statistic_id)
        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"Licznik wody {self.config_entry.data.get(CONF_ADRES, self.punkt)}",
            source=DOMAIN,
            statistic_id=self.statistic_id,
            unit_class=VolumeConverter.UNIT_CLASS,
            unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        )
        async_add_external_statistics(self.hass, metadata, stats)


def _to_utc(local_naive: datetime) -> datetime:
    return local_naive.replace(tzinfo=_TZ).astimezone(UTC)
