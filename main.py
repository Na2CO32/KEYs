import os
import time
from typing import List
from datetime import datetime
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from starlette.exceptions import HTTPException as StarletteHTTPException

#時區設定
if not os.name == 'nt':  # 非 Windows 環境才執行
    os.environ['TZ'] = 'Asia/Taipei'
    time.tzset()

# --- 資料庫配置 ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 加入 connect_args={"sslmode": "require"} 解決 Render 連線問題
engine = create_engine(
    DATABASE_URL or "sqlite:///./local_test.db",
    connect_args={"sslmode": "require"} if DATABASE_URL and "postgresql" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 資料庫模型定義 ---
class KeyConfig(Base):
    __tablename__ = "keys"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    img = Column(Text)

class RentalRecord(Base):
    __tablename__ = "rentals"
    id = Column(Integer, primary_key=True, index=True)
    key_id = Column(String)
    name = Column(String)
    phone = Column(String)
    email = Column(String)
    date = Column(String)
    slots = Column(JSON)
    status = Column(String)
    create_time = Column(String)
    actual_return_time = Column(String, nullable=True)

# 啟動時自動建立資料表
Base.metadata.create_all(bind=engine)

# --- 初始化 ---
app = FastAPI(title="鑰匙租借系統")
templates = Jinja2Templates(directory="templates")

CONFIG = {
    "ALLOWED_PASSWORDS": ["A1b2", "K9p3", "X8y7", "Z1q2"],
    "SESSIONS": [
        {"name": "第一節", "time": "08:10 - 09:00"},
        {"name": "第二節", "time": "09:10 - 10:00"},
        {"name": "第三節", "time": "10:10 - 11:00"},
        {"name": "第四節", "time": "11:10 - 12:00"},
        {"name": "第五節", "time": "13:00 - 13:50"},
        {"name": "第六節", "time": "14:00 - 14:50"},
        {"name": "第七節", "time": "15:10 - 16:00"}
    ],
    "ADMIN_PWD": "FhCTF"
}

# --- 依賴項 ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(request: Request):
    if not request.cookies.get("user_session"):
        raise HTTPException(status_code=401)
    return True

async def verify_admin(request: Request):
    if request.cookies.get("admin_session") != "admin_authenticated":
        raise HTTPException(status_code=401)
    return True

# --- 路由：登入/登出 ---
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def handle_login(password: str = Form(...)):
    if password in CONFIG["ALLOWED_PASSWORDS"]:
        response = JSONResponse(content={"status": "success"})
        response.set_cookie(key="user_session", value="authenticated", max_age=900)
        return response
    return JSONResponse(status_code=401, content={"message": "❌ 密碼錯誤"})

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})

@app.post("/admin/login")
async def handle_admin_login(password: str = Form(...)):
    if password == CONFIG["ADMIN_PWD"]:
        response = JSONResponse(content={"status": "success"})
        response.set_cookie(key="admin_session", value="admin_authenticated", max_age=3600)
        return response
    return JSONResponse(status_code=401, content={"message": "❌ 密碼錯誤"})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_session")
    response.delete_cookie("admin_session")
    return response

# --- 路由：使用者介面 ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # 使用 templates.TemplateResponse 來渲染你的 index.html
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/rent", response_class=HTMLResponse)
async def rent_page(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    keys = db.query(KeyConfig).all()
    return templates.TemplateResponse("rent.html", {"request": request, "keys": keys, "sessions": CONFIG["SESSIONS"]})

@app.get("/return", response_class=HTMLResponse)
async def return_page(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    keys = db.query(KeyConfig).all()
    return templates.TemplateResponse("return.html", {"request": request, "keys": keys})

# --- 路由：邏輯 API ---
# --- [修正] 預約衝突邏輯 (handle_rent) ---
@app.post("/submit_rent")
async def handle_rent(
    name: str = Form(...), phone: str = Form(...), email: str = Form(...), 
    password: str = Form(...), key_id: str = Form(...), 
    timeslots: List[str] = Form(...), rent_date: str = Form(...), # rent_date 格式為 YYYY-MM-DD
    db: Session = Depends(get_db)
):
    if password not in CONFIG["ALLOWED_PASSWORDS"]:
        return JSONResponse(status_code=401, content={"message": "❌ 授權碼錯誤"})
    
    # 1. 產生與資料庫格式一致的日期字串用於查詢 (例如: "2026-02-24 (")
    # 使用 .like() 查詢可以更精準且高效
    date_prefix = f"{rent_date} ("
    
    # 2. 直接在資料庫過濾：同把鑰匙、同一天、且狀態非已歸還
    existing_conflicts = db.query(RentalRecord).filter(
        RentalRecord.key_id == key_id,
        RentalRecord.date.like(f"{date_prefix}%"), # 只找這一天
        RentalRecord.status.in_(["審查中", "已借出", "待確認歸還"])
    ).all()
    
    # 3. 檢查時段是否有交集
    for lease in existing_conflicts:
        overlap = set(timeslots) & set(lease.slots)
        if overlap:
            conflict_slots = ", ".join(list(overlap))
            return JSONResponse(
                status_code=400, 
                content={"message": f"❌ 預約衝突！該時段({conflict_slots})已被佔用。"}
            )

    # 4. 寫入新紀錄
    dt = datetime.strptime(rent_date, "%Y-%m-%d")
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    full_date_info = f"{rent_date} ({weekdays[dt.weekday()]})"
    
    new_record = RentalRecord(
        name=name, phone=phone, email=email, key_id=key_id,
        date=full_date_info,
        slots=timeslots, status="審查中",
        create_time=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    db.add(new_record)
    db.commit()
    return {"status": "success", "message": "預約成功"}

@app.post("/submit_return")
async def handle_return(phone: str = Form(...), key_id: str = Form(...), db: Session = Depends(get_db)):
    record = db.query(RentalRecord).filter(
        RentalRecord.phone == phone, 
        RentalRecord.key_id == key_id, 
        RentalRecord.status == "已借出"
    ).first()
    
    if not record:
        return JSONResponse(status_code=400, content={"message": "找不到符合的借出紀錄"})
    
    record.status = "待確認歸還"
    db.commit()
    return {"status": "success", "message": "歸還申請已提交"}

# --- 路由：管理員介面 ---
@app.get("/admin/records", response_class=HTMLResponse)
async def admin_records(request: Request, db: Session = Depends(get_db), _=Depends(verify_admin)):
    records = db.query(RentalRecord).order_by(RentalRecord.id.desc()).all()
    return templates.TemplateResponse("admin_records.html", {"request": request, "records": records})

@app.get("/admin/keys", response_class=HTMLResponse)
async def admin_keys_page(request: Request, db: Session = Depends(get_db), _=Depends(verify_admin)):
    keys = db.query(KeyConfig).all()
    return templates.TemplateResponse("admin_keys.html", {"request": request, "keys": keys})

@app.post("/admin/update_keys")
async def update_keys(request: Request, db: Session = Depends(get_db), _=Depends(verify_admin)):
    form_data = await request.form()
    names = form_data.getlist("keys")
    imgs = form_data.getlist("key_imgs")
    
    db.query(KeyConfig).delete()
    for name, img in zip(names, imgs):
        if name.strip():
            db.add(KeyConfig(name=name.strip(), img=img.strip()))
    db.commit()
    return {"status": "success"}

@app.post("/admin/update_status")
async def update_status(
    phone: str = Form(...), key_id: str = Form(...), date: str = Form(...), 
    target_status: str = Form(...), db: Session = Depends(get_db), _=Depends(verify_admin)
):
    record = db.query(RentalRecord).filter(
        RentalRecord.phone == phone, RentalRecord.key_id == key_id, RentalRecord.date == date
    ).first()
    
    if record:
        if target_status == "已歸還":
            record.actual_return_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        record.status = target_status
        db.commit()
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "紀錄不存在"})

# --- 錯誤處理 ---
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 401:
        return RedirectResponse(url="/admin/login" if "/admin" in request.url.path else "/login")

    return JSONResponse(status_code=exc.status_code, content={"message": str(exc.detail)})
