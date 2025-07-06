@echo off
chcp 65001 >nul
echo.
echo ========================================
echo 🚀 流光下载器 - 自动分发打包工具
echo ========================================
echo.

REM 检查是否存在构建好的应用
if not exist "dist\流光下载器\流光下载器.exe" (
    echo ❌ 错误：未找到构建好的应用程序
    echo 请先运行 build.bat 进行构建
    pause
    exit /b 1
)

REM 获取当前日期作为版本号
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "YY=%dt:~2,2%" & set "YYYY=%dt:~0,4%" & set "MM=%dt:~4,2%" & set "DD=%dt:~6,2%"
set "version=%YYYY%%MM%%DD%"

echo 📦 正在准备分发包...
echo 版本号: v%version%

REM 创建分发目录
if exist "release" rmdir /s /q "release"
mkdir "release"

REM 复制应用文件
echo.
echo 📁 复制应用文件...
xcopy "dist\流光下载器" "release\流光下载器_v%version%" /E /I /Q /Y
if errorlevel 1 (
    echo ❌ 复制文件失败
    pause
    exit /b 1
)

REM 复制说明文件
echo 📄 复制文档文件...
copy "分发指南.md" "release\流光下载器_v%version%\使用说明.md" >nul
if exist "README.md" copy "README.md" "release\流光下载器_v%version%\" >nul

REM 创建用户使用说明
echo 📝 创建用户说明文件...
(
echo 🎬 流光下载器 v%version%
echo.
echo 📖 使用方法：
echo 1. 双击运行 "流光下载器.exe"
echo 2. 程序会自动在浏览器中打开
echo 3. 输入视频链接即可下载
echo.
echo 📁 文件说明：
echo - 流光下载器.exe: 主程序
echo - _internal/: 运行时依赖（请勿删除）
echo - 使用说明.md: 详细使用指南
echo.
echo ⚠️ 注意事项：
echo - 请保持整个文件夹完整，不要单独移动 exe 文件
echo - 下载的视频和字幕会保存在桌面
echo - 如需下载需要登录的网站内容，请添加 cookies.txt
echo.
echo 🐛 遇到问题？
echo 查看桌面上的"流光下载器日志"文件夹获取错误信息
echo.
echo 版本日期: %YYYY%-%MM%-%DD%
) > "release\流光下载器_v%version%\🎬 使用说明.txt"

REM 计算文件夹大小
echo.
echo 📊 分析分发包大小...
for /f "tokens=3" %%a in ('dir "release\流光下载器_v%version%" /s /-c ^| find "个文件"') do set "filesize=%%a"
for /f "tokens=1 delims=," %%b in ("!filesize!") do set "size_mb=%%b"
set /a "size_mb=!size_mb!/1024/1024"

echo 📦 文件夹大小: 约 %size_mb% MB

REM 创建压缩包
echo.
echo 🗜️ 创建压缩包...
set "zipname=流光下载器_v%version%.zip"

REM 尝试使用 PowerShell 创建压缩包
powershell -command "Compress-Archive -Path 'release\流光下载器_v%version%\*' -DestinationPath 'release\%zipname%' -Force" 2>nul
if errorlevel 1 (
    echo ⚠️ PowerShell 压缩失败，跳过压缩步骤
    echo 📁 可手动压缩 release\流光下载器_v%version% 文件夹
) else (
    echo ✅ 压缩包创建成功: %zipname%
    
    REM 获取压缩包大小
    for %%i in ("release\%zipname%") do set "zipsize=%%~zi"
    set /a "zipsize_mb=!zipsize!/1024/1024"
    echo 📦 压缩包大小: %zipsize_mb% MB
)

echo.
echo ========================================
echo ✅ 分发包创建完成！
echo ========================================
echo.
echo 📂 分发内容位置:
echo   文件夹: release\流光下载器_v%version%\
if exist "release\%zipname%" echo   压缩包: release\%zipname%
echo.
echo 🚀 分发建议:
echo   - 上传压缩包到网盘/GitHub Releases
echo   - 提供详细的使用说明
echo   - 说明系统要求（Windows 64位）
echo.

REM 询问是否打开文件夹
set /p choice="是否打开分发文件夹? (y/n): "
if /i "%choice%"=="y" (
    start "" "release"
)

echo.
echo 🎉 打包完成！感谢使用流光下载器！
pause
