@echo off
setlocal
cd /d "%~dp0"
py -3.14 -m venv .venv
if errorlevel 1 goto hata
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto hata
echo Kurulum tamamlandi. BASLAT.bat ile acabilirsiniz.
pause
exit /b 0
:hata
echo Kurulum basarisiz. Python 3.14 ve internet baglantisini kontrol edin.
pause
exit /b 1
