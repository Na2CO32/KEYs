import json
import os
from typing import List, Optional
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import time
import asyncio

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

    #避免輸入過長字串存入
    if len(phone) > 10 or len(email) > 40:
        return JSONResponse(status_code=400, content={"message": "🚫 資料格式過長！"})

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
        "message": f"🎉 預約成功！\n鑰匙:{key_id}\n時段:{', '.join(timeslots)}\n登記電話:{phone}"
    }

@app.post("/submit_return")
async def handle_return(
    phone: str = Form(...),
    key_id: str = Form(...)
):
    records = load_records()

    #檢查鑰匙是否有任何借出紀錄
    if key_id not in records or not records[key_id]:
        return JSONResponse(status_code=400, content={"message": "⚠️ 系統顯示這把鑰匙目前都在家，不需要歸還喔！"})

    #尋找該電話對應的租借人
    found_lease = None
    for lease in records[key_id]:
        if lease["phone"] == phone:
            found_lease = lease
            break

    if not found_lease:
        return JSONResponse(status_code=403, content={"message": "🚫 歸還失敗！找不到此電話對應的租借時段。"})

    #刪除該筆紀錄並更新檔案
    records[key_id].remove(found_lease)
    
    #如果這把鑰匙已經沒有人借任何時段了，就清空
    if not records[key_id]:
        del records[key_id]
        
    save_records(records)

    return {
        "status": "success", 
        "message": f"✅ 歸還成功！\n您借用的 {key_id} 時段已登記歸還。"
    }