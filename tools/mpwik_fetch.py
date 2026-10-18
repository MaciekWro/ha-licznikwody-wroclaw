#!/usr/bin/env python3
"""Pobiera godzinowe zużycie wody z eBOK MPWiK Wrocław i zapisuje je do CSV.

Przykład:
    export MPWIK_COOKIE='JSESSIONID=...; SERVERG1=...'
    python3 tools/mpwik_fetch.py --podmiot 380281 --od 2026-10-01 --do 2026-10-15 -o zuzycie.csv

Wymaga: pip install aiohttp
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "licznik_wody_wroclaw"))

import aiohttp  # noqa: E402

from api import MpwikAuthError, MpwikClient  # noqa: E402


async def main(args: argparse.Namespace) -> int:
    cookie = args.cookie or os.environ.get("MPWIK_COOKIE")
    if not cookie:
        print("Podaj ciasteczko przez --cookie albo zmienną MPWIK_COOKIE", file=sys.stderr)
        return 2

    async with aiohttp.ClientSession() as session:
        client = MpwikClient(session, cookie)
        try:
            info = await client.session_info()
        except MpwikAuthError as err:
            print(f"Błąd logowania: {err}", file=sys.stderr)
            return 1
        print(f"Zalogowano jako {info['user_login']}", file=sys.stderr)

        punkt = args.punkt
        if not punkt:
            punkty = await client.punkty_sieci(args.podmiot)
            for p in punkty:
                print(f"  punkt {p['numer']}: {p['adres']}", file=sys.stderr)
            punkt = punkty[0]["numer"]
        print(f"Punkt: {punkt}", file=sys.stderr)

        out = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
        writer = csv.writer(out)
        writer.writerow(["koniec_godziny", "wskazanie_m3", "zuzycie_m3", "licznik"])
        seen = set()
        dzien = args.od
        while dzien <= args.do:
            for o in await client.odczyty_godzinowe(args.podmiot, punkt, dzien):
                if o.data in seen:
                    continue
                seen.add(o.data)
                writer.writerow([o.data.isoformat(), o.wskazanie, o.zuzycie, o.licznik])
            dzien += timedelta(days=1)
        if out is not sys.stdout:
            out.close()
            print(f"Zapisano {len(seen)} odczytów do {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cookie", help="nagłówek Cookie z przeglądarki (lub wartość JSESSIONID)")
    parser.add_argument("--podmiot", required=True, help="kod podmiotu (parametr ?p= w adresie eBOK)")
    parser.add_argument("--punkt", help="numer punktu sieci, np. 0670/5550 (domyślnie pierwszy)")
    parser.add_argument("--od", type=date.fromisoformat, default=date.today() - timedelta(days=7))
    parser.add_argument("--do", type=date.fromisoformat, default=date.today())
    parser.add_argument("-o", "--output", help="plik CSV (domyślnie stdout)")
    sys.exit(asyncio.run(main(parser.parse_args())))
