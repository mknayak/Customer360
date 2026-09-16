from datetime import datetime, timezone
from uuid import uuid4

from typing import Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


PaymentStatus = Literal["pending", "failed", "succeeded"]
DeliveryMode = Literal["email", "postal", "collection", "collect_at_store"]


class CartCreate(BaseModel):
    customer_id: str
    site_id: str | None = None
    status: str = "active"
    payment_status: PaymentStatus = "pending"
    payment_method: str | None = None
    transaction_id: str | None = None
    failure_reason: str | None = None
    paid_at: datetime | None = None
    store_id: str | None = None
    delivery_mode: DeliveryMode = "collect_at_store"
    delivery_address: str | None = None
    fulfillment_status: str = "not_started"


class CartUpdate(BaseModel):
    status: str | None = Field(default=None, min_length=1)
    payment_status: PaymentStatus | None = None
    payment_method: str | None = None
    transaction_id: str | None = None
    failure_reason: str | None = None
    paid_at: datetime | None = None
    store_id: str | None = None
    delivery_mode: DeliveryMode | None = None
    delivery_address: str | None = None
    fulfillment_status: str | None = None


class Cart(CartCreate):
    cart_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CartItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(gt=0)


class CartItem(CartItemCreate):
    cart_item_id: str = Field(default_factory=lambda: str(uuid4()))
    cart_id: str


class CartView(Cart):
    items: list[CartItem] = Field(default_factory=list)


class OrderItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(gt=0)
    discount_amount: float = Field(default=0, ge=0)


class OrderCreate(BaseModel):
    customer_id: str
    site_id: str | None = None
    promotion_id: str | None = None
    currency: str = Field(min_length=3, max_length=3)
    items: list[OrderItemCreate] = Field(min_length=1)
    payment_status: PaymentStatus = "pending"
    payment_method: str | None = None
    transaction_id: str | None = None
    failure_reason: str | None = None
    store_id: str | None = None
    delivery_mode: DeliveryMode = "collect_at_store"
    delivery_address: str | None = None


class OrderUpdate(BaseModel):
    status: str = Field(min_length=1)


class OrderItem(OrderItemCreate):
    order_item_id: str = Field(default_factory=lambda: str(uuid4()))
    order_id: str


class Order(BaseModel):
    order_id: str = Field(default_factory=lambda: str(uuid4()))
    customer_id: str
    site_id: str | None = None
    promotion_id: str | None = None
    total_amount: float
    currency: str
    status: str = "created"
    payment_status: PaymentStatus = "pending"
    payment_method: str | None = None
    transaction_id: str | None = None
    failure_reason: str | None = None
    paid_at: datetime | None = None
    store_id: str | None = None
    delivery_mode: DeliveryMode = "collect_at_store"
    delivery_address: str | None = None
    fulfillment_status: str = "not_started"
    created_at: datetime = Field(default_factory=utc_now)
    items: list[OrderItem] = Field(default_factory=list)
