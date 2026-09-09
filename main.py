from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
import database as db
import uuid

app = FastAPI(title="Smart Restaurant Cloud ERP System")

# Initialize database schemas on startup automatically
db.init_db()

# DB Dependency link session
def get_db():
    database = db.SessionLocal()
    try:
        yield database
    finally:
        database.close()

@app.get("/")
def read_root():
    return {"status": "ONLINE", "system": "Restaurant POS & ERP Engine Active"}

# ----------------- ORDER PIPELINE ENDPOINTS -----------------

@app.post("/orders/create", status_code=status.HTTP_201_CREATED)
def place_new_order(client: str, o_type: db.OrderType, items: list, dbs: Session = Depends(get_db)):
    """Receives an input order entry from a Client or Waiter and routes it directly to the system database."""
    # Generate unique alphanumeric secure code for receipt matching
    receipt_uid = f"REC-{uuid.uuid4().hex[:6].upper()}"
    
    new_order = db.Order(client_name=client, order_type=o_type, receipt_token=receipt_uid, total_price=0.0)
    dbs.add(new_order)
    dbs.commit()
    dbs.refresh(new_order)
    
    calc_total = 0.0
    for item in items:
        # Loop over array mapping strings/quantities
        order_item = db.OrderItem(order_id=new_order.id, product_name=item["name"], quantity=item["quantity"])
        # Calculating pricing parameters based on default estimation of $12.50 per hospitality item unit
        calc_total += (12.50 * item["quantity"])
        dbs.add(order_item)
    
    dbs.commit()
    setattr(new_order, "total_price", calc_total)
    dbs.commit()
    dbs.refresh(new_order)

    
    return {
        "message": "Order successfully routed to Kitchen Department!",
        "receipt_id": new_order.receipt_token,
        "client": new_order.client_name,
        "type": new_order.order_type,
        "status": new_order.status,
        "total_bill": f"${new_order.total_price:.2f}"
    }

@app.get("/kitchen/queue")
def get_kitchen_queue(dbs: Session = Depends(get_db)):
    """Allows the Kitchen monitor panel to pull active orders waiting for preparation processing."""
    active_orders = dbs.query(db.Order).filter(db.Order.status == db.OrderStatus.PENDING).all()
    return [{"id": o.id, "client": o.client_name, "token": o.receipt_token, "time": o.created_at} for o in active_orders]

@app.patch("/orders/{receipt_token}/update-status")
def update_order_state(receipt_token: str, new_status: str, dbs: Session = Depends(get_db)):
    """Allows Driver Dispatch, Managers, or Kitchen staff to advance the state step safely."""
    target_order = dbs.query(db.Order).filter(db.Order.receipt_token == receipt_token).first()
    if not target_order:
        raise HTTPException(status_code=404, detail="Receipt verification failed. Order record not located.")
        
    setattr(target_order, "status", new_status)
    dbs.commit()
    return {"status": "SUCCESS", "receipt": receipt_token, "new_operational_state": target_order.status}
