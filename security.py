"""
安全防护模块
用于防止恶意攻击和滥用
"""

import time
import re
import hashlib
import logging
from typing import Dict, Tuple, Optional
from functools import wraps


# ============================================================
# 频率限制配置
# ============================================================

# 订单查询限制：每个用户每分钟最多查询5次
ORDER_QUERY_LIMIT_PER_MINUTE = 5

# 激活尝试限制：每个IP每10分钟最多尝试10次
ACTIVATION_ATTEMPT_LIMIT = 10

# 登录尝试限制：每个IP每5分钟最多尝试5次，每个账号每15分钟最多3次
LOGIN_ATTEMPT_LIMIT_PER_IP = 5
LOGIN_WINDOW_PER_IP = 300  # 5分钟
LOGIN_ATTEMPT_LIMIT_PER_USER = 3
LOGIN_WINDOW_PER_USER = 900  # 15分钟

# 订单查询缓存（避免重复查询相同订单）
ORDER_QUERY_CACHE: Dict[str, Tuple[float, dict]] = {}
ORDER_QUERY_CACHE_TTL = 300  # 5分钟

# 激活尝试记录
ACTIVATION_ATTEMPTS: Dict[str, Tuple[float, int]] = {}
ACTIVATION_WINDOW = 600  # 10分钟

# 登录尝试记录
LOGIN_ATTEMPTS_IP: Dict[str, Tuple[float, int]] = {}  # IP -> (last_time, count)
LOGIN_ATTEMPTS_USER: Dict[str, Tuple[float, int]] = {}  # email -> (last_time, count)


# ============================================================
# 会话安全增强
# ============================================================

def generate_session_token(user_id: int, ip_address: str) -> str:
    """
    生成安全的会话令牌

    Args:
        user_id: 用户ID
        ip_address: 客户端IP

    Returns:
        会话令牌
    """
    import os
    import secrets

    # 使用用户ID、IP地址和时间戳生成令牌
    timestamp = str(int(time.time()))
    random_part = secrets.token_urlsafe(32)
    ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:16]

    return f"{user_id}:{timestamp}:{random_part}:{ip_hash}"


def validate_session_token(token: str, expected_user_id: int, ip_address: str) -> bool:
    """
    验证会话令牌的有效性

    Args:
        token: 会话令牌
        expected_user_id: 期望的用户ID
        ip_address: 当前IP地址

    Returns:
        是否有效
    """
    try:
        parts = token.split(':')
        if len(parts) != 4:
            return False

        user_id_str, timestamp, _, ip_hash = parts

        # 验证用户ID
        if int(user_id_str) != expected_user_id:
            return False

        # 验证IP哈希
        current_ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:16]
        if current_ip_hash != ip_hash:
            return False

        # 验证时间戳（24小时内有效）
        current_time = int(time.time())
        token_time = int(timestamp)
        if current_time - token_time > 86400:  # 24小时
            return False

        return True
    except:
        return False


# ============================================================
# 防暴力破解增强
# ============================================================

def check_login_attempts(identifier: str, limit: int, window: int, attempts_dict: dict) -> Tuple[bool, int]:
    """
    检查登录尝试次数

    Args:
        identifier: 标识符（IP或email）
        limit: 限制次数
        window: 时间窗口（秒）
        attempts_dict: 尝试记录字典

    Returns:
        (是否允许, 剩余秒数)
    """
    current_time = time.time()

    if identifier not in attempts_dict:
        attempts_dict[identifier] = (current_time, 1)
        return True, 0

    last_time, count = attempts_dict[identifier]

    # 如果时间窗口已过，重置计数
    if current_time - last_time > window:
        attempts_dict[identifier] = (current_time, 1)
        return True, 0

    # 检查是否超过限制
    if count >= limit:
        remaining = int(window - (current_time - last_time))
        return False, remaining

    # 增加计数
    attempts_dict[identifier] = (last_time, count + 1)
    return True, 0


def can_attempt_login(email: str, ip_address: str) -> Tuple[bool, str]:
    """
    检查是否可以尝试登录

    Args:
        email: 邮箱地址
        ip_address: IP地址

    Returns:
        (是否允许, 错误消息)
    """
    # 检查IP级别的限制
    ip_allowed, ip_remaining = check_login_attempts(
        ip_address,
        LOGIN_ATTEMPT_LIMIT_PER_IP,
        LOGIN_WINDOW_PER_IP,
        LOGIN_ATTEMPTS_IP
    )

    if not ip_allowed:
        return False, f"⏸️ 登录尝试过于频繁（IP级别），请等待 {ip_remaining} 秒后再试。"

    # 检查用户级别的限制
    user_allowed, user_remaining = check_login_attempts(
        email,
        LOGIN_ATTEMPT_LIMIT_PER_USER,
        LOGIN_WINDOW_PER_USER,
        LOGIN_ATTEMPTS_USER
    )

    if not user_allowed:
        return False, f"⏸️ 登录尝试过于频繁（账号级别），请等待 {user_remaining} 秒后再试。"

    return True, ""


def record_login_attempt(email: str, ip_address: str, success: bool = True):
    """
    记录登录尝试

    Args:
        email: 邮箱地址
        ip_address: IP地址
        success: 是否成功
    """
    current_time = time.time()

    # 记录IP尝试
    if ip_address in LOGIN_ATTEMPTS_IP:
        last_time, count = LOGIN_ATTEMPTS_IP[ip_address]
        LOGIN_ATTEMPTS_IP[ip_address] = (last_time, count + 1)
    else:
        LOGIN_ATTEMPTS_IP[ip_address] = (current_time, 1)

    # 记录用户尝试
    if email in LOGIN_ATTEMPTS_USER:
        last_time, count = LOGIN_ATTEMPTS_USER[email]
        LOGIN_ATTEMPTS_USER[email] = (last_time, count + 1)
    else:
        LOGIN_ATTEMPTS_USER[email] = (current_time, 1)


# 清理过期的登录尝试记录
def cleanup_old_login_attempts():
    """清理过期的登录尝试记录"""
    current_time = time.time()
    cutoff_time = current_time - 3600  # 1小时

    # 清理IP记录
    ips_to_remove = []
    for ip, (last_time, _) in LOGIN_ATTEMPTS_IP.items():
        if current_time - last_time > cutoff_time:
            ips_to_remove.append(ip)

    for ip in ips_to_remove:
        del LOGIN_ATTEMPTS_IP[ip]

    # 清理用户记录
    users_to_remove = []
    for email, (last_time, _) in LOGIN_ATTEMPTS_USER.items():
        if current_time - last_time > cutoff_time:
            users_to_remove.append(email)

    for email in users_to_remove:
        del LOGIN_ATTEMPTS_USER[email]


# 定期清理
import atexit
atexit.register(cleanup_old_login_attempts)

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

def sanitize_input(text: str, max_length: int = 10000, input_type: str = "general") -> str:
    """
    增强的输入清理和验证

    Args:
        text: 输入文本
        max_length: 最大长度
        input_type: 输入类型（general, email, password, requirement, activation_code）

    Returns:
        清理后的文本，如果无效返回空字符串
    """
    if not text:
        return ""

    original_text = text
    text = str(text)  # 确保是字符串

    # 长度检查
    if len(text) > max_length:
        text = text[:max_length]
        logger.warning(f"输入被截断（类型：{input_type}，原始长度：{len(original_text)}）")

    # 根据输入类型进行不同的清理
    if input_type == "email":
        # 邮箱地址清理
        text = text.strip()
        # 移除可能的恶意内容
        text = re.sub(r'<[^>]*>', '', text)  # 移除HTML标签
        text = re.sub(r'\s+', '', text)  # 移除空白字符
        # 基本格式验证
        if '@' not in text or '.' not in text.split('@')[1]:
            return ""
        return text

    elif input_type == "password":
        # 密码清理（允许更多字符但需要验证强度）
        text = text.strip()
        # 不移除特殊字符，密码需要复杂度
        return text

    elif input_type == "requirement":
        # 需求描述清理
        text = text.strip()
        # 移除潜在的恶意脚本
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
        text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)
        # 清理多余的空白
        text = re.sub(r'\n\s*\n', '\n', text)
        return text

    elif input_type == "activation_code":
        # 激活码清理（严格限制字符集）
        text = text.strip().upper()
        # 只允许字母、数字和连字符
        if not re.match(r'^[A-Z0-9\-]+$', text):
            return ""
        return text

    elif input_type == "general":
        # 通用输入清理
        text = text.strip()
        # 移除控制字符（除了常见的换行、制表符）
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t\r')
        # 移除潜在的恶意字符
        dangerous_patterns = [
            r'<iframe.*?>.*?</iframe>',
            r'<object.*?>.*?</object>',
            r'<embed.*?>.*?</embed>',
            r'<link.*?>.*?</link>',
            r'<meta.*?>.*?</meta>',
            r'<style.*?>.*?</style>',
            r'<script[^>]*>.*?</script>',
        ]
        for pattern in dangerous_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        return text

    else:
        # 默认清理
        text = text.strip()
        return text


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