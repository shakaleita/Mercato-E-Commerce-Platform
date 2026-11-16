import importlib,os,sys,tempfile
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
temp = tempfile.mkdtemp(prefix='portfolio-test-')
os.environ['APP_DB']=str(Path(temp)/'test.db')
os.environ['OWNER_SETUP_TOKEN']='test-only-setup-token-1234567890123'
if 'main' in sys.modules: del sys.modules['main']
from main import app
client=TestClient(app)
assert client.post('/api/auth/register',json={'username':'qaowner','password':'DemoPassword123!','setup_token':'test-only-setup-token-1234567890123'}).status_code==201
assert client.post('/api/auth/login',json={'username':'qaowner','password':'DemoPassword123!'}).status_code==200

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



def test_v05_idempotent_cancel():
    product=client.post('/api/items',json={'name':'Notebook','price':12.5,'stock':5}).json()
    body={'product_id':product['id'],'quantity':2,'idempotency_key':'unique-checkout-token-0001'}
    first=client.post('/api/checkout',json=body).json()
    second=client.post('/api/checkout',json=body).json()
    assert first['order_id']==second['order_id'] and second['replayed'] is True
    assert client.post(f"/api/orders/{first['order_id']}/cancel").status_code==200
    assert client.post(f"/api/orders/{first['order_id']}/cancel").status_code==409

def test_v05_authentication():
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/items').status_code==401
        assert anonymous.post('/api/auth/register',json={'username':'intruder','password':'DemoPassword123!','setup_token':'bad'}).status_code==403

# v0.6 request-origin and owner audit regression
def test_v06_audit_record_and_cross_site_guard():
    attempted=client.post('/api/__audit_probe_404')
    assert attempted.status_code==404
    audit=client.get('/api/auth/audit')
    assert audit.status_code==200
    assert any(row['method']=='POST' and row['path']=='/api/__audit_probe_404'
               and row['status_code']==404 for row in audit.json())
    assert client.get('/api/auth/audit',params={'limit':201}).status_code==422
    blocked=client.post('/api/__audit_probe_404',headers={'sec-fetch-site':'cross-site'})
    assert blocked.status_code==403


def test_prices_calculated_in_integer_cents():
    product=client.post('/api/items',json={'name':'Penny product','price':'0.29','stock':10}).json()
    assert product['price_cents']==29
    result=client.post('/api/checkout',json={'product_id':product['id'],'quantity':3,
                                            'idempotency_key':'precise-cents-case-0001'})
    assert result.status_code==200
    assert result.json()['total_cents']==87
    assert result.json()['total']==0.87
    replay=client.post('/api/checkout',json={'product_id':product['id'],'quantity':3,
                                            'idempotency_key':'precise-cents-case-0001'})
    assert replay.json()['total_cents']==87
    assert replay.json()['replayed'] is True
    assert client.post('/api/items',json={'name':'Invalid rounding','price':'1.999','stock':5}).status_code==422


def test_revenue_reflects_completed_orders_in_cents():
    product=client.post('/api/items',json={'name':'Tiny','price':'0.01','stock':10}).json()
    before={x['label']:x['value'] for x in client.get('/api/summary').json()}['Revenue']
    order=client.post('/api/checkout',json={'product_id':product['id'],'quantity':7}).json()
    after={x['label']:x['value'] for x in client.get('/api/summary').json()}['Revenue']
    assert round(after-before,2)==0.07
    assert client.post('/api/orders/'+str(order['order_id'])+'/cancel').status_code==200
    final={x['label']:x['value'] for x in client.get('/api/summary').json()}['Revenue']
    assert round(final-before,2)==0
