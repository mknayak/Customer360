# Shopping Service

Owns carts, cart items, orders, and order items in `data/shopping.sqlite3`.

Run from the repository root:

```text
.venv/bin/python -m pip install -e Enterprise/Services/shopping
.venv/bin/uvicorn shopping_service.app:app --app-dir Enterprise/Services/shopping --reload
```

Customer, site, and product references are stored as identifiers owned by their respective services.
Orders and carts expose payment status (`pending`, `failed`, or `succeeded`) plus
payment method, transaction ID, failure reason, and payment timestamp.