# XY.com MVP – 1.0

Ez az első működő backend-prototípus.

## Indítás

Windows:
```bash
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Ezután:
- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs

## Teszt API-kulcs
`xy-demo-key-123`

Header:
`X-API-Key: xy-demo-key-123`

## Fontos
Ez DEMÓ: az adatok memóriában vannak, nincs valódi fizetés, nincs valódi rendelés és nincs Webshippy kapcsolat.
A következő lépésben ezt köthetjük adatbázishoz, majd a fulfillment/API réteghez.

## 0.2.0 – Kosár + megerősítés

Új folyamat:
1. `POST /api/carts`
2. `POST /api/carts/{cart_token}/items`
3. `GET /api/carts/{cart_token}`
4. opcionálisan `PATCH` / `DELETE` a kosár tételeire
5. csak explicit megerősítés után: `POST /api/carts/{cart_token}/confirm`

A szerver a közvetlen `POST /api/orders` végpontot 410-es hibával letiltja, így a rendelés nem hozható létre kosár és confirm nélkül.

A cart token felhasználóhoz kötött, ezért más felhasználó nem tudja használni.
