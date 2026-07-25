"""
软件测试用例生成器 - Web 原型
基于 Python + Streamlit + 智谱 GLM-4-Flash 模型

功能：
  - 根据需求描述自动生成结构化测试用例
  - 每个 API Key 每天免费生成 5 次
  - 超出限制后需输入激活码解除限制
  - 激活码通过面包多售卖
  - 数据存储：Supabase PostgreSQL
"""

import streamlit as st
import pandas as pd
import io
import hashlib
from datetime import date, datetime
from openai import OpenAI
from supabase import create_client, Client


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

# 面包多购买链接（请替换为您的实际商品链接）
MIANBADUO_URL = "https://mbd.pub/your-product-link"

# Supabase 配置（从 Streamlit Secrets 读取）
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]


# ============================================================
# Supabase 初始化
# ============================================================

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# API Key 哈希工具
# ============================================================

def hash_api_key(api_key: str) -> str:
    """
    对 API Key 做 SHA-256 哈希，用于存储时脱敏。
    实际 API Key 明文不会落盘。

    Args:
        api_key: 明文 API Key

    Returns:
        SHA-256 哈希值（十六进制字符串）
    """

    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


# ============================================================
# 使用次数管理（Supabase）
# ============================================================

def get_usage_info(api_key_hash: str) -> dict:
    """
    获取某个 API Key 当日的使用信息。

    返回格式：
        {
            "date": "2026-07-21",   # 当天日期
            "count": 3,             # 今日已用次数
            "activated": false      # 是否已激活（无限次）
        }

    如果记录不存在或日期不是今天，则返回默认值（0次、未激活）。

    Args:
        api_key_hash: API Key 的哈希值

    Returns:
        使用信息字典
    """

    today_str = date.today().isoformat()

    # 查询数据库
    response = supabase.table('usage').select('*').eq('api_key_hash', api_key_hash).execute()

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
        }).eq('api_key_hash', api_key_hash).execute()

    # 确保字段完整
    record.setdefault("count", 0)
    record.setdefault("activated", False)

    return record


def increment_usage(api_key_hash: str) -> None:
    """
    将指定 API Key 的今日使用次数 +1，并更新到数据库。

    Args:
        api_key_hash: API Key 的哈希值
    """

    info = get_usage_info(api_key_hash)
    new_count = info.get("count", 0) + 1

    # 使用 upsert：如果记录存在则更新，不存在则插入
    supabase.table('usage').upsert({
        "api_key_hash": api_key_hash,
        "date": info["date"],
        "count": new_count,
        "activated": info.get("activated", False)
    }).execute()


def set_activated(api_key_hash: str) -> None:
    """
    将指定 API Key 标记为已激活（无限次使用）。

    Args:
        api_key_hash: API Key 的哈希值
    """

    today_str = date.today().isoformat()

    # 检查是否有记录
    response = supabase.table('usage').select('*').eq('api_key_hash', api_key_hash).execute()

    if response.data:
        # 更新现有记录
        supabase.table('usage').update({
            "activated": True,
            "date": today_str,
            "count": 0  # 激活后重置今日次数
        }).eq('api_key_hash', api_key_hash).execute()
    else:
        # 插入新记录
        supabase.table('usage').insert({
            "api_key_hash": api_key_hash,
            "date": today_str,
            "count": 0,
            "activated": True
        }).execute()


# ============================================================
# 激活码管理（Supabase）
# ============================================================

def validate_and_activate(code: str, api_key_hash: str) -> tuple[bool, str]:
    """
    验证激活码并绑定到当前 API Key。

    Args:
        code:          用户输入的激活码
        api_key_hash:  当前 API Key 的哈希值

    Returns:
        (是否成功, 提示消息)
    """

    code = code.strip().upper()

    # 查询激活码
    response = supabase.table('activation_codes').select('*').eq('code', code).execute()

    # 激活码不存在
    if not response.data:
        return False, "❌ 激活码无效，请检查后重试。"

    code_info = response.data[0]

    # 激活码已被使用
    if code_info.get("used", False):
        used_by = code_info.get("used_by", "")
        if used_by == api_key_hash:
            return False, "⚠️ 该激活码已被当前账号使用过，无需重复激活。"
        else:
            return False, "❌ 该激活码已被其他账号使用。"

    # 激活码有效，执行激活
    supabase.table('activation_codes').update({
        "used": True,
        "used_by": api_key_hash,
        "used_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }).eq('code', code).execute()

    # 标记 API Key 为已激活
    set_activated(api_key_hash)

    return True, "✅ 激活成功！现已解除生成次数限制。"


def is_key_activated(api_key_hash: str) -> bool:
    """
    检查 API Key 是否已激活（不受每日次数限制）。

    Args:
        api_key_hash: API Key 的哈希值

    Returns:
        是否已激活
    """

    info = get_usage_info(api_key_hash)
    return info.get("activated", False)


def get_remaining_count(api_key_hash: str) -> int:
    """
    获取今日剩余可生成次数。

    已激活的 Key 返回 -1 表示无限制。

    Args:
        api_key_hash: API Key 的哈希值

    Returns:
        剩余次数；-1 表示无限制
    """

    info = get_usage_info(api_key_hash)

    if info.get("activated", False):
        return -1  # 无限制

    used = info.get("count", 0)
    return max(0, FREE_DAILY_LIMIT - used)


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
# 侧边栏：使用次数与激活码 UI
# ============================================================

def render_usage_sidebar(api_key_hash: str) -> None:
    """
    在侧边栏渲染使用次数提示和激活码输入区域。

    Args:
        api_key_hash: API Key 的哈希值
    """

    remaining = get_remaining_count(api_key_hash)

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
            success, msg = validate_and_activate(code, api_key_hash)
            if success:
                st.success(msg)
                st.rerun()  # 刷新页面以更新状态
            else:
                st.error(msg)

    # 购买提示（未激活时显示）
    if remaining != -1:
        st.markdown(
            f'<div style="text-align:center;font-size:13px;color:#888;">'
            f'📌 次数不够？[前往面包多购买激活码]({MIANBADUO_URL})</div>',
            unsafe_allow_html=True,
        )


# ============================================================
# Streamlit 页面主体
# ============================================================

def main():
    """应用主入口：页面布局、交互逻辑与结果展示。"""

    # ---------- 页面基础配置 ----------
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="wide",
    )

    # ---------- 侧边栏 ----------
    with st.sidebar:
        st.header("⚙️ 参数配置")

        # API Key 输入（密码框）
        api_key = st.text_input(
            label="智谱 AI API Key",
            type="password",
            placeholder="请输入您的 API Key",
            help="在 open.bigmodel.cn 获取您的 API Key，信息仅在本会话使用，不会上传。",
        )

        st.divider()

        # ---- 使用次数与激活码区域 ----
        # 只有输入了 API Key 才显示（需要 hash 来查询记录）
        if api_key:
            render_usage_sidebar(hash_api_key(api_key))
        else:
            st.info("👆 请先输入 API Key 以查看使用次数")

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

        # 使用说明
        st.divider()
        with st.expander("📖 使用说明"):
            st.markdown(
                f"""
1. 在右侧文本框中粘贴需求描述；
2. 在左侧配置 API Key、测试类型和输出风格；
3. 点击 **生成测试用例** 按钮；
4. 等待模型返回结果，即可查看和下载。

**免费额度**：每个 API Key 每天可免费生成 **{FREE_DAILY_LIMIT}** 次。
**解除限制**：[前往面包多购买激活码]({MIANBADUO_URL})，输入后即可无限次使用。
                """
            )

    # ---------- 主区域 ----------
    st.title(f"{PAGE_ICON} {PAGE_TITLE}")
    st.caption("基于智谱 GLM 大模型，自动生成结构化软件测试用例")

    # 需求描述输入
    requirement = st.text_area(
        label="📝 请粘贴需求描述",
        height=220,
        placeholder=(
            "示例：用户注册功能。用户需要通过邮箱注册账号，"
            "需要输入用户名、邮箱地址和密码。密码要求至少8位，"
            "包含大小写字母和数字。注册成功后发送验证邮件。"
        ),
    )

    # ---------- 生成逻辑 ----------
    if generate_btn:
        # 输入校验
        if not api_key:
            st.error("❌ 请先在侧边栏输入智谱 AI 的 API Key！")
            return
        if not requirement.strip():
            st.error("❌ 请输入需求描述！")
            return

        # ---- 试用次数校验 ----
        api_key_hash = hash_api_key(api_key)
        remaining = get_remaining_count(api_key_hash)

        if remaining == 0:
            st.error(
                f"❌ 今日免费生成次数已用完（{FREE_DAILY_LIMIT}/{FREE_DAILY_LIMIT}）。"
                f"请在侧边栏输入激活码，或[前往面包多购买]({MIANBADUO_URL})。"
            )
            return

        # 构建 prompt
        prompt = build_prompt(requirement, test_type, output_style)

        # 调用模型（带 loading 提示）
        with st.spinner("⏳ 正在调用模型生成测试用例，请稍候……"):
            try:
                result_text = call_glm(api_key, prompt)
            except Exception as e:
                error_msg = str(e)
                # 对常见错误做友好提示
                if "authentication" in error_msg.lower() or "401" in error_msg:
                    st.error("❌ API Key 无效或已过期，请检查后重试。")
                elif "rate" in error_msg.lower() or "429" in error_msg:
                    st.error("❌ 请求过于频繁，请稍后再试。")
                elif "timeout" in error_msg.lower():
                    st.error("❌ 请求超时，请检查网络连接后重试。")
                else:
                    st.error(f"❌ 调用模型失败：{error_msg}")
                return

        # 生成成功，更新使用次数（已激活的不计数，但调用也无妨）
        if remaining != -1:
            increment_usage(api_key_hash)

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


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    main()