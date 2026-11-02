"""One function per store. Each returns a list of product dicts (camelCase keys, same as the Android app)."""
import json
import re
import time
from html import unescape
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

UA = {"User-Agent": "PriceHunterBot/0.1 (personal price comparison project)"}


def num(text):
    digits = re.sub(r"[^\d.]", "", (text or "").replace(",", ""))
    return int(float(digits)) if digits else None


def extract_specifications(markup):
    soup = BeautifulSoup(markup or "", "html.parser")
    rows = soup.select(".product-specs-table tr") or soup.select("table tr")
    specifications = {}
    for row in rows[:30]:
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) < 2:
            continue
        name = unescape(cells[0].get_text(" ", strip=True))
        value = unescape(cells[1].get_text(" ", strip=True))
        if name and value:
            specifications[name[:80]] = value[:300]
    return specifications


def opencart_store(store_id, base, categories):
    out, seen = [], set()
    with httpx.Client(headers=UA, timeout=30, follow_redirects=True) as client:
        for path, category in categories.items():
            for page in range(1, 21):
                r = client.get(urljoin(base, path), params={"page": page, "limit": 100})
                if r.status_code != 200:
                    print(f"[{store_id}] {path} page {page} returned HTTP {r.status_code}")
                    break
                cards = BeautifulSoup(r.text, "html.parser").select(".product-layout")
                new_items = 0
                for card in cards:
                    link = card.select_one(".name a") or card.select_one("a[href]")
                    if not link:
                        continue
                    url = urljoin(base, link["href"])
                    if urlparse(url).hostname != urlparse(base).hostname:
                        continue
                    pid = f"{store_id}:" + urlparse(url).path.rstrip("/").split("/")[-1]
                    if pid in seen:
                        continue
                    price_element = next(
                        (card.select_one(selector) for selector in (".price-new", ".price-normal", ".price")
                         if card.select_one(selector)),
                        None
                    )
                    price = num(price_element.get_text(" ", strip=True) if price_element else "")
                    if not price:
                        continue
                    old = card.select_one(".price-old")
                    img = card.select_one("img")
                    name = (
                        link.get_text(" ", strip=True)
                        or link.get("title")
                        or (img.get("alt") or img.get("title") if img else "")
                    )
                    if not name:
                        continue
                    brand_link = card.select_one(".brand a")
                    brand = brand_link.get_text(" ", strip=True) if brand_link else ""
                    description = str(card.select_one(".description") or "")
                    specifications = (
                        extract_specifications(description) if "<table" in description.lower() else {}
                    )
                    seen.add(pid)
                    new_items += 1
                    out.append({
                        "id": pid, "name": name, "brand": brand or name.split(" ")[0],
                        "category": category, "storeId": store_id, "price": price,
                        "oldPrice": num(old.get_text(" ", strip=True)) if old else None,
                        "imageUrl": urljoin(base, img.get("data-src") or img.get("src"))
                        if img and (img.get("data-src") or img.get("src")) else None,
                        "specifications": specifications,
                        "inStock": "out of stock" not in card.get_text(" ").lower(),
                        "url": url,
                    })
                if new_items == 0:
                    break
                time.sleep(1)  # be gentle with the store's server
            else:
                print(f"[{store_id}] stopped at the 20-page limit for {path}")
    return out


def badr():
    return opencart_store("elbadr", "https://elbadrgroupeg.store/", {
        "cpu": "CPU", "motherboard": "Motherboard", "ram": "RAM", "hdd": "Hard Disk",
        "ssd": "SSD", "monitors": "Monitor", "vga": "Graphics Card",
        "cooling": "Cooling", "power-supply": "Power Supply",
    })


def maximum():
    return opencart_store("maximum", "https://maximumhardware.store/", {
        "cpu-%E2%97%8F-mobo/processors": "CPU",
        "cpu-%E2%97%8F-mobo/motherboards": "Motherboard",
        "mem-%E2%97%8F-ssd-%E2%97%8F-hdd/memory": "RAM",
        "mem-%E2%97%8F-ssd-%E2%97%8F-hdd/hard-disks": "Hard Disk",
        "mem-%E2%97%8F-ssd-%E2%97%8F-hdd/ssd": "SSD",
        "monitors": "Monitor",
        "graphic-card": "Graphics Card",
        "cases-%E2%97%8F-psu-%E2%97%8F-fans/fans-pc-cooling": "Cooling",
        "cases-%E2%97%8F-psu-%E2%97%8F-fans/power-supply": "Power Supply",
    })


def elnour():
    base = "https://elnour-tech.com/api/agent/v1/products"
    out = []
    with httpx.Client(headers=UA, timeout=30, follow_redirects=True) as client:
        page = 1
        last_page = 1
        while page <= last_page and page <= 100:
            response = client.get(base, params={
                "locale": "en", "limit": 50, "page": page, "in_stock_only": "false"
            })
            response.raise_for_status()
            payload = response.json()
            reported_pages = int(payload.get("last_page", 1))
            last_page = min(reported_pages, 100)
            if reported_pages > 100 and page == 1:
                print("[elnour] catalogue exceeds the 100-page refresh limit")
            for item in payload.get("results", []):
                price = num(str(item.get("price", "")))
                if price is None or price <= 0:
                    continue
                old_price = num(str(item.get("regular_price", "")))
                name = item.get("name", "").strip()
                out.append({
                    "id": f"elnour:{item['id']}",
                    "name": name,
                    "brand": item.get("brand") or (name.split(" ")[0] if name else ""),
                    "category": item.get("category") or "Other",
                    "storeId": "elnour",
                    "price": price,
                    "oldPrice": old_price if old_price and old_price > price else None,
                    "imageUrl": item.get("image"),
                    "inStock": bool(item.get("in_stock")),
                    "url": item["url"],
                })
            if page < last_page:
                time.sleep(0.6)
            page += 1
    return out


def compumarts():
    base = "https://www.compumarts.com/products.json"
    out = []
    with httpx.Client(headers=UA, timeout=30, follow_redirects=True) as client:
        for page in range(1, 101):
            response = client.get(base, params={"limit": 250, "page": page})
            response.raise_for_status()
            products = response.json().get("products", [])
            if not products:
                break
            for item in products:
                variants = item.get("variants", [])
                priced_variants = [
                    (variant, num(str(variant.get("price", ""))))
                    for variant in variants
                ]
                priced_variants = [
                    (variant, price) for variant, price in priced_variants
                    if price is not None and price > 0
                ]
                if not priced_variants:
                    continue
                variant, price = min(priced_variants, key=lambda value: value[1])
                old_price = num(str(variant.get("compare_at_price") or ""))
                name = item.get("title", "").strip()
                image = (item.get("images") or [{}])[0].get("src")
                body_html = item.get("body_html", "")
                specifications = extract_specifications(body_html) if "<table" in body_html.lower() else {}
                out.append({
                    "id": f"compumarts:{item['id']}",
                    "name": name,
                    "brand": item.get("vendor") or (name.split(" ")[0] if name else ""),
                    "category": item.get("product_type") or "Other",
                    "storeId": "compumarts",
                    "price": price,
                    "oldPrice": old_price if old_price and old_price > price else None,
                    "imageUrl": image,
                    "specifications": specifications,
                    "inStock": any(bool(value.get("available")) for value in variants),
                    "url": urljoin("https://www.compumarts.com/", f"products/{item['handle']}"),
                })
            if page < 100:
                time.sleep(0.6)
        else:
            print("[compumarts] stopped after 100 product pages")
    return out


def sigma_computer():
    store_id = "9d96d97b-d53e-4a6a-a393-68c388b31d9e"
    api_base = "https://api.sigma-computer.com/api/stores/v1"
    site_base = "https://www.sigma-computer.com"
    headers = {
        **UA,
        "X-Store-Id": store_id,
        "Accept-Language": "en",
    }
    out, seen = [], set()
    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
        response = client.get(f"{api_base}/categories")
        response.raise_for_status()
        categories = response.json().get("data", [])
        if not categories:
            raise ValueError("Sigma did not return any public product categories")

        for category in categories:
            category_id = category.get("id")
            category_name = category.get("name")
            if not category_id or not category_name:
                continue
            page = 1
            while page <= 100:
                response = client.get(
                    f"{site_base}/en/search",
                    params={
                        "filters": json.dumps({"category_id": [category_id]}, separators=(",", ":")),
                        "page": page,
                        "pageSize": 50,
                    },
                )
                if response.status_code != 200:
                    print(
                        f"[sigma] {category_name} page {page} returned "
                        f"HTTP {response.status_code}"
                    )
                    break

                soup = BeautifulSoup(response.text, "html.parser")
                images = soup.select('img[alt="Product Image"]')
                for image in images:
                    card = image.find_parent("div", class_="rounded-2xl")
                    if card is None:
                        continue
                    link = card.select_one('a[href*="/en/item"]')
                    if link is None:
                        continue
                    product_url = urljoin(site_base, link.get("href", ""))
                    if urlparse(product_url).hostname not in {
                        "www.sigma-computer.com", "sigma-computer.com"
                    }:
                        continue
                    product_slug = parse_qs(urlparse(product_url).query).get("id", [""])[0]
                    name = link.get_text(" ", strip=True)
                    price_element = card.select_one("p.font-bold")
                    price = num(price_element.get_text(" ", strip=True) if price_element else "")
                    if not product_slug or not name or price is None or price <= 0:
                        continue
                    product_id = f"sigma:{product_slug}"
                    if product_id in seen:
                        continue

                    old_price_element = card.select_one("p.line-through")
                    old_price = num(
                        old_price_element.get_text(" ", strip=True) if old_price_element else ""
                    )
                    image_url = image.get("src")
                    if image_url:
                        image_url = urljoin(site_base, image_url)
                    stock_text = card.get_text(" ", strip=True).lower()
                    seen.add(product_id)
                    out.append({
                        "id": product_id,
                        "name": name,
                        "brand": name.split(" ")[0],
                        "category": category_name,
                        "storeId": "sigma",
                        "price": price,
                        "oldPrice": old_price if old_price and old_price > price else None,
                        "imageUrl": image_url,
                        "inStock": "out of stock" not in stock_text,
                        "url": product_url,
                    })

                if len(images) < 50:
                    break
                if page == 100:
                    print(f"[sigma] stopped at the 100-page limit for {category_name}")
                else:
                    time.sleep(0.3)
                page += 1
    return out


ADAPTERS = {
    "elbadr": badr,
    "maximum": maximum,
    "elnour": elnour,
    "compumarts": compumarts,
    "sigma": sigma_computer,
}
