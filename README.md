# Email Assist

本地企业邮箱调研/询价助手。当前代码实现的是第一版 MVP 骨架：任务创建、收件人记录、回复匹配规则、截止前催发判定、附件归档、附件本地解析、OpenAI-compatible API 请求封装、Excel/ZIP 导出和基础 Web/API。

## 技术栈

- Python 3.11+
- FastAPI
- SQLite
- Jinja2
- openpyxl
- httpx
- pytest

## 本地安装

```bash
uv sync --extra dev
```

如果沙箱环境无法写入 `uv` 用户缓存，可以直接使用项目内虚拟环境执行命令：

```bash
.venv/bin/python -m pytest -q
```

## 启动

开发模式：

```bash
.venv/bin/uvicorn app.main:app --reload
```

macOS 本地 App 模式：

```bash
.venv/bin/python scripts/run_macos_app.py
```

打开：

```text
http://127.0.0.1:8000
```

App 模式会自动选择可用端口并打开浏览器，数据默认保存在：

```text
~/Library/Application Support/Email Assist
```

## 已实现能力

- 任务列表和设置页。
- 左侧侧栏只保留任务总览和流程提示；创建任务、连接配置等动作集中在主工作区，避免重复入口。
- macOS 本地 App 启动器：自动选择端口、启动服务、打开浏览器、使用用户级数据目录。
- 设置向导：SMTP、IMAP、OpenAI-compatible API 配置保存。
- 连接测试：SMTP 登录测试、IMAP 登录测试、AI API ping 测试。
- `POST /api/campaigns` 创建调研/询价任务。
- `GET /api/campaigns` 查看任务列表。
- `GET /api/campaigns/{campaign_id}` 查看任务和收件人。
- `GET /campaigns/new` 通过页面创建调研任务。
- `GET /campaigns/{campaign_id}` 查看任务详情、收件人状态、发送记录、回复正文和附件。
- `POST /api/campaigns/{campaign_id}/send` 使用已保存 SMTP 配置发送草稿收件人。
- `POST /api/campaigns/{campaign_id}/refresh` 使用 IMAP 拉取近期邮件并匹配回复。
- `POST /api/campaigns/{campaign_id}/reminders/send` 发送截止前提醒邮件，并记录提醒时间。
- `POST /api/campaigns/{campaign_id}/export` 生成 Excel 汇总和 ZIP 包。
- 任务归档：归档后移出活跃任务区，保留查看/导出能力，禁止发送、刷新、认领和附件处理；支持取消归档恢复归档前状态。
- 收件人导入：创建任务页支持粘贴、CSV 和 XLSX，重复邮箱按首次出现保留。
- SQLite 保存任务和收件人。
- 收件人状态机和全部回复判定。
- 逾期判定：已发送/已提醒但超过截止时间仍未回复的收件人会标记为 `overdue`，任务状态同步为 `overdue`。
- 回复匹配：优先线程头，其次发件人 + 任务编号/主题前缀。
- 回复摘要：刷新收件箱时保存回复正文，并生成短摘要用于页面展示和 Excel 导出。
- 催发判定：截止时间前 6 小时，支持自动催发和人工确认两种策略。
- 附件归档：按任务、收件人、回复邮件保存正文、原始邮件和附件。
- 所见即可得：任务内支持预览回复正文、预览附件，并可用本机默认应用打开本地文件。
- 附件本地解析：CSV/XLSX 可直接读取；PDF/Word/图片进入 AI/OCR 处理队列。
- OpenAI-compatible API 客户端：支持 `base_url`、`api_key`、`model`。
- 邮件构造：每个外部收件人单独一封，支持 CC，不把 BCC 写入邮件头。

## 当前边界

- SMTP 真实发送已接入任务详情页，支持正文和任务附件。
- IMAP 刷新已接入任务详情页，拉取近期邮件，支持回复匹配、正文归档和附件归档。
- 截止前 6 小时提醒已接入任务详情页和任务总览；提醒发送后会更新收件人状态，避免重复提醒。
- 联系人库还未做；当前支持手动粘贴收件人，也支持 CSV/XLSX 临时导入。
- 资料工作台：整合在“附件与资料”页签下，按“解析附件 -> AI 识别 -> 导出资料”的业务流程组织。
- 附件 PDF/Word 文本抽取和图片 OCR 当前默认进入 `needs_ai` 状态；点击 `AI 识别待处理附件` 后会在确认后调用已配置的 OpenAI-compatible API。
- 邮箱密码、API Key、邮件正文和附件第一版按本地明文处理；敏感配置保存在本机用户级目录，不要提交到仓库。

## 验证

```bash
.venv/bin/python -m pytest -q
```

当前测试覆盖：

- 任务状态流转。
- 回复匹配。
- 催发窗口和去重。
- 附件归档路径和文件保存。
- CSV/XLSX 解析入口。
- Excel/ZIP 导出。
- SQLite 持久化。
- FastAPI 基础接口。
- 邮件构造。
- OpenAI-compatible API 请求 payload。

## 第一条真实业务验证

1. 打开 `http://127.0.0.1:8000/settings`，确认 SMTP/IMAP/AI API 测试均通过。
2. 打开 `http://127.0.0.1:8000/campaigns/new`。
3. 创建一个只发给自己或测试邮箱的任务。
4. 外部收件人按行填写，格式为：

```text
test@example.com,测试公司,测试联系人
```

也可以上传 CSV/XLSX 收件人文件，表头可使用 `email/邮箱`、`company/公司`、`name/联系人`。

5. 保存任务后进入详情页。
6. 点击 `发送草稿收件人`。
7. 查看详情页中收件人状态是否变为 `sent`，并确认目标邮箱收到邮件。
8. 使用测试收件人回复邮件并附带一个小附件。
9. 回到任务详情页点击 `刷新收件箱`。
10. 查看收件人状态是否变为 `replied`，并在 `回复`、`附件与资料` 中预览正文、打开附件并生成导出包。

真实发信会通过你保存的 SMTP 账号对外发送邮件；建议第一轮只用自己的测试收件人。
