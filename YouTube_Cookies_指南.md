# YouTube Cookies 导出指南

当遇到 "Sign in to confirm you're not a bot" 错误时，需要导出浏览器 cookies。

## 方法一：自动从浏览器提取（推荐）

程序已经配置自动从 Chrome 浏览器提取 cookies，请：

1. 确保你在 Chrome 浏览器中已登录 YouTube
2. 重新启动流光下载器
3. 程序会自动尝试从 Chrome 提取 cookies

## 方法二：手动导出 cookies.txt

如果自动提取失败，请手动导出：

### 使用浏览器扩展（最简单）

1. 安装 Chrome 扩展：[Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)

2. 打开 YouTube 网站，确保已登录

3. 点击扩展图标，选择 "Export cookies.txt"

4. 将下载的 `cookies.txt` 文件放到流光下载器目录

### 使用开发者工具（手动）

1. 在 Chrome 中打开 YouTube，按 F12 打开开发者工具

2. 转到 Application → Storage → Cookies → https://www.youtube.com

3. 复制所有 cookies 并按 Netscape 格式保存为 `cookies.txt`

## 方法三：使用其他浏览器

如果你主要使用其他浏览器，修改程序中的浏览器类型：
- Firefox: `--cookies-from-browser firefox`
- Edge: `--cookies-from-browser edge`
- Safari: `--cookies-from-browser safari`

## 测试是否成功

导出 cookies 后，在命令行测试：
```bash
yt-dlp --cookies cookies.txt "https://www.youtube.com/watch?v=视频ID"
```

如果命令行能正常下载，说明 cookies 设置成功。

## 注意事项

- cookies 有时效性，需要定期更新
- 不要分享你的 cookies 文件，包含个人信息
- 确保 cookies.txt 文件编码为 UTF-8
