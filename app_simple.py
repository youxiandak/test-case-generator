"""
软件测试用例生成器 - 简化版本（用于部署测试）
基于 Python + Streamlit
"""

import streamlit as st
import pandas as pd
import io
import hashlib
import time
from datetime import date, datetime, timedelta
from openai import OpenAI

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

# 试用限制相关常量
# 每个API Key每天免费生成次数
FREE_DAILY_LIMIT = 5

# Supabase 配置（从 Streamlit Secrets 读取）
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

# ============================================================
# 初始化会话状态
# ============================================================

def init_session_state():
    """初始化 session state"""
    if 'user' not in st.session_state:
        st.session_state.user = None

# ============================================================
# API Key 安全管理函数（简化版本）
# ============================================================

def validate_api_key_format(api_key: str) -> tuple[bool, str]:
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

def is_api_key_safe(api_key: str) -> tuple[bool, str]:
    """检查API Key是否安全可用"""
    # 简化版本的安全检查
    if not api_key or len(api_key.strip()) == 0:
        return False, "API Key不能为空"

    # 基本格式验证
    valid, msg = validate_api_key_format(api_key)
    if not valid:
        return False, msg

    return True, "API Key安全"

# ============================================================
# 简单的模型调用函数
# ============================================================

def call_glm(api_key: str, prompt: str, model: str = DEFAULT_MODEL) -> str:
    """调用智谱 GLM 模型，返回生成的文本"""

    # 先验证API Key
    valid, msg = validate_api_key_format(api_key)
    if not valid:
        raise Exception(f"API Key无效: {msg}")

    if not is_api_key_safe(api_key)[0]:
        raise Exception("API Key安全检查失败")

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
    """将模型返回的 Markdown 表格文本解析为 pandas DataFrame"""

    lines = md_text.strip().split("\n")

    # 筛选出表格行
    table_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and not all(ch in "|-: " for ch in stripped):
            table_lines.append(stripped)

    if len(table_lines) < 2:
        return pd.DataFrame()

    # 解析表头
    headers = [cell.strip() for cell in table_lines[0].split("|") if cell.strip()]

    # 解析数据行
    rows = []
    for line in table_lines[1:]:
        cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        if len(cells) == len(headers):
            rows.append(cells)

    df = pd.DataFrame(rows, columns=headers)
    return df

# ============================================================
# CSV 下载辅助函数
# ============================================================

def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """将 DataFrame 转换为 UTF-8 BOM 编码的 CSV 字节数据"""
    output = io.StringIO()
    df.to_csv(output, index=False, encoding="utf-8")
    csv_str = output.getvalue()
    return ("﻿" + csv_str).encode("utf-8")

# ============================================================
# 主应用
# ============================================================

def main():
    """应用主入口：页面布局、交互逻辑与结果展示。"""

    # 初始化 session state
    init_session_state()

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
            st.markdown("### 📄 应用信息")
            st.markdown("- 基于 GLM-4-Flash 大模型")
            st.markdown("- 每个邮箱每天 5 次免费")
            st.markdown("- 简化版本测试")
        else:
            # 显示用户信息
            st.markdown(
                f'<div style="background:#e8f4f8;padding:10px;border-radius:6px;'
                f'text-align:center;font-size:14px;">'
                f'👤 **{st.session_state.user["email"]}**</div>',
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
                    if is_api_key_safe(st.session_state.user_api_key)[0]:
                        st.success("✅ API Key 有效")
                    else:
                        st.error("❌ API Key 无效，请检查后重试")

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
                st.session_state.user = None
                st.rerun()

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
1. **注册登录**：使用邮箱注册（简化版）
2. **获取API Key**：在 https://open.bigmodel.cn/ 注册并获取API Key
3. **生成测试用例**：输入需求，一键生成

        """)

        # 注册引导
        st.markdown("""
## 🚀 立即体验

注册账号即可开始使用，每个邮箱每天免费生成 5 次测试用例。
**注意**：您需要有自己的智谱AI API Key才能使用本工具。
        """)

        # 简单的登录表单
        st.subheader("🔐 快速登录")
        email = st.text_input("邮箱地址")
        password = st.text_input("密码", type="password")

        if st.button("登录", use_container_width=True):
            if email and password:
                # 简单的登录逻辑（实际应该连接数据库）
                st.session_state.user = {
                    'id': 1,
                    'email': email,
                    'created_at': datetime.now().isoformat()
                }
                st.success("登录成功！")
                st.rerun()
            else:
                st.error("请填写邮箱和密码")

    else:
        # 已登录状态
        st.title(f"{PAGE_ICON} {PAGE_TITLE}")
        st.caption(f"欢迎回来，{st.session_state.user['email']}")

        # 需求描述输入
        st.caption("💡 提示：需求描述建议控制在7000字符以内")
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

            # 文本长度检查
            max_requirement_length = 7000
            if len(requirement) > max_requirement_length:
                st.warning(f"⚠️ 需求描述过长（{len(requirement)}字符），已自动截断")
                requirement = requirement[:max_requirement_length]
                st.rerun()

            # 检查API Key
            user_api_key = st.session_state.get("user_api_key", "").strip()
            if not user_api_key:
                st.error("❌ 请先输入智谱AI API Key！")
                st.rerun()

            # 调用模型
            with st.spinner("⏳ 正在调用模型生成测试用例，请稍候……"):
                try:
                    # 构建prompt
                    prompt = f"""你是一位资深软件测试工程师，请根据以下需求描述，生成功能测试用例。

## 需求描述
{requirement}

## 输出要求
1. 请直接输出 Markdown 表格，不要输出多余的解释文字。
2. 表格列依次为：| 用例编号 | 模块 | 测试标题 | 前置条件 | 测试步骤 | 预期结果 |
3. 共生成 8-12 条用例，需覆盖正常场景、异常场景和边界场景。
4. 用例编号格式为 TC-001、TC-002 ……

请直接输出表格："""

                    result_text = call_glm(user_api_key, prompt)

                except Exception as e:
                    error_msg = str(e)
                    if "authentication" in error_msg.lower() or "401" in error_msg:
                        st.error("❌ API Key 无效，请检查后重试。")
                    elif "rate" in error_msg.lower() or "429" in error_msg:
                        st.error("❌ 请求过于频繁，请稍后再试。")
                    elif "timeout" in error_msg.lower():
                        st.error("❌ 请求超时，请检查网络连接后重试。")
                    else:
                        st.error(f"❌ 调用模型失败：{error_msg}")
                    st.rerun()

            # 生成成功
            st.success("✅ 测试用例生成完成！")

            # 解析 Markdown 表格
            df = parse_markdown_table(result_text)

            # 展示结果
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

                # 同时展示原始 Markdown
                with st.expander("📄 查看原始 Markdown 输出"):
                    st.markdown(result_text)
            else:
                # 解析失败时直接展示原始文本
                st.warning("⚠️ 未能解析为标准表格，以下是模型原始输出：")
                st.markdown(result_text)

    # 评价区域
    st.divider()
    st.subheader("🌟 用户反馈")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**感谢使用！**")
        st.write("如果您有任何建议或问题，欢迎通过以下方式联系我们：")
        st.write("- 邮箱：support@example.com")
        st.write("- GitHub Issues")

    with col2:
        with st.form("feedback_form"):
            rating = st.slider("评分", 1, 5, 3)
            feedback = st.text_area("反馈意见")

            if st.form_submit_button("提交反馈"):
                if feedback.strip():
                    st.success("感谢您的反馈！")
                else:
                    st.error("请填写反馈意见")

# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    main()