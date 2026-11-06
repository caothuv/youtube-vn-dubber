@echo off
REM update_server.bat — script cập nhật 1 chạm (Windows)
REM Cách chạy: server.py tự gọi script này rồi tắt.
REM   update_server.bat <duong-dan-zip-ban-moi> <thu-muc-cai-dat>
REM Việc làm:
REM   1. Chờ server cũ tắt hẳn (cổng 8000 trống)
REM   2. Sao lưu file cũ vào update_backup\<ngay-gio>\ (TRỪ cache, .env, custom_voices, config.json)
REM   3. Giải nén zip mới đè lên thư mục cài đặt (giữ lại cache, .env, custom_voices, config.json)
REM   4. Ghi version.json mới + chạy lại START_WINDOWS.bat
setlocal EnableDelayedExpansion
set "ZIP=%~1"
set "ROOT=%~2"
if "%ZIP%"=="" exit /b 1
if "%ROOT%"=="" exit /b 1
set "LOG=%ROOT%\update.log"
echo [%date% %time%] Bat dau cap nhat tu %ZIP% >> "%LOG%"

REM 1. Cho server cu 5 giay de tat han
timeout /t 5 /nobreak >nul

REM 2. Sao luu
for /f "tokens=1-4 delims=/ " %%a in ("%date%") do set "D=%%d%%b%%c"
for /f "tokens=1-2 delims=: " %%a in ("%time%") do set "T=%%a%%b"
set "BACKUP=%ROOT%\update_backup\%D%_%T%"
mkdir "%BACKUP%" 2>nul
robocopy "%ROOT%\extension" "%BACKUP%\extension" /E /NFL /NDL /NJH /NJS >nul
robocopy "%ROOT%\server" "%BACKUP%\server" /E /NFL /NDL /NJH /NJS /XD cache custom_voices /XF .env config.json server.log >nul
copy "%ROOT%\START_WINDOWS.bat" "%BACKUP%\" >nul 2>&1
copy "%ROOT%\version.json" "%BACKUP%\" >nul 2>&1
echo [%date% %time%] Da sao luu vao %BACKUP% >> "%LOG%"

REM 3. Giai nen zip moi (ghi de, giu lai cache/.env/custom_voices/config.json)
powershell -NoProfile -Command ^
  "Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '%ROOT%\_update_tmp' -Force"
if errorlevel 1 (
  echo [%date% %time%] LOI: khong giai nen duoc zip moi >> "%LOG%"
  exit /b 1
)
REM Neu zip co thu muc goc duy nhat thi xuong 1 cap
for /d %%d in ("%ROOT%\_update_tmp\*") do (
  if exist "%%d\version.json" set "SRC=%%d"
)
if not defined SRC set "SRC=%ROOT%\_update_tmp"
robocopy "%SRC%\extension" "%ROOT%\extension" /E /NFL /NDL /NJH /NJS >nul
robocopy "%SRC%\server" "%ROOT%\server" /E /NFL /NDL /NJH /NJS /XD cache custom_voices /XF .env config.json version.json server.log >nul
copy "%SRC%\START_WINDOWS.bat" "%ROOT%\" >nul 2>&1
copy "%SRC%\version.json" "%ROOT%\" >nul 2>&1
copy "%SRC%\version.json" "%ROOT%\server\version.json" >nul 2>&1
copy "%SRC%\README_HUONG_DAN.md" "%ROOT%\" >nul 2>&1
copy "%SRC%\CHANGELOG.md" "%ROOT%\" >nul 2>&1
rmdir /S /Q "%ROOT%\_update_tmp"
del "%ZIP%" 2>nul
echo [%date% %time%] Da thay file moi xong >> "%LOG%"

REM 4. Khoi dong lai server
echo [%date% %time%] Khoi dong lai server... >> "%LOG%"
start "" /min "%ROOT%\START_WINDOWS.bat"
echo [%date% %time%] Cap nhat xong. >> "%LOG%"
exit /b 0
