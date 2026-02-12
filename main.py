import json
import os
from typing import List, Optional
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import time
import asyncio
from datetime import datetime

# ---初始化與配置---
app = FastAPI(title="鑰匙租借系統")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

DATA_FILE = "rentals_db.json"

CONFIG = {
    "KEYS_LIST": ["K001 (大門)", "K002 (會議室)", "K003 (器材室)", "K004 (實驗室)", "K005 (後室)", "K006 (你家)", "K007 (我家)"],
    "ALLOWED_PASSWORDS": ["A1b2", "K9p3", "X8y7", "Z1q2"],
    "SESSIONS": [
        {"name": "第一節", "time": "08:10 - 09:00"},
        {"name": "第二節", "time": "09:10 - 10:00"},
        {"name": "第三節", "time": "10:10 - 11:00"},
        {"name": "第四節", "time": "11:10 - 12:00"},
        {"name": "第五節", "time": "13:00 - 13:50"},
        {"name": "第六節", "time": "14:00 - 14:50"},
        {"name": "第七節", "time": "15:10 - 16:00"}
    ]
}

# ---檔案存取邏輯---

def load_records():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_records(records):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=4)

# ---頁面路由區---

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/rent", response_class=HTMLResponse)
async def rent_page(request: Request):
    return templates.TemplateResponse("rent.html", {
        "request": request, 
        "keys": CONFIG["KEYS_LIST"],
        "sessions": CONFIG["SESSIONS"] 
    })

@app.get("/return", response_class=HTMLResponse)
async def return_page(request: Request):
    return templates.TemplateResponse("return.html", {
        "request": request, 
        "keys": CONFIG["KEYS_LIST"]
    })

# ---資料處理區(支援分時段借用)---

@app.post("/submit_rent")
async def handle_rent(
    phone: str = Form(...),
    email: str = Form(...),
    key_id: str = Form(...),
    timeslots: List[str] = Form(None),
    password: str = Form(...)
):
    records = load_records()

    # 驗證電話長度 (必須剛好 10 碼)
    if len(phone) != 10:
        return JSONResponse(status_code=400, content={"message": "🚫 電話格式錯誤！請輸入 10 位數字。"})

    # 驗證 Email 長度 (防止惡意輸入超長字串，例如超過 50 碼)
    if len(email) > 30 or len(email) < 15:
        return JSONResponse(status_code=400, content={"message": "🚫 Email 格式有誤，請重新輸入。"})

    #驗證日期與計算星期
    try:
        dt = datetime.strptime(rent_date, "%Y-%m-%d")
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_str = weekdays[dt.weekday()]
        full_date_info = f"{rent_date} ({weekday_str})"
    except:
        return JSONResponse(status_code=400, content={"message": "🚫 日期格式錯誤"})
    
    #檢查密碼&輸入錯誤需要等15秒
    if password not in CONFIG["ALLOWED_PASSWORDS"]:
        # 使用 asyncio.sleep 讓當前請求等待，但不會卡住其他人的請求
        await asyncio.sleep(15) 
        return {"status": "error", "message": "❌ 密碼錯誤！請輸入正確的授權碼。"}

    #檢查時段是否有勾選
    if not timeslots:
        return JSONResponse(status_code=400, content={"message": "❌ 請至少選擇一個租借時段！"})

    #檢查該鑰匙在選定時段是否已被佔用
    booked_slots = []
    if key_id in records:
        for lease in records[key_id]:
            booked_slots.extend(lease["slots"])

    overlap = set(timeslots) & set(booked_slots)
    if overlap:
        return JSONResponse(
            status_code=400, 
            content={"message": f"❌ 衝突！{key_id} 的 {', '.join(overlap)} 已經被其他人預約了。"}
        )

    #記錄租借資訊
    new_lease = {
        "date": full_date_info,
        "phone": phone,
        "email": email,
        "slots": timeslots
    }
    
    if key_id not in records:
        records[key_id] = []
    
    records[key_id].append(new_lease)
    save_records(records)

    return {
        "status": "success", 
        "message": f"🎉 預約成功！\n日期:{full_date_info}\n鑰匙:{key_id}\n登記電話:{phone}"
    }

@app.post("/submit_return")
async def handle_return(
    phone: str = Form(...),
    key_id: str = Form(...),
    return_date: str = Form(...) # 這裡要接收日期
):
    records = load_records()
    if key_id not in records or not records[key_id]:
        return JSONResponse(status_code=400, content={"message": "⚠️ 此鑰匙無借出紀錄"})

    #格式化日期以進行比對
    try:
        dt = datetime.strptime(return_date, "%Y-%m-%d")
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        full_date_info = f"{return_date} ({weekdays[dt.weekday()]})"
    except:
        return JSONResponse(status_code=400, content={"message": "🚫 日期格式錯誤"})

    #找到該日期且該電話的紀錄並移除
    initial_len = len(records[key_id])
    records[key_id] = [
        lease for lease in records[key_id] 
        if not (lease.get("phone") == phone and lease.get("date") == full_date_info)
    ]

    if len(records[key_id]) == initial_len:
        return JSONResponse(status_code=400, content={"message": "❌ 找不到對應日期與電話的預約紀錄。"})

    save_records(records)
    return {"status": "success", "message": f"✅ 已成功歸還 {return_date} 的鑰匙！"}