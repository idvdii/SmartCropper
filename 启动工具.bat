@echo off
chcp 65001 >nul
echo 正在启动裁剪工具...

python run.py

if %errorlevel% neq 0 (
    echo.
    echo 程序发生错误，请检查上方报错信息。
    pause
)