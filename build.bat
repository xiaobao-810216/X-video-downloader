@echo off
echo 开始打包流光下载器...
echo.

REM 检查是否安装了 PyInstaller
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo 正在安装 PyInstaller...
    pip install PyInstaller
    echo.
)

REM 清理之前的构建文件
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
echo 已清理旧的构建文件

REM 开始打包
echo 正在打包应用程序...
pyinstaller build_app.spec

REM 检查打包结果
if exist "dist\流光下载器\流光下载器.exe" (
    echo.
    echo ========================================
    echo 打包成功！
    echo 可执行文件位置: dist\流光下载器\流光下载器.exe
    echo ========================================
    echo.
    
    REM 询问是否打开文件夹
    set /p choice="是否打开输出文件夹? (y/n): "
    if /i "%choice%"=="y" (
        start "" "dist\流光下载器"
    )
) else (
    echo.
    echo ========================================
    echo 打包失败！请检查错误信息。
    echo ========================================
)

pause
