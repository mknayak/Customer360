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

## API

- `POST /api/carts`
- `GET /api/carts`
- `GET /api/carts/{cart_id}`
- `PUT /api/carts/{cart_id}`
- `POST /api/carts/{cart_id}/items`
- `PUT /api/carts/{cart_id}/items/{item_id}`
- `DELETE /api/carts/{cart_id}/items/{item_id}`
- `POST /api/orders`
- `GET /api/orders`
- `GET /api/orders/{order_id}`
- `PUT /api/orders/{order_id}`

`GET /api/carts` and `GET /api/orders` return paginated responses with `items`,
`page`, `page_size`, `total`, and `total_pages`. They accept optional
`customer_id`, `start_date`, `end_date`, `page`, and `page_size` filters.