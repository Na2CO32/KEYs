import json
import os
from typing import List, Optional
from fastapi import FastAPI, Request, Form, Query, HTTPException, Depends, Response, Cookie
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import asyncio
from datetime import datetime
from starlette.exceptions import HTTPException as StarletteHTTPException

# --- 初始化與配置 ---
app = FastAPI(title="鑰匙租借系統")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

DATA_FILE = "rentals_db.json"
KEYS_FILE = "keys_config.json"

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
    "ADMIN_PWD": "FhCTF"  # 管理員專屬密碼
}

# --- 工具函數 ---
def load_keys():
    if not os.path.exists(KEYS_FILE):
        default_keys = ["K001 (大門)", "K002 (會議室)", "K003 (器材室)"]
        save_keys(default_keys)
        return default_keys
    with open(KEYS_FILE, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return []

def save_keys(keys_list):
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(keys_list, f, ensure_ascii=False, indent=4)

def load_records():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return {}

def save_records(records):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=4)

# --- 權限驗證邏輯 ---

async def get_current_user(request: Request):
    """一般使用者登入檢查"""
    user = request.cookies.get("user_session")
    if not user:
        raise HTTPException(status_code=401, detail="請先登入")
    return user

async def verify_admin(request: Request):
    """管理員登入檢查"""
    admin_token = request.cookies.get("admin_session")
    if admin_token != "admin_authenticated":
        raise HTTPException(status_code=401, detail="管理員權限不足")
    return True

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 401:
        # 根據路徑判斷要跳轉到一般登入還是管理員登入
        if request.url.path.startswith("/admin"):
            return RedirectResponse(url="/admin/login")
        return RedirectResponse(url="/login")
    return JSONResponse(status_code=exc.status_code, content={"message": str(exc.detail)})

# --- 登入/登出路由 ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def handle_login(password: str = Form(...)):
    if password in CONFIG["ALLOWED_PASSWORDS"]:
        response = JSONResponse(content={"status": "success"})
        response.set_cookie(key="user_session", value="authenticated", max_age=86400)
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
    return JSONResponse(status_code=401, content={"message": "❌ 管理員密碼錯誤"})

@app.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_session")
    response.delete_cookie("admin_session")
    return response

# --- 借還系統路由 ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/rent", response_class=HTMLResponse)
async def rent_page(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse("rent.html", {"request": request, "keys": load_keys(), "sessions": CONFIG["SESSIONS"]})

@app.get("/return", response_class=HTMLResponse)
async def return_page(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse("return.html", {"request": request, "keys": load_keys()})

# --- 管理員頁面 (已拆分) ---

@app.get("/admin/records", response_class=HTMLResponse)
async def admin_records(request: Request, _=Depends(verify_admin)):
    records = load_records()
    display_list = []
    for key_id, leases in records.items():
        for lease in leases:
            display_list.append({**lease, "key_id": key_id})
    display_list.sort(key=lambda x: x['date'], reverse=True)
    return templates.TemplateResponse("admin_records.html", {"request": request, "records": display_list})

@app.get("/admin/keys", response_class=HTMLResponse)
async def admin_keys_page(request: Request, _=Depends(verify_admin)):
    return templates.TemplateResponse("admin_keys.html", {"request": request, "keys": load_keys()})

# --- 邏輯 API ---

@app.post("/submit_rent")
async def handle_rent(name: str = Form(...), phone: str = Form(...), email: str = Form(...), password: str = Form(...), key_id: str = Form(...), timeslots: List[str] = Form(...), rent_date: str = Form(...)):
    if password not in CONFIG["ALLOWED_PASSWORDS"]:
        await asyncio.sleep(2)
        return JSONResponse(status_code=401, content={"message": "❌ 授權碼錯誤"})
    
    # ... (其餘租借邏輯保持不變) ...
    records = load_records()
    # --- 🛡️ 這裡就是你原本缺少的「防呆比對」邏輯 ---
    if key_id in records:
        for lease in records[key_id]:
            # 只有在單子還沒「已歸還」的情況下才需要檢查衝突
            if lease.get("status") in ["審查中", "已借出", "待確認歸還"]:
                # 檢查日期 (比對前 10 位字元，即 YYYY-MM-DD)
                existing_date = lease["date"][:10] 
                if rent_date == existing_date:
                    # 檢查時段是否有交集
                    # 使用 set 的交集 & 來比對是否有重複時段
                    overlap = set(timeslots) & set(lease["slots"])
                    if overlap:
                        conflict_slots = ", ".join(list(overlap))
                        return JSONResponse(
                            status_code=400, 
                            content={"message": f"❌ 預約衝突！該時段({conflict_slots})已被佔用，請更換時段或鑰匙。"}
                        )
    # --- 防呆結束 ---

    # 格式化日期顯示
    dt = datetime.strptime(rent_date, "%Y-%m-%d")
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    full_date_info = f"{rent_date} ({weekdays[dt.weekday()]})"
    
    new_lease = {
        "name": name, 
        "date": full_date_info, 
        "phone": phone, 
        "email": email, 
        "slots": timeslots, 
        "status": "審查中", 
        "create_time": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    if key_id not in records: records[key_id] = []
    records[key_id].append(new_lease)
    save_records(records)
    return {"status": "success", "message": "預約成功"}

@app.post("/submit_return")
async def handle_return(phone: str = Form(...), key_id: str = Form(...), user: str = Depends(get_current_user)):
    records = load_records()
    found = False
    if key_id in records:
        for lease in records[key_id]:
            if lease.get("phone") == phone and lease.get("status") == "已借出":
                lease["status"] = "待確認歸還"
                found = True; break
    if not found: return JSONResponse(status_code=400, content={"message": "找不到符合紀錄"})
    save_records(records)
    return {"status": "success", "message": "歸還申請已提交"}

# --- 管理員操作 API (改為 Session 驗證) ---

@app.post("/admin/update_status")
async def update_status(
    phone: str = Form(...),
    key_id: str = Form(...),
    date: str = Form(...),
    target_status: str = Form(...),
    _=Depends(verify_admin)  # 改用這個檢查 Session，不用再傳密碼
):
    records = load_records()
    if key_id in records:
        for lease in records[key_id]:
            if lease.get("phone") == phone and lease.get("date") == date:
                # 缺陷 1：如果已經是「已歸還」，不允許再變更狀態
                if lease.get("status") == "已歸還":
                    return JSONResponse(status_code=400, content={"message": "此紀錄已完成歸還，無法更改"})
                
                lease["status"] = target_status
                if target_status == "已歸還":
                    lease["actual_return_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                save_records(records)
                return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "找不到紀錄"})

@app.post("/admin/update_keys")
async def update_keys(
    keys: List[str] = Form(...), 
    _=Depends(verify_admin)  # 👈 這是關鍵！強制檢查 Cookie 門禁
):
    cleaned_keys = [k.strip() for k in keys if k.strip()]
    save_keys(cleaned_keys)
    return {"status": "success"}