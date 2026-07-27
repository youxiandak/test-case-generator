"""
验证码服务模拟器
实际使用时需要替换为真实的服务商 API
支持阿里云、腾讯云、SendGrid 等
"""

import random
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional
import logging


# ============================================================
# 配置
# ============================================================

# 阿里云短信配置（需要开通短信服务）
ALIYUN_ACCESS_KEY_ID = "你的AccessKey ID"
ALIYUN_ACCESS_KEY_SECRET = "你的AccessKey Secret"
ALIYUN_SIGN_NAME = "软件测试用例生成器"
ALIYUN_TEMPLATE_CODE = "SMS_123456789"  # 阿里云短信模板

# 邮件配置 - QQ邮箱
SMTP_SERVER = "smtp.qq.com"  # QQ邮箱SMTP服务器
SMTP_PORT = 587
SMTP_USERNAME = "1715678582@qq.com"  # 你的QQ邮箱
SMTP_PASSWORD = "ghhgqinabnamccae"  # QQ邮箱需要使用授权码，不是登录密码
FROM_EMAIL = "1715678582@qq.com"

# 验证码有效期（分钟）
CODE_EXPIRE_MINUTES = 10

# 验证码长度
CODE_LENGTH = 6

# 存储验证码（实际应使用数据库）
verification_codes: Dict[str, Dict] = {}


# ============================================================
# 工具函数
# ============================================================

def generate_code(length: int = CODE_LENGTH) -> str:
    """生成随机验证码"""
    return "".join([str(random.randint(0, 9)) for _ in range(length)])


def send_email_verification(email: str, code: str) -> bool:
    """
    发送邮箱验证码

    Args:
        email: 目标邮箱
        code: 验证码

    Returns:
        是否发送成功
    """
    try:
        # 创建邮件
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = email
        msg['Subject'] = "验证您的邮箱 - 软件测试用例生成器"

        # 邮件内容
        body = f"""
        您好！

        验证码是：{code}

        请在 {CODE_EXPIRE_MINUTES} 分钟内使用。
        如果不是您本人的操作，请忽略此邮件。

        —— 软件测试用例生成器
        """

        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # 发送邮件
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)

        text = msg.as_string()
        server.sendmail(FROM_EMAIL, email, text)
        server.quit()

        logging.info(f"验证码已发送到 {email}: {code}")
        return True

    except Exception as e:
        logging.error(f"发送验证码失败: {e}")
        return False


def send_sms_verification(phone: str, code: str) -> bool:
    """
    发送短信验证码（示例，需要实际集成）

    Args:
        phone: 手机号
        code: 验证码

    Returns:
        是否发送成功
    """
    try:
        # 这里应该集成阿里云、腾讯云等短信服务
        # 以下是示例代码结构

        # import requests
        # data = {
        #     'AccessKeyId': ALIYUN_ACCESS_KEY_ID,
        #     'Action': 'SendSms',
        #     'PhoneNumbers': phone,
        #     'SignName': ALIYUN_SIGN_NAME,
        #     'TemplateCode': ALIYUN_TEMPLATE_CODE,
        #     'TemplateParam': f'{{"code": "{code}"}}',
        #     'Version': '2017-05-25'
        # }
        # response = requests.post('https://dysmsapi.aliyuncs.com/', data=data)
        # return response.status_code == 200

        print(f"模拟发送短信到 {phone}: {code}")
        return True

    except Exception as e:
        logging.error(f"发送短信验证码失败: {e}")
        return False


def store_verification_code(email: str, code: str, code_type: str = "register") -> bool:
    """
    存储验证码到内存（实际应存储到数据库）

    Args:
        email: 邮箱
        code: 验证码
        code_type: 验证码类型（register/login）

    Returns:
        是否存储成功
    """
    try:
        verification_codes[email] = {
            'code': code,
            'type': code_type,
            'expires_at': time.time() + CODE_EXPIRE_MINUTES * 60
        }
        return True
    except Exception as e:
        logging.error(f"存储验证码失败: {e}")
        return False


def verify_code(email: str, code: str, code_type: str = "register") -> bool:
    """
    验证邮箱验证码

    Args:
        email: 邮箱
        code: 用户输入的验证码
        code_type: 验证码类型

    Returns:
        验证是否成功
    """
    try:
        if email not in verification_codes:
            return False

        stored = verification_codes[email]

        # 检查类型
        if stored['type'] != code_type:
            return False

        # 检查有效期
        if time.time() > stored['expires_at']:
            return False

        # 检查验证码
        if stored['code'] != code:
            return False

        # 标记为已使用
        verification_codes[email]['used'] = True

        return True

    except Exception as e:
        logging.error(f"验证码验证失败: {e}")
        return False


def is_code_expired(email: str) -> bool:
    """检查验证码是否过期"""
    if email not in verification_codes:
        return True

    return time.time() > verification_codes[email]['expires_at']


# ============================================================
# 接口函数（供应用调用）
# ============================================================

def send_verification(email: str, code_type: str = "register") -> Dict[str, any]:
    """
    发送验证码

    Args:
        email: 邮箱地址
        code_type: 验证码类型（register/login）

    Returns:
        {'success': bool, 'message': str}
    """
    try:
        # 检查是否频繁发送（防止短信轰炸）
        if email in verification_codes and not is_code_expired(email):
            remaining = verification_codes[email]['expires_at'] - time.time()
            if remaining > 60:  # 1分钟内不能重复发送
                return {
                    'success': False,
                    'message': f'验证码已发送，请{int(remaining/60)}秒后再试'
                }

        # 生成验证码
        code = generate_code()

        # 发送验证码
        # 优先发邮件，其次短信
        success = send_email_verification(email, code)

        # 如果邮件失败，可以尝试发送短信
        if not success:
            print("邮件发送失败，尝试短信...")
            success = send_sms_verification(email, code)

        # 存储验证码
        if success:
            store_verification_code(email, code, code_type)
            return {
                'success': True,
                'message': '验证码已发送'
            }
        else:
            return {
                'success': False,
                'message': '发送失败，请检查邮箱/手机号是否正确'
            }

    except Exception as e:
        logging.error(f"发送验证码时出错: {e}")
        return {
            'success': False,
            'message': '发送失败，请稍后重试'
        }


def check_code(email: str, code: str, code_type: str = "register") -> Dict[str, any]:
    """
    验证验证码

    Args:
        email: 邮箱
        code: 用户输入的验证码
        code_type: 验证码类型

    Returns:
        {'success': bool, 'message': str, 'expired': bool}
    """
    try:
        if email not in verification_codes:
            return {
                'success': False,
                'message': '请先发送验证码',
                'expired': False
            }

        if is_code_expired(email):
            return {
                'success': False,
                'message': '验证码已过期',
                'expired': True
            }

        if verify_code(email, code, code_type):
            return {
                'success': True,
                'message': '验证成功',
                'expired': False
            }
        else:
            return {
                'success': False,
                'message': '验证码错误',
                'expired': False
            }

    except Exception as e:
        logging.error(f"验证验证码时出错: {e}")
        return {
            'success': False,
            'message': '验证失败，请稍后重试',
            'expired': False
        }


# ============================================================
# 定时清理过期验证码
# ============================================================

def cleanup_expired_codes():
    """清理过期验证码"""
    global verification_codes

    current_time = time.time()
    emails_to_remove = []

    for email, data in verification_codes.items():
        if current_time > data['expires_at']:
            emails_to_remove.append(email)

    for email in emails_to_remove:
        del verification_codes[email]

    if emails_to_remove:
        logging.info(f"已清理 {len(emails_to_remove)} 个过期验证码")


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    # 测试发送验证码
    result = send_verification("test@example.com", "register")
    print(result)

    # 模拟用户输入验证码
    code = input("请输入收到的验证码: ")
    check_result = check_code("test@example.com", code, "register")
    print(check_result)