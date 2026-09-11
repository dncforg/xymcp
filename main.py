from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from pathlib import Path
import json, uuid, re

app = FastAPI(
    title="XY.com API",
    version="0.2.0",
    description="MVP API az AI-alapú bevásárláshoz."
)

PRODUCTS = json.loads(Path("products.json").read_text(encoding="utf-8"))
ORDERS = []
CARTS = {}

# Demo user. Productionben ezt adatbázis + valódi auth váltja ki.
USERS = {
    "xy-demo-key-123": {
        "id": "demo-user",
        "name": "Teszt Vásárló",
        "email": "teszt@example.com",
        "address": "Hajdú-Bihar, teszt cím"
    }
}

def user_from_key(key):
    if key not in USERS:
        raise HTTPException(status_code=401, detail="Érvénytelen API kulcs")
    return USERS[key]

def product_by_id(product_id: int):
    return next((p for p in PRODUCTS if p["id"] == product_id), None)

def build_cart(cart):
    lines, total = [], 0
    for item in cart["items"]:
        p = product_by_id(item["product_id"])
        if not p:
            raise HTTPException(400, f"Ismeretlen termék: {item['product_id']}")
        if item["quantity"] > p["stock"]:
            raise HTTPException(409, f"Nincs elég készlet: {p['name']}")
        line_total = p["price"] * item["quantity"]
        lines.append({
            "product_id": p["id"],
            "name": p["name"],
            "quantity": item["quantity"],
            "unit_price": p["price"],
            "line_total": line_total
        })
        total += line_total
    return lines, total

class CartItem(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=99)

class CartCreate(BaseModel):
    pass

class CartAdd(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=99)

class CartUpdate(BaseModel):
    quantity: int = Field(gt=0, le=99)

class OrderCreate(BaseModel):
    items: List[CartItem]
    payment_method: str = "cash_on_delivery"

@app.get("/api/products")
def search_products(q: Optional[str] = None, category: Optional[str] = None):
    result = PRODUCTS
    if q:
        terms = re.findall(r"\w+", q.lower())
        result = [p for p in result if all(
            t in (p["name"] + " " + p["category"] + " " + p.get("brand", "")).lower()
            for t in terms
        )]
    if category:
        result = [p for p in result if p["category"].lower() == category.lower()]
    return {"products": result, "count": len(result)}

@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    p = product_by_id(product_id)
    if not p:
        raise HTTPException(404, "Termék nem található")
    return p

@app.get("/api/me")
def me(x_api_key: str = Header(default="")):
    return user_from_key(x_api_key)

@app.get("/api/orders")
def orders(x_api_key: str = Header(default="")):
    user = user_from_key(x_api_key)
    return {"orders": [o for o in ORDERS if o["user_id"] == user["id"]]}

@app.post("/api/carts")
def create_cart(x_api_key: str = Header(default="")):
    user = user_from_key(x_api_key)
    token = uuid.uuid4().hex
    CARTS[token] = {
        "cart_token": token,
        "user_id": user["id"],
        "items": [],
        "status": "open"
    }
    return get_cart_response(CARTS[token])

def get_cart_response(cart):
    lines, total = build_cart(cart)
    return {
        "cart_token": cart["cart_token"],
        "status": cart["status"],
        "items": lines,
        "total": total,
        "currency": "HUF"
    }

def get_cart_or_404(cart_token, user):
    cart = CARTS.get(cart_token)
    if not cart or cart["user_id"] != user["id"]:
        raise HTTPException(404, "Kosár nem található")
    return cart

@app.get("/api/carts/{cart_token}")
def get_cart(cart_token: str, x_api_key: str = Header(default="")):
    user = user_from_key(x_api_key)
    cart = get_cart_or_404(cart_token, user)
    return get_cart_response(cart)

@app.post("/api/carts/{cart_token}/items")
def add_to_cart(cart_token: str, item: CartAdd, x_api_key: str = Header(default="")):
    user = user_from_key(x_api_key)
    cart = get_cart_or_404(cart_token, user)
    if cart["status"] != "open":
        raise HTTPException(409, "A kosár már le van zárva")

    p = product_by_id(item.product_id)
    if not p:
        raise HTTPException(400, "Termék nem található")

    existing = next((i for i in cart["items"] if i["product_id"] == item.product_id), None)
    new_qty = item.quantity if existing is None else existing["quantity"] + item.quantity

    if new_qty > p["stock"]:
        raise HTTPException(409, f"Nincs elég készlet: {p['name']}")

    if existing:
        existing["quantity"] = new_qty
    else:
        cart["items"].append({
            "product_id": item.product_id,
            "quantity": item.quantity
        })

    return get_cart_response(cart)

@app.patch("/api/carts/{cart_token}/items/{product_id}")
def update_cart_item(
    cart_token: str,
    product_id: int,
    item: CartUpdate,
    x_api_key: str = Header(default="")
):
    user = user_from_key(x_api_key)
    cart = get_cart_or_404(cart_token, user)
    if cart["status"] != "open":
        raise HTTPException(409, "A kosár már le van zárva")

    p = product_by_id(product_id)
    if not p:
        raise HTTPException(400, "Termék nem található")
    if item.quantity > p["stock"]:
        raise HTTPException(409, f"Nincs elég készlet: {p['name']}")

    existing = next((i for i in cart["items"] if i["product_id"] == product_id), None)
    if not existing:
        raise HTTPException(404, "A termék nincs a kosárban")

    existing["quantity"] = item.quantity
    return get_cart_response(cart)

@app.delete("/api/carts/{cart_token}/items/{product_id}")
def remove_from_cart(
    cart_token: str,
    product_id: int,
    x_api_key: str = Header(default="")
):
    user = user_from_key(x_api_key)
    cart = get_cart_or_404(cart_token, user)
    if cart["status"] != "open":
        raise HTTPException(409, "A kosár már le van zárva")

    before = len(cart["items"])
    cart["items"] = [i for i in cart["items"] if i["product_id"] != product_id]
    if len(cart["items"]) == before:
        raise HTTPException(404, "A termék nincs a kosárban")

    return get_cart_response(cart)

@app.post("/api/carts/{cart_token}/confirm")
def confirm_order(cart_token: str, x_api_key: str = Header(default="")):
    user = user_from_key(x_api_key)
    cart = get_cart_or_404(cart_token, user)

    if cart["status"] != "open":
        raise HTTPException(409, "A kosár már le lett zárva")
    if not cart["items"]:
        raise HTTPException(400, "A kosár üres")

    # Újra ellenőrizzük a készletet közvetlenül rendelés előtt.
    lines, total = build_cart(cart)

    for item in cart["items"]:
        p = product_by_id(item["product_id"])
        p["stock"] -= item["quantity"]

    new_order = {
        "order_id": "XY-" + uuid.uuid4().hex[:8].upper(),
        "user_id": user["id"],
        "items": lines,
        "total": total,
        "payment_method": "cash_on_delivery",
        "status": "teszt-rendeles"
    }

    ORDERS.append(new_order)
    cart["status"] = "confirmed"

    return new_order

# A régi közvetlen rendelési útvonalat szándékosan letiltjuk.
# Így a szerveroldali szabály kikényszeríti:
# create cart -> add/update -> explicit confirm -> order.
@app.post("/api/orders")
def create_order_legacy():
    raise HTTPException(
        status_code=410,
        detail="A közvetlen rendelés megszűnt. Előbb kosarat kell létrehozni, majd /api/carts/{cart_token}/confirm."
    )
