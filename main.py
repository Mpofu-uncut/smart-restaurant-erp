from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import database as db
import uuid
from datetime import datetime

app = FastAPI(title="Smart Restaurant Cloud ERP System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()
templates = Jinja2Templates(directory="templates")

def get_db():
    database = db.SessionLocal()
    try:
        yield database
    finally:
        database.close()

@app.on_event("startup")
def seed_inventory():
    dbs = db.SessionLocal()
    if dbs.query(db.Inventory).count() == 0:
        initial_stock = {"Pizza": 20, "Burger": 30, "Fries": 50, "Soda": 100}
        for name, qty in initial_stock.items():
            dbs.add(db.Inventory(ingredient_name=name, stock_qty=qty))
        dbs.commit()
    dbs.close()

def verify_manager_access(username: str = "admin"):
    if username.lower() != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access Denied.")
    return True

@app.get("/")
def read_root():
    return {"status": "ONLINE"}

@app.get("/dashboard", response_class=HTMLResponse)
def render_live_operations_board(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")

@app.post("/orders/create", status_code=status.HTTP_201_CREATED)
def place_new_order(client: str, o_type: db.OrderType, items: str, dbs: Session = Depends(get_db)):
    receipt_uid = f"REC-{uuid.uuid4().hex[:6].upper()}"
    item_list = [i.strip() for i in items.split(",") if i.strip()]
    
    for item_name in item_list:
        stock_item = dbs.query(db.Inventory).filter(db.Inventory.ingredient_name == item_name).first()
        if not stock_item or int(getattr(stock_item, "stock_qty", 0)) <= 0:
            raise HTTPException(status_code=400, detail="Stockout or invalid item.")

    new_order = db.Order(client_name=client, order_type=o_type, receipt_token=receipt_uid, total_price=0.0)
    dbs.add(new_order)
    dbs.commit()
    dbs.refresh(new_order)
    
    calc_total = 0.0
    for item_name in item_list:
        stock_item = dbs.query(db.Inventory).filter(db.Inventory.ingredient_name == item_name).first()
        if stock_item:
            setattr(stock_item, "stock_qty", int(getattr(stock_item, "stock_qty", 0)) - 1)
        
        order_item = db.OrderItem(order_id=new_order.id, product_name=item_name, quantity=1)
        calc_total += 12.50
        dbs.add(order_item)
        
    dbs.commit()
    setattr(new_order, "total_price", calc_total)
    dbs.commit()
    dbs.refresh(new_order)
    return {"status": "SUCCESS", "receipt_id": new_order.receipt_token}

@app.get("/inventory/status")
def view_stock_levels(dbs: Session = Depends(get_db)):
    stock = dbs.query(db.Inventory).all()
    return {item.ingredient_name: item.stock_qty for item in stock}

@app.patch("/orders/{receipt_token}/update-status")
def update_order_state(receipt_token: str, new_status: str, dbs: Session = Depends(get_db)):
    target_order = dbs.query(db.Order).filter(db.Order.receipt_token == receipt_token).first()
    if target_order:
        setattr(target_order, "status", new_status)
        dbs.commit()
    return {"status": "SUCCESS"}

@app.post("/dispatch/assign/{receipt_token}")
def assign_order_to_driver(receipt_token: str, driver_name: str, dbs: Session = Depends(get_db)):
    order = dbs.query(db.Order).filter(db.Order.receipt_token == receipt_token).first()
    if not order or getattr(order, "order_type", "") != "delivery":
        raise HTTPException(status_code=400, detail="Not a delivery order.")
    
    new_log = db.DispatchLog(order_id=order.id, driver_name=driver_name)
    dbs.add(new_log)
    setattr(order, "status", db.OrderStatus.OUT_FOR_DELIVERY)
    dbs.commit()
    return {"status": "DISPATCHED"}

@app.get("/admin/dashboard/transactions")
def get_all_transactions(username: str = "admin", is_manager: bool = Depends(verify_manager_access), dbs: Session = Depends(get_db)):
    all_orders = dbs.query(db.Order).all()
    gross_revenue = sum(o.total_price for o in all_orders)
    return {
        "access_granted": True,
        "gross_system_revenue": f"${gross_revenue:.2f}",
        "detailed_ledger": [{
            "receipt_id": o.receipt_token, 
            "client_name": o.client_name, 
            "total_bill": o.total_price, 
            "order_type": o.order_type,
            "status": o.status,
            "items_summary": ", ".join([i.product_name for i in o.items])
        } for o in all_orders]
    }
