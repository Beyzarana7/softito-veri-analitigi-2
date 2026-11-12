@echo off
setlocal
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
if not exist ".venv\Scripts\python.exe" (
 echo Once KURULUM.bat dosyasini calistirin. README.md dosyasini inceleyin.
 pause
 exit /b 1
)
cd uygulama
"..\.venv\Scripts\python.exe" -B -m streamlit run app.py --server.address 127.0.0.1 --server.port 8508 --browser.gatherUsageStats false
endlocal
