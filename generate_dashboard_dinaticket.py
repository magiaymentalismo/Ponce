#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ONEBOX_EVENTS = {
    "ALGUIEN DIJO ¿SUPERPODERES?": "https://entradas.laescaleradejacob.es/laescaleradejacob/events/56123",
    "VA DE MAGIA": "https://entradas.laescaleradejacob.es/laescaleradejacob/events/56127",
    "Fantasia": "https://entradas.laescaleradejacob.es/laescaleradejacob/events/56128",
}

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
    )
}

TZ = ZoneInfo("Europe/Madrid")

TEMPLATE_PATH = Path("template.html")
MANIFEST_PATH = Path("manifest.json")
SW_PATH = Path("sw.js")

MESES_ES = {
    "ene": "01", "enero": "01",
    "feb": "02", "febrero": "02",
    "mar": "03", "marzo": "03",
    "abr": "04", "abril": "04",
    "may": "05", "mayo": "05",
    "jun": "06", "junio": "06",
    "jul": "07", "julio": "07",
    "ago": "08", "agosto": "08",
    "sep": "09", "sept": "09", "septiembre": "09",
    "oct": "10", "octubre": "10",
    "nov": "11", "noviembre": "11",
    "dic": "12", "diciembre": "12",
}


def write_html(payload: dict) -> None:
    if not TEMPLATE_PATH.exists():
        print("❌ Error: No existe template.html")
        return

    html_template = TEMPLATE_PATH.read_text("utf-8")
    html = html_template.replace(
        "{{PAYLOAD_JSON}}",
        json.dumps(payload, ensure_ascii=False).replace("</script>", "<\\/script>")
    )

    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    (docs_dir / "index.html").write_text(html, "utf-8")
    print("✔ Generado docs/index.html")

    if MANIFEST_PATH.exists():
        shutil.copy(MANIFEST_PATH, docs_dir / "manifest.json")
        print("✔ Copiado manifest.json")

    if SW_PATH.exists():
        shutil.copy(SW_PATH, docs_dir / "sw.js")
        print("✔ Copiado sw.js")


def write_schedule_json(payload: dict) -> None:
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    (docs_dir / "schedule.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        "utf-8",
    )
    print("✔ Generado docs/schedule.json")


def parse_onebox_date(raw: str) -> tuple[str, str] | None:
    raw = raw.replace("\xa0", " ")
    raw = " ".join(raw.split()).lower()

    m = re.search(
        r"(?:lun|mar|mi[eé]|jue|vie|s[aá]b|dom)\.?,?\s+"
        r"(\d{1,2})\s+([a-záéíóúñ]+)\s+(\d{4})\s*-\s*(\d{1,2}):(\d{2})",
        raw,
        re.IGNORECASE,
    )

    if not m:
        return None

    dia, mes_txt, anio, hh, mm = m.groups()
    mes_key = mes_txt.lower().replace(".", "")
    mes_num = MESES_ES.get(mes_key)

    if not mes_num:
        print("DEBUG mes Onebox no reconocido:", repr(mes_txt))
        return None

    fecha_iso = f"{anio}-{mes_num}-{dia.zfill(2)}"
    hora = f"{int(hh):02d}:{mm}"

    return fecha_iso, hora


def extract_onebox_dates_from_text(text: str) -> list[str]:
    text = text.replace("\xa0", " ")
    text = " ".join(text.split())

    pattern = re.compile(
        r"(?:lun|mar|mi[eé]|jue|vie|s[aá]b|dom)\.?,?\s+"
        r"\d{1,2}\s+"
        r"(?:ene|feb|mar|abr|may|jun|jul|ago|sep|sept|oct|nov|dic|"
        r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
        r"septiembre|octubre|noviembre|diciembre)"
        r"\s+\d{4}\s*-\s*\d{1,2}:\d{2}",
        re.IGNORECASE,
    )

    return pattern.findall(text)


def count_onebox_stock_playwright(page) -> tuple[int | None, int | None]:
    available_selectors = [
        "[data-status='available']",
        "[data-state='available']",
        "[data-seat-status='available']",
        "[data-availability='available']",
        ".available",
        ".is-available",
        ".seat.available",
        "button:not([disabled])[aria-label*='Asiento']",
        "button:not([disabled])[aria-label*='Butaca']",
        "button:not([disabled])[aria-label*='Seat']",
        "svg [role='button']:not([aria-disabled='true'])",
    ]

    total_selectors = [
        "[data-seat-id]",
        "[data-place-id]",
        "[data-seat]",
        ".seat",
        "button[aria-label*='Asiento']",
        "button[aria-label*='Butaca']",
        "button[aria-label*='Seat']",
        "svg [role='button']",
    ]

    stock = None
    capacidad = None

    for selector in available_selectors:
        try:
            n = page.locator(selector).count()
            if n:
                stock = n
                break
        except Exception:
            pass

    for selector in total_selectors:
        try:
            n = page.locator(selector).count()
            if n:
                capacidad = n
                break
        except Exception:
            pass

    return stock, capacidad


def get_onebox_select_urls(page, parent_url: str) -> list[str]:
    if "/select/" in parent_url:
        return [parent_url]

    hrefs = page.eval_on_selector_all(
        "a[href]",
        """els => els.map(a => a.href).filter(h => h.includes('/select/'))"""
    )

    return sorted(set(hrefs))


def fetch_functions_onebox(url: str) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        page = browser.new_page(
            user_agent=UA["User-Agent"],
            viewport={"width": 1440, "height": 1100},
            locale="es-ES",
            timezone_id="Europe/Madrid",
        )

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"ERROR Onebox página padre {url}: {e}")
            browser.close()
            return []

        select_urls = get_onebox_select_urls(page, url)
        print("DEBUG Onebox select URLs:", select_urls)

        for select_url in select_urls:
            try:
                page.goto(select_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)

                body_text = page.locator("body").inner_text(timeout=15000)
                date_texts = extract_onebox_dates_from_text(body_text)

                print("DEBUG Onebox fechas en", select_url, ":", date_texts)

                for raw_date in date_texts:
                    parsed = parse_onebox_date(raw_date)
                    if not parsed:
                        continue

                    fecha_iso, hora = parsed
                    key = (fecha_iso, hora)

                    if key in seen:
                        continue

                    seen.add(key)

                    stock, capacidad = count_onebox_stock_playwright(page)
                    vendidas = (
                        max(0, capacidad - stock)
                        if stock is not None and capacidad is not None
                        else None
                    )

                    fecha_dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
                    fecha_label = fecha_dt.strftime("%d %b %Y")

                    out.append({
                        "fecha_label": fecha_label,
                        "fecha_iso": fecha_iso,
                        "hora": hora,
                        "vendidas_dt": vendidas,
                        "capacidad": capacidad,
                        "stock": stock,
                    })

            except Exception as e:
                print(f"ERROR Onebox select {select_url}: {e}")

        browser.close()

    return sorted(out, key=lambda f: (f["fecha_iso"], f.get("hora") or "00:00"))


def build_rows(funcs: list[dict]) -> list[list]:
    return [
        [
            f.get("fecha_label"),
            f.get("hora"),
            f.get("vendidas_dt"),
            f.get("fecha_iso"),
            f.get("capacidad"),
            f.get("stock"),
            None,
            None,
        ]
        for f in funcs
    ]


def build_payload(eventos: dict[str, list[dict]]) -> dict:
    now = datetime.now(TZ)
    out: dict[str, dict] = {}

    for sala, funcs in eventos.items():
        proximas: list[dict] = []
        pasadas: list[dict] = []

        for f in funcs:
            fecha_iso = f["fecha_iso"]
            hora_txt = f.get("hora") or "00:00"

            try:
                ses_dt = datetime.strptime(
                    f"{fecha_iso} {hora_txt}",
                    "%Y-%m-%d %H:%M"
                ).replace(tzinfo=TZ)
            except Exception:
                ses_dt = None

            if ses_dt and ses_dt >= now:
                proximas.append(f)
            elif ses_dt:
                pasadas.append(f)
            else:
                d = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
                if d >= now.date():
                    proximas.append(f)
                else:
                    pasadas.append(f)

        proximas.sort(key=lambda f: (f["fecha_iso"], f.get("hora") or "00:00"))

        print(
            f"[DEBUG] {sala}: total={len(funcs)} "
            f"· proximas={len(proximas)} · pasadas={len(pasadas)}"
        )

        headers = ["Fecha", "Hora", "Vendidas", "FechaISO", "Capacidad", "Stock", "Abono", "Fever"]

        out[sala] = {
            "table": {
                "headers": headers,
                "rows": build_rows(proximas),
            },
            "proximas": {
                "table": {
                    "headers": headers,
                    "rows": build_rows(proximas),
                }
            },
        }

    return {
        "generated_at": datetime.now(TZ).isoformat(),
        "eventos": out,
        "fever_urls": {},
    }


if __name__ == "__main__":
    current: dict[str, list[dict]] = {}

    for sala, url in ONEBOX_EVENTS.items():
        try:
            funcs = fetch_functions_onebox(url)
        except Exception as e:
            print(f"ERROR Onebox {sala}: {e}")
            funcs = []

        current[sala] = funcs
        print(f"{sala}: {len(funcs)} funciones Onebox extraídas")
        print(f"DEBUG {sala} funcs:", funcs)

    payload = build_payload(current)

    write_html(payload)
    write_schedule_json(payload)
