"""
软件测试用例生成器 - Web 原型
基于 Python + Streamlit + 智谱 GLM-4-Flash 模型

功能：
  - 根据需求描述自动生成结构化测试用例
  - 用户注册/登录系统
  - 每个邮箱每天免费生成 5 次
  - 超出限制后需输入激活码解除限制
  - 激活码通过面包多售卖
  - 数据存储：Supabase PostgreSQL
  - 用户评价功能
"""

import streamlit as st
import pandas as pd
import io
import hashlib
import bcrypt
import time
from datetime import date, datetime, timedelta
from typing import Tuple
from openai import OpenAI
from supabase import create_client, Client
from verification_service import send_verification, check_code, cleanup_expired_codes
from mb_integration import create_purchase_order, get_user_orders, get_statistics
from security import check_activation_rate_limit, sanitize_input, validate_email, validate_password, get_cached_order, cache_order, check_rate_limit, can_attempt_login, record_login_attempt, validate_session_token, generate_session_token
# API Key安全管理函数（直接集成到app.py中避免导入错误）
def hash_api_key(api_key: str) -> str:
    """对API Key进行单向哈希"""
    return hashlib.sha256(api_key.encode()).hexdigest()

def validate_api_key_format(api_key: str) -> Tuple[bool, str]:
    """验证API Key格式"""
    if not api_key:
        return False, "API Key不能为空"

    # 检查长度
    length = len(api_key)
    if not 20 <= length <= 100:
        return False, f"API Key长度异常（{length}字符）"

    # 检查前缀
    valid_prefixes = ['sk-', 'gl-', 'zhipu-', 'glm-']
    has_valid_prefix = any(api_key.startswith(prefix) for prefix in valid_prefixes)
    if not has_valid_prefix:
        return False, "API Key前缀异常"

    return True, ""

def is_api_key_safe(api_key: str, ip_address: str = "unknown") -> Tuple[bool, str]:
    """检查API Key是否安全可用"""
    # 简化版本的安全检查
    if not api_key or len(api_key.strip()) == 0:
        return False, "API Key不能为空"

    # 基本格式验证
    valid, msg = validate_api_key_format(api_key)
    if not valid:
        return False, msg

    # 这里可以添加更多的安全检查
    # 比如检查是否在黑名单中等

    return True, "API Key安全"

def record_api_key_usage(api_key: str, ip_address: str, user_agent: str = "", success: bool = True):
    """记录API Key使用情况（简化版本）"""
    # 这里可以添加使用记录逻辑
    # 为了避免复杂度，暂时返回成功
    return {'allowed': True, 'usage_count': 1, 'success_rate': 1.0}

def get_api_key_stats(api_key_hash: str):
    """获取API Key统计信息（简化版本）"""
    return {}


# ============================================================
# 常量定义
# ============================================================

# 智谱 AI API 基础地址
ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
# 默认模型名称
DEFAULT_MODEL = "glm-4-flash"

# 测试类型选项
TEST_TYPES = ["功能测试", "接口测试", "性能测试", "安全测试"]

# 输出风格选项
OUTPUT_STYLES = ["详细", "简洁"]

# 页面配置
PAGE_TITLE = "软件测试用例生成器"
PAGE_ICON = "🧪"

# ---------- 试用限制相关常量 ----------
# 每个API Key每天免费生成次数
FREE_DAILY_LIMIT = 5

# 面包多配置
MIANBADUO_URL = "https://mbd.pub/o/bread/YZaUlppuag=="
MBD_PRODUCT_NAME = "软件测试用例生成器 - 专业版激活码"
MBD_PRICE = 99.00  # 激活码价格

# Supabase 配置（从 Streamlit Secrets 读取）
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]


# ============================================================
# Supabase 初始化
# ============================================================

try:
    print(f"[DEBUG] Initializing Supabase...")
    print(f"[DEBUG] SUPABASE_URL: {SUPABASE_URL}")
    print(f"[DEBUG] SUPABASE_KEY length: {len(SUPABASE_KEY) if SUPABASE_KEY else 0}")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"[DEBUG] Supabase initialized successfully")
except Exception as e:
    print(f"[DEBUG] Supabase initialization failed: {str(e)}")
    supabase = None


# ============================================================
# Session State 管理
# ============================================================

def init_session_state():
    """初始化 session state"""
    if 'user' not in st.session_state:
        st.session_state.user = None
    if 'verification_sent' not in st.session_state:
        st.session_state.verification_sent = False
    if 'verification_email' not in st.session_state:
        st.session_state.verification_email = ""
    if 'verification_type' not in st.session_state:
        st.session_state.verification_type = ""
    if 'temp_password' not in st.session_state:
        st.session_state.temp_password = ""


# ============================================================
# 密码哈希工具
# ============================================================

def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    try:
        print(f"[DEBUG] Verifying password. Plain: {plain_password[:4]}..., Hashed: {hashed_password[:20]}...")
        result = bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        print(f"[DEBUG] Password verification result: {result}")
        return result
    except Exception as e:
        print(f"[DEBUG] Password verification error: {str(e)}")
        return False


# ============================================================
# 会话安全工具
# ============================================================

def verify_session() -> bool:
    """
    增强的会话验证（带安全检查）

    Returns:
        会话是否有效
    """
    if 'user' not in st.session_state or not st.session_state.user:
        return False

    # 检查会话过期
    if 'session_expiry' in st.session_state:
        current_time = int(time.time())
        if current_time > st.session_state.session_expiry:
            # 会话过期，清除
            logout_user()
            return False

    # 检查会话令牌（如果存在）
    if 'session_token' in st.session_state and 'login_ip' in st.session_state:
        client_ip = "unknown"
        try:
            import streamlit.web.server.websockets_ws
            client_ip = streamlit.web.server.websockets_ws.get_remote_ip()
        except:
            pass

        # 验证令牌和IP
        from security import validate_session_token
        if not validate_session_token(
            st.session_state.session_token,
            st.session_state.user['id'],
            client_ip
        ):
            # 会话令牌无效，可能是劫持
            log_security_event("session_hijack_attempt", {
                'user_id': st.session_state.user['id'],
                'current_ip': client_ip,
                'stored_ip': st.session_state.get('login_ip', 'unknown')
            })
            logout_user()
            return False

    # 检查异常登录地点
    if 'login_ip' in st.session_state:
        current_ip = "unknown"
        try:
            import streamlit.web.server.websockets_ws
            current_ip = streamlit.web.server.websockets_ws.get_remote_ip()
        except:
            pass

        if current_ip != "unknown" and current_ip != st.session_state.login_ip:
            # IP地址发生变化，记录警告
            log_security_event("ip_address_change", {
                'user_id': st.session_state.user['id'],
                'old_ip': st.session_state.login_ip,
                'new_ip': current_ip
            })

    return True


def check_user_permission(required_user_id: int) -> bool:
    """
    检查用户是否有权限访问资源

    Args:
        required_user_id: 要求的用户ID

    Returns:
        是否有权限
    """
    if not verify_session():
        return False

    current_user_id = st.session_state.user.get('id')

    return str(current_user_id) == str(required_user_id)


# ============================================================
# 用户管理函数
# ============================================================

def register_user(email: str, password: str) -> tuple[bool, str]:
    """
    注册新用户

    Args:
        email: 邮箱
        password: 密码

    Returns:
        (成功状态, 消息)
    """
    try:
        # 输入验证
        if not validate_email(email):
            return False, "邮箱格式不正确"

        valid, message = validate_password(password)
        if not valid:
            return False, message

        # 检查邮箱是否已存在
        response = supabase.table('users').select('id').eq('email', email).execute()

        if response.data:
            return False, "该邮箱已被注册"

        # 哈希密码
        password_hash = hash_password(password)

        # 创建用户
        result = supabase.table('users').insert({
            'email': email,
            'password_hash': password_hash,
            'created_at': datetime.now().isoformat()
        }).execute()

        if result.data:
            return True, "注册成功！请登录"
        else:
            return False, "注册失败，请重试"

    except Exception as e:
        # 不暴露内部错误信息
        return False, "注册失败，请稍后重试"


def login_user(email: str, password: str, ip_address: str = "unknown") -> tuple[bool, str]:
    """
    增强的用户登录（带安全防护）

    Args:
        email: 邮箱
        password: 密码
        ip_address: 客户端IP地址

    Returns:
        (成功状态, 消息)
    """
    try:
        print(f"[DEBUG] Login attempt for email: {email}")

        # 输入验证和清理
        email = sanitize_input(email, max_length=100, input_type="email")
        if not email:
            return False, "邮箱格式错误"

        print(f"[DEBUG] Email sanitized: {email}")

        # 检查登录尝试频率（增强版）
        can_login, msg = can_attempt_login(email, ip_address)
        if not can_login:
            print(f"[DEBUG] Login blocked by rate limit: {msg}")
            return False, msg

        # 查找用户
        print(f"[DEBUG] Querying user with email: {email}")
        if not supabase:
            print(f"[DEBUG] Supabase client is not initialized!")
            return False, "系统错误，请稍后重试"

        try:
            response = supabase.table('users').select('*').eq('email', email).execute()
            print(f"[DEBUG] Supabase response: {response}")
        except Exception as e:
            print(f"[DEBUG] Supabase query failed: {str(e)}")
            return False, "数据库查询失败，请稍后重试"

        if not response.data:
            print(f"[DEBUG] User not found: {email}")
            # 记录失败的登录尝试
            record_login_attempt(email, ip_address, success=False)
            return False, "邮箱或密码错误"  # 统一错误消息，防止账户枚举

        user = response.data[0]
        print(f"[DEBUG] User found: {user['email']}, ID: {user.get('id')}")

        # 验证密码
        print(f"[DEBUG] Verifying password...")
        if verify_password(password, user['password_hash']):
            print(f"[DEBUG] Password verified successfully")

            # 更新最后登录时间和IP
            print(f"[DEBUG] Updating user last login info...")
            supabase.table('users').update({
                'last_login': datetime.now().isoformat(),
                'last_login_ip': ip_address
            }).eq('id', user['id']).execute()

            # 生成安全的会话令牌
            session_token = generate_session_token(user['id'], ip_address)
            print(f"[DEBUG] Session token generated")

            # 防止会话固定攻击：登录后重新生成会话
            if 'user' in st.session_state:
                del st.session_state.user

            # 添加会话过期时间（24小时）
            st.session_state.session_expiry = int(time.time()) + 86400

            # 添加登录时间戳和安全令牌用于安全检查
            st.session_state.login_time = datetime.now().isoformat()
            st.session_state.session_token = session_token
            st.session_state.login_ip = ip_address

            # 记录登录成功
            record_login_attempt(email, ip_address, success=True)

            # 生成安全的用户信息（不包含敏感数据）
            st.session_state.user = {
                'id': user['id'],
                'email': user['email'],
                'activation_code': user.get('activation_code'),
                'created_at': user['created_at'],
                'last_login': datetime.now().isoformat()
            }
            print(f"[DEBUG] User session created successfully")

            # 记录安全日志
            log_security_event("user_login_success", {
                'user_id': user['id'],
                'email': email,
                'ip_address': ip_address
            })

            print(f"[DEBUG] Login successful for {email}")
            return True, "登录成功！"
        else:
            print(f"[DEBUG] Password verification failed for {email}")
            # 记录失败的登录尝试
            record_login_attempt(email, ip_address, success=False)
            return False, "邮箱或密码错误"  # 统一错误消息，防止账户枚举

    except Exception as e:
        # 详细错误记录
        import traceback
        print(f"[DEBUG] Login failed with exception: {str(e)}")
        print(f"[DEBUG] Traceback: {traceback.format_exc()}")
        return False, "登录失败，请稍后重试"


def logout_user():
    """退出登录"""
    st.session_state.user = None
    st.rerun()


def send_email_verification_code(email: str, code_type: str = "register") -> tuple[bool, str]:
    """
    发送邮箱验证码

    Args:
        email: 邮箱
        code_type: 验证码类型（register/login）

    Returns:
        (成功状态, 消息)
    """
    try:
        # 邮箱格式验证
        if not validate_email(email):
            return False, "邮箱格式不正确"

        # 验证码发送频率限制（每个邮箱1次/分钟，5次/小时）
        email_key = f"email_code_{email}_{code_type}"
        allowed, remaining = check_rate_limit(email_key, 5, 3600)  # 5次/小时
        if not allowed:
            return False, f"⏸️ 验证码发送过于频繁，请等待 {remaining} 秒后再试。"

        # 发送验证码
        result = send_verification(email, code_type)

        if result['success']:
            st.session_state.verification_sent = True
            st.session_state.verification_email = email
            st.session_state.verification_type = code_type
            return True, "验证码已发送"
        else:
            return False, result['message']

    except Exception as e:
        # 不暴露内部错误
        return False, "发送验证码失败，请稍后重试"


def verify_email_code(email: str, code: str, code_type: str) -> tuple[bool, str]:
    """
    验证邮箱验证码

    Args:
        email: 邮箱
        code: 用户输入的验证码
        code_type: 验证码类型

    Returns:
        (成功状态, 消息)
    """
    try:
        # 调用验证码服务的验证函数
        result = check_code(email, code, code_type)

        if result['success']:
            return True, "验证成功"
        else:
            if result.get('expired'):
                return False, "验证码已过期"
            else:
                return False, result['message']

    except Exception as e:
        return False, f"验证失败: {str(e)}"


# ============================================================
# 使用次数管理（Supabase + 用户关联）
# ============================================================

def get_usage_info(user_id: int) -> dict:
    """
    获取用户的使用信息。

    Args:
        user_id: 用户 ID

    Returns:
        使用信息字典
    """

    today_str = date.today().isoformat()

    # 查询数据库
    response = supabase.table('usage').select('*').eq('user_id', user_id).execute()

    if not response.data:
        # 无记录，返回默认
        return {"date": today_str, "count": 0, "activated": False}

    record = response.data[0]

    # 如果日期不是今天，重置次数（但保留激活状态）
    if record.get("date") != today_str:
        record["date"] = today_str
        record["count"] = 0
        # 同步到数据库
        supabase.table('usage').update({
            "date": today_str,
            "count": 0
        }).eq('user_id', user_id).execute()

    # 确保字段完整
    record.setdefault("count", 0)
    record.setdefault("activated", False)

    return record


def increment_usage(user_id: int) -> None:
    """
    将用户的今日使用次数 +1，并更新到数据库。

    Args:
        user_id: 用户 ID
    """

    info = get_usage_info(user_id)
    new_count = info.get("count", 0) + 1

    # 使用 upsert：如果记录存在则更新，不存在则插入
    supabase.table('usage').upsert({
        "user_id": user_id,
        "date": info["date"],
        "count": new_count,
        "activated": info.get("activated", False)
    }).execute()


def set_activated(user_id: int, activation_code: str) -> None:
    """
    将用户标记为已激活（无限次使用）。

    Args:
        user_id: 用户 ID
        activation_code: 激活码
    """

    today_str = date.today().isoformat()

    # 检查是否有记录
    response = supabase.table('usage').select('*').eq('user_id', user_id).execute()

    if response.data:
        # 更新现有记录
        supabase.table('usage').update({
            "activated": True,
            "date": today_str,
            "count": 0  # 激活后重置今日次数
        }).eq('user_id', user_id).execute()
    else:
        # 插入新记录
        supabase.table('usage').insert({
            "user_id": user_id,
            "date": today_str,
            "count": 0,
            "activated": True
        }).execute()

    # 更新用户的激活码
    supabase.table('users').update({
        "activation_code": activation_code
    }).eq('id', user_id).execute()


# ============================================================
# 激活码管理（Supabase + 用户关联）
# ============================================================

def validate_and_activate(activation_code: str, user_id: int, user_email: str) -> tuple[bool, str]:
    """
    验证激活码并绑定到当前用户。
    支持两种模式：
    1. 预生成激活码（数据库中已存在）
    2. 面包多订单号（通过API验证支付状态）

    Args:
        activation_code: 用户输入的激活码
        user_id: 当前用户 ID
        user_email: 用户邮箱

    Returns:
        (是否成功, 提示消息)
    """

    code = activation_code.strip()

    # 先查询数据库中是否已存在该激活码
    response = supabase.table('activation_codes').select('*').eq('code', code).execute()

    if response.data:
        # 数据库中已存在，走原有的验证流程
        code_info = response.data[0]

        # 检查是否已被使用
        if code_info.get("used", False):
            used_by = code_info.get("used_by", "")
            if str(used_by) == str(user_id):
                return False, "⚠️ 该激活码已被当前账号使用过，无需重复激活。"
            else:
                return False, "❌ 该激活码已被其他账号使用。"

        # 执行激活
        supabase.table('activation_codes').update({
            "used": True,
            "used_by": user_id,
            "used_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }).eq('code', code).execute()

        set_activated(user_id, code)
        return True, "✅ 激活成功！现已解除生成次数限制。"

    # 数据库中不存在，作为面包多订单号处理
    # 面包多订单号是32位字母数字组合，设置最小长度避免无意义输入
    if len(code) >= 20:  # 支持面包多订单号（32位）或较长的自定义订单号

        # 检查频率限制
        allowed, message = check_activation_rate_limit(user_id)
        if not allowed:
            return False, message

        # 检查缓存
        cached_data = get_cached_order(code)
        if cached_data:
            if cached_data.get('state') == 'success':
                # 缓存显示已支付，继续激活流程
                pass
            else:
                # 缓存显示未支付或无效
                state = cached_data.get('state', 'unknown')
                if state == 'cancel':
                    return False, "❌ 订单已取消"
                elif state == 'invalid':
                    return False, "❌ 订单已过期"
                else:
                    return False, f"❌ 订单无效 ({state})"

        # 调用面包多API验证订单状态
        from mb_integration import verify_order_paid
        from mb_integration import get_order_detail

        with st.spinner("⏳ 正在验证订单状态..."):
            is_paid, api_message = verify_order_paid(code)

        # 缓存查询结果
        order_data = get_order_detail(code)
        if order_data.get('success'):
            cache_order(code, order_data)

        if not is_paid:
            return False, api_message

        # 订单已支付，创建激活码记录并激活
        try:
            insert_result = supabase.table('activation_codes').insert({
                'code': code,
                'product_name': '测试用例生成器 - Pro 无限版',
                'price': 9.9,
                'used': True,  # 直接标记为已使用
                'used_by': user_id,
                'used_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'created_at': datetime.now().isoformat()
            }).execute()

            if insert_result.data:
                # 插入后立即验证，防止竞态条件
                verify_result = supabase.table('activation_codes').select('*').eq('code', code).execute()

                if verify_result.data:
                    record = verify_result.data[0]
                    if str(record.get('used_by')) != str(user_id):
                        # 记录已被其他用户抢占
                        return False, "❌ 该激活码已被其他账号使用。"

                # 标记用户为已激活
                set_activated(user_id, code)
                return True, "✅ 订单验证成功！激活成功，现已解除生成次数限制。"
            else:
                return False, "❌ 激活失败，请重试。"

        except Exception as e:
            # 可能是唯一约束冲突（被其他用户抢先激活）
            if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
                # 重新查询确认
                verify_result = supabase.table('activation_codes').select('*').eq('code', code).execute()
                if verify_result.data:
                    record = verify_result.data[0]
                    if str(record.get('used_by')) != str(user_id):
                        return False, "❌ 该激活码已被其他账号使用。"
                    else:
                        # 已被当前用户激活
                        set_activated(user_id, code)
                        return True, "✅ 激活成功！"
            # 不暴露内部错误信息
            return False, "❌ 激活失败，请稍后重试"

    # 既不是数据库中的激活码，也不是有效的订单号格式
    return False, "❌ 激活码无效，请检查后重试。"


def is_user_activated(user_id: int) -> bool:
    """
    检查用户是否已激活（不受每日次数限制）。

    Args:
        user_id: 用户 ID

    Returns:
        是否已激活
    """

    info = get_usage_info(user_id)
    return info.get("activated", False)


def get_remaining_count(user_id: int) -> int:
    """
    获取今日剩余可生成次数。

    已激活的用户返回 -1 表示无限制。

    Args:
        user_id: 用户 ID

    Returns:
        剩余次数；-1 表示无限制
    """

    info = get_usage_info(user_id)

    if info.get("activated", False):
        return -1  # 无限制

    used = info.get("count", 0)
    return max(0, FREE_DAILY_LIMIT - used)


# ============================================================
# 激活码购买功能（面包多集成）
# ============================================================

def create_purchase_order(user_id: int) -> dict:
    """
    创建面包多购买订单

    Args:
        user_id: 用户ID

    Returns:
        订单信息字典
    """
    try:
        # 导入面包多集成
        from mb_integration import create_purchase_order as mbd_create_order

        result = mbd_create_order(user_id)

        if result['success']:
            # 保存订单到数据库
            order_data = {
                'order_id': result['order_id'],
                'user_id': user_id,
                'activation_code_id': None,  # 支付成功后更新
                'product_name': MBD_PRODUCT_NAME,
                'price': MBD_PRICE,
                'commission_rate': 0.50,
                'commission_amount': MBD_PRICE * 0.50,
                'status': 'pending',
                'payment_method': 'breadmore'
            }

            supabase.table('orders').insert(order_data).execute()

            return {
                'success': True,
                'order_id': result['order_id'],
                'payment_url': result['payment_url'],
                'qrcode_url': result['qrcode_url'],
                'message': '订单创建成功，请完成支付'
            }
        else:
            return result

    except Exception as e:
        return {
            'success': False,
            'message': f'创建订单失败: {str(e)}'
        }

def get_user_orders(user_id: int) -> list:
    """
    获取用户的订单列表

    Args:
        user_id: 用户ID

    Returns:
        订单列表
    """
    try:
        from mb_integration import get_user_orders as mbd_get_orders

        orders = mbd_get_orders(user_id)

        # 添加激活码信息
        for order in orders:
            if order.get('activation_code_id'):
                # 查询激活码信息
                code_result = supabase.table('activation_codes').select('code').eq('id', order['activation_code_id']).execute()
                if code_result.data:
                    order['activation_code'] = code_result.data[0]['code']

        return orders

    except Exception as e:
        st.error(f"获取订单失败: {str(e)}")
        return []

def handle_payment_callback(order_id: str, status: str) -> bool:
    """
    处理支付回调

    Args:
        order_id: 订单ID
        status: 支付状态

    Returns:
        是否处理成功
    """
    try:
        if status == 'paid':
            # 更新订单状态
            supabase.table('orders').update({
                'status': 'completed',
                'completion_time': datetime.now().isoformat()
            }).eq('order_id', order_id).execute()

            return True
        return False

    except Exception as e:
        st.error(f"处理支付回调失败: {str(e)}")
        return False

def show_purchase_page(user_id: int):
    """
    显示购买页面

    Args:
        user_id: 用户ID
    """
    st.subheader("🛒 购买激活码")

    # 显示商品信息
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown(f"""
        ### {MBD_PRODUCT_NAME}

        **价格**: ¥{MBD_PRICE}
        **功能**: 解除生成次数限制，无限次使用
        **支持**: 终身有效

        **商品说明**:
        - 购买后立即激活您的账号
        - 无限制生成测试用例
        - 专业技术支持
        """)

    with col2:
        st.image("https://via.placeholder.com/150", caption="商品图片")

    # 购买按钮
    if st.button("🛒 立即购买", use_container_width=True):
        with st.spinner("正在创建订单..."):
            order_result = create_purchase_order(user_id)

            if order_result['success']:
                st.session_state.purchase_order = order_result
                st.rerun()
            else:
                st.error(f"创建订单失败: {order_result['message']}")

    # 显示订单信息
    if 'purchase_order' in st.session_state:
        order = st.session_state.purchase_order

        st.success("✅ 订单创建成功！")

        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown(f"""
            **订单号**: {order['order_id']}
            **支付金额**: ¥{MBD_PRICE}
            """)

            if order.get('qrcode_url'):
                st.image(order['qrcode_url'], caption="扫码支付")

        with col2:
            st.markdown("""
            **支付方式**:
            - 微信支付
            - 支付宝

            **支付说明**:
            - 请在30分钟内完成支付
            - 支付成功后自动激活
            - 如有问题请联系客服
            """)

            if order.get('payment_url'):
                st.markdown(f"[点击前往支付]({order['payment_url']})")

    # 我的订单
    st.divider()
    st.subheader("📋 我的订单")

    orders = get_user_orders(user_id)

    if orders:
        for order in orders:
            status_text = {
                'pending': '待支付',
                'paid': '已支付',
                'completed': '已完成',
                'failed': '支付失败'
            }.get(order.get('status', ''), '未知状态')

            with st.expander(f"订单号: {order['order_id']} - {status_text}"):
                col1, col2, col3 = st.columns([1, 1, 1])

                with col1:
                    st.write(f"**商品**: {order['product_name']}")
                    st.write(f"**价格**: ¥{order['price']}")

                with col2:
                    st.write(f"**状态**: {status_text}")
                    st.write(f"**时间**: {order['created_at'][:19]}")

                with col3:
                    if order.get('activation_code'):
                        st.success(f"激活码: {order['activation_code']}")
                    elif order['status'] == 'pending':
                        if st.button("重新支付", key=f"retry_{order['order_id']}"):
                            # 重新创建订单逻辑
                            pass
    else:
        st.info("暂无订单记录")

# ============================================================
# 评价功能（Supabase）
# ============================================================

def submit_review(user_id: int, name: str, email: str, rating: int, content: str) -> bool:
    """
    提交用户评价。

    Args:
        user_id: 用户 ID
        name: 用户名（可选）
        email: 邮箱（可选）
        rating: 评分（1-5）
        content: 评价内容

    Returns:
        是否提交成功
    """

    try:
        # 权限验证：确保只能为自己的user_id提交评价
        if not verify_session():
            return False

        current_user_id = st.session_state.user.get('id')
        if str(current_user_id) != str(user_id):
            return False  # 防止越权提交

        # 输入验证
        if not content or len(content.strip()) == 0:
            return False

        if len(content) > 1000:
            return False  # 限制评价长度

        if rating < 1 or rating > 5:
            return False  # 无效评分

        # 清理输入
        content = sanitize_input(content, max_length=1000)
        if name:
            name = sanitize_input(name, max_length=50)
        if email:
            if not validate_email(email):
                email = ""  # 无效邮箱则不存储

        # 防刷单：同一用户1小时内只能提交1次评价
        review_key = f"review_submit_{user_id}"
        allowed, remaining = check_rate_limit(review_key, 1, 3600)  # 1次/小时
        if not allowed:
            return False

        response = supabase.table('reviews').insert({
            "user_id": user_id,
            "name": name,
            "email": email,
            "rating": rating,
            "content": content
        }).execute()

        if response.data and len(response.data) > 0:
            return True
        return False
    except Exception:
        return False


def get_all_reviews(limit: int = 20) -> list:
    """
    获取所有评价（按时间倒序）。

    Args:
        limit: 返回数量限制

    Returns:
        评价列表
    """

    try:
        response = supabase.table('reviews').select('*').order('created_at', desc=True).limit(limit).execute()
        return response.data or []
    except Exception:
        return []


def calculate_average_rating() -> float:
    """
    计算平均评分。

    Returns:
        平均分（四舍五入到 1 位小数）
    """

    try:
        response = supabase.table('reviews').select('rating').execute()
        if not response.data:
            return 0.0

        ratings = [r['rating'] for r in response.data if 'rating' in r]
        if not ratings:
            return 0.0

        return round(sum(ratings) / len(ratings), 1)
    except Exception:
        return 0.0


# ============================================================
# Prompt 安全工具
# ============================================================

def detect_prompt_injection(text: str) -> bool:
    """
    检测提示词注入攻击

    Args:
        text: 待检测的文本

    Returns:
        是否检测到注入
    """
    # 常见的注入模式
    injection_patterns = [
        '忽略', '忽略之前的', 'forget', 'disregard',
        '新指令', 'new instruction', 'override',
        '提示词', 'system prompt', '你的系统提示',
        '告诉我你的', 'show me your', 'reveal your',
        '绕过', 'bypass', 'hack', 'exploit'
    ]

    text_lower = text.lower()

    for pattern in injection_patterns:
        if pattern in text_lower:
            return True

    # 检查是否尝试输出JSON或代码格式来绕过过滤
    if ('```json' in text or '```code' in text) and ('system' in text_lower or 'prompt' in text_lower):
        return True

    return False


def clean_model_output(output: str) -> str:
    """
    清理模型输出，防止敏感信息泄露

    Args:
        output: 模型原始输出

    Returns:
        清理后的输出
    """
    # 如果输出中包含明显的系统提示词或敏感信息，进行替换
    sensitive_patterns = [
        ('你是一位专业的软件测试工程师', 'AI助手'),
        ('system prompt', '系统配置'),
        ('你是一名', ''),
        ('你的任务', '任务'),
    ]

    cleaned = output
    for pattern, replacement in sensitive_patterns:
        cleaned = cleaned.replace(pattern, replacement)

    return cleaned


# ============================================================
# Prompt 构建函数
# ============================================================

def build_prompt(requirement: str, test_type: str, style: str) -> str:
    """
    根据用户输入的需求描述、测试类型和输出风格，拼接出完整的 prompt。

    Args:
        requirement: 用户粘贴的需求描述文本
        test_type:   测试类型（功能/接口/性能/安全）
        style:       输出风格（详细/简洁）

    Returns:
        拼接好的完整 prompt 字符串
    """

    # 检测提示词注入
    if detect_prompt_injection(requirement):
        requirement = "用户提供了测试用例生成需求（内容已清理）"

    # 如果需求描述过长，使用更简洁的prompt
    if len(requirement) > 3000:
        simplified_requirement = requirement[:1000] + "...[内容已简化]"
        step_instruction = (
            "测试步骤尽量简短，每项用一句话概括即可。"
        )
        prompt = f"""生成{test_type}用例。

需求：{simplified_requirement}

要求：
1. 输出Markdown表格：|编号|模块|标题|前置条件|步骤|预期结果|
2. 生成8-12条用例，包含正常、异常、边界场景
3. {step_instruction}
4. 编号格式：TC-001, TC-002...

直接输出表格："""
        return prompt

    # 根据输出风格决定步骤描述的详细程度
    if style == "详细":
        step_instruction = (
            "测试步骤需要详细描述每一步操作，包括输入数据、点击按钮、"
            "等待响应等具体动作；前置条件也要写明需要准备的环境和数据。"
        )
    else:
        step_instruction = (
            "测试步骤和前置条件尽量简短，每项用一句话概括即可。"
        )

    prompt = f"""你是一位资深软件测试工程师，请根据以下需求描述，生成{test_type}用例。

## 需求描述
{requirement}

## 输出要求
1. 请直接输出 Markdown 表格，不要输出多余的解释文字。
2. 表格列依次为：| 用例编号 | 模块 | 测试标题 | 前置条件 | 测试步骤 | 预期结果 |
3. 共生成 8-12 条用例，需覆盖以下场景：
   - 正常场景（ happy path ）：核心功能的主流程
   - 异常场景：非法输入、权限不足、网络异常等
   - 边界场景：空值、最大长度、临界值等
4. {step_instruction}
5. 用例编号格式为 TC-001、TC-002 ……

请直接输出表格："""

    return prompt


# ============================================================
# 模型调用函数
# ============================================================

def validate_zhipu_api_key(api_key: str, ip_address: str = "unknown") -> tuple[bool, str]:
    """
    增强的智谱API Key验证（带安全检查）。

    Args:
        api_key: 智谱 AI 的 API Key
        ip_address: 客户端IP地址

    Returns:
        (是否有效, 消息)
    """
    try:
        # 首先进行安全检查
        safe, msg = is_api_key_safe(api_key, ip_address)
        if not safe:
            return False, f"API Key 安全检查失败: {msg}"

        # 格式验证
        validate_api_key_format
        valid, format_msg = validate_api_key_format(api_key)
        if not valid:
            return False, f"API Key 格式错误: {format_msg}"
        client = OpenAI(
            api_key=api_key,
            base_url=ZHIPU_BASE_URL,
        )
        # 发送一个小的测试请求
        response = client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=1
        )
        return True
    except:
        return False


def call_glm(api_key: str, prompt: str, model: str = DEFAULT_MODEL) -> str:
    """
    调用智谱 GLM 模型，返回生成的文本。

    Args:
        api_key: 智谱 AI 的 API Key
        prompt:  完整的 prompt 字符串
        model:   模型名称，默认 glm-4-flash

    Returns:
        模型生成的文本内容

    Raises:
        Exception: 调用失败时抛出异常，由上层捕获处理
    """

    # 先验证API Key
    if not validate_zhipu_api_key(api_key):
        raise Exception("API Key无效，请检查是否正确")

    client = OpenAI(
        api_key=api_key,
        base_url=ZHIPU_BASE_URL,
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "你是一位专业的软件测试工程师，擅长编写高质量的测试用例。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.7,
        top_p=0.9,
    )

    return response.choices[0].message.content


# ============================================================
# Markdown 表格解析函数
# ============================================================

def parse_markdown_table(md_text: str) -> pd.DataFrame:
    """
    将模型返回的 Markdown 表格文本解析为 pandas DataFrame。

    Args:
        md_text: 包含 Markdown 表格的文本

    Returns:
        解析后的 DataFrame；如果解析失败则返回空 DataFrame
    """

    lines = md_text.strip().split("\n")

    # 筛选出表格行（以 | 开头且非分隔行）
    table_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and not all(
            ch in "|- : " for ch in stripped
        ):
            table_lines.append(stripped)

    if len(table_lines) < 2:
        # 至少需要表头 + 一行数据
        return pd.DataFrame()

    # 解析表头
    headers = [cell.strip() for cell in table_lines[0].split("|") if cell.strip()]

    # 解析数据行
    rows = []
    for line in table_lines[1:]:
        cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        # 如果列数与表头一致才收录
        if len(cells) == len(headers):
            rows.append(cells)

    df = pd.DataFrame(rows, columns=headers)
    return df


# ============================================================
# CSV 下载辅助函数
# ============================================================

def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """
    将 DataFrame 转换为 UTF-8 BOM 编码的 CSV 字节数据，
    以确保 Excel 打开时中文不乱码。

    Args:
        df: 要转换的 DataFrame

    Returns:
        UTF-8 BOM 编码的 CSV 字节数据
    """

    output = io.StringIO()
    df.to_csv(output, index=False, encoding="utf-8-sig")
    # 添加 BOM 头，让 Excel 正确识别 UTF-8
    csv_str = output.getvalue()
    return ("﻿" + csv_str).encode("utf-8")


# ============================================================
# 侧边栏组件
# ============================================================

def show_login_register_sidebar():
    """
    显示登录/注册表单
    """
    tab1, tab2 = st.tabs(["🔐 登录", "📝 注册"])

    with tab1:
        st.subheader("登录")

        email = st.text_input("邮箱", key="login_email")
        password = st.text_input("密码", type="password", key="login_password")

        if st.button("登录", use_container_width=True):
            if not email or not password:
                st.error("请填写邮箱和密码")
            else:
                success, msg = login_user(email, password)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        with st.expander("忘记密码？"):
            st.info("请通过验证码重置密码")

    with tab2:
        st.subheader("注册")

        reg_email = st.text_input("邮箱", key="reg_email")

        if st.button("发送验证码", key="send_reg_code", use_container_width=True):
            if not reg_email:
                st.error("请输入邮箱")
            else:
                success, msg = send_email_verification_code(reg_email, "register")
                if success:
                    st.success(msg)
                    st.session_state.verification_type = "register"
                else:
                    st.error(msg)

        if st.session_state.verification_sent and st.session_state.verification_type == "register":
            reg_code = st.text_input("验证码", key="reg_code")
            new_password = st.text_input("密码", type="password", key="new_password")
            confirm_password = st.text_input("确认密码", type="password", key="confirm_password")

            if st.button("注册", use_container_width=True):
                if not reg_code or not new_password or not confirm_password:
                    st.error("请填写所有字段")
                elif new_password != confirm_password:
                    st.error("两次密码不一致")
                else:
                    success, msg = verify_email_code(reg_email, reg_code, "register")
                    if success:
                        success, msg = register_user(reg_email, new_password)
                        if success:
                            st.success(msg)
                            st.session_state.verification_sent = False
                        else:
                            st.error(msg)
                    else:
                        st.error(msg)


def render_usage_sidebar(user_id: int, user_email: str):
    """
    在侧边栏渲染使用次数提示和激活码输入区域。

    Args:
        user_id: 用户 ID
        user_email: 用户邮箱
    """

    remaining = get_remaining_count(user_id)

    if remaining == -1:
        # 已激活，无限制
        st.markdown(
            '<div style="background:#d4edda;padding:10px;border-radius:6px;'
            'color:#155724;font-size:14px;">'
            '👑 **Pro 已激活** · 今日不限次数</div>',
            unsafe_allow_html=True,
        )
    else:
        # 免费用户，显示剩余次数
        used = FREE_DAILY_LIMIT - remaining
        bar_pct = remaining / FREE_DAILY_LIMIT

        # 用进度条直观展示
        st.progress(bar_pct, text=f"今日剩余 **{remaining}** / {FREE_DAILY_LIMIT} 次")

        if remaining == 0:
            st.warning("⚠️ 今日免费次数已用完")
        elif remaining <= 2:
            st.info(f"💡 今日仅剩 **{remaining}** 次免费机会")

    # 激活码输入区域（仅未激活时突出显示）
    st.text_input(
        label="🔑 输入激活码",
        key="activation_code",
        placeholder="例如：TCGEN-PRO-2026A",
        help="输入从面包多购买的激活码，激活后无限次使用",
    )

    activate_btn = st.button(
        label="✅ 激活",
        use_container_width=True,
    )

    if activate_btn:
        code = st.session_state.get("activation_code", "").strip()
        if not code:
            st.error("请先输入激活码！")
        else:
            success, msg = validate_and_activate(code, user_id, user_email)
            if success:
                st.success(msg)
                st.rerun()  # 刷新页面以更新状态
            else:
                st.error(msg)

    # 购买提示（未激活时显示）
    if remaining != -1:
        st.info(f"📌 次数不够？[前往面包多购买激活码]({MIANBADUO_URL}) 💰 ¥{MBD_PRICE}")


# ============================================================
# 评价展示组件
# ============================================================

def show_reviews_section():
    """
    展示用户评价区域。
    """

    st.subheader("🌟 用户评价")

    # 显示平均评分
    avg_rating = calculate_average_rating()
    st.markdown(
        f'<div style="background:#f8f9fa;padding:10px;border-radius:6px;'
        'text-align:center;font-size:16px;">'
        f'⭐ 平均评分：<strong>{avg_rating}</strong> / 5.0 '
        f'({get_all_reviews().__len__() if get_all_reviews() else 0} 条评价)</div>',
        unsafe_allow_html=True,
    )

    # 显示评价列表
    reviews = get_all_reviews()
    if reviews:
        for review in reviews:
            rating_stars = "⭐" * review['rating'] + "☆" * (5 - review['rating'])

            # 格式化时间
            created_at = datetime.fromisoformat(review['created_at'].replace('Z', '+00:00'))
            time_str = created_at.strftime("%Y-%m-%d %H:%M")

            st.markdown("---")
            with st.expander(f"{review['name'] or '匿名用户'} · {time_str}"):
                st.markdown(f"**{rating_stars} ({review['rating']}/5)**")
                st.write(review['content'])
    else:
        st.info("暂无评价，欢迎使用后分享体验！")


# ============================================================
# 评价提交组件
# ============================================================

def show_review_submission(user_id: int):
    """
    展示评价提交表单。

    Args:
        user_id: 用户 ID
    """
    # 双重验证确保用户ID有效
    if not verify_session():
        st.error("❌ 会话无效，请重新登录")
        st.rerun()

    current_user_id = st.session_state.user.get('id')
    if str(current_user_id) != str(user_id):
        st.error("❌ 权限验证失败")
        st.rerun()

    st.subheader("💬 写评价")
    st.markdown("您的反馈对我们很重要！")

    with st.form("review_form"):
        # 评分选择
        rating = st.radio(
            "评分",
            [1, 2, 3, 4, 5],
            horizontal=True,
            captions=["😢 很不满意", "😐 一般", "👍 满意", "😊 很满意", "🤩 超级满意"]
        )

        # 基本信息
        name = st.text_input("昵称（可选）")
        email = st.text_input("邮箱（可选，仅用于联系）")

        # 评价内容
        content = st.text_area(
            "评价内容",
            placeholder="请分享您的使用体验...",
            height=120
        )

        # 提交按钮
        submitted = st.form_submit_button("提交评价", use_container_width=True)

        if submitted:
            if not content.strip():
                st.error("请填写评价内容")
            else:
                success = submit_review(user_id, name.strip(), email.strip(), rating, content.strip())
                if success:
                    st.success("感谢您的评价！🎉")
                    st.rerun()
                else:
                    st.error("提交失败，请重试")


# ============================================================
# 安全日志功能
# ============================================================

# 安全日志功能
def log_security_event(event_type, data):
    """记录安全事件（简化版）"""
    print(f"[Security Event] {event_type}: {data}")
    # 尝试导入安全日志模块（如果存在）
    try:
        from security_logging import SecurityEvent
        event = SecurityEvent(event_type, None, None, data)
        from security_logging import log_security_event as security_log
        security_log(event)
    except ImportError:
        # 如果没有security_logging模块，使用简化版
        pass
    except:
        # 如果有security_logging模块但创建SecurityEvent失败，使用简化版
        pass

def log_error(error_type, error_msg, data):
    """记录错误信息（简化版）"""
    print(f"[Error] {error_type}: {error_msg} - Data: {data}")
    # 尝试导入错误日志模块（如果存在）
    try:
        from security_logging import log_error as security_log_error
        security_log_error(error_type, {"message": error_msg, **data})
    except ImportError:
        # 如果没有security_logging模块，使用简化版
        pass
    except:
        # 如果有security_logging模块但调用失败，使用简化版
        pass

# 如果生产环境尝试从 security_logging 导入，我们提供兼容性
try:
    from security_logging import log_error as production_log_error
    def log_error_compatible(error_type, error_msg, data=None):
        """兼容性函数，调用 production_log_error"""
        if data is None:
            data = {}
        production_log_error(error_type, {"message": error_msg, **data})
except (ImportError, Exception):
    # 如果不存在或有其他错误，使用我们自己的实现
    def log_error_compatible(error_type, error_msg, data=None):
        """兼容性函数，回退到 log_error"""
        if data is None:
            data = {}
        log_error(error_type, error_msg, data)

# ============================================================
# 主应用
# ============================================================

def main():
    """应用主入口：页面布局、交互逻辑与结果展示。"""

    # 初始化 session state
    init_session_state()

    # 清理过期验证码
    cleanup_expired_codes()

    # 处理购买页面路由
    if st.session_state.get('show_purchase_page') and st.session_state.user:
        show_purchase_page(st.session_state.user['id'])
        return  # 这个是合理的，在函数调用后退出

    # ---------- 页面基础配置 ----------
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="wide",
    )

    # ---------- 侧边栏 ----------
    with st.sidebar:
        st.header("⚙️ 参数配置")

        # 如果用户未登录
        if not st.session_state.user:
            show_login_register_sidebar()

            # 应用信息
            st.divider()
            st.markdown("### 📄 应用信息")
            st.markdown("- 基于 GLM-4-Flash 大模型")
            st.markdown("- 每个邮箱每天 5 次免费")
            st.markdown("- 激活码无限次使用")
            st.markdown("- 支持多种测试类型")

        else:
            # 验证会话有效性
            if not verify_session():
                st.warning("⚠️ 会话已过期，请重新登录")
                if st.button("重新登录", use_container_width=True):
                    logout_user()
                st.rerun()  # 使用rerun刷新页面

            # 用户已登录
            user = st.session_state.user

            # 显示用户信息
            st.markdown(
                f'<div style="background:#e8f4f8;padding:10px;border-radius:6px;'
                f'text-align:center;font-size:14px;">'
                f'👤 **{user["email"]}**</div>',
                unsafe_allow_html=True,
            )

            # API Key输入
            st.text_input(
                label="🔑 智谱AI API Key",
                key="user_api_key",
                placeholder="输入您的智谱AI API Key",
                help="请输入从 https://open.bigmodel.cn/ 获取的API Key",
                type="password"
            )

            # API Key验证状态
            if st.session_state.get("user_api_key"):
                with st.spinner("验证API Key..."):
                    if validate_zhipu_api_key(st.session_state.user_api_key):
                        st.success("✅ API Key 有效")
                    else:
                        st.error("❌ API Key 无效，请检查后重试")

            # 激活码信息
            if user.get('activation_code'):
                st.markdown(
                    f'<div style="background:#d1ecf1;padding:10px;border-radius:6px;'
                    f'text-align:center;font-size:12px; margin-top:10px;">'
                    f'激活码: {user["activation_code"][:10]}...</div>',
                    unsafe_allow_html=True,
                )

            # 使用次数
            st.divider()
            remaining = get_remaining_count(user['id'])
            st.metric("今日剩余次数", remaining if remaining != -1 else "无限制")

            # 激活码输入
            st.text_input(
                label="🎯 输入激活码",
                key="activation_code",
                placeholder="例如：TCGEN-PRO-2026A",
                help="输入从面包多购买的激活码，激活后无限次使用",
            )

            activate_btn = st.button("✅ 激活", use_container_width=True)

            if activate_btn:
                code = st.session_state.get("activation_code", "").strip()
                if not code:
                    st.error("请先输入激活码！")
                else:
                    # 确保user_id有效
                    user_id = user.get('id')
                    if not user_id:
                        st.error("❌ 用户信息异常，请重新登录")
                        logout_user()
                        st.rerun()

                    success, msg = validate_and_activate(code, user_id, user['email'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

            st.divider()

            # 测试类型选择
            test_type = st.selectbox(
                label="测试类型",
                options=TEST_TYPES,
                index=0,
                help="选择需要生成的测试用例类型",
            )

            # 输出风格选择
            output_style = st.selectbox(
                label="输出风格",
                options=OUTPUT_STYLES,
                index=0,
                help="详细模式会给出完整的步骤描述，简洁模式则精简概括",
            )

            st.divider()

            # 生成按钮
            generate_btn = st.button(
                label="🚀 生成测试用例",
                type="primary",
                use_container_width=True,
            )

            # 退出登录
            if st.button("🚪 退出登录", use_container_width=True):
                logout_user()

            # 使用说明
            with st.expander("📖 使用说明"):
                st.markdown(
                    f"""
1. 在右侧文本框中粘贴需求描述；
2. **输入您的智谱AI API Key**（从 https://open.bigmodel.cn/ 获取）
3. 选择测试类型和输出风格；
4. 点击 **生成测试用例** 按钮；
5. 等待模型返回结果，即可查看和下载。

**免费额度**：每个邮箱每天可免费生成 **{FREE_DAILY_LIMIT}** 次。
**解除限制**：[前往面包多购买激活码]({MIANBADUO_URL})，输入后即可无限次使用。
                    """
                )

    # ---------- 主区域 ----------
    if not st.session_state.user:
        # 未登录状态
        st.title(f"{PAGE_ICON} {PAGE_TITLE}")
        st.caption("基于智谱 GLM 大模型，自动生成结构化软件测试用例")

        st.divider()

        # 介绍部分
        st.markdown("""
## 📋 产品介绍

### 核心功能
- **AI 生成测试用例**：基于 GLM-4-Flash 大模型
- **多类型支持**：功能、接口、性能、安全测试
- **灵活输出**：详细/简洁两种风格
- **CSV 导出**：支持 Excel 打开

### 使用流程
1. **注册登录**：使用邮箱注册
2. **获取API Key**：在 https://open.bigmodel.cn/ 注册并获取API Key
3. **免费试用**：每天 5 次免费生成
4. **购买激活码**：解锁无限次使用
5. **生成测试用例**：输入需求，一键生成

### 适用场景
- 软件测试工程师
- 开发人员
- 产品经理
- 项目负责人

        """)

        # 注册引导
        st.markdown("""
## 🚀 立即体验

注册账号即可开始使用，每个邮箱每天免费生成 5 次测试用例。
**注意**：您需要有自己的智谱AI API Key才能使用本工具。
        """)

    else:
        # 已登录状态
        st.title(f"{PAGE_ICON} {PAGE_TITLE}")
        st.caption(f"欢迎回来，{st.session_state.user['email']}")

        # 需求描述输入
        st.caption("💡 提示：需求描述建议控制在7000字符以内，避免超出模型限制")
        requirement = st.text_area(
            label="📝 请粘贴需求描述",
            height=220,
            placeholder=(
                "示例：用户注册功能。用户需要通过邮箱注册账号，"
                "需要输入用户名、邮箱地址和密码。密码要求至少8位，"
                "包含大小写字母和数字。注册成功后发送验证邮件。"
            ),
        )

        # 生成逻辑区域
        if generate_btn:
            # 输入校验
            if not requirement.strip():
                st.error("❌ 请输入需求描述！")
                st.rerun()

            # 清理输入，防止恶意内容
            requirement = sanitize_input(requirement, max_length=7000)

            # 文本长度检查 - 防止上下文窗口溢出
            max_requirement_length = 7000  # 约9K tokens，预留空间给prompt
            if len(requirement) > max_requirement_length:
                st.warning(f"⚠️ 需求描述过长（{len(requirement)}字符），已自动截断到{max_requirement_length}字符")
                requirement = requirement[:max_requirement_length]
                st.rerun()  # 刷新以显示截断后的内容

            # ---- 试用次数校验 ----
            # 确保用户ID有效
            user_id = st.session_state.user.get('id')
            if not user_id:
                st.error("❌ 用户信息异常，请重新登录")
                logout_user()
                st.rerun()

            remaining = get_remaining_count(user_id)

            if remaining == 0:
                st.error(
                    f"❌ 今日免费生成次数已用完（{FREE_DAILY_LIMIT}/{FREE_DAILY_LIMIT}）。"
                    f"请输入激活码，或[前往面包多购买]({MIANBADUO_URL})。"
                )
                st.rerun()

            # 构建 prompt
            prompt = build_prompt(requirement, test_type, output_style)

            # 检查API Key（增强版安全检查）
            user_api_key = st.session_state.get("user_api_key", "").strip()
            if not user_api_key:
                st.error("❌ 请先输入智谱AI API Key！")
                st.rerun()

            # 获取客户端IP
            try:
                import streamlit.web.server.websockets_ws
                client_ip = streamlit.web.server.websockets_ws.get_remote_ip()
            except:
                client_ip = "unknown"

            # 验证API Key安全性
            safe, msg = is_api_key_safe(user_api_key, client_ip)
            if not safe:
                st.error(f"❌ {msg}")

                # 记录安全事件
                log_security_event("api_key_rejected", {
                    'user_id': st.session_state.user['id'],
                    'api_key_hash': hashlib.sha256(user_api_key.encode()).hexdigest()[:8] + "...",
                    'ip_address': client_ip,
                    'reason': msg
                })

                st.rerun()

            # 调用模型（带 loading 提示和安全记录）
            with st.spinner("⏳ 正在调用模型生成测试用例，请稍候……"):
                try:
                    # 记录API Key使用（成功）
                    record_api_key_usage
                    usage_result = record_api_key_usage(
                        user_api_key,
                        client_ip,
                        "Test Case Generation",
                        success=True
                    )

                    # 记录到安全日志
                    # 记录API Key使用成功
                    log_security_event("api_key_used", {
                        'user_id': st.session_state.user['id'],
                        'usage_count': usage_result.get('usage_count', 0),
                        'success_rate': usage_result.get('success_rate', 0),
                        'ip_address': client_ip
                    })

                    result_text = call_glm(user_api_key, prompt)  # 使用用户输入的API Key
                    # 清理模型输出，防止敏感信息泄露
                    result_text = clean_model_output(result_text)
                except Exception as e:
                    error_msg = str(e)
                    # 对常见错误做友好提示
                    if "authentication" in error_msg.lower() or "401" in error_msg:
                        st.error("❌ API Key 无效，请检查后重试。")
                    elif "rate" in error_msg.lower() or "429" in error_msg:
                        st.error("❌ 请求过于频繁，请稍后再试。")
                    elif "timeout" in error_msg.lower():
                        st.error("❌ 请求超时，请检查网络连接后重试。")
                    elif "context window" in error_msg.lower() or "maximum length" in error_msg.lower():
                        st.error("❌ 输入内容过长，已达到模型上限。请简化需求描述或分拆成多个部分。")
                    else:
                        st.error(f"❌ 调用模型失败：{error_msg}")
                    st.rerun()

            # 生成成功，更新使用次数
            increment_usage(st.session_state.user['id'])

            # 解析 Markdown 表格
            df = parse_markdown_table(result_text)

            # ---------- 展示结果 ----------
            st.success("✅ 测试用例生成完成！")

            # 如果表格解析成功，同时展示表格和原始文本
            if not df.empty:
                st.subheader("📊 结构化表格")
                st.dataframe(df, use_container_width=True, hide_index=True)

                # 下载按钮
                csv_bytes = dataframe_to_csv_bytes(df)
                st.download_button(
                    label="📥 下载 CSV 文件",
                    data=csv_bytes,
                    file_name="test_cases.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

                # 同时展示原始 Markdown（折叠）
                with st.expander("📄 查看原始 Markdown 输出"):
                    st.markdown(result_text)
            else:
                # 解析失败时直接展示原始文本
                st.warning("⚠️ 未能解析为标准表格，以下是模型原始输出：")
                st.markdown(result_text)

    # ---------- 评价区域 ----------
    st.divider()
    tab1, tab2 = st.tabs(["🌟 查看评价", "💬 写评价"])

    with tab1:
        show_reviews_section()

    with tab2:
        # 检查用户是否登录
        if st.session_state.user and verify_session():
            show_review_submission(st.session_state.user['id'])
        else:
            st.warning("💡 请先登录后再提交评价")
            with st.expander("登录提示"):
                st.markdown("""
                **如何登录？**
                1. 在页面左侧点击"登录"按钮
                2. 输入您的邮箱和密码
                3. 登录成功后即可提交评价
                """)


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    main()