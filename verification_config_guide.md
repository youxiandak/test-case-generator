# 验证码服务配置指南

## 快速配置方案

### 方案1：使用免费邮件服务（推荐新手）

#### Gmail配置（免费，适合测试）
```python
# verification_service.py 配置
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "your@gmail.com"
SMTP_PASSWORD = "16位应用专用密码"  # 不是登录密码！
FROM_EMAIL = "your@gmail.com"
```

#### 配置步骤：
1. [开启Gmail两步验证](https://myaccount.google.com/security)
2. [生成应用密码](https://myaccount.google.com/apppasswords)
   - 选择"应用"：邮件
   - 选择"设备"：其他（填写"验证码服务"）
   - 复制生成的16位密码
3. 替换代码中的配置

#### 注意事项：
- Gmail可能有发送频率限制（每天100封）
- 收件箱可能会被标记为垃圾邮件
- 测试时建议使用专门的测试邮箱

### 方案2：使用专业邮件服务商

#### 推荐服务商：
1. **SendGrid**（免费100封/天）
   - 注册：https://sendgrid.com
   - 配置SMTP服务器信息
   
2. **Mailgun**（免费5000封/月）
   - 注册：https://www.mailgun.com
   - 获取API Key和SMTP配置

3. **阿里云邮件推送**（免费40封/天）
   - 注册：https://www.aliyun.com/product/directmail

#### SendGrid配置示例：
```python
# SendGrid SMTP配置
SMTP_SERVER = "smtp.sendgrid.net"
SMTP_PORT = 587
SMTP_USERNAME = "apikey"
SMTP_PASSWORD = "SG.your_api_key_here"
FROM_EMAIL = "your@verified-domain.com"
```

### 方案3：使用短信服务

#### 推荐服务商：
1. **阿里云短信**（免费100条/天）
   - 价格：0.05元/条
   - 文档：https://help.aliyun.com/product/44282.html

2. **腾讯云短信**（免费100条/天）
   - 价格：0.04元/条
   - 文档：https://cloud.tencent.com/document/product/382

#### 阿里云配置示例：
```python
# verification_service.py 阿里云配置
ALIYUN_ACCESS_KEY_ID = "LTAI5t6Nxxxxxxxx"
ALIYUN_ACCESS_KEY_SECRET = "xxxxxxxx"
ALIYUN_SIGN_NAME = "您的应用名称"
ALIYUN_TEMPLATE_CODE = "SMS_123456789"

# 在 send_sms_verification 函数中实现
import requests

def send_sms_verification(phone: str, code: str) -> bool:
    url = "https://dysmsapi.aliyuncs.com/"
    params = {
        'Action': 'SendSms',
        'PhoneNumbers': phone,
        'SignName': ALIYUN_SIGN_NAME,
        'TemplateCode': ALIYUN_TEMPLATE_CODE,
        'TemplateParam': f'{{"code": "{code}"}}',
        'Version': '2017-05-25',
        'AccessKeyId': ALIYUN_ACCESS_KEY_ID,
        'Timestamp': datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        'Signature': generate_signature(params, ALIYUN_ACCESS_KEY_SECRET)
    }
    response = requests.get(url, params=params)
    return response.json().get('Code') == 'OK'
```

## 生产环境部署建议

### 1. 使用环境变量管理配置
```python
import os

# 从环境变量读取配置
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
```

### 2. Streamlit Secrets配置
在 `.streamlit/secrets.toml` 中：
```toml
[smtp]
server = "smtp.gmail.com"
username = "your@gmail.com"
password = "your_app_password"
from_email = "your@gmail.com"
```

### 3. 监控和日志
```python
# 添加发送记录
def log_verification_attempt(email: str, success: bool):
    # 记录到数据库或日志文件
    pass
```

## 故障排查

### 常见问题：
1. **发送失败**：检查SMTP配置是否正确
2. **到达率低**：使用专业邮件服务商
3. **延迟**：添加重试机制
4. **被拦截**：配置SPF、DKIM记录

### 测试方法：
```python
# 测试邮件发送
if __name__ == "__main__":
    result = send_verification("test@example.com", "register")
    print(result)
```

## 成本估算

### 邮件服务：
- Gmail：免费（但有限制）
- SendGrid：免费100封/天
- 阿里云：0.05元/封

### 短信服务：
- 阿里云：0.05元/条
- 腾讯云：0.04元/条

### 建议：
- 测试期使用Gmail免费版
- 生产环境使用阿里云/腾讯云
- 预估1000用户/天，月成本约150-300元