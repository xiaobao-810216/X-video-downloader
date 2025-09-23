# errors.py - simple error classification utility
from __future__ import annotations

# Minimal heuristic mapping; can be expanded
_ERROR_MAP = [
    ("HTTP Error 404", ("not_found", "资源不存在/已被删除")),
    ("HTTP Error 401", ("unauthorized", "需要登录授权 (401)")),
    ("HTTP Error 403", ("forbidden", "访问被拒绝/权限不足 (403)")),
    ("429", ("rate_limited", "请求过于频繁，被限流 (429)")),
    ("This video is private", ("private", "视频是私有的")),
    ("Sign in to confirm", ("age_check", "需要登录验证年龄/身份")),
    ("members-only content", ("members_only", "频道会员专属内容")),
    ("not available in your country", ("geo_block", "区域限制，尝试更换节点")),
    ("IncompleteRead", ("network", "网络不稳定/连接被重置")),
    ("timed out", ("timeout", "网络超时")),
    ("Unable to extract", ("extract_fail", "解析失败 (可能版本过旧)")),
]

def classify_error(msg: str):
    if not msg:
        return None, "未知错误"
    low = msg.lower()
    for pat, (code, friendly) in _ERROR_MAP:
        if pat.lower() in low:
            return code, friendly
    # fallback: first line
    return None, msg.strip().split('\n')[0][:400]

__all__ = ["classify_error"]
