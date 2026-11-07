import json
import hmac
import os
import sqlite3
import threading
import time
from contextlib import asynccontextmanager, closing

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Header, HTTPException, Query

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None

from stores import ADAPTERS

DATABASE_URL = os.environ.get("DATABASE_URL")
DB = os.environ.get("PRICEHUNTER_DB", "prices.db")


def conn():
    if DATABASE_URL and psycopg2:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    else:
        c = sqlite3.connect(DB)
        c.row_factory = sqlite3.Row
        return c


def run_sql(c, sql, args=()):
    if DATABASE_URL and psycopg2:
        sql = sql.replace("?", "%s")
        cur = c.cursor()
        cur.execute(sql, args)
        return cur
    else:
        return c.execute(sql, args)


def init_db():
    with closing(conn()) as c:
        run_sql(c, """
        CREATE TABLE IF NOT EXISTS products(
            id TEXT PRIMARY KEY, name TEXT, brand TEXT, category TEXT, store_id TEXT,
            price INTEGER, old_price INTEGER, image_url TEXT, in_stock INTEGER, url TEXT,
            updated_at INTEGER, specifications TEXT);
        CREATE TABLE IF NOT EXISTS price_history(product_id TEXT, price INTEGER, ts INTEGER);
        CREATE INDEX IF NOT EXISTS idx_hist ON price_history(product_id, ts);
        """)
        c.commit()


def upsert(items):
    now = int(time.time())
    with closing(conn()) as c:
        for p in items:
            last = run_sql(c, "SELECT price FROM price_history WHERE product_id=? ORDER BY ts DESC LIMIT 1",
                           (p["id"],)).fetchone()
            last_price = last["price"] if last else None
            if last is None or last_price != p["price"]:
                run_sql(c, "INSERT INTO price_history VALUES(?,?,?)", (p["id"], p["price"], now))
            
            hi_row = run_sql(c, "SELECT MAX(price) m FROM price_history WHERE product_id=? AND ts>?",
                             (p["id"], now - 30 * 86400)).fetchone()
            hi = hi_row["m"] if hi_row else None
            old = p.get("oldPrice") or (hi if hi and hi > p["price"] else None)
            specifications = p.get("specifications")
            
            run_sql(c, """INSERT INTO products
                (id, name, brand, category, store_id, price, old_price, image_url,
                 in_stock, url, updated_at, specifications)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, brand=excluded.brand,
                category=excluded.category, price=excluded.price, old_price=excluded.old_price,
                image_url=excluded.image_url, in_stock=excluded.in_stock, url=excluded.url,
                updated_at=excluded.updated_at,
                specifications=COALESCE(excluded.specifications, products.specifications)""",
                      (p["id"], p["name"], p["brand"], p["category"], p["storeId"], p["price"], old,
                       p.get("imageUrl"), int(p.get("inStock", True)), p["url"], now,
                       json.dumps(specifications, ensure_ascii=False) if specifications else None))
        c.commit()


def refresh():
    init_db()
    for store_id, fetch in ADAPTERS.items():
        try:
            items = fetch()
            upsert(items)
            print(f"[{store_id}] saved {len(items)} products")
        except Exception as e:
            print(f"[{store_id}] failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(refresh, "interval", hours=3)
    scheduler.start()
    threading.Thread(target=refresh, daemon=True).start()
    yield
    scheduler.shutdown()


app = FastAPI(title="PriceHunter API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/products")
def products(
    q: str = "",
    limit: int = Query(default=3000, ge=1, le=3000),
    offset: int = Query(default=0, ge=0, le=1000000),
):
    sql, args = "SELECT * FROM products", []
    if q.strip():
        sql += " WHERE LOWER(name || ' ' || brand || ' ' || category) LIKE ?"
        args.append(f"%{q.strip().lower()}%")
    sql += " ORDER BY id LIMIT ? OFFSET ?"
    args.extend((limit, offset))
    with closing(conn()) as c:
        rows = run_sql(c, sql, args).fetchall()
    return [{
        "id": r["id"], "name": r["name"], "brand": r["brand"], "category": r["category"],
        "storeId": r["store_id"], "price": r["price"], "oldPrice": r["old_price"],
        "imageUrl": r["image_url"], "inStock": bool(r["in_stock"]), "url": r["url"],
        "specifications": json.loads(r["specifications"] or "{}"),
    } for r in rows]


@app.get("/products/{product_id}/history")
def history(product_id: str):
    with closing(conn()) as c:
        rows = run_sql(c, "SELECT price, ts FROM price_history WHERE product_id=? ORDER BY ts",
                       (product_id,)).fetchall()
    return [{"price": r["price"], "ts": r["ts"]} for r in rows]


@app.post("/refresh")
def manual_refresh(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    expected_key = os.environ.get("REFRESH_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=503, detail="Manual refresh is not configured.")
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid API key.")
    threading.Thread(target=refresh, daemon=True).start()
    return {"started": True}
