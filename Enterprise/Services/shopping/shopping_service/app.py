from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query

from .models import Cart, CartCreate, CartItem, CartItemCreate, CartPage, CartUpdate, CartView, Order, OrderCreate, OrderItem, OrderPage, OrderUpdate
from .events import publish_event
from .repository import ShoppingRepository

app = FastAPI(title="Customer360 Shopping Service", version="0.1.0")
repository = ShoppingRepository()


def get_cart_or_404(cart_id: str) -> CartView:
    cart = repository.get_cart(cart_id)
    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found")
    return cart


def get_order_or_404(order_id: str) -> Order:
    order = repository.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/api/health")
def health() -> dict[str, str]:
    repository.list_orders()
    return {"status": "ok", "service": "shopping"}


@app.post("/api/carts", response_model=CartView, status_code=201)
def create_cart(payload: CartCreate) -> CartView:
    cart = repository.save_cart(Cart(**payload.model_dump()))
    publish_event("CartCreated", "cart", cart.cart_id, cart.model_dump(mode="json"), occurred_at=cart.created_at)
    return CartView(**cart.model_dump())


@app.get("/api/carts", response_model=CartPage)
def list_carts(
    customer_id: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> CartPage:
    items = repository.list_carts(customer_id=customer_id, start_date=start_date, end_date=end_date, page=page, page_size=page_size)
    total = repository.count_carts(customer_id=customer_id, start_date=start_date, end_date=end_date)
    total_pages = max(1, (total + page_size - 1) // page_size)
    return CartPage(items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)


@app.get("/api/carts/{cart_id}", response_model=CartView)
def get_cart(cart_id: str) -> CartView:
    return get_cart_or_404(cart_id)


@app.put("/api/carts/{cart_id}", response_model=CartView)
def update_cart(cart_id: str, payload: CartUpdate) -> CartView:
    cart = get_cart_or_404(cart_id)
    changes = payload.model_dump(exclude_unset=True)
    changes["updated_at"] = datetime.now(timezone.utc)
    updated = cart.model_copy(update=changes)
    repository.save_cart(Cart(**updated.model_dump(exclude={"items"})))
    event_type = "CartAbandoned" if updated.status == "abandoned" else "CartUpdated"
    publish_event(event_type, "cart", updated.cart_id, updated.model_dump(mode="json"), occurred_at=updated.updated_at)
    return get_cart_or_404(cart_id)


@app.post("/api/carts/{cart_id}/items", response_model=CartItem, status_code=201)
def add_cart_item(cart_id: str, payload: CartItemCreate) -> CartItem:
    get_cart_or_404(cart_id)
    item = repository.save_item(CartItem(cart_id=cart_id, **payload.model_dump()))
    publish_event("CartItemAdded", "cart", cart_id, item.model_dump(mode="json"), occurred_at=datetime.now(timezone.utc))
    return item


@app.put("/api/carts/{cart_id}/items/{item_id}", response_model=CartItem)
def update_cart_item(cart_id: str, item_id: str, payload: CartItemCreate) -> CartItem:
    get_cart_or_404(cart_id)
    item = next((candidate for candidate in get_cart_or_404(cart_id).items if candidate.cart_item_id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Cart item not found")
    updated = repository.save_item(item.model_copy(update=payload.model_dump()))
    publish_event("CartItemUpdated", "cart", cart_id, updated.model_dump(mode="json"), occurred_at=datetime.now(timezone.utc))
    return updated


@app.delete("/api/carts/{cart_id}/items/{item_id}", status_code=204)
def delete_cart_item(cart_id: str, item_id: str) -> None:
    get_cart_or_404(cart_id)
    if not repository.delete_item(cart_id, item_id):
        raise HTTPException(status_code=404, detail="Cart item not found")
    publish_event("CartItemRemoved", "cart", cart_id, {"cart_id": cart_id, "cart_item_id": item_id}, occurred_at=datetime.now(timezone.utc))


@app.post("/api/orders", response_model=Order, status_code=201)
def create_order(payload: OrderCreate) -> Order:
    items = [OrderItem(order_id="pending", **item.model_dump()) for item in payload.items]
    order_id = Order.model_fields["order_id"].default_factory()
    items = [item.model_copy(update={"order_id": order_id}) for item in items]
    total = sum((item.quantity * item.unit_price) - item.discount_amount for item in items)
    if total < 0:
        raise HTTPException(status_code=400, detail="Discounts cannot exceed line totals")
    if payload.payment_status == "failed" and not payload.failure_reason:
        raise HTTPException(status_code=400, detail="failure_reason is required for failed payments")
    order_status = {"pending": "pending_payment", "failed": "payment_failed", "succeeded": "created"}[payload.payment_status]
    paid_at = datetime.now(timezone.utc) if payload.payment_status == "succeeded" else None
    fulfillment_status = "ready_for_fulfillment" if payload.payment_status == "succeeded" else "not_started"
    order = repository.save_order(Order(order_id=order_id, customer_id=payload.customer_id, site_id=payload.site_id, promotion_id=payload.promotion_id, total_amount=round(total, 2), currency=payload.currency, status=order_status, payment_status=payload.payment_status, payment_method=payload.payment_method, transaction_id=payload.transaction_id, failure_reason=payload.failure_reason, paid_at=paid_at, store_id=payload.store_id, delivery_mode=payload.delivery_mode, delivery_address=payload.delivery_address, fulfillment_status=fulfillment_status, items=items))
    publish_event("OrderCreated", "order", order.order_id, order.model_dump(mode="json"), occurred_at=order.created_at)
    if order.payment_status == "succeeded":
        publish_event("PaymentCompleted", "order", order.order_id, {"order_id": order.order_id, "transaction_id": order.transaction_id, "amount": order.total_amount}, occurred_at=order.paid_at or order.created_at)
    elif order.payment_status == "failed":
        publish_event("PaymentFailed", "order", order.order_id, {"order_id": order.order_id, "failure_reason": order.failure_reason}, occurred_at=order.created_at)
    return order


@app.get("/api/orders", response_model=OrderPage)
def list_orders(
    customer_id: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> OrderPage:
    items = repository.list_orders(customer_id=customer_id, start_date=start_date, end_date=end_date, page=page, page_size=page_size)
    total = repository.count_orders(customer_id=customer_id, start_date=start_date, end_date=end_date)
    total_pages = max(1, (total + page_size - 1) // page_size)
    return OrderPage(items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)


@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str) -> Order:
    return get_order_or_404(order_id)


@app.put("/api/orders/{order_id}", response_model=Order)
def update_order(order_id: str, payload: OrderUpdate) -> Order:
    get_order_or_404(order_id)
    order = repository.update_order(order_id, payload.status)
    event_type = "OrderCancelled" if order.status == "cancelled" else "OrderStatusChanged"
    publish_event(event_type, "order", order.order_id, order.model_dump(mode="json"), occurred_at=datetime.now(timezone.utc))
    return order
