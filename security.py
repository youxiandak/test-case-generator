"""
安全防护模块
用于防止恶意攻击和滥用
"""

import time
from typing import Dict, Tuple
from functools import wraps


# ============================================================
# 频率限制配置
# ============================================================

# 订单查询限制：每个用户每分钟最多查询5次
ORDER_QUERY_LIMIT_PER_MINUTE = 5

# 激活尝试限制：每个IP每10分钟最多尝试10次
ACTIVATION_ATTEMPT_LIMIT = 10

# 订单查询缓存（避免重复查询相同订单）
ORDER_QUERY_CACHE: Dict[str, Tuple[float, dict]] = {}
ORDER_QUERY_CACHE_TTL = 300  # 5分钟

# 激活尝试记录
ACTIVATION_ATTEMPTS: Dict[str, Tuple[float, int]] = {}
ACTIVATION_WINDOW = 600  # 10分钟


# ============================================================
# 频率限制函数
# ============================================================

def check_rate_limit(identifier: str, limit: int, window: int) -> Tuple[bool, int]:
    """
    检查频率限制

    Args:
        identifier: 标识符（user_id、IP地址等）
        limit: 时间窗口内的最大次数
        window: 时间窗口（秒）

    Returns:
        (是否允许, 剩余秒数)
    """
    current_time = time.time()

    if identifier not in ACTIVATION_ATTEMPTS:
        ACTIVATION_ATTEMPTS[identifier] = (current_time, 1)
        return True, 0

    last_time, count = ACTIVATION_ATTEMPTS[identifier]

    # 如果时间窗口已过，重置计数
    if current_time - last_time > window:
        ACTIVATION_ATTEMPTS[identifier] = (current_time, 1)
        return True, 0

    # 检查是否超过限制
    if count >= limit:
        remaining = int(window - (current_time - last_time))
        return False, remaining

    # 增加计数
    ACTIVATION_ATTEMPTS[identifier] = (last_time, count + 1)
    return True, 0


def check_activation_rate_limit(user_id: int) -> Tuple[bool, str]:
    """
    检查激活尝试的频率限制

    Args:
        user_id: 用户ID

    Returns:
        (是否允许, 错误消息)
    """
    allowed, remaining = check_rate_limit(str(user_id), ACTIVATION_ATTEMPT_LIMIT, ACTIVATION_WINDOW)

    if not allowed:
        return False, f"❌ 激活尝试过于频繁，请等待 {remaining} 秒后再试。"

    return True, ""


# ============================================================
# 订单查询缓存
# ============================================================

def get_cached_order(order_id: str) -> dict | None:
    """
    获取缓存的订单信息

    Args:
        order_id: 订单号

    Returns:
        订单信息，如果不存在或已过期返回None
    """
    if order_id not in ORDER_QUERY_CACHE:
        return None

    timestamp, data = ORDER_QUERY_CACHE[order_id]

    # 检查是否过期
    if time.time() - timestamp > ORDER_QUERY_CACHE_TTL:
        del ORDER_QUERY_CACHE[order_id]
        return None

    return data


def cache_order(order_id: str, data: dict):
    """
    缓存订单信息

    Args:
        order_id: 订单号
        data: 订单数据
    """
    ORDER_QUERY_CACHE[order_id] = (time.time(), data)


# ============================================================
# 输入验证
# ============================================================

def sanitize_input(text: str, max_length: int = 10000) -> str:
    """
    清理输入文本

    Args:
        text: 输入文本
        max_length: 最大长度

    Returns:
        清理后的文本
    """
    if not text:
        return ""

    # 截断到最大长度
    text = text[:max_length]

    # 移除潜在的恶意字符（简单过滤）
    dangerous_chars = ['<', '>', '\x00', '\x01', '\x02', '\x03', '\x04', '\x05']
    for char in dangerous_chars:
        text = text.replace(char, '')

    return text.strip()


def validate_email(email: str) -> bool:
    """
    验证邮箱格式

    Args:
        email: 邮箱地址

    Returns:
        是否有效
    """
    if not email or '@' not in email:
        return False

    parts = email.split('@')
    if len(parts) != 2:
        return False

    local, domain = parts

    if not local or not domain:
        return False

    if '.' not in domain:
        return False

    return len(domain) > 3


def validate_password(password: str) -> Tuple[bool, str]:
    """
    验证密码强度

    Args:
        password: 密码

    Returns:
        (是否有效, 错误消息)
    """
    if not password:
        return False, "密码不能为空"

    if len(password) < 8:
        return False, "密码长度至少为8位"

    if len(password) > 100:
        return False, "密码长度不能超过100位"

    # 检查是否包含至少一个字母和一个数字
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)

    if not has_letter:
        return False, "密码必须包含至少一个字母"

    if not has_digit:
        return False, "密码必须包含至少一个数字"

    return True, ""


# ============================================================
# 装饰器
# ============================================================

def rate_limit(limit: int = 5, window: int = 60):
    """
    频率限制装饰器

    Args:
        limit: 时间窗口内的最大次数
        window: 时间窗口（秒）
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 使用函数名 + 参数作为标识符
            identifier = f"{func.__name__}_{str(args)}_{str(kwargs)}"
            allowed, remaining = check_rate_limit(identifier, limit, window)

            if not allowed:
                return None, f"⏸️ 请求过于频繁，请等待 {remaining} 秒后再试。"

            return func(*args, **kwargs)
        return wrapper
    return decorator