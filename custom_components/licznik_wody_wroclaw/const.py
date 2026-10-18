"""Stałe integracji MPWiK Wrocław."""

from datetime import timedelta

DOMAIN = "licznik_wody_wroclaw"

CONF_COOKIE = "cookie"
CONF_PODMIOT = "podmiot"
CONF_PUNKT = "punkt"
CONF_ADRES = "adres"
CONF_BACKFILL_DAYS = "backfill_days"

DEFAULT_BACKFILL_DAYS = 30
MAX_BACKFILL_DAYS = 365

# Częste zapytanie o /session/info podtrzymuje sesję eBOK przy życiu
# (sesja wygasa po ok. 45 min bez aktywności). Ustawiane w opcjach integracji.
CONF_KEEPALIVE_MINUTES = "keepalive_minutes"
DEFAULT_KEEPALIVE_MINUTES = 5
MIN_KEEPALIVE_MINUTES = 1
MAX_KEEPALIVE_MINUTES = 30
# Pełne pobranie danych (dobowe + import godzinowych do statystyk).
FETCH_INTERVAL = timedelta(hours=1)
# Brak danych z dnia młodszego niż tyle dni = dane jeszcze nie dotarły, czekamy.
DATA_DELAY_DAYS = 7

TIMEZONE = "Europe/Warsaw"
