# nsign

现代 N / 伊兰特N 小程序（ElantraN）自动签到脚本。修复了"发帖、回复内容固定（早上好/帅气）被官方识别封禁"的问题：

- **发帖**：每次内容都不一样 —— 优先调用 LLM 按"真人车主随手发帖"的口吻重新生成；没配 Key 时用内置话题库 + 时间/季节/城市/车况随机组合，贴近车主日常（通勤、跑山、油耗、保养、声浪、赛道日、IONIQ N 资讯…）。
- **回复**：先读取目标帖子详情，按帖子主题（提车/活动/声浪/保养/风景…）生成相关回复，不再见谁都回"帅气"。
- **配图**：发帖自动带图。来源按优先级：
  1. AI 生成（默认硅基流动 SiliconFlow，需同时配生图 Key + 平台上图接口）；
  2. 平台 feed 里已有图片（域名与官方一致，展示最稳）；
  3. Wikimedia Commons 真实伊兰特N 实拍图（免费许可，已校验可访问）；
  4. Picsum 随机风景图（贴合"风景"场景）。
- 多账号同轮跑批自动去重，每次运行内容均不重样。

## 最少要配什么

| Secret | 值 | 必填 |
| --- | --- | --- |
| `ELANTRAN_AUTH` | 签到 Token（多个账号用 `&` 分隔） | ✅ 必填 |
| `PUSHPLUS_TOKEN` | 推送通知 | 可选 |

以上两项就够跑了：文案用内置话题库随机生成，配图自动用社区已有图 / Wikimedia 实拍 / 风景图。

## 可选增强（GitHub Actions Secrets）

| Secret | 说明 | 默认 |
| --- | --- | --- |
| `LLM_API_KEY` | **聊天** LLM Key（OpenAI 兼容接口，默认走硅基流动） | 无（自动用内置话题库） |
| `LLM_BASE_URL` | 聊天 LLM 接口地址 | `https://api.siliconflow.cn/v1` |
| `LLM_MODEL` | 聊天模型名 | `deepseek-ai/DeepSeek-V4-Flash` |
| `IMG_API_KEY` | **文生图** Key（硅基流动 SiliconFlow 等）。⚠️ 别填只支持聊天的 Key（如 DeepSeek 官方直连）——DeepSeek 官方没有文生图接口 | 无 |
| `IMG_BASE_URL` | 文生图接口地址 | `https://api.siliconflow.cn/v1` |
| `IMG_MODEL` | 文生图模型 | `Kwai-Kolors/Kolors` |
| `ELANTRAN_UPLOAD_URL` | 平台上图接口（抓包可得，形如 `/home/xxx/upload`） | 无 |
| `IMG_MODE` | `auto` / `feed`（只用社区已有图）/ `remote`（只用外链图）/ `none`（不带图） | `auto` |

配置建议：

- 一个**硅基流动 Key** 即可同时负责聊天和生图：填到 `LLM_API_KEY`（DeepSeek-V4-Flash 文案）+ `IMG_API_KEY`（Kolors 配图）。两套配置相互独立，不会互相污染。
- **想要 LLM 写文案更像真人**：填 `LLM_API_KEY` 即可（默认就是硅基流动 + DeepSeek-V4-Flash）。
- **想要 AI 生成配图**：填 `IMG_API_KEY`，**并且**配 `ELANTRAN_UPLOAD_URL`。只配 Key 没配上图接口时不会发AI生图请求（自动退回社区图/实拍图/风景图，不影响运行）。
- 硅基流动文生图模型推荐：
  - `Kwai-Kolors/Kolors`（默认，性价比高、中文效果好）；
  - `black-forest-labs/FLUX.1-schnell`（快、便宜，画质中上）；
  - `Qwen/Qwen-Image`（效果更好、更贵）。以硅基流动控制台"图像生成"里当前可用的模型名为准。
- 硅基流动生成的图片 URL 约 1 小时后失效，所以代码会**立即下载再上传**到平台；没配上传接口时**不会发起生图请求**（避免白花钱），自动退回社区图/实拍图/风景图。

配图说明：

- 平台如对小程序图片域名有白名单限制，外链图（Wikimedia/Picsum）可能不展示——此时把 `IMG_MODE` 设为 `feed`，或配置 `ELANTRAN_UPLOAD_URL` 先上传。
- 发帖/回复内容任何一步失败都会自动降级、不中断签到主流程。

## 本地试跑

```bash
pip3 install requests pytz
python3 elantran_checkin.py
```

GitHub Actions 手动触发 `NSign` workflow 即可；`.github/workflows/run.yml` 里的定时调度默认是关闭的，需要时自行打开。
