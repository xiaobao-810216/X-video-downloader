@echo off
echo 🎬 流光下载器 - 清除缓存启动
echo.

echo 🔄 正在关闭可能存在的旧进程...
taskkill /f /im python.exe >nul 2>&1
timeout /t 2 >nul

echo 🗑️ 清除浏览器缓存提示：
echo    请在浏览器中按 Ctrl+Shift+Delete 清除缓存
echo    或者按 Ctrl+F5 强制刷新页面
echo.

echo 🚀 启动流光下载器（新端口：5001）...
python app.py

pause
