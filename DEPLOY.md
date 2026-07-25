# Streamlit Community Cloud 部署指南

## 前置准备

完成以下步骤后再部署。

---

## 步骤 1：注册 Supabase

1. 打开 [supabase.com](https://supabase.com)
2. 点击 **Start your project**
3. 注册/登录账号（免费计划）
4. 创建新项目：
   - Project Name: `test-case-generator`
   - Database Password: 设置一个强密码（记住它）
   - Region: 选择 `Southeast Asia (Singapore)` 或离你近的

---

## 步骤 2：初始化数据库

1. 进入项目 → 左侧菜单 **SQL Editor**
2. 点击 **New query**
3. 复制 `init_db.sql` 的全部内容
4. 粘贴到编辑器
5. 点击 **Run** 执行

成功后会显示两个表已创建：`usage` 和 `activation_codes`

---

## 步骤 3：获取 Supabase 凭证

1. 进入项目 → 左侧菜单 **Settings** → **API**
2. 复制以下两项：

| 字段 | 示例 | 说明 |
|---|---|---|
| **Project URL** | `https://abc123xyz.supabase.co | - |
| **anon public** | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` | 以 `eyJ` 开头 |

---

## 步骤 4：推送代码到 GitHub

```bash
# 初始化 git
cd C:\Users\lenovo
git init

# 添加文件
git add app.py requirements.txt init_db.sql

# 提交
git commit -m "feat: 使用 Supabase 存储数据"

# 创建 GitHub 仓库（如果没有）后执行
git remote add origin https://github.com/你的用户名/test-case-generator.git
git branch -M main
git push -u origin main
```

---

## 步骤 5：在 Streamlit Cloud 部署

1. 打开 [share.streamlit.io](https://share.streamlit.io)
2. 点击 **New app**
3. 填写：
   - **Repository**: 选择你的 GitHub 仓库
   - **Branch**: `main`
   - **Main file path**: `app.py`
4. 点击 **Advanced settings** → **Secrets**
5. 添加两个 secrets：

   | Key | Value |
   |---|---|
   | `SUPABASE_URL` | 你的 Project URL |
   | `SUPABASE_KEY` | 你的 anon public key |

6. 点击 **Deploy**

等待部署完成（约 1-2 分钟），成功后会显示访问地址：
```
https://你的用户名-test-case-generator.streamlit.app
```

---

## 步骤 6：配置自定义域名（可选）

如果你有域名（如 `youxiandak.com`），可以绑定：

1. 在 Streamlit Cloud → 你的应用 → **Settings** → **Custom domain**
2. 输入域名 → 点击 **Add domain**
3. 按提示在域名注册商添加 CNAME 记录：
   ```
   类型: CNAME
   主机记录: @
   记录值: 你的用户名-test-case-generator.streamlit.app
   ```
4. 等 DNS 生效（10-30 分钟）

---

## 完成！

现在你的应用已上线，数据持久保存在 Supabase，每次部署不会丢失。

---

## 管理激活码

在 Supabase 数据库管理激活码：

1. 进入项目 → **Table Editor** → **activation_codes** 表
2. 可以直接添加/修改激活码
3. `used=True` 的激活码表示已使用

---

## 免费额度参考

| 服务 | 免费额度 |
|---|---|
| **Supabase** | 500MB 数据库 + 1GB 文件存储 + 2GB 带宽/月 |
| **Streamlit Community Cloud** | 无限应用 + 每个应用 1GB 内存 |
| **智谱 GLM-4-Flash** | 首月免费，后续按 tokens 计费 |