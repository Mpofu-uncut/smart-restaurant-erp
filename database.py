from datetime import datetime
from enum import Enum
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = "sqlite:///./restaurant_enterprise.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserRole(str, Enum):
    CLIENT = "client"
    WAITER = "waiter"
    KITCHEN = "kitchen"
    DRIVER = "driver"
    ADMIN = "admin"

class OrderType(str, Enum):
    DINE_IN = "dine_in"
    DELIVERY = "delivery"

class OrderStatus(str, Enum):
    PENDING = "pending"
    IN_KITCHEN = "in_kitchen"
    READY_FOR_DISPATCH = "ready_for_dispatch"
    OUT_FOR_DELIVERY = "out_for_delivery"
    COMPLETED = "completed"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False)

class MenuProduct(Base):
    __tablename__ = "menu_products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    price = Column(Float, nullable=False)
    is_available = Column(Integer, default=1)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String, nullable=False)
    order_type = Column(SQLEnum(OrderType), nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    total_price = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    receipt_token = Column(String, unique=True, nullable=False)
    
    items = relationship("OrderItem", back_populates="order")
    dispatch_log = relationship("DispatchLog", back_populates="order", uselist=False)

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, default=1)
    
    order = relationship("Order", back_populates="items")

class DispatchLog(Base):
    __tablename__ = "dispatch_logs"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)
    driver_name = Column(String, nullable=False)
    dispatched_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime, nullable=True)

    order = relationship("Order", back_populates="dispatch_log")

class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, index=True)
    ingredient_name = Column(String, unique=True, nullable=False)
    stock_qty = Column(Integer, default=100)

def init_db():
    Base.metadata.create_all(bind=engine)
