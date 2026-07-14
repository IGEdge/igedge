@echo off
rem Scarica dal Raspberry i dati del sampler dentro il repo locale.
rem Uso:  pull-data.bat            (default pi@raspberrypi.local, repo ~/ig-trading)
rem       set PI=pi@192.168.1.42 && pull-data.bat
setlocal
if "%PI%"=="" set PI=pi@raspberrypi.local
if "%PIDIR%"=="" set PIDIR=ig-trading
set ROOT=%~dp0..\..

echo Scarico da %PI%:%PIDIR% ...
scp "%PI%:%PIDIR%/data/research/skew_samples.csv" "%ROOT%\data\research\skew_samples.csv"
if errorlevel 1 echo ERRORE: skew_samples.csv non scaricato (Pi acceso? SSH ok? host giusto?) & exit /b 1
scp "%PI%:%PIDIR%/logs/sampler.log" "%ROOT%\logs\sampler-pi.log"

echo.
echo OK. Verdetto del gate:
python "%ROOT%\scripts\sample_skew_us500.py" --report
endlocal
