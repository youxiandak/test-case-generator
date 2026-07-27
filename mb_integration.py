"""
面包多 (mbd.pub) API 集成模块
用于验证订单状态、获取订单信息
"""

import requests


# ============================================================
# 配置
# ============================================================

MBD_API_BASE = "https://x.mbd.pub/api"
MBD_DEVELOPER_KEY = "6777118:1woJAb:Q7OGT889kYAG0nyLxd8a_kfr4hsWzZPgMZgouwQpJU4"


# ============================================================
# 订单查询
# ============================================================

def get_order_detail(order_id: str) -> dict:
    """
    通过订单号获取订单详细信息

    Args:
        order_id: 面包多订单号

    Returns:
        {
            'success': bool,
            'order_id': str,
            'state': str,  # 'success', 'cancel', 'invalid'
            'orderamount': float,
            'ordertime': int,
            'message': str
        }
    """
    try:
        url = f"{MBD_API_BASE}/order-detail"
        headers = {
            'x-token': MBD_DEVELOPER_KEY
        }
        params = {
            'order_id': order_id
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()

            if data.get('code') == 200:
                result = data.get('result', {})
                return {
                    'success': True,
                    'order_id': result.get('orderid'),
                    'state': result.get('state'),  # 'success' = 已支付
                    'orderamount': result.get('orderamount'),
                    'ordertime': result.get('ordertime'),
                    'message': '订单查询成功'
                }
            elif data.get('code') == 403:
                return {
                    'success': False,
                    'message': 'API认证失败，请检查开发者key'
                }
            else:
                error_info = data.get('error_info', '未知错误')
                return {
                    'success': False,
                    'message': f'API错误: {error_info}'
                }
        else:
            return {
                'success': False,
                'message': f'HTTP请求失败: {response.status_code}'
            }

    except requests.exceptions.Timeout:
        return {
            'success': False,
            'message': '请求超时，请稍后重试'
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'查询失败: {str(e)}'
        }


def verify_order_paid(order_id: str) -> tuple[bool, str]:
    """
    验证订单是否已支付

    Args:
        order_id: 面包多订单号

    Returns:
        (是否已支付, 消息)
    """
    result = get_order_detail(order_id)

    if not result['success']:
        return False, result['message']

    state = result.get('state')

    if state == 'success':
        return True, '✅ 订单已支付，激活成功'
    elif state == 'cancel':
        return False, '❌ 订单已取消'
    elif state == 'invalid':
        return False, '❌ 订单已过期'
    else:
        return False, f'❌ 未知订单状态: {state}'


# ============================================================
# 兼容旧代码的函数（已弃用，但保留以避免报错）
# ============================================================

def create_purchase_order(user_id: int) -> dict:
    """
    已弃用：创建购买订单功能
    现在直接跳转到面包多商品链接即可
    """
    return {
        'success': False,
        'message': '请直接访问面包多商品页面购买：https://mbd.pub/o/bread/YZaUlppuag=='
    }


def get_user_orders(user_id: int) -> list:
    """
    已弃用：获取用户订单列表
    """
    return []


def get_statistics() -> dict:
    """
    已弃用：获取统计数据
    """
    return {
        'total_orders': 0,
        'total_revenue': 0
    }