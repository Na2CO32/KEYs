import json
import os
from typing import List, Optional
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import time
import asyncio
from datetime import datetime
from fastapi import Query, HTTPException, Depends

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

#開啟檔案
def load_records():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {}

#存檔
def save_records(records):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=4)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
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
    # 密碼與長度驗證
    if password not in CONFIG["ALLOWED_PASSWORDS"]:
        await asyncio.sleep(15)
        return JSONResponse(status_code=401, content={"message": "❌ 授權碼錯誤，請重新輸入。"})

    if len(phone) != 10:
        return JSONResponse(status_code=400, content={"message": "🚫 電話格式錯誤(需10位數)"})

    # 日期處理：轉換為 "2024-02-12 (星期四)" 格式
    try:
        dt = datetime.strptime(rent_date, "%Y-%m-%d")
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        full_date_info = f"{rent_date} ({weekdays[dt.weekday()]})"
    except:
        return JSONResponse(status_code=400, content={"message": "🚫 日期格式錯誤"})

    records = load_records()
    booked_leases = records.get(key_id, [])

    # 同一天的時段衝突檢查
    overlap = []
    for lease in booked_leases:
        if lease.get("date") == full_date_info:
            booked_slots = lease.get("slots", [])
            current_overlap = set(timeslots) & set(booked_slots)
            if current_overlap:
                overlap.extend(list(current_overlap))

    if overlap:
        return JSONResponse(status_code=400, content={"message": f"❌ 衝突！{key_id} 在 {full_date_info} 的 {', '.join(overlap)} 已被預約。"})

    # 儲存新紀錄
    new_lease = {
        "name": name,
        "date": full_date_info,
        "phone": phone,
        "email": email,
        "slots": timeslots,
        "status": "租借中"  #預設狀態為租借中
    }
    
    if key_id not in records:
        records[key_id] = []
    records[key_id].append(new_lease)
    save_records(records)

    return {"status": "success", "message": f"🎉 預約成功！\n日期: {full_date_info}"}

@app.post("/submit_return")
async def handle_return(
    phone: str = Form(...),
    key_id: str = Form(...),
    return_date: str = Form(...)
):
    records = load_records()
    if key_id not in records or not records[key_id]:
        return JSONResponse(status_code=400, content={"message": "⚠️ 此鑰匙無借出紀錄"})

    #日期格式處理
    try:
        dt = datetime.strptime(return_date, "%Y-%m-%d")
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        target_date_info = f"{return_date} ({weekdays[dt.weekday()]})"
    except:
        return JSONResponse(status_code=400, content={"message": "🚫 歸還日期格式錯誤"})

    # 尋找並更新紀錄狀態，而不是刪除它
    found = False
    for lease in records[key_id]:
        # 條件：電話對、日期對，且目前狀態還不是「已歸還」
        if (lease.get("phone") == phone and 
            lease.get("date") == target_date_info and 
            lease.get("status") != "已歸還"):
            
            lease["status"] = "已歸還"  # ✨ 標記狀態
            lease["actual_return_time"] = datetime.now().strftime("%Y-%m-%d %H:%M") # ✨ 紀錄實際歸還時間
            found = True
            break

    if not found:
        return JSONResponse(status_code=400, content={"message": f"❌ 找不到符合的租借紀錄，或該紀錄已歸還。"})

    save_records(records)
    return {"status": "success", "message": f"✅ 已成功歸還 {target_date_info} 的鑰匙！"}

#依賴注入管理員認證
async def verify_admin(pwd: str = Query(None)):
    if pwd != "SECRET_123":
        raise HTTPException(status_code=403, detail="🚫 權限不足")
    return True

#管理員用的
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request, 
    authenticated: bool = Depends(verify_admin)  # 這裡就是依賴注入
):
    # 只要執行到這，代表 verify_admin 已經驗證成功了
    records = load_records()
    
    #格式排版整理
    display_list = [] 
    for key_id, leases in records.items():
        for lease in leases:
            display_list.append({
                "name": lease.get("name", "未填寫"),
                "key_id": key_id,
                "date": lease.get("date"),
                "phone": lease.get("phone"),
                "email": lease.get("email"),
                "slots": ", ".join(lease.get("slots", [])),
                "status": lease.get("status", "租借中")
})
            
    # 按日期排序（可選）
    display_list.sort(key=lambda x: x['date'], reverse=True)

    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "records": display_list
    })