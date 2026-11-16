APP_TITLE = 'Mercato'
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
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
    price:float = Field(ge=0, allow_inf_nan=False)
    stock:int = Field(ge=0)
class Checkout(BaseModel):
    product_id:int
    quantity:int = Field(gt=0, le=10000)
@app.get('/api/items')
def items():
    with db() as c:return rows(c.execute('SELECT * FROM products ORDER BY id DESC'))
@app.post('/api/items',status_code=201)
def create_item(p:Product):
    if not p.name.strip() or p.price<0 or p.stock<0:raise HTTPException(422,'Invalid product')
    with db() as c:
        cur=c.execute('INSERT INTO products(name,category,price,stock) VALUES(?,?,?,?)',(p.name,p.category,p.price,p.stock))
        return dict(c.execute('SELECT * FROM products WHERE id=?',(cur.lastrowid,)).fetchone())
@app.post('/api/checkout')
def checkout(o:Checkout):
    if o.quantity<=0:raise HTTPException(422,'Quantity must be positive')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        p=c.execute('SELECT * FROM products WHERE id=?',(o.product_id,)).fetchone()
        if not p:raise HTTPException(404,'Product not found')
        if p['stock']<o.quantity:raise HTTPException(409,'Insufficient stock')
        c.execute('UPDATE products SET stock=stock-? WHERE id=?',(o.quantity,o.product_id))
        total=round(p['price']*o.quantity,2)
        cur=c.execute('INSERT INTO orders(product_id,quantity,total) VALUES(?,?,?)',(o.product_id,o.quantity,total))
        return {'order_id':cur.lastrowid,'total':total,'remaining_stock':p['stock']-o.quantity}
@app.get('/api/summary')
def summary():
    with db() as c:return [{'label':'Products','value':c.execute('SELECT COUNT(*) FROM products').fetchone()[0]},{'label':'Orders','value':c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]},{'label':'Revenue','value':round(c.execute('SELECT COALESCE(SUM(total),0) FROM orders').fetchone()[0],2)}]


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
            o.quantity, o.total, o.created_at FROM orders o
            JOIN products p ON p.id=o.product_id ORDER BY o.id DESC LIMIT ?""",(limit,)))

