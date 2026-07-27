#!/usr/bin/env python3
"""
测试验证码发送功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from verification_service import send_verification

def test_verification():
    """测试验证码发送"""
    email = input("请输入测试邮箱地址: ")

    print(f"\n正在向 {email} 发送验证码...")

    result = send_verification(email, "register")

    if result['success']:
        print("✅ 验证码发送成功！")
        print("请检查邮箱，输入收到的验证码进行测试。")

        # 测试验证码验证
        code = input("\n请输入收到的6位验证码: ")
        from verification_service import check_code

        check_result = check_code(email, code, "register")
        if check_result['success']:
            print("✅ 验证码验证成功！")
        else:
            print(f"❌ 验证码验证失败: {check_result['message']}")
    else:
        print(f"❌ 验证码发送失败: {result['message']}")

if __name__ == "__main__":
    test_verification()