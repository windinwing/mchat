@echo off
setlocal
set MCHAT=%USERPROFILE%\dev\mchat
set LOGDIR=%USERPROFILE%\dev\gamecenter-agent
set LOG=%LOGDIR%\agent.log
set ERR=%LOGDIR%\agent.err.log

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

cd /d "%MCHAT%"
echo [%date% %time%] starting agent>>"%LOG%"

where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 ops\scripts\gamecenter-windows-build-agent.py 1>>"%LOG%" 2>>"%ERR%"
    goto :done
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
    python ops\scripts\gamecenter-windows-build-agent.py 1>>"%LOG%" 2>>"%ERR%"
    goto :done
)

where python3 >nul 2>&1
if %ERRORLEVEL%==0 (
    python3 ops\scripts\gamecenter-windows-build-agent.py 1>>"%LOG%" 2>>"%ERR%"
    goto :done
)

echo [%date% %time%] ERROR: no Python (py/python/python3)>>"%LOG%"
exit /b 1

:done
echo [%date% %time%] agent exited %ERRORLEVEL%>>"%LOG%"
endlocal
