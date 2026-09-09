from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
import database as db
import uuid
from datetime import datetime

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

# Mock Security Check (In production, this decodes a secure JWT login token)
def verify_manager_access(username: str = "admin"):
    """Gatekeeper tracking system roles. Blocks anyone who isn't a manager/admin."""
    if username.lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access Denied: Administrative and Management credentials required."
        )
    return True

@app.get("/")
def read_root():
    return {"status": "ONLINE", "system": "Restaurant POS & ERP Engine Active"}

# ----------------- PIPELINE ENDPOINTS -----------------

@app.post("/orders/create", status_code=status.HTTP_201_CREATED)
def place_new_order(client: str, o_type: db.OrderType, items: str, dbs: Session = Depends(get_db)):
    """Receives an input order entry from a Client or Waiter and routes it to the database."""
    receipt_uid = f"REC-{uuid.uuid4().hex[:6].upper()}"
    
    new_order = db.Order(client_name=client, order_type=o_type, receipt_token=receipt_uid, total_price=0.0)
    dbs.add(new_order)
    dbs.commit()
    dbs.refresh(new_order)
    
    calc_total = 0.0
    # Clean up the incoming item text string (e.g., "Pizza, Burger" -> ["Pizza", "Burger"])
    item_list = [i.strip() for i in items.split(",") if i.strip()]
    
    for item_name in item_list:
        order_item = db.OrderItem(order_id=new_order.id, product_name=item_name, quantity=1)
        calc_total += 12.50  # Default $12.50 per individual dish item
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


@app.get("/orders/{receipt_token}/receipt")
def generate_printable_receipt(receipt_token: str, dbs: Session = Depends(get_db)):
    """Generates a beautifully formatted terminal/printer receipt text summary for clients and dispatchers."""
    order = dbs.query(db.Order).filter(db.Order.receipt_token == receipt_token).first()
    if not order:
        raise HTTPException(status_code=404, detail="Receipt verification token not found.")
    
    # Build text block string mapping layout items itemized line by line
    border = "========================================\n"
    header = "       MPOFU ENTERPRISE RESTAURANT      \n"
    meta_info = f" Receipt: {order.receipt_token}\n Type: {order.order_type.upper()} | Status: {order.status.upper()}\n Client: {order.client_name}\n"
    item_header = "----------------------------------------\n Item               Qty       Est. Price\n----------------------------------------\n"
    
    items_body = ""
    for item in order.items:
        items_body += f" {item.product_name:<18} {item.quantity:<9} ${12.50 * item.quantity:.2f}\n"
        
    footer = f"----------------------------------------\n TOTAL AMOUNT DUE:           ${order.total_price:.2f}\n"
    thank_you = "      THANK YOU FOR DINING WITH US!     \n"
    
    receipt_raw_text = border + header + border + meta_info + item_header + items_body + footer + border + thank_you + border
    return {"receipt_token": order.receipt_token, "printable_ascii_receipt": receipt_raw_text}

@app.get("/kitchen/queue")
def get_kitchen_queue(dbs: Session = Depends(get_db)):
    """Allows the Kitchen monitor panel to pull active orders waiting for preparation."""
    active_orders = dbs.query(db.Order).filter(db.Order.status == db.OrderStatus.PENDING).all()
    return [{"id": o.id, "client": o.client_name, "token": o.receipt_token, "time": o.created_at} for o in active_orders]

@app.patch("/orders/{receipt_token}/update-status")
def update_order_state(receipt_token: str, new_status: str, dbs: Session = Depends(get_db)):
    """Allows Driver Dispatch, Managers, or Kitchen staff to advance the state step safely."""
    target_order = dbs.query(db.Order).filter(db.Order.receipt_token == receipt_token).first()
    if not target_order:
        raise HTTPException(status_code=404, detail="Receipt verification failed.")
        
    setattr(target_order, "status", new_status)
    dbs.commit()
    return {"status": "SUCCESS", "receipt": receipt_token, "new_operational_state": target_order.status}

# ----------------- ADMIN GATED METRICS -----------------

@app.get("/admin/dashboard/transactions")
def get_all_transactions(username: str = "client", is_manager: bool = Depends(verify_manager_access), dbs: Session = Depends(get_db)):
    """A highly secure route that allows ONLY managers to pull financial data totals across departments."""
    all_orders = dbs.query(db.Order).all()
    gross_revenue = sum(o.total_price for o in all_orders)
    return {
        "access_granted": True,
        "total_orders_processed": len(all_orders),
        "gross_system_revenue": f"${gross_revenue:.2f}",
        "detailed_ledger": [{"receipt": o.receipt_token, "client": o.client_name, "total": o.total_price, "type": o.order_type} for o in all_orders]
    }

# ----------------- DISPATCH & DELIVERY TRACKING ENDPOINTS -----------------

@app.post("/dispatch/assign/{receipt_token}")
def assign_order_to_driver(receipt_token: str, driver_name: str, dbs: Session = Depends(get_db)):
    """Logs when an order leaves the counter and hands tracking over to a specific delivery driver."""
    order = dbs.query(db.Order).filter(db.Order.receipt_token == receipt_token).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    if order.order_type.value != db.OrderType.DELIVERY.value:
        raise HTTPException(status_code=400, detail="Action error: This order is marked as Dine-In.")
        
    # Check if this order is already dispatched to prevent data overlap
    existing_log = dbs.query(db.DispatchLog).filter(db.DispatchLog.order_id == order.id).first()
    if existing_log:
        return {"status": "ALREADY_DISPATCHED", "driver": existing_log.driver_name, "time": existing_log.dispatched_at}

    # 1. Create a live log footprint entry link
    new_log = db.DispatchLog(order_id=order.id, driver_name=driver_name)
    dbs.add(new_log)
    
    # 2. Advance order operational pipeline state
    setattr(order, "status", db.OrderStatus.OUT_FOR_DELIVERY)
    dbs.commit()
    
    return {
        "status": "DISPATCHED",
        "receipt_id": order.receipt_token,
        "assigned_driver": driver_name,
        "dispatch_timestamp": new_log.dispatched_at
    }

@app.patch("/dispatch/complete/{receipt_token}")
def mark_order_delivered(receipt_token: str, dbs: Session = Depends(get_db)):
    """Logs the exact second a driver hands the meal box to the client, closing out the transaction ledger."""
    order = dbs.query(db.Order).filter(db.Order.receipt_token == receipt_token).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not located.")
        
    log = dbs.query(db.DispatchLog).filter(db.DispatchLog.order_id == order.id).first()
    if not log:
        raise HTTPException(status_code=400, detail="Dispatch configuration sequence error: Order was never assigned to a driver.")

    # Mark completion timestamp records live
    setattr(log, "delivered_at", datetime.utcnow())
    setattr(order, "status", db.OrderStatus.COMPLETED)
    dbs.commit()
    
    return {
        "status": "DELIVERED_SUCCESS",
        "receipt_id": order.receipt_token,
        "driver": log.driver_name,
        "completed_at": log.delivered_at
    }

