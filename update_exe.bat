@echo off
chcp 65001 >nul
color 0A
cls

echo ========================================================
echo          正在启动全自动打包流程...
echo ========================================================

:: 1. 检查有没有安装 pyinstaller (防止报错)
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 检测到未安装 Pyinstaller，正在尝试自动安装...
    pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
)

:: 2. 开始打包 (这里写你的脚本名，如果是 a.py 就不用改)
echo.
echo [1/3] 正在编译代码 a.py -> SmartCropper.exe ...
echo       (这可能需要几秒钟，请耐心等待)
pyinstaller --onefile --noconsole --name="SmartCropper" run.py

:: 检查打包是否出错
if %errorlevel% neq 0 (
    color 0C
    echo.
    echo ========================================================
    echo [错误] 打包失败！请检查 Python 代码是否有语法错误。
    echo ========================================================
    pause
    exit
)

:: 3. 自动提取并覆盖
echo.
echo [2/3] 正在提取新文件并覆盖旧版...
if exist "dist\SmartCropper.exe" (
    move /y "dist\SmartCropper.exe" ".\SmartCropper.exe" >nul
) else (
    echo [错误] 找不到生成的文件，奇怪...
    pause
    exit
)

:: 4. 自动清理垃圾 (build文件夹, dist文件夹, spec文件)
echo.
echo [3/3] 正在清理临时垃圾文件...
rmdir /s /q build
rmdir /s /q dist
del /q SmartCropper.spec
del /q __pycache__ 2>nul

echo.
echo ========================================================
echo               恭喜！更新成功！
echo       现在的 SmartCropper.exe 已经是最新版了
echo ========================================================
echo.
pause