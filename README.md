# nsign

现代 N / 伊兰特N 小程序（ElantraN）自动签到脚本。修复了"发帖、回复内容固定（早上好/帅气）被官方识别封禁"的问题：

- **发帖**：每次内容都不一样 —— 优先调用 LLM 按"真人车主随手发帖"的口吻重新生成；没配 Key 时用内置话题库 + 时间/季节/城市/车况随机组合，贴近车主日常（通勤、跑山、油耗、保养、声浪、赛道日、IONIQ N 资讯…）。
- **回复**：先读取目标帖子详情，按帖子主题（提车/活动/声浪/保养/风景…）生成相关回复，不再见谁都回"帅气"。
- **配图**：发帖自动带图。来源按优先级：
  1. AI 生成（可选，OpenAI 兼容 images 接口），可"顺着社区最近帖子话题"生成新图；
  2. 平台 feed 里已有图片（域名与官方一致，展示最稳）；
  3. Wikimedia Commons 真实伊兰特N 实拍图（免费许可，已校验可访问）；
  4. Picsum 随机风景图（贴合"风景"场景）。
- 多账号同轮跑批自动去重，每次运行内容均不重样。

## 运行环境

- Python 3.8+，依赖 `requests`、`pytz`
- 环境变量 `ELANTRAN_AUTH`（必填，多个账号用 `&` 分隔）、`PUSHPLUS_TOKEN`（可选，推送通知）

## 新增可选配置（GitHub Actions Secrets 里加即可）

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `LLM_API_KEY` | 聊天 LLM Key（OpenAI 兼容接口） | 无（自动用内置话题库） |
| `LLM_BASE_URL` | LLM 接口地址 | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
| `IMG_API_KEY` | AI 生图 Key（OpenAI 兼容 `/images/generations`） | 缺省复用 `LLM_*` |
| `IMG_BASE_URL` | 生图接口地址 | 缺省复用 `LLM_BASE_URL` |
| `IMG_MODEL` | 生图模型（如 SiliconFlow 的 FLUX） | 缺省复用 `LLM_MODEL` |
| `ELANTRAN_UPLOAD_URL` | 平台上图接口（抓包可得，形如 `/home/xxx/upload`）。AI 生成的图会上传到这里再引用，展示最稳 | 无 |
| `IMG_MODE` | `auto` / `feed`（只用平台已有图）/ `remote`（只用外链图）/ `none`（不带图） | `auto` |
| `IMG_ALLOW_REMOTE_AI` | 设为 `1` 时允许直接把 AI 厂商返回的 URL 作为外链（部分厂商 URL 有时效） | 无 |

配图说明：

- 平台如对小程序图片域名有白名单限制，外链图（Wikimedia/Picsum/AI 厂商 URL）可能不展示——此时把 `IMG_MODE` 设为 `feed`，或配置 `ELANTRAN_UPLOAD_URL` 先上传。
- 不发帖/不回复图片不影响签到主流程，任何一步失败都会自动降级、不中断任务。

## 本地试跑

```bash
pip3 install requests pytz
python3 elantran_checkin.py
```

GitHub Actions 手动触发 `NSign` workflow 即可；`.github/workflows/run.yml` 里的定时调度默认是关闭的，需要时自行打开。
