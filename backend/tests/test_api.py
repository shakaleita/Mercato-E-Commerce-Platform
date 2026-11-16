import importlib,os,sys,tempfile
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
temp = tempfile.mkdtemp(prefix='portfolio-test-')
os.environ['APP_DB']=str(Path(temp)/'test.db')
if 'main' in sys.modules: del sys.modules['main']
from main import app
client=TestClient(app)

def test_health():
    r=client.get('/api/health')
    assert r.status_code==200 and r.json()['ok']

def test_initial_list():
    r=client.get('/api/items')
    assert r.status_code==200 and isinstance(r.json(),list)

def test_summary():
    r=client.get('/api/summary')
    assert r.status_code==200 and isinstance(r.json(),list)


# v0.3 regression tests
def test_checkout_stock_order_history_and_restock():
    p=client.post('/api/items',json={'name':'Desk','category':'Home','price':19.99,'stock':3})
    assert p.status_code==201
    pid=p.json()['id']
    assert client.post('/api/checkout',json={'product_id':pid,'quantity':4}).status_code==409
    checkout=client.post('/api/checkout',json={'product_id':pid,'quantity':2})
    assert checkout.status_code==200 and checkout.json()['remaining_stock']==1
    assert client.post('/api/checkout',json={'product_id':pid,'quantity':2}).status_code==409
    history=client.get('/api/orders').json()
    assert history[0]['quantity']==2 and history[0]['product']=='Desk'
    restock=client.post(f'/api/products/{pid}/restock',json={'quantity':5})
    assert restock.status_code==200 and restock.json()['stock']==6
    assert client.post(f'/api/products/{pid}/restock',json={'quantity':-1}).status_code==422
    assert client.post('/api/items',json={'name':'Bad','price':-2,'stock':1}).status_code==422

