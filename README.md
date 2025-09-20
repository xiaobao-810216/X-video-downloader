# 🎬 流光下载器 (X/Twitter Video Downloader)

[![下载最新版本](https://img.shields.io/github/v/release/xiaobao-810216/X-video-downloader?label=下载最新版本&color=blue)](https://github.com/xiaobao-810216/X-video-downloader/releases/latest)
[![GitHub stars](https://img.shields.io/github/stars/xiaobao-810216/X-video-downloader)](https://github.com/xiaobao-810216/X-video-downloader/stargazers)
[![License](https://img.shields.io/github/license/xiaobao-810216/X-video-downloader)](LICENSE)

## � 2025-09 重大更新 (计划版本: v3.0)
本次为向后不完全兼容升级，旧的 `/download` 流式端点已废弃 (410)。请所有脚本 / 前端插件 / 自动化集成尽快迁移。

### 新特性汇总
- 统一 SSE 接口：`/api/stream_task` 提供增量日志(`type=log`) + 状态快照(`type=status`)；支持取消、字幕-only、quality 动态映射。
- 任务体系重构：标准字段 (status / stage / progress / file_path / codecs)，支持 `/api/tasks` 快照与 `/api/tasks/<id>/cancel`。
- Cookies 策略革新：默认不再偷偷尝试浏览器；新增 `LUMINA_FORCE_BROWSER_COOKIES` / `LUMINA_DISABLE_BROWSER_COOKIES`；失败自动回退匿名，不再中止公共视频任务。
- 诊断端点：`/diag/cookie_strategy`、`/diag/version`、`/diag/raw_formats`、`/diag/yt` 提升可观测性与故障定位速度。
- 打包可靠性：修复 `_ctypes` / `libffi` 丢失导致启动失败；子进程窗口隐藏；构建写入 `build_meta.json`（含 commit / build_time）。
- 质量映射策略：best / best4k / best8k / fast / height<=X 统一服务端解释成 yt-dlp 表达式，前端更简洁。
- 字幕-only 优化：VTT→SRT 转换 & 行合并策略；进度直接反馈 100%。
- 日志精炼：仅在 FORCE 模式打印浏览器提取尝试；普通模式减少噪声。

### 升级快速检查清单
1. 替换所有对 `/download` 的调用为 `/api/stream_task` (GET SSE)。
2. SSE 解析逻辑：根据 JSON 的 `type` 分支 (log / status)，更新 UI 进度条与日志窗口。
3. 取消按钮使用 `POST /api/tasks/<id>/cancel`。
4. 字幕下载改为 `subtitles_only=true` 参数，无需独立代码路径。
5. 如果之前依赖浏览器自动 cookies，请显式导出 `cookies.txt` 或设置 `LUMINA_FORCE_BROWSER_COOKIES=1`。
6. 打包脚本更新后生成的目录应包含 `build_meta.json`；发布时附上该文件方便溯源。
7. 验证 `/diag/version` 与 `/diag/cookie_strategy` 正常返回，确保运行环境一致。

### API 变化摘要
| 旧 | 新 | 状态 |
|----|----|------|
| `/download` | `/api/stream_task` | 已废弃 (410) |
| (无) | `/diag/cookie_strategy` | 新增 |
| (无) | `/diag/version` | 新增 |

> 建议在创建 GitHub Release (v3.0) 时，将本节内容复制到 Release Notes，方便已有用户理解变更范围。

## �📥 快速下载

**🚀 一键下载打包版本（推荐）**

[⬇️ 下载 Windows 可执行文件](https://github.com/xiaobao-810216/X-video-downloader/releases/latest) - 无需安装Python，双击即用！

## 项目描述
一个功能强大的视频下载工具，支持多平台视频下载，包括：
- 🔥 X/Twitter 视频下载
- 📺 YouTube 视频/播放列表下载
- 🎵 字幕下载和处理
- 🚀 高性能多线程下载

## ✨ 主要特性
- ✅ 支持多平台视频下载（Twitter/X, YouTube等）
- ✅ 播放列表批量下载
- ✅ 多语言字幕下载和自动处理
- ✅ 实时下载进度显示
- ✅ 统一任务队列 + SSE 实时日志 (/api/stream_task)
- ✅ 现代化Web界面
- ✅ 自动质量选择（1080p/720p）
- ✅ 断点续传支持
- ✅ 桌面直接保存

> 新版 (2025-09) 已弃用旧 `/download` 流式端点，前端与所有自动化集成请改用 `/api/stream_task` 与任务 API。

## 🛠️ 技术栈
- Python 3.10+
- Flask Web框架
- yt-dlp (youtube-dl的增强版)
- FFmpeg 视频处理
- Aria2 多线程下载
- HTML5 + JavaScript 前端

## 🚀 快速开始

### 方式一：直接下载可执行文件（推荐）
1. 前往 [Releases 页面](https://github.com/xiaobao-810216/X-video-downloader/releases/latest)
2. 下载最新的 `.exe` 文件
3. 双击运行即可使用

### 方式二：从源码运行

### 前提条件
- Python 3.10 或更高版本
- pip
- FFmpeg

### 克隆仓库
```bash
git clone https://github.com/xiaobao-810216/X-video-downloader.git
cd X-video-downloader
```

### 创建虚拟环境
```bash
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux
```

### 安装依赖
```bash
pip install -r requirements.txt
```

### 运行应用
```bash
python app.py
```

访问 `http://localhost:5001`

## 📖 使用方法
1. 🌐 打开浏览器访问 `http://localhost:5001`
2. 📋 粘贴视频链接（支持Twitter/X, YouTube等）
3. ⚙️ 选择下载质量和字幕选项
4. 🎯 点击下载，视频将自动保存到桌面
5. 📊 实时查看下载进度

### 🔄 新版任务 & SSE 说明

### 🍪 Cookies 使用策略 (YouTube 等)

默认行为：如果同目录存在 `cookies.txt` 则使用；否则不会自动尝试浏览器提取（避免 Chrome 数据库复制失败导致任务中止）。

可用环境变量：

| 变量 | 值 | 作用 |
|------|----|------|
| `LUMINA_FORCE_BROWSER_COOKIES` | 1/true | 在缺少 `cookies.txt` 时强制尝试 `--cookies-from-browser chrome` |
| `LUMINA_DISABLE_BROWSER_COOKIES` | 1/true | 禁止任何浏览器自动提取（即使设置了 FORCE 也不执行） |

生效优先级：`cookies.txt` > DISABLE > FORCE > none。

什么时候需要 cookies.txt：
- 年龄限制 / 会员专属 / 需登录的视频。
- 需要获取某些自动字幕轨但匿名无法访问时。

什么时候不需要：
- 公共/普通可直接访问的视频（绝大多数 YouTube 公开内容）。

如何获取 `cookies.txt`：
1. 浏览器安装任意支持导出 Cookie 的插件（例如 “Get cookies.txt”）。
2. 登录目标网站（YouTube），进入任一视频页。
3. 使用插件导出为 `cookies.txt`，保存到程序根目录。
4. 重新启动应用并在启动日志中确认 `[PROBE] 使用cookies.txt文件`。

诊断辅助：访问 `http://127.0.0.1:5001/diag/cookie_strategy` 查看当前策略判定。

失败回退：若 FORCE 模式下浏览器提取失败（Chrome 数据库锁定），程序会记录警告并回退为匿名模式继续，不再直接终止公共视频任务。

后端围绕 TaskManager 暴露统一接口：

| 场景 | 端点/方式 | 说明 |
|------|-----------|------|
| 创建并实时观看下载 | `GET /api/stream_task?url=...&mode=merged&quality=best` | SSE，包含增量日志(type=log) + 状态(type=status) |
| 查询所有任务快照 | `GET /api/tasks` | 返回当前内存中的任务列表 |
| 查询单任务 | `GET /api/tasks/<task_id>` | 结构化字段（progress, status, stage 等） |
| 取消任务 | `POST /api/tasks/<task_id>/cancel` | 终止运行中的 yt-dlp / ffmpeg 子进程 |
| 清理终态任务 | `POST /api/tasks/cleanup` | 支持 max_keep / remove_active 参数 |
| （已弃用）旧流式下载 | `/download` | 现返回 410 JSON: endpoint_deprecated |

#### /api/stream_task 参数
| 参数 | 示例 | 说明 |
|------|------|------|
| url | https://www.youtube.com/watch?v=xxxx | 必填，视频或支持站点链接 |
| mode | merged / video_only / audio_only / subtitles | 下载模式（subtitles 会自动设置 subtitles_only=true） |
| quality | best / best4k / best8k / height<=1080 / height<=720 / fast | 自适应格式选择器映射到 yt-dlp 的格式表达式 |
| subtitles | en,zh-Hans | 需要的字幕语言（逗号分隔） |
| subtitles_only | true/false | 仅字幕，不下载媒体轨 |

#### SSE 事件格式
```
data: {"type":"log","line":"[download]  35.4% ..."}
data: {"type":"status","task_id":"...","status":"downloading","stage":"downloading","progress":35.4,"file_path":null}
data: {"type":"status", ... status=finished, progress=100.0 }
data: {"event":"end"}
```

字段含义：
- status: queued / downloading / merging / finished / error / canceled
- stage: 细分阶段（可能与 status 相同）
- progress: (0~100) 百分比，来自解析 yt-dlp `[download]` 行
- file_path: 最终合并文件或当前已确定输出文件路径
- vcodec/acodec/width/height/filesize: 完成或阶段性探测后填充

#### 质量（quality）映射策略
前端/调用方传入的 `quality` 会在后端转换为 yt-dlp 选择表达式：

| 输入 | 格式选择器示意 | 说明 |
|------|----------------|-----|
| best | `bv[height<=?1080]+ba/best[height<=?1080]/b` | 优先 1080p 及以下组合 |
| best4k | `bv[height<=?2160]+ba/best[height<=?2160]/b` | 4K 向下兼容 |
| best8k | `bv[height<=?4320]+ba/best[height<=?4320]/b` | 8K 向下兼容 |
| fast | `bv[height<=?720]+ba/best[height<=?720]/b` | 强制限制 720p 及以下加速 |
| height<=X | `bv[height<=?X]+ba/best[height<=?X]/b` | 自定义限制 |
| video_only + best... | 只选 `bestvideo[...]` | 无音频轨 |
| audio_only | `bestaudio/best` | 若需要容器统一由 ffmpeg 处理 |

#### 字幕下载模式
发起：
```
GET /api/stream_task?url=...&subtitles=zh-Hans&subtitles_only=true
```
逻辑：
1. 使用 `--skip-download --write-subs/--write-auto-subs` 提取字幕
2. vtt → srt 转换并合并多行对话为单行（便于阅读）
3. progress 直接快进到 100%（字幕大小通常很小）

#### 取消任务
```
POST /api/tasks/<task_id>/cancel
```
标记任务为 canceled 并 kill 对应子进程；SSE 端收到 status= canceled 后会终止。

#### 常用错误与提示
| 错误 | 含义 | 建议 |
|------|------|------|
| endpoint_deprecated | 访问了旧 /download | 改用 /api/stream_task |
| 需要登录验证 | YouTube 需要 cookies | 放置 `cookies.txt` 同目录 |
| 请求过于频繁 | 429/限流 | 等待或换网络 / VPN |
| 区域限制 | geo block | 使用 `--geo-bypass` (自动) 或切换出口 |

### 🧪 示例 (curl)
```
curl -N "http://127.0.0.1:5001/api/stream_task?url=...&mode=merged&quality=best"
```
可直接在终端观察 SSE 行（每个 data: 块）。

## 🎯 支持的网站
- Twitter/X (包括私有视频)
- YouTube (单个视频和播放列表)
- 更多平台持续添加中...

## 📱 截图展示
*界面截图即将添加*

## 💝 支持开发

如果这个项目对您有帮助，欢迎打赏支持开发者！

<div align="center">
<img src="donate_qr.png" alt="支付宝/微信打赏" width="300">
<br>
<em>扫码打赏 ❤️</em>
</div>

## 🔄 版本历史
- **v1.0** - 初始发布，基础下载功能
- **v2.0** - 新增字幕下载、播放列表支持、界面美化
- **v3.0 (2025-09)** - 统一 `/api/stream_task` SSE、废弃 `/download`、新增任务/取消接口、可观测诊断端点、Cookies 策略重写、构建元数据与打包稳定性提升

## ⚖️ 许可证
MIT License

## ⚠️ 免责声明
本工具仅供学习和个人使用，请遵守相关网站的服务条款，尊重版权。下载的内容请勿用于商业用途。

## 🤝 贡献
欢迎提交 Issue 和 Pull Request！

### 开发建议
- 避免再调用 `/download`，它只返回 410。
- 新增进度字段或速度统计：在 `tasks.py` 的 `run_once` 中解析 `[download]` 行扩展 Task 模型，然后在 `/api/stream_task` SSE 输出。
- 若要支持前端文件打开，可新增后端路由返回 `file://` 风格或直接调用操作系统（Windows explorer）。

### 调试工具
| 路由 | 用途 |
|------|------|
| `/diag/routes` | 查看已注册路由 |
| `/diag/yt?url=...` | 快速诊断 YouTube 解析和 cookies 情况 |
| `/diag/raw_formats?url=...` | 列出原始格式供分析最高分辨率 |
| `/api/tasks` | 当前任务快照 |
| `/api/tasks/<id>` | 单任务详情 |
| `/api/tasks/<id>/log` | 增量日志（手动轮询调试） |

### 目录与输出
- 默认下载目录由 `config.DOWNLOAD_DIR` 控制；若出现两个桌面子目录，请统一配置并清理旧残留。
- 合并后的文件如果容器不兼容（不同编码组合），兜底为 `.mkv`。

### 升级指南 (旧版本迁移)
1. 前端不再使用 `/download` SSE。
2. 将所有进度 UI 改为解析 `type=status` & `type=log`。
3. 质量选项映射改为发送 best / best4k / best8k / height<=数字。
4. 字幕按钮改为 `subtitles_only=true` 参数而非单独实现。
5. 可定期调用 `/api/tasks/cleanup` 减少内存占用。

## 📞 联系作者
如有问题或建议，欢迎通过 GitHub Issue 联系。

---
<div align="center">
⭐ 如果这个项目对您有帮助，请给个 Star 支持一下！ ⭐
</div>
