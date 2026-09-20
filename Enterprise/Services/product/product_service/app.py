from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, status

from .models import CatalogEntry, CatalogEntryCreate, Category, CategoryCreate, Inventory, InventoryCreate, Price, PriceCreate, Product, ProductCreate, ProductUpdate, Promotion, PromotionCreate, PromotionUpdate, Store, StoreCreate
from .events import publish_event
from .repository import ProductRepository

app = FastAPI(title="Customer360 Product Service", version="0.1.0")
repository = ProductRepository()


def missing(message: str = "Resource not found") -> None:
    raise HTTPException(status_code=404, detail=message)


@app.get("/api/health")
def health() -> dict[str, str]:
    repository.list_products()
    return {"status": "ok", "service": "product"}


@app.post("/api/products", response_model=Product, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate) -> Product:
    item = repository.save_product(Product(**payload.model_dump()))
    publish_event("ProductCreated", "product", item.product_id, item.model_dump(mode="json"), occurred_at=item.created_at)
    return item


@app.get("/api/products", response_model=list[Product])
def list_products() -> list[Product]:
    return repository.list_products()


@app.get("/api/products/{product_id}", response_model=Product)
def get_product(product_id: str) -> Product:
    item = repository.get_product(product_id)
    if item is None:
        missing("Product not found")
    return item


@app.put("/api/products/{product_id}", response_model=Product)
def update_product(product_id: str, payload: ProductUpdate) -> Product:
    item = get_product(product_id)
    updated = repository.save_product(item.model_copy(update={**payload.model_dump(exclude_unset=True), "updated_at": datetime.now(timezone.utc)}))
    publish_event("ProductUpdated", "product", updated.product_id, updated.model_dump(mode="json"), occurred_at=updated.updated_at)
    return updated


@app.delete("/api/products/{product_id}", status_code=204)
def delete_product(product_id: str) -> None:
    item = get_product(product_id)
    repository.delete_product(product_id)
    publish_event("ProductDeleted", "product", item.product_id, {"product_id": item.product_id}, occurred_at=datetime.now(timezone.utc))


@app.post("/api/categories", response_model=Category, status_code=201)
def create_category(payload: CategoryCreate) -> Category:
    item = repository.save_category(Category(**payload.model_dump()))
    publish_event("CategoryCreated", "category", item.category_id, item.model_dump(mode="json"), occurred_at=datetime.now(timezone.utc))
    return item


@app.get("/api/categories", response_model=list[Category])
def list_categories() -> list[Category]:
    return repository.list_categories()


@app.post("/api/stores", response_model=Store, status_code=201)
def create_store(payload: StoreCreate) -> Store:
    item = repository.save_store(Store(**payload.model_dump()))
    publish_event("StoreCreated", "store", item.store_id, item.model_dump(mode="json"), occurred_at=datetime.now(timezone.utc))
    return item


@app.get("/api/stores", response_model=list[Store])
def list_stores() -> list[Store]:
    return repository.list_stores()


@app.post("/api/stores/{store_id}/catalog", response_model=CatalogEntry, status_code=201)
def add_catalog_entry(store_id: str, payload: CatalogEntryCreate) -> CatalogEntry:
    if store_id not in {store.store_id for store in repository.list_stores()}:
        missing("Store not found")
    get_product(payload.product_id)
    item = repository.save_catalog_entry(CatalogEntry(store_id=store_id, **payload.model_dump()))
    publish_event("CatalogEntryCreated", "catalog_entry", item.catalog_entry_id, item.model_dump(mode="json"), occurred_at=datetime.now(timezone.utc))
    return item


@app.get("/api/stores/{store_id}/catalog", response_model=list[CatalogEntry])
def list_catalog(store_id: str) -> list[CatalogEntry]:
    if store_id not in {store.store_id for store in repository.list_stores()}:
        missing("Store not found")
    return repository.list_catalog(store_id)


@app.post("/api/stores/{store_id}/inventory", response_model=Inventory, status_code=201)
def save_inventory(store_id: str, payload: InventoryCreate) -> Inventory:
    if store_id not in {store.store_id for store in repository.list_stores()}:
        missing("Store not found")
    get_product(payload.product_id)
    if payload.reserved_quantity > payload.quantity:
        raise HTTPException(status_code=400, detail="Reserved inventory cannot exceed quantity")
    item = repository.save_inventory(Inventory(store_id=store_id, **payload.model_dump()))
    publish_event("InventoryChanged", "inventory", f"{item.store_id}:{item.product_id}", item.model_dump(mode="json"), occurred_at=datetime.now(timezone.utc))
    return item


@app.get("/api/stores/{store_id}/inventory", response_model=list[Inventory])
def list_inventory(store_id: str) -> list[Inventory]:
    if store_id not in {store.store_id for store in repository.list_stores()}:
        missing("Store not found")
    return repository.list_inventory(store_id)


@app.post("/api/products/{product_id}/prices", response_model=Price, status_code=201)
def add_price(product_id: str, payload: PriceCreate) -> Price:
    get_product(product_id)
    item = repository.add_price(Price(product_id=product_id, **payload.model_dump()))
    publish_event("PriceChanged", "price", item.price_id, item.model_dump(mode="json"), occurred_at=item.effective_from)
    return item


@app.get("/api/products/{product_id}/prices", response_model=list[Price])
def list_prices(product_id: str) -> list[Price]:
    get_product(product_id)
    return repository.list_prices(product_id)


@app.post("/api/promotions", response_model=Promotion, status_code=201)
def create_promotion(payload: PromotionCreate) -> Promotion:
    for product_id in payload.product_ids:
        get_product(product_id)
    item = repository.save_promotion(Promotion(**payload.model_dump()))
    publish_event("PromotionCreated", "promotion", item.promotion_id, item.model_dump(mode="json"), occurred_at=item.start_date)
    return item


@app.get("/api/promotions", response_model=list[Promotion])
def list_promotions() -> list[Promotion]:
    return repository.list_promotions()


@app.get("/api/promotions/{promotion_id}", response_model=Promotion)
def get_promotion(promotion_id: str) -> Promotion:
    item = repository.get_promotion(promotion_id)
    if item is None:
        missing("Promotion not found")
    return item


@app.put("/api/promotions/{promotion_id}", response_model=Promotion)
def update_promotion(promotion_id: str, payload: PromotionUpdate) -> Promotion:
    item = get_promotion(promotion_id)
    changes = payload.model_dump(exclude_unset=True)
    updated = item.model_copy(update=changes)
    for product_id in updated.product_ids:
        get_product(product_id)
    updated = repository.save_promotion(updated)
    publish_event("PromotionChanged", "promotion", updated.promotion_id, updated.model_dump(mode="json"), occurred_at=datetime.now(timezone.utc))
    return updated


@app.delete("/api/promotions/{promotion_id}", status_code=204)
def delete_promotion(promotion_id: str) -> None:
    item = get_promotion(promotion_id)
    repository.delete_promotion(promotion_id)
    publish_event("PromotionDeleted", "promotion", item.promotion_id, {"promotion_id": item.promotion_id}, occurred_at=datetime.now(timezone.utc))
