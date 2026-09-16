# Product Service

Owns products, categories, prices, promotions, stores, store-specific catalogs,
and store inventory in `data/product.sqlite3`.

Run from the repository root:

```text
.venv/bin/python -m pip install -e Enterprise/Services/product
.venv/bin/uvicorn product_service.app:app --app-dir Enterprise/Services/product --reload
```

The API implements the product contract in `enterprise-intelligence-brain-development.md`.
Store APIs are available at `/api/stores`, `/api/stores/{id}/catalog`, and
`/api/stores/{id}/inventory`.

## Simulator CSV

The simulator's `data/catalog.csv` is the bootstrap format for products and
stores. A generation template is available at
`Enterprise/Simulator/catalog-prompt.txt`. Each row represents one product in
one store. Required columns are:

```text
store_name,channel,sku,name,price_amount,currency,quantity
```

Optional columns include `city`, `country`, `description`, `brand`,
`reserved_quantity`, `product_status`, and `catalog_status`. Load it from the
simulator's Customers view with **Load bundled catalog** or **Choose catalog CSV**.
Products are reused by SKU and stores by name, so reloading the same file is
safe and updates store pricing and inventory.