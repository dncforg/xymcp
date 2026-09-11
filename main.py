from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from pathlib import Path
import json, uuid, re

app = FastAPI(
    title="XY.com API",
    version="0.2.0",
    description="MVP API az AI-alapú bevásárláshoz."
)

# CORS a helyi HTML demohoz és fejlesztéshez. Productionben szűkítsd az origin listát.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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


# ============================================================
# MCP LAYER
# ============================================================
# Development/test implementation. Production must replace the
# demo user/API key with OAuth-based user identity.
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import os

from starlette.routing import Mount
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

MCP_DEMO_API_KEY = os.getenv("XY_MCP_API_KEY", "xy-demo-key-123")

mcp = MCPServer(
    "XY.com",
    title="XY.com Shopping",
    description="AI shopping tools for the XY.com test store.",
    instructions=(
        "Use search_products to find products. Create or use a cart before "
        "adding items. Never call confirm_order until the user has explicitly "
        "confirmed the final cart and total."
    ),
)

@mcp.tool()
def search_products(query: str) -> dict:
    """Search XY products by name, category/type, or brand."""
    result = PRODUCTS
    terms = re.findall(r"\w+", query.lower().strip())
    if terms:
        result = [
            p for p in result
            if all(
                t in (
                    p["name"] + " " +
                    p["category"] + " " +
                    p.get("brand", "")
                ).lower()
                for t in terms
            )
        ]
    return {"products": result, "count": len(result)}

@mcp.tool()
def get_cart(cart_token: str) -> dict:
    """Get the current XY shopping cart and total."""
    user = user_from_key(MCP_DEMO_API_KEY)
    cart = get_cart_or_404(cart_token, user)
    return get_cart_response(cart)

@mcp.tool()
def add_to_cart(cart_token: str, product_id: int, quantity: int) -> dict:
    """Add a product to an existing XY cart."""
    user = user_from_key(MCP_DEMO_API_KEY)
    cart = get_cart_or_404(cart_token, user)

    if cart["status"] != "open":
        raise ValueError("A kosár már le van zárva.")

    if quantity <= 0 or quantity > 99:
        raise ValueError("A mennyiség 1 és 99 között legyen.")

    p = product_by_id(product_id)
    if not p:
        raise ValueError("Termék nem található.")

    existing = next(
        (i for i in cart["items"] if i["product_id"] == product_id),
        None
    )
    new_qty = quantity if existing is None else existing["quantity"] + quantity

    if new_qty > p["stock"]:
        raise ValueError(f"Nincs elég készlet: {p['name']}")

    if existing:
        existing["quantity"] = new_qty
    else:
        cart["items"].append({
            "product_id": product_id,
            "quantity": quantity
        })

    return get_cart_response(cart)

@mcp.tool()
def confirm_order(cart_token: str) -> dict:
    """Confirm an XY cart and create the cash-on-delivery test order.

    IMPORTANT: Call this only after the user has explicitly confirmed
    the displayed cart contents and total.
    """
    user = user_from_key(MCP_DEMO_API_KEY)
    cart = get_cart_or_404(cart_token, user)

    if cart["status"] != "open":
        raise ValueError("A kosár már le lett zárva.")
    if not cart["items"]:
        raise ValueError("A kosár üres.")

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

# Add a helper tool to start a new test cart. This is useful during
# development; production will create the cart from the authenticated user.
@mcp.tool()
def create_cart() -> dict:
    """Create a new XY shopping cart for the current test user."""
    token = uuid.uuid4().hex
    CARTS[token] = {
        "cart_token": token,
        "user_id": user_from_key(MCP_DEMO_API_KEY)["id"],
        "items": [],
        "status": "open"
    }
    return get_cart_response(CARTS[token])

@asynccontextmanager
async def mcp_lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Mounted MCP apps do not run their own lifespan automatically.
    # Keep the session manager alive from the host FastAPI application.
    async with mcp.session_manager.run():
        yield

# Render serves this service at xymcp.onrender.com. The allowlist is
# required by the current MCP SDK's DNS-rebinding protection for a
# non-local deployment.
mcp_transport_security = TransportSecuritySettings(
    allowed_hosts=[
        "xymcp.onrender.com",
        "xymcp.onrender.com:*",
    ],
    allowed_origins=[
        "https://chatgpt.com",
        "https://chat.openai.com",
    ],
)

mcp_asgi = mcp.streamable_http_app(
    transport_security=mcp_transport_security,
    stateless_http=True,
)

# The host FastAPI app must own the MCP lifespan when the MCP app is mounted.
app.router.lifespan_context = mcp_lifespan
app.router.routes.append(Mount("/mcp", app=mcp_asgi))
# ============================================================
# END MCP LAYER
# ============================================================

