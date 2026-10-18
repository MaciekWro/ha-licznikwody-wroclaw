"""Stałe integracji MPWiK Wrocław."""

from datetime import timedelta

DOMAIN = "mpwik_wroclaw"

CONF_COOKIE = "cookie"
CONF_PODMIOT = "podmiot"
CONF_PUNKT = "punkt"
CONF_ADRES = "adres"
CONF_BACKFILL_DAYS = "backfill_days"

DEFAULT_BACKFILL_DAYS = 30
MAX_BACKFILL_DAYS = 365

# Częste zapytanie o /session/info podtrzymuje sesję eBOK przy życiu.
KEEPALIVE_INTERVAL = timedelta(minutes=5)
# Pełne pobranie danych (dobowe + import godzinowych do statystyk).
FETCH_INTERVAL = timedelta(hours=1)
# Brak danych z dnia młodszego niż tyle dni = dane jeszcze nie dotarły, czekamy.
DATA_DELAY_DAYS = 7

TIMEZONE = "Europe/Warsaw"

# Sensory z wcześniejszych wersji, usuwane z rejestru encji przy starcie.
REMOVED_SENSOR_KEYS = ("zuzycie_dobowe", "zuzycie_ostatniej_godziny")
