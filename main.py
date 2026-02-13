import json
import os
from typing import List, Optional
from fastapi import FastAPI, Request, Form, Query, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import asyncio
from datetime import datetime

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
    "ADMIN_PWD": "SECRET_123"  # 管理員後台密碼
}

# --- 工具函數 ---

def load_keys():
    """載入鑰匙庫，若無檔案則建立預設值"""
    if not os.path.exists(KEYS_FILE):
        default_keys = ["K001 (大門)", "K002 (會議室)", "K003 (器材室)"]
        save_keys(default_keys)
        return default_keys
    with open(KEYS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return []

def save_keys(keys_list):
    """儲存鑰匙庫"""
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(keys_list, f, ensure_ascii=False, indent=4)

def load_records():
    """載入所有租借紀錄"""
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_records(records):
    """儲存所有租借紀錄"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=4)

# --- 權限驗證 (Dependency) ---

async def verify_admin(pwd: str = Query(None)):
    """驗證管理員密碼，失敗回傳 403"""
    if pwd != CONFIG["ADMIN_PWD"]:
        raise HTTPException(status_code=403, detail="🚫 權限不足，密碼錯誤。")
    return True

# --- 頁面路由 ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/rent", response_class=HTMLResponse)
async def rent_page(request: Request):
    return templates.TemplateResponse("rent.html", {
        "request": request,
        "keys": load_keys(),
        "sessions": CONFIG["SESSIONS"]
    })

@app.get("/return", response_class=HTMLResponse)
async def return_page(request: Request):
    return templates.TemplateResponse("return.html", {
        "request": request,
        "keys": load_keys()
    })

# --- 邏輯 API ---

@app.post("/submit_rent")
async def handle_rent(
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    key_id: str = Form(...),
    timeslots: List[str] = Form(...),
    rent_date: str = Form(...)
):
    # 1. 驗證前端輸入密碼
    if password not in CONFIG["ALLOWED_PASSWORDS"]:
        await asyncio.sleep(2) # 稍微延遲增加暴力破解難度
        return JSONResponse(status_code=401, content={"message": "❌ 授權碼錯誤，請詢問管理員。"})

    if len(phone) != 10:
        return JSONResponse(status_code=400, content={"message": "🚫 電話格式錯誤 (請輸入 10 位數)"})

    # 2. 處理日期格式與星期計算
    try:
        dt = datetime.strptime(rent_date, "%Y-%m-%d")
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        full_date_info = f"{rent_date} ({weekdays[dt.weekday()]})"
    except:
        return JSONResponse(status_code=400, content={"message": "🚫 日期格式不正確"})

    records = load_records()
    booked_leases = records.get(key_id, [])

    # 3. 衝突檢查
    overlap = []
    for lease in booked_leases:
        if lease.get("date") == full_date_info and lease.get("status") != "已歸還":
            booked_slots = lease.get("slots", [])
            current_overlap = set(timeslots) & set(booked_slots)
            if current_overlap:
                overlap.extend(list(current_overlap))

    if overlap:
        return JSONResponse(status_code=400, content={"message": f"❌ 預約衝突！此時段已有人預約：{', '.join(overlap)}"})

    # 4. 建立紀錄
    new_lease = {
        "name": name,
        "date": full_date_info,
        "phone": phone,
        "email": email,
        "slots": timeslots,
        "status": "審查中",
        "create_time": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    if key_id not in records:
        records[key_id] = []
    records[key_id].append(new_lease)
    save_records(records)

    return {"status": "success", "message": f"🎉 預約成功！狀態為「審查中」。\n日期：{full_date_info}"}

@app.post("/submit_return")
async def handle_return(phone: str = Form(...), key_id: str = Form(...)):
    records = load_records()
    if key_id not in records:
        return JSONResponse(status_code=400, content={"message": "⚠️ 查無此鑰匙的借用紀錄"})

    found = False
    for lease in records[key_id]:
        if lease.get("phone") == phone and lease.get("status") == "已借出":
            lease["status"] = "待確認歸還"
            found = True
            break

    if not found:
        return JSONResponse(status_code=400, content={"message": "❌ 找不到符合「已借出」狀態的紀錄，請確認電話是否正確。"})

    save_records(records)
    return {"status": "success", "message": "✅ 歸還申請已提交，請將鑰匙放回原處。"}

# --- 管理員後台 API ---

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, authenticated: bool = Depends(verify_admin)):
    records = load_records()
    display_list = [] 
    for key_id, leases in records.items():
        for lease in leases:
            display_list.append({
                "name": lease.get("name"),
                "key_id": key_id,
                "date": lease.get("date"),
                "phone": lease.get("phone"),
                "slots": ", ".join(lease.get("slots", [])),
                "status": lease.get("status")
            })
            
    # 按日期倒序排（最新的在上面）
    display_list.sort(key=lambda x: x['date'], reverse=True)
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "records": display_list, 
        "keys": load_keys()
    })

@app.post("/admin/update_status")
async def update_status(
    phone: str = Form(...),
    key_id: str = Form(...),
    date: str = Form(...),
    target_status: str = Form(...),
    pwd: str = Query(...)
):
    if pwd != CONFIG["ADMIN_PWD"]:
        return JSONResponse(status_code=403, content={"message": "權限不足"})

    records = load_records()
    found = False
    if key_id in records:
        for lease in records[key_id]:
            if lease.get("phone") == phone and lease.get("date") == date:
                lease["status"] = target_status
                if target_status == "已歸還":
                    lease["actual_return_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                found = True
                break
    
    if found:
        save_records(records)
        return {"status": "success"}
    return JSONResponse(status_code=404, content={"message": "找不到該筆紀錄"})

@app.post("/admin/update_keys")
async def update_keys(keys: List[str] = Form(...), pwd: str = Query(...)):
    if pwd != CONFIG["ADMIN_PWD"]:
        return JSONResponse(status_code=403, content={"message": "權限不足"})
    
    cleaned_keys = [k.strip() for k in keys if k.strip()]
    save_keys(cleaned_keys)
    return {"status": "success"}