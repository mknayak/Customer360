from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1)
    parent_category_id: str | None = None


class Category(CategoryCreate):
    category_id: str = Field(default_factory=lambda: str(uuid4()))


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    category_id: str | None = None
    brand: str | None = None
    status: str = "active"


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    category_id: str | None = None
    brand: str | None = None
    status: str | None = None


class Product(ProductCreate):
    product_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class StoreCreate(BaseModel):
    name: str = Field(min_length=1)
    channel: str = Field(pattern="^(physical|online|both)$")
    city: str | None = None
    country: str | None = None


class Store(StoreCreate):
    store_id: str = Field(default_factory=lambda: str(uuid4()))


class CatalogEntryCreate(BaseModel):
    product_id: str
    price_amount: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    status: str = "active"


class CatalogEntry(CatalogEntryCreate):
    store_id: str
    catalog_entry_id: str = Field(default_factory=lambda: str(uuid4()))


class InventoryCreate(BaseModel):
    product_id: str
    quantity: int = Field(ge=0)
    reserved_quantity: int = Field(default=0, ge=0)


class Inventory(InventoryCreate):
    store_id: str

    @property
    def available_quantity(self) -> int:
        return max(0, self.quantity - self.reserved_quantity)


class PriceCreate(BaseModel):
    amount: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    effective_from: datetime = Field(default_factory=utc_now)
    effective_to: datetime | None = None


class Price(PriceCreate):
    price_id: str = Field(default_factory=lambda: str(uuid4()))
    product_id: str


class PromotionCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    discount_type: str = Field(pattern="^(percentage|fixed)$")
    discount_value: float = Field(gt=0)
    start_date: datetime
    end_date: datetime | None = None
    status: str = "scheduled"
    product_ids: list[str] = Field(default_factory=list)


class PromotionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    discount_type: str | None = Field(default=None, pattern="^(percentage|fixed)$")
    discount_value: float | None = Field(default=None, gt=0)
    start_date: datetime | None = None
    end_date: datetime | None = None
    status: str | None = None
    product_ids: list[str] | None = None


class Promotion(PromotionCreate):
    promotion_id: str = Field(default_factory=lambda: str(uuid4()))
