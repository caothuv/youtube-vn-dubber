@echo off
REM START_WINDOWS.bat — bật server lồng tiếng Việt (bấm đúp là chạy)
REM Lần đầu: script tự tạo môi trường ảo + cài thư viện (mất vài phút, chỉ 1 lần).
REM Các lần sau: bấm đúp là server chạy ngay.
setlocal
cd /d "%~dp0"
title Long tieng Viet AI - Server
echo ============================================================
echo  LONG TIENG VIET AI CHO YOUTUBE - SERVER
echo ============================================================
echo.

REM 1. Kiem tra Python
python --version >nul 2>&1
if errorlevel 1 (
  echo [LOI] Chua thay Python. Anh cai Python 3.11 tro len truoc:
  echo       https://www.python.org/downloads/
  echo       (Luc cai NHO TICH vao o "Add python.exe to PATH")
  pause
  exit /b 1
)

REM 2. Tao moi truong ao neu chua co
if not exist "server\.venv\Scripts\python.exe" (
  echo [1/3] Tao moi truong ao lan dau (chi 1 lan)...
  python -m venv server\.venv
  if errorlevel 1 (
    echo [LOI] Khong tao duoc moi truong ao.
    pause
    exit /b 1
  )
)

REM 3. Cai thu vien neu chua cai
server\.venv\Scripts\python.exe -c "import fastapi, uvicorn, httpx, vieneu" >nul 2>&1
if errorlevel 1 (
  echo [2/3] Cai thu vien lan dau (mat vai phut, can mang)...
  server\.venv\Scripts\python.exe -m pip install --upgrade pip
  server\.venv\Scripts\python.exe -m pip install -r server\requirements.txt
  if errorlevel 1 (
    echo [LOI] Cai thu vien loi. Kiem tra mang roi chay lai file nay.
    pause
    exit /b 1
  )
)

REM 4. Nhac tao file .env neu chua co
if not exist "server\.env" (
  echo [CHU Y] Chua co file server\.env — da copy mau tu .env.example
  echo         Mo file server\.env bang Notepad de dien key DeepSeek (neu dung),
  echo         hoac cu de vay neu chi dung Unsloth local.
  copy server\.env.example server\.env >nul
)

echo [3/3] Dang bat server...
echo.
echo  Server chay tai: http://127.0.0.1:8000
echo  Mo Chrome -^> YouTube -^> bam nut "AI Viet" tren thanh video.
echo  De tat server: dong cua so nay (Ctrl+C).
echo.
server\.venv\Scripts\python.exe server\server.py
pause
