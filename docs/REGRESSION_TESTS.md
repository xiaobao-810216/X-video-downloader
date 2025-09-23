# 流光下载器 v3.0.0 回归测试清单 (REGRESSION TESTS)

> 目标：在每次发版前 10~15 分钟内快速验证核心能力未回退。
> 覆盖维度：任务创建/取消、格式/质量选择、字幕、音频补救、Cookies 策略、SSE 稳定性、路径与合并。

---
## 0. 准备
- 使用“全新解压目录”（不要覆盖旧文件）。
- 确认 `build_meta.json` commit 与待发布 tag 一致。
- 浏览器 Ctrl+F5 强制刷新，页面显示 UI_VERSION = 3.0.0。

环境建议：普通公网网络（无全局代理）+ 可访问目标视频站点。

---
## 1. 基础任务（公开视频 + 默认 best）
| 步骤 | 期望 | 结果 |
|------|------|------|
| 输入公开视频 URL，质量选 best | 任务进入 probe -> download -> merge -> finished | PASS/FAIL |
| 合成文件存在且可播放 | 有视频+音频 | PASS/FAIL |
| 日志无异常 Traceback | 仅普通 info | PASS/FAIL |

检查点：无“无音频”假阳性；日志含 `[audio-fallback]` 时最终仍成功。

---
## 2. 高分辨率任务（4K / 8K）
| 步骤 | 期望 | 结果 |
|------|------|------|
| 选择 best4k（视频确实 >=2160p） | 下载成功，合并正常 | PASS/FAIL |
| 若源站仅 1440p，显示自动降级 | 日志提示选取实际最高 | PASS/FAIL |
| 选择 best8k（若无 8K） | 回退到最高可用分辨率，不报错 | PASS/FAIL |

检查点：日志中格式选择表达式生效，未抛异常。

---
## 3. 字幕-only 模式
| 步骤 | 期望 | 结果 |
|------|------|------|
| 勾选“字幕 only”并开始 | 只生成字幕文件 (srt) | PASS/FAIL |
| 文件编码 UTF-8 可读 | 内容行被合并（无多余空行） | PASS/FAIL |
| UI 显示状态 finished | 无多余视频临时文件残留 | PASS/FAIL |

---
## 4. Cookies 策略切换
| 场景 | 操作 | 期望 | 结果 |
|------|------|------|------|
| 匿名模式 | 无 cookies.txt | `/diag/cookie_strategy` 显示 anonymous | PASS/FAIL |
| 文件模式 | 放置有效 cookies.txt | strategy = file | PASS/FAIL |
| 强制浏览器 | `set LUMINA_FORCE_BROWSER_COOKIES=1` 启动 | strategy = browser-forced 或 fallback anonymous | PASS/FAIL |
| 禁用 cookies | `set LUMINA_DISABLE_BROWSER_COOKIES=1` | strategy = anonymous | PASS/FAIL |

检查点：不同策略切换不会导致启动崩溃；任务仍可在匿名模式下载公开视频。

---
## 5. 任务取消 & 并行
| 步骤 | 期望 | 结果 |
|------|------|------|
| 启动任务 A（较大视频），下载中点击取消 | 状态变为 canceled，后台不再追加日志 | PASS/FAIL |
| 立即启动任务 B | B 正常运行，不受 A 影响 | PASS/FAIL |
| 同时启动 2~3 个任务 | UI 均能更新进度（或轮询列表） | PASS/FAIL |

---
## 6. 多组件合并与音频补救
| 场景 | 期望 | 结果 |
|------|------|------|
| 触发 `[component-merge]` 日志 | 最终合并生成单一媒体文件 | PASS/FAIL |
| 触发 `[audio-fallback]` | 重试后成功合并音频 | PASS/FAIL |
| 强行断网中途再恢复 | 任务可能失败 / 或重启后新任务可成功 | PASS/FAIL |

---
## 7. SSE / UI 稳定性
| 步骤 | 期望 | 结果 |
|------|------|------|
| 任务进行时刷新页面 | 不崩溃，但刷新后需重新发起任务（当前版本不做恢复） | PASS/FAIL |
| 打开浏览器控制台无 CORS 报错 | 仅普通日志 | PASS/FAIL |
| SSE 连接无 4xx/5xx | Network 显示 200 & 持续 open | PASS/FAIL |

---
## 8. 路径 / 文件系统
| 场景 | 期望 | 结果 |
|------|------|------|
| 下载目录含中文 | 成功写入 | PASS/FAIL |
| 桌面在 OneDrive 重定向 | 能创建输出文件 | PASS/FAIL |
| 同一个视频重复下载 | 当前策略覆盖（确认行为） | PASS/FAIL |

---
## 9. 失败用例验证（负向）
| 用例 | 期望 | 结果 |
|------|------|------|
| 输入非法 URL | UI 明确错误，任务结束状态 error | PASS/FAIL |
| 输入受会员限制视频（匿名模式） | 失败并提示权限/登录限制 | PASS/FAIL |
| 端口冲突（占用 5000） | 启动失败或需指定其他端口 | PASS/FAIL |

---
## 10. 结果审计
- 统计本次测试 PASS/FAIL 数量：`X / 总数`。
- 若 FAIL > 2，则建议暂停发布或补充说明。
- 将“失败截图 + app.log + build_meta.json + cookies 策略输出”归档。

---
## 11. 建议自动化（后续）
| 目标 | pytest 伪代码要点 |
|------|-------------------|
| 健康探测 | GET /diag/version -> 200 & 包含 commit |
| 任务成功 | POST /api/stream_task -> 监听 SSE -> 最终 status=finished |
| 任务取消 | 发起 -> 立即 /api/tasks/<id>/cancel -> SSE 最终 canceled |
| Cookies 切换 | 设置 env 启动 -> 调 /diag/cookie_strategy |

---
## 12. 附录：快速命令（可选）
```powershell
# 查看当前 commit
git rev-parse --short HEAD
# 列出最近 10 条提交
git --no-pager log --oneline -n 10
```

---
完成以上用例后，可将表格填好随发布归档，便于下个版本对比。欢迎继续完善此清单。
