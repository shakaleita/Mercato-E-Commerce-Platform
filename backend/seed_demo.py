"""Insert optional synthetic demonstration records (safe to rerun)."""
from fastapi.testclient import TestClient
from main import app

SEEDS = [{'name': 'Studio Headphones', 'category': 'Audio', 'price': 129.99, 'stock': 12}, {'name': 'Desk Mat', 'category': 'Accessories', 'price': 34.5, 'stock': 50}]
client=TestClient(app)
if client.get('/api/items').json():
    print('Existing records found; skipping seed.')
else:
    for record in SEEDS:
        result=client.post('/api/items',json=record)
        result.raise_for_status()
    print('Added',len(SEEDS),'synthetic sample records.')
