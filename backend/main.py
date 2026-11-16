APP_TITLE = 'Mercato'
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Any
import sqlite3, os
from contextlib import contextmanager
from pathlib import Path

DB = Path(os.environ.get("APP_DB", str(Path(__file__).parent / "app.db")))
app = FastAPI(title=APP_TITLE, version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","), allow_methods=["*"], allow_headers=["*"])

@contextmanager
def db():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def rows(cursor):
    return [dict(r) for r in cursor.fetchall()]

def setup(sql):
    with db() as con:
        con.executescript(sql)

@app.get("/api/health")
def health():
    return {"ok": True, "service": APP_TITLE}


setup("""CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL,price REAL NOT NULL CHECK(price>=0),stock INTEGER NOT NULL CHECK(stock>=0));
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL,quantity INTEGER NOT NULL,total REAL NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(product_id) REFERENCES products(id));""")
class Product(BaseModel):
    name:str
    category:str="General"
    price:Decimal = Field(ge=0, le=9999999, decimal_places=2)
    stock:int = Field(ge=0)
class Checkout(BaseModel):
    product_id:int
    quantity:int = Field(gt=0, le=10000)
    idempotency_key:str|None=Field(default=None,min_length=12,max_length=128)

with db() as con:
    cols={r['name'] for r in con.execute('PRAGMA table_info(orders)')}
    if 'status' not in cols:con.execute("ALTER TABLE orders ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'")
    if 'idempotency_key' not in cols:con.execute('ALTER TABLE orders ADD COLUMN idempotency_key TEXT')
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_idempotency ON orders(idempotency_key)')
    product_cols={row['name'] for row in con.execute('PRAGMA table_info(products)')}
    if 'price_cents' not in product_cols:
        con.execute('ALTER TABLE products ADD COLUMN price_cents INTEGER')
    con.execute('UPDATE products SET price_cents=CAST(ROUND(price * 100) AS INTEGER) WHERE price_cents IS NULL')
    if 'total_cents' not in cols:
        con.execute('ALTER TABLE orders ADD COLUMN total_cents INTEGER')
    con.execute('UPDATE orders SET total_cents=CAST(ROUND(total * 100) AS INTEGER) WHERE total_cents IS NULL')
@app.get('/api/items')
def items():
    with db() as c:return rows(c.execute('SELECT * FROM products ORDER BY id DESC'))
@app.post('/api/items',status_code=201)
def create_item(p:Product):
    if not p.name.strip() or p.price<0 or p.stock<0:raise HTTPException(422,'Invalid product')
    cents=int(p.price*100)
    with db() as c:
        cur=c.execute('INSERT INTO products(name,category,price,stock,price_cents) VALUES(?,?,?,?,?)',(p.name,p.category,float(p.price),p.stock,cents))
        return dict(c.execute('SELECT * FROM products WHERE id=?',(cur.lastrowid,)).fetchone())
@app.post('/api/checkout')
def checkout(o:Checkout):
    if o.quantity<=0:raise HTTPException(422,'Quantity must be positive')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if o.idempotency_key:
            previous=c.execute('SELECT * FROM orders WHERE idempotency_key=?',(o.idempotency_key,)).fetchone()
            if previous:
                if previous['product_id']!=o.product_id or previous['quantity']!=o.quantity:
                    raise HTTPException(409,'Idempotency key belongs to a different checkout')
                stock=c.execute('SELECT stock FROM products WHERE id=?',(o.product_id,)).fetchone()
                return {'order_id':previous['id'],'total':previous['total_cents']/100,'total_cents':previous['total_cents'],'status':previous['status'],'remaining_stock':stock['stock'],'replayed':True}
        p=c.execute('SELECT * FROM products WHERE id=?',(o.product_id,)).fetchone()
        if not p:raise HTTPException(404,'Product not found')
        if p['stock']<o.quantity:raise HTTPException(409,'Insufficient stock')
        c.execute('UPDATE products SET stock=stock-? WHERE id=?',(o.quantity,o.product_id))
        total_cents=p['price_cents']*o.quantity
        total=total_cents/100
        cur=c.execute('INSERT INTO orders(product_id,quantity,total,total_cents,idempotency_key) VALUES(?,?,?,?,?)',(o.product_id,o.quantity,total,total_cents,o.idempotency_key))
        return {'order_id':cur.lastrowid,'total':total,'total_cents':total_cents,'remaining_stock':p['stock']-o.quantity,'status':'completed','replayed':False}
@app.get('/api/summary')
def summary():
    with db() as c:return [{'label':'Products','value':c.execute('SELECT COUNT(*) FROM products').fetchone()[0]},{'label':'Orders','value':c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]},{'label':'Revenue','value':c.execute("SELECT COALESCE(SUM(total_cents),0) FROM orders WHERE status='completed'").fetchone()[0]/100}]


# v0.3: order lifecycle and inventory replenishment
class StockAdjustment(BaseModel):
    quantity: int = Field(gt=0, le=100000)

@app.post('/api/products/{product_id}/restock')
def restock(product_id: int, adjustment: StockAdjustment):
    with db() as con:
        updated = con.execute('UPDATE products SET stock=stock+? WHERE id=?', (adjustment.quantity,product_id))
        if not updated.rowcount:
            raise HTTPException(404,'Product not found')
        return dict(con.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone())

@app.get('/api/orders')
def order_history(limit: int = 50):
    if limit < 1 or limit > 200:
        raise HTTPException(422, 'Limit must be between 1 and 200')
    with db() as con:
        return rows(con.execute("""SELECT o.id, o.product_id, p.name AS product,
            o.quantity, o.total, o.total_cents, o.created_at, o.status FROM orders o
            JOIN products p ON p.id=o.product_id ORDER BY o.id DESC LIMIT ?""",(limit,)))


@app.post('/api/orders/{order_id}/cancel')
def cancel_order(order_id:int):
    with db() as con:
        con.execute('BEGIN IMMEDIATE')
        order=con.execute('SELECT * FROM orders WHERE id=?',(order_id,)).fetchone()
        if not order:raise HTTPException(404,'Order not found')
        if order['status']!='completed':raise HTTPException(409,'Order already cancelled')
        con.execute("UPDATE orders SET status='cancelled' WHERE id=?",(order_id,))
        con.execute('UPDATE products SET stock=stock+? WHERE id=?',(order['quantity'],order['product_id']))
        return {'id':order_id,'status':'cancelled','restored':order['quantity']}

from security import install_auth
install_auth(app,DB)
