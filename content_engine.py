#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容生成引擎：发帖文案 / 评论回复 / 配图选择
================================================

解决"发帖、回复内容太固定被官方识别封禁"的问题：

1. 文案不再固定为"早上好 / 帅气"，而是：
   - 可选接入 LLM（OpenAI 兼容接口），每次发帖/回复都重新生成、风格贴近真人车主；
   - 未配置 LLM 时使用内置的高质量话题库 + 时间/季节/城市/车况随机参数，
     保证每次运行内容都不同，且贴近"现代N / 伊兰特N 车主"真实语境。
2. 评论回复前先读取目标帖子详情，按帖子主题（提车/赛道/声浪/活动/风景…）生成相关回复，
   而不是对所有帖子回同一句话。
3. 发帖自动配图：
   - 平台 feed 里已有的图片（域名与官方一致，渲染最稳）；
   - Wikimedia Commons 上真实伊兰特N/现代N 实拍图（免费许可、稳定可外链）；
   - Lorem Picsum 随机风景图；
   - 可选 AI 生图（OpenAI 兼容 images 接口），若配置了上传接口则先上传再引用。

环境变量（全部可选，缺省自动降级，不影响签到主流程）：
  LLM_API_KEY / LLM_BASE_URL / LLM_MODEL   聊天 LLM（如 DeepSeek / OpenAI / SiliconFlow 兼容）
  IMG_API_KEY / IMG_BASE_URL / IMG_MODEL   图片生成 LLM（缺省复用 LLM_*，需支持 images/generations）
  ELANTRAN_UPLOAD_URL                      平台上图接口（POST multipart, 字段名 file），抓包可得
  IMG_MODE                                 auto / remote / feed / none
"""

import os
import re
import json
import time
import base64
import random
import requests
from datetime import datetime

# 本进程内已生成的正文（多账号同轮跑批时避免内容撞车）
_GLOBAL_USED_BODIES = []
_MAX_USED_BODIES = 160
_ENGINE_COUNTER = 0


def _mark_body_used(body):
    global _GLOBAL_USED_BODIES
    if body in _GLOBAL_USED_BODIES:
        return False
    _GLOBAL_USED_BODIES.append(body)
    if len(_GLOBAL_USED_BODIES) > _MAX_USED_BODIES:
        _GLOBAL_USED_BODIES = _GLOBAL_USED_BODIES[-_MAX_USED_BODIES:]
    return True

# ---------------------------------------------------------------------------
# 固定的真实"伊兰特N / 现代N"实拍图（Wikimedia Commons，免费许可，已验证可访问）
# ---------------------------------------------------------------------------
WIKI_CAR_IMAGES = [
    "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/HYUNDAI_ELANTRA_N_%28CN7%29_China.jpg/1280px-HYUNDAI_ELANTRA_N_%28CN7%29_China.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/6/62/HYUNDAI_ELANTRA_N_%28CN7%29_China_%282%29.jpg/1280px-HYUNDAI_ELANTRA_N_%28CN7%29_China_%282%29.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/a/af/HYUNDAI_ELANTRA_N_%28CN7%29_China_%283%29.jpg/1280px-HYUNDAI_ELANTRA_N_%28CN7%29_China_%283%29.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1e/HYUNDAI_ELANTRA_N_%28CN7%29_China_%284%29.jpg/1280px-HYUNDAI_ELANTRA_N_%28CN7%29_China_%284%29.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/5/57/Hyundai_Elantra_N_CN7_2.0T_Performance_Blue_01.jpg/1280px-Hyundai_Elantra_N_CN7_2.0T_Performance_Blue_01.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6e/Hyundai_Elantra_N_CN7_2.0T_Performance_Blue_02.jpg/1280px-Hyundai_Elantra_N_CN7_2.0T_Performance_Blue_02.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/9/90/Hyundai_Elantra_N_CN7_PE_2.0T_Black.jpg/1280px-Hyundai_Elantra_N_CN7_PE_2.0T_Black.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/8/82/2022_Hyundai_Elantra_N_in_Fiery_Red%2C_Front_Left%2C_04-18-2022.jpg/1280px-2022_Hyundai_Elantra_N_in_Fiery_Red%2C_Front_Left%2C_04-18-2022.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/42/2024_Hyundai_Elantra_N_2.0T_in_Performance_Blue%2C_front_left%2C_06-16-2024.jpg/1280px-2024_Hyundai_Elantra_N_2.0T_in_Performance_Blue%2C_front_left%2C_06-16-2024.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/3/33/2024_Hyundai_Elantra_N_2.0T_in_Performance_Blue%2C_rear_right%2C_06-16-2024.jpg/1280px-2024_Hyundai_Elantra_N_2.0T_in_Performance_Blue%2C_rear_right%2C_06-16-2024.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7d/Hyundai_Elantra_N_%28CN7%29_Washington_DC_Metro_Area%2C_USA.jpg/1280px-Hyundai_Elantra_N_%28CN7%29_Washington_DC_Metro_Area%2C_USA.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/1/13/2023_Hyundai_Elantra_N_TCR.jpg/1280px-2023_Hyundai_Elantra_N_TCR.jpg",
]

# 城市/出行地点库（模拟真人车主语境，账号越多、差异越大）
CITIES = ["上海", "杭州", "苏州", "宁波", "南京", "北京", "成都", "重庆", "武汉", "长沙",
          "西安", "广州", "深圳", "无锡", "合肥", "青岛", "厦门", "福州"]
DESTINATIONS = ["四明山", "莫干山", "天马山", "龙泉山", "妙峰山", "潭王路", "安吉的山路",
                "千岛湖环湖路", "太湖边", "皖南川藏线", "括苍山", "青山湖", "富春江边",
                "淀山湖边", "大别山", "南昆山", "云雾山", "黑麋峰"]
CAR_COLORS = ["性能蓝", "珍珠白", "幻影黑", "水泥灰", "炽焰红"]

# 时间段集合
MORNING_PHASE = ["morning"]
DAY_PHASE = ["morning", "afternoon"]
NIGHT_PHASE = ["evening", "night"]

# ---------------------------------------------------------------------------
# 发帖话题库：每一条都是"标题+正文"成对（保证不跑题）
# scene 影响配图：car→车图 / scenery→风景图 / ask/news/activity→混合
# phase 限定时间段(morning/afternoon/evening/night)，weekend 限定周末
# {color}=车身颜色 {city}=所在城市 {d}=目的地 {km1}/{km2}=油耗数字
# ---------------------------------------------------------------------------
POST_BANK = [
    # ---- 早高峰 / 通勤（早上） ----
    {"scene": "car", "phase": MORNING_PHASE,
     "title": "早高峰通勤随手记",
     "body": "早高峰路上车不算多，一路切运动模式超了俩龟速车，到公司神清气爽，这车就适合早上醒脑。"},
    {"scene": "car", "phase": MORNING_PHASE,
     "title": "今天路上还挺顺",
     "body": "今天出门早，路上空荡荡的，特意绕了段高架爽了一把，运动排气都没舍得关，到公司心情都是好的。"},
    {"scene": "car", "phase": MORNING_PHASE,
     "title": "我的{color}通勤日常",
     "body": "早高峰慢慢挪了四十分钟，好在座椅加热和方向盘加热都开着，堵车也不至于烦躁，就是油耗看着有点心疼。"},
    # ---- 周末跑山 / 自驾 ----
    {"scene": "car", "phase": DAY_PHASE, "weekend": True,
     "title": "周末跑了趟{d}",
     "body": "周末天气不错，拉上朋友去{d}跑了半天。山路弯多车少，N模式下底盘和转向的反馈太对味了，原厂避震居然这么能打，下来手都是抖的，过瘾！"},
    {"scene": "car", "phase": DAY_PHASE, "weekend": True,
     "title": "{d}半日游",
     "body": "第一次跑{d}这条线，风景是真的好，弯道也密，一路二三挡来回切，声浪在山谷里回响，值回油钱。回来路上还在回味。"},
    {"scene": "car", "phase": DAY_PHASE, "weekend": True,
     "title": "和{N}去{d}转了一圈",
     "body": "{d}人不多，路上碰到好几台性能车，大家都挺规矩。跑完在山脚停车场歇了会，随手拍了几张，这车侧面线条在山景里很出片。"},
    {"scene": "scenery", "phase": DAY_PHASE, "weekend": True,
     "title": "周末出门放放风",
     "body": "周末不想闷在家里，开车沿着城郊公路随便晃了一圈。路边树荫浓密，风从窗户灌进来，这种漫无目的的开车最解压。"},
    # ---- 洗车 ----
    {"scene": "car",
     "title": "周末洗车安排上",
     "body": "自己动手洗了两个小时，{color}洗干净是真的亮，回头率都高了。就是这颜色太不耐脏，开一天又一层灰，痛并快乐着。"},
    {"scene": "car",
     "title": "自己动手洗车",
     "body": "自助洗车店撸了一下午，内饰也擦了一遍。洗完拍两张交作业，车友们都多久洗一次？"},
    {"scene": "car",
     "title": "洗完车心情都好了",
     "body": "洗完车停路边吃个饭，回来发现被人拍了照发群里，说这台N挺精神，哈哈虚荣心得到极大满足。"},
    # ---- 油耗/加油 ----
    {"scene": "car",
     "title": "这箱油跑出惊喜",
     "body": "这箱油基本城市快速路加高架，表显{km1}，比想象中省。市区堵车就得{km2}起步了，鱼和熊掌不可兼得，爽就完事了。"},
    {"scene": "car",
     "title": "高速油耗确实可以",
     "body": "跑了趟高速，巡航定速{km1}，来回几百公里下来表显{km1}，2.0T这个油耗还要啥自行车。"},
    {"scene": "car",
     "title": "95加满，肉疼但快乐",
     "body": "最近油价又涨了，加满一箱95有点肉疼。不过每次点火那一声，又觉得值了。各位平时加95还是98？"},
    # ---- 保养 ----
    {"scene": "car",
     "title": "首保回来交个作业",
     "body": "首保做完了，免费油先跑着，师傅说这车放油螺丝位置有点刁钻，别的没啥问题。顺带看了眼底盘，护板挺规整。"},
    {"scene": "car",
     "title": "保养小记",
     "body": "今天去保养顺便把车机升级了下，店里态度不错，就是等得久。保养完开出来感觉换挡又顺了，不知道是不是心理作用。"},
    {"scene": "car",
     "title": "和技师聊了聊保养",
     "body": "保养时跟技师聊了会，说N的变速箱油按手册来就行，别过度保养。出来路上特意踩了两脚，一切正常，放心了。"},
    # ---- 车机/OTA ----
    {"scene": "car",
     "title": "车机更新完体验不错",
     "body": "车机推送了新版本，更新完导航跟手了不少，语音也比以前聪明点。各位收到推送了没？"},
    {"scene": "car",
     "title": "这波车机升级可以",
     "body": "昨晚在车库把车机升到最新版，界面更干净了，carplay连接也稳定了，好评。就是升级过程别动车，等得有点久。"},
    # ---- 声浪/阀门 ----
    {"scene": "car", "phase": NIGHT_PHASE,
     "title": "阀门一开，谁也不爱",
     "body": "晚上路过一条没车的隧道，开阀门踩了两脚，回火声在隧道里炸开，副驾直接笑出声，说这钱花得值。"},
    {"scene": "car",
     "title": "这声浪太上头了",
     "body": "运动模式加阀门全开，冷启动那一嗓子真的太N了。邻居已经习惯我每天早上准时热车了，就是不知道会不会被投诉哈哈。"},
    {"scene": "car",
     "title": "给朋友演示了一把",
     "body": "跟朋友炫耀声浪，他说电车没有灵魂。我直接带他坐了一圈，出弯补油那一下他沉默了，下车只说了一句：这玩意儿哪儿买的。"},
    # ---- 弹射/NGS ----
    {"scene": "car",
     "title": "第一次弹射，腿软了",
     "body": "找了一段封闭路段试弹射起步，第一次没敢给全油门，第二次直接起飞，那20秒超增压真不是白给的，下来手心全是汗。"},
    {"scene": "car",
     "title": "NGS那20秒真不是闹着玩的",
     "body": "今天在空旷场地试了NGS，20秒过增压一开，推背感直接把人按在座椅上，这车买得值。友情提示：注意安全，量力而行。"},
    # ---- 赛道/赛道日 ----
    {"scene": "car", "phase": DAY_PHASE,
     "title": "第一次下赛道，交作业了",
     "body": "第一次参加赛道日，原厂刹车和轮胎跑了三节居然没怎么衰减，散热是真的强。圈速不重要，能全油门出弯的感觉太爽了。"},
    {"scene": "car", "phase": DAY_PHASE,
     "title": "赛道日碰到好几台N",
     "body": "赛道日碰到好几台N，大家交流了下驾驶模式设置，收获很大。这车的散热和刹车在赛道上是真顶，不用改装就能玩得很开心。"},
    # ---- 偶遇车友 ----
    {"scene": "car",
     "title": "路上偶遇同款",
     "body": "今天在{city}路上碰到一台同款{color}，车牌没看清，闪了两下灯打了个招呼，不知道是不是群里的兄弟。"},
    {"scene": "car",
     "title": "停车场碰到一台N",
     "body": "商场停车场停我旁边的居然也是N，果断停过去合了个影。这车保有量不高，碰上一次能开心一天。"},
    # ---- 风景/随手拍 ----
    {"scene": "scenery",
     "title": "今日份随手拍",
     "body": "今天天空通透得不像话，路边的树都开始变色了，随手拍了一张，秋天真的来了，开着车在这样的路上本身就是享受。"},
    {"scene": "scenery", "phase": ["evening"],
     "title": "下班路上正好赶上日落",
     "body": "下班路上正好赶上日落，半边天都是橘红色的，停路边拍了几张，有时候觉得生活里的小确幸就是这么简单。"},
    {"scene": "scenery",
     "title": "出差路上的惊喜",
     "body": "出差路上经过一段河堤，视野开阔，远处有山有云，忍不住停下来待了会，吹吹风，感觉一周的疲惫都没了。"},
    # ---- 深夜/心情 ----
    {"scene": "car", "phase": NIGHT_PHASE,
     "title": "深夜放风",
     "body": "加完班不想回家，绕路开了二十分钟，夜里的{city}车少路宽，开着窗吹风，一天的疲惫都散得差不多了。"},
    {"scene": "car", "phase": NIGHT_PHASE,
     "title": "下班路上的快乐",
     "body": "深夜高架车不多，没开阀门也够安静地巡航，这种一个人的时刻，车就是最好的陪伴。"},
    # ---- 提问帖 ----
    {"scene": "ask",
     "title": "求推荐行车记录仪",
     "body": "最近想装个行车记录仪，又不想破线动内饰，车友们有推荐的吗？最好是隐藏式那种，先谢过了。"},
    {"scene": "ask",
     "title": "车友们脚垫用的哪款",
     "body": "原厂脚垫雨天太容易脏了，想换套全包围的，大家有没有用着不错的款式推荐一下？"},
    {"scene": "ask",
     "title": "问下大家贴膜都贴的啥",
     "body": "夏天快到了，准备去贴个隔热膜，品牌型号太多了看得眼花，车友们有靠谱的店或者型号推荐吗？"},
    # ---- 新能源相关讨论 ----
    {"scene": "news",
     "title": "IONIQ 6 N大家看了吗",
     "body": "看了下IONIQ 6 N的发布新闻，高性能电驱还能模拟换挡，古德伍德上那动静确实唬人。油车电车各有各的乐趣，N是真的把驾驶乐趣玩明白了。"},
    {"scene": "news",
     "title": "聊下IONIQ 5 N",
     "body": "试过朋友的IONIQ 5 N，电门响应是真的快，模拟声浪做得也像模像样。不过我个人还是更喜欢2.0T高转的声音，各花入各眼吧。"},
    # ---- 活动/聚会 ----
    {"scene": "activity", "phase": DAY_PHASE,
     "title": "最近的活动有人报名吗",
     "body": "看到官方又在组织赛道日活动了，名额好像不多，有一起报名的车友吗？到时候可以互相拍点照片。"},
    {"scene": "activity", "phase": DAY_PHASE, "weekend": True,
     "title": "周末车友局走起",
     "body": "周末有车友聚会，地点群里投票还没定。有没有去过的朋友说说体验？第一次参加有点紧张。"},
    # ---- 购车意向 ----
    {"scene": "ask",
     "title": "准备入手N，求建议",
     "body": "关注N挺久了，试驾完直接上头。平时要兼顾家用，后排坐人到底挤不挤？有娃的车友现身说法一下？"},
    {"scene": "ask",
     "title": "选颜色选择困难了",
     "body": "准备订车了，在纠结选哪个颜色。{color}实车都见过，各有各的好，选择困难症犯了，车友们给点意见？"},
    # ---- 雨天/安全 ----
    {"scene": "car",
     "title": "雨天路滑，大家慢点",
     "body": "今天这场雨下得不小，路上好几个积水路段，大家记得减速慢行，别在积水区开阀门浪，安全第一。"},
    {"scene": "car",
     "title": "雨天通勤提醒",
     "body": "雨天通勤比平时多花了二十分钟，好在原厂胎湿地抓地还行，稳稳当当到公司。提醒大家保持车距，别急刹。"},
]

# 评论类别关键字与回复池
REPLY_RULES = [
    ("提车恭喜", ["提车", "喜提", "落地", "订车", "新车到店", "交付", "恭喜"],
     ["恭喜提车🎉，落地多少方便说下吗？",
      "恭喜恭喜！颜色选得好，N的灵魂就在{color}上。",
      "羡慕了，落地价方便私一下吗，最近也在看这台车。",
      "恭喜入坑！以后路上见到记得闪灯。"]),
    ("赛道驾驶", ["赛道", "跑山", "圈速", "漂移", "山路", "攻弯", "弹射", "NGS", "驾驶乐趣"],
     ["羡慕了，我这边一直没找到合适的场地跑。",
      "赛道日这个可以有，原厂车直接下场就是N的强项。",
      "同款路过，上次跑山下来手都是抖的，太爽了。",
      "下次组个局喊上我，坐标{city}，可以一起跑。"]),
    ("声浪排气", ["声浪", "排气", "阀门", "炸街", "回火", "放炮", "轰鸣", "冷启动"],
     ["阀门一开是真的上头，隧道里效果翻倍。",
      "哈哈 这声音听多少次都不会腻。",
      "运动排气绝对是N最值回票价的配置之一。",
      "冷启动那一嗓子，每天早上都像在开演唱会。"]),
    ("保养维修", ["保养", "首保", "机油", "胎压", "异响", "故障", "索赔", "召回", "4S", "店里"],
     ["帮顶，蹲一个懂行的解答。",
      "我首保也是这么过来的，免费的先用着没啥问题。",
      "感谢分享，正好过阵子也要去保养，心里有底了。",
      "记录一下，以后保养可以参考。",
      "异响这种还是趁质保期内早点去店里查一下，别拖。"]),
    ("油耗充电", ["油耗", "续航", "充电", "电耗", "加油", "油价", "电费"],
     ["这个油耗可以了，我城里通勤就没下过两位数。",
      "高速巡航确实是它的主场，燃油车跑长途还是省心的。",
      "同款，加满一箱95是真肉疼，但爽就完事了。"]),
    ("改装升级", ["改装", "轮毂", "卡钳", "避震", "包围", "贴膜", "改色", "刹车", "轮胎", "尾翼"],
     ["改得挺精神，轮毂数据方便分享下吗？",
      "这套搭配看着协调，避震高度调得刚好。",
      "同款外观件，英雄所见略同哈哈。"]),
    ("新能源", ["IONIQ", "艾尼氪", "电动", "电车", "快充", "新能源", "N Vision"],
     ["电动N的响应是真的快，试过一次很难忘。",
      "油电双修才是完全体，各有各的快乐。",
      "模拟声浪做得确实像，但真排气还是更有灵魂，个人看法哈。"]),
    ("风景照片", ["风景", "随手拍", "大片", "照片", "拍照", "出片", "日落", "夜景", "海边", "光线"],
     ["拍得真好，构图很舒服，壁纸级别了。",
      "这光线绝了，什么设备拍的？",
      "同款机位打卡过，确实怎么拍都好看。"]),
    ("活动聚会", ["活动", "报名", "招募", "聚会", "车友会", "打卡", "车展", "赛道日", "组局"],
     ["已经报名了，到时候现场见！",
      "怎么报名呀？求个入口。",
      "这个活动关注好久了，时间合适的话一定去。"]),
    ("新闻资讯", ["发布", "上市", "首发", "亮相", "官图", "谍照", "十周年", "古德伍德", "纽北", "消息"],
     ["感谢分享，我正想找这个视频呢。",
      "这条信息量可以，转给车友群了。",
      "期待后续更多细节，蹲一个国内上市时间。"]),
]
REPLY_FALLBACK = [
    "哈哈 太真实了，N车主的日常了属于是。",
    "同款路过帮顶，这车确实越开越喜欢。",
    "说得我都有点心动，改天也去试试。",
    "确实，只有开过的人才懂。",
    "好分享，已收藏，以后参考。",
    "支持一下，多发点这种日常，看着亲切。",
    "真实，我也经常这样，一个人开着车就满足了。",
]

# 视频贴常见前缀
VIDEO_REPLIES = [
    "视频先收藏了，晚上回去慢慢看。",
    "拍得不错，转场再顺一点就是大片了。",
    "这运镜可以啊，用的什么设备拍的？",
]

# 通用"真诚问一句"式补充（小概率追加在回复末尾，让回复更像真人）
REPLY_TAILS = [
    "", "", "", "", "", "",
    " 有后续记得更新。",
    " 蹲一个后续。",
    " 改天约一下一起跑。",
]


def _strip_html(text):
    """去掉 HTML 标签、转义符，提取纯文本"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def _extract_image_urls(post):
    """从帖子里解析出图片 URL（image 字段 JSON 或 HTML 里的 <img>）"""
    urls = []
    if not post:
        return urls
    raw = post.get("image") or ""
    if isinstance(raw, str):
        try:
            raw_list = json.loads(raw)
            if isinstance(raw_list, list):
                urls.extend(raw_list)
        except Exception:
            urls.extend(re.findall(r"https?://[^\s\"']+", raw))
    elif isinstance(raw, list):
        urls.extend(str(x) for x in raw)
    content = post.get("content") or ""
    if content:
        urls.extend(re.findall(r'<img[^>]+src="([^"]+)"', content))
    # 只保留看起来像图片的
    out = []
    for u in urls:
        if re.search(r"\.(jpg|jpeg|png|webp|gif|jfif)(\?|$)", u, re.I) and u not in out:
            out.append(u)
    return out


class ContentEngine(object):
    """发帖/回复内容与配图决策引擎"""

    def __init__(self, user_name="", user_id="", uploader=None):
        global _ENGINE_COUNTER
        _ENGINE_COUNTER += 1
        self.user_name = user_name or ""
        self.uploader = uploader  # callable(bytes, filename, content_type) -> platform URL or None

        # RNG：账号维度保证同轮多账号内容不同，时间维度保证每次运行都不重样
        acc_seed = 0
        for ch in (user_name + (user_id or "")):
            acc_seed = (acc_seed * 31 + ord(ch)) & 0x7FFFFFFF
        self.rng = random.Random(
            (acc_seed ^ (_ENGINE_COUNTER * 1000003)) & 0xFFFFFFFF ^ int(time.time() * 1000000))

        # LLM 配置
        self.llm_key = os.getenv("LLM_API_KEY", "").strip()
        self.llm_base = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1").strip().rstrip("/")
        self.llm_model = os.getenv("LLM_MODEL", "deepseek-chat").strip()
        # 图片生成配置（缺省复用 LLM 配置）
        self.img_key = os.getenv("IMG_API_KEY", "").strip() or self.llm_key
        self.img_base = os.getenv("IMG_BASE_URL", "").strip().rstrip("/") or self.llm_base
        self.img_model = os.getenv("IMG_MODEL", "").strip()
        self.img_mode = os.getenv("IMG_MODE", "auto").strip().lower() or "auto"

        self.llm_on = bool(self.llm_key and self.llm_base and self.llm_model)
        # AI 生图可用：需要 key，且要么配了平台上图接口、要么显式允许外链 AI 图
        self.ai_img_on = bool(self.img_key and self.img_base)
        self._ai_remote_ok = os.getenv("IMG_ALLOW_REMOTE_AI", "") == "1"
        self.ai_usable = self.ai_img_on and (bool(self.uploader) or self._ai_remote_ok)
        # 已有帖子标题（同进程内避免重复）
        self._used_titles = set()

        # 人物设定：按账号做稳定随机，多账号内容自然分化
        seed = 0
        for ch in (user_name + (user_id or "") + "N-SIGN"):
            seed = (seed * 31 + ord(ch)) & 0x7FFFFFFF
        prng = random.Random(seed)
        self.persona = {
            "city": prng.choice(CITIES),
            "color": prng.choice(CAR_COLORS),
            "nick": user_name or "车友",
        }

    # ------------------------------------------------------------------
    # 对外主接口
    # ------------------------------------------------------------------
    def build_post(self, feed_posts=None, feed_images=None):
        """生成一条发帖内容。
        返回 dict: {title, text, scene, image_url}
        text 为纯文本，段落之间用 \\n 分隔。
        """
        ctx = self._context()
        ref = self._pick_ref(feed_posts)

        scene = ctx["scene_pick"]
        title, text, scene, ref_topic = None, None, scene, None

        # 1) 优先 LLM 每次重新生成
        if self.llm_on:
            try:
                res = self._llm_post(ctx, ref)
                if res:
                    title, text, scene = res
                    ref_topic = ref
            except Exception:
                pass

        # 2) 离线话题库兜底（多账号同轮跑批时自动避开已用过的正文）
        if not text:
            for _ in range(8):
                cand_title, cand_text, cand_scene = self._offline_post(ctx)
                if _mark_body_used(cand_text):
                    break
            else:
                cand_title, cand_text, cand_scene = self._offline_post(ctx)
            title, text, scene = cand_title, cand_text, cand_scene

        # 标题去重（同进程内尽量不重）
        for _ in range(5):
            if title not in self._used_titles:
                break
            title = self._retitle(title, ctx)
        self._used_titles.add(title)

        # 3) 配图
        image_url = None
        try:
            image_url = self._choose_image(scene, feed_posts, feed_images, ref_topic)
        except Exception:
            image_url = None

        return {
            "title": title,
            "text": text,
            "scene": scene,
            "image_url": image_url,
        }

    def build_reply(self, post_detail):
        """根据帖子详情生成回复内容"""
        title = ""
        text = ""
        is_video = False
        if isinstance(post_detail, dict):
            title = post_detail.get("title") or ""
            text = _strip_html(post_detail.get("content") or "")
            if not text:
                text = _strip_html(post_detail.get("desc") or "")
            videos = post_detail.get("video") or []
            if isinstance(videos, str):
                try:
                    videos = json.loads(videos)
                except Exception:
                    videos = []
            is_video = bool(videos) or ("<video" in (post_detail.get("content") or ""))
        elif isinstance(post_detail, str):
            text = _strip_html(post_detail)

        # LLM 回复
        if self.llm_on:
            try:
                reply = self._llm_reply(title, text)
                if reply:
                    return reply
            except Exception:
                pass
        return self._offline_reply(title, text, is_video)

    # ------------------------------------------------------------------
    # 上下文
    # ------------------------------------------------------------------
    def _context(self):
        now = datetime.now()
        hour = now.hour
        if hour < 5:
            phase = "night"
        elif hour < 10:
            phase = "morning"
        elif hour < 17:
            phase = "afternoon"
        else:
            phase = "evening"
        wd = now.weekday()  # 0=周一
        season = (now.month % 12 // 3 + 2) % 4  # 粗略：0春 1夏 2秋 3冬
        season_names = ["春天", "夏天", "秋天", "冬天"]
        return {
            "hour": hour,
            "phase": phase,
            "wd": wd,
            "wd_cn": "周{}".format("一二三四五六日"[wd]),
            "weekend": wd >= 5,
            "season": season,
            "season_name": season_names[season],
            "month": now.month,
            # 配图随机偏向：45% 车、30% 风景、25% 其他
            "scene_pick": self.rng.choices(["car", "scenery", "any"],
                                           weights=[45, 30, 25])[0],
            "city": self.persona["city"],
            "color": self.persona["color"],
        }

    def _pick_ref(self, feed_posts):
        """从现有帖子里挑一条当参考，供 LLM 结合社区话题发挥"""
        if not feed_posts:
            return None
        pool = [p for p in feed_posts if isinstance(p, dict)]
        if not pool:
            return None
        p = self.rng.choice(pool)
        title = p.get("title") or ""
        desc = _strip_html(p.get("content") or "") or _strip_html(p.get("desc") or "")
        return {"title": title[:60], "text": desc[:120]}

    # ------------------------------------------------------------------
    # LLM 部分（OpenAI 兼容接口）
    # ------------------------------------------------------------------
    def _chat(self, system, user, max_tokens=500, temperature=1.0, timeout=60):
        url = "{}/chat/completions".format(self.llm_base)
        payload = {
            "model": self.llm_model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = requests.post(url, json=payload, timeout=timeout,
                             headers={"Authorization": "Bearer {}".format(self.llm_key)})
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def _llm_post(self, ctx, ref):
        now = datetime.now()
        time_desc = "{:02d}点".format(now.hour)
        if ctx["phase"] == "morning":
            time_desc += "，早上"
        elif ctx["phase"] == "night":
            time_desc += "，深夜"
        else:
            time_desc += "，白天"

        ref_note = "最近社区里有一条帖子：『{}』{}，可以在不抄袭的前提下顺着类似话题展开，也可以完全聊自己的。".format(
            ref["title"], ref["text"][:60]) if ref else "自由发挥，聊车主日常、车况、驾驶感受、风景出行都可以。"

        system = (
            "你是国内某现代N性能车俱乐部小程序里的真实车主，你的车是伊兰特N（2.0T），车身颜色{}，常驻{}。"
            "请以真人车主随手发帖的口吻写一条社区动态。要求：口语化、自然、有真实细节，"
            "可以带少量表情和语气词，不要广告、不要营销腔、不要'在这个快节奏的时代'之类的套话，"
            "不要出现'作为车主''作为一名'这类句式，不要提及AI。正文50~120字，1~2段。".format(
                ctx["color"], ctx["city"])
        )
        user = (
            "现在是{}（{}）。{}"
            "请只输出一个JSON对象，不要任何多余文字，格式："
            '{{"title":"不超过18个汉字的标题","content":"正文内容","scene":"car或scenery或any中选一个"}}'
        ).format(time_desc, ctx["wd_cn"], ref_note)

        raw = self._chat(system, user, max_tokens=400)
        obj = self._parse_json(raw)
        if not obj:
            return None
        title = str(obj.get("title", "")).strip()
        content = str(obj.get("content", "")).strip()
        scene = str(obj.get("scene", "any")).strip()
        if scene not in ("car", "scenery", "any"):
            scene = "any"
        if not title or not content:
            return None
        content = re.sub(r"\n{2,}", "\n", content)
        return title, content, scene

    def _llm_reply(self, title, text):
        post_text = "标题：{}\n内容：{}".format(title, text[:200]) if title else text[:250]
        system = (
            "你是国内某现代N性能车俱乐部小程序里的真实车主。请给下面这条帖子写一条回复。"
            "要求：像真人车友随手评论，和帖子内容相关，口语化，可以带少量表情，"
            "10~40字，不要客套模板、不要广告、不要提及AI。只输出回复正文，不要引号、不要解释。"
        )
        user = "帖子：{}".format(post_text)
        return self._chat(system, user, max_tokens=200, temperature=1.1, timeout=45)

    def _parse_json(self, raw):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            pass
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return None

    # ------------------------------------------------------------------
    # 离线发帖话题库
    # ------------------------------------------------------------------
    def _offline_post(self, ctx):
        # 按时间/周末条件筛选可用话题
        cands = []
        for tpl in POST_BANK:
            phase_ok = not tpl.get("phase") or ctx["phase"] in tpl["phase"]
            wd_ok = not tpl.get("weekend") or ctx["weekend"]
            if phase_ok and wd_ok:
                cands.append(tpl)
        tpl = self.rng.choice(cands)

        slots = {"color": ctx["color"], "city": ctx["city"], "N": "N",
                 "d": self.rng.choice(DESTINATIONS),
                 "km1": self.rng.choice(["6.3", "6.8", "5.9", "7.1", "6.5"]),
                 "km2": self.rng.choice(["9.5", "10.2", "8.8", "11.0"])}
        title = tpl["title"].format(**slots)[:30]
        body = tpl["body"].format(**slots)
        return title, body, tpl["scene"]

    def _retitle(self, title, ctx):
        """标题去重时换个说法"""
        alt = self.rng.choice(["{}（续）", "再来说说", "补一条：{}"]).format(title)
        return alt[:30]

    # ------------------------------------------------------------------
    # 离线回复
    # ------------------------------------------------------------------
    def _classify(self, title, text):
        best_cat, best_score = None, 0
        hay = "{} {}".format(title or "", text or "")
        for cat, kws, _pool in REPLY_RULES:
            score = sum(2 for k in kws if k in hay)
            if score > best_score:
                best_score, best_cat = score, cat
        return best_cat if best_cat else None

    # 结尾口语补白只用于偏社交类的回复，避免对求助/保养帖生硬
    _SOCIAL_CATS = ("赛道驾驶", "活动聚会", "风景照片", "声浪排气", "提车恭喜", "新能源")

    def _offline_reply(self, title, text, is_video):
        if is_video and self.rng.random() < 0.8:
            return self.rng.choice(VIDEO_REPLIES)
        cat = self._classify(title, text)
        if cat:
            pool = [r for _c, _k, r in REPLY_RULES if _c == cat][0]
            reply = self.rng.choice(pool)
            reply = reply.replace("{color}", self.persona["color"])
            reply = reply.replace("{city}", self.persona["city"])
        else:
            reply = self.rng.choice(REPLY_FALLBACK)
        if cat in self._SOCIAL_CATS and self.rng.random() < 0.5:
            reply += self.rng.choice(REPLY_TAILS)
        return reply.strip()

    # ------------------------------------------------------------------
    # 配图
    # ------------------------------------------------------------------
    def _feed_images(self, feed_posts, feed_images):
        out = []
        if feed_images:
            out.extend(feed_images)
        if feed_posts:
            for p in feed_posts:
                out.extend(_extract_image_urls(p))
        # 只留平台自己 CDN 的图片（渲染最稳）
        platform = [u for u in out if "elantran-oss-cdn.vintro.cn" in u or "aliyuncs.com" in u]
        return platform or list(out)

    def _choose_image(self, scene, feed_posts, feed_images, ref=None):
        if self.img_mode == "none":
            return None
        # 1) 有 AI 生图能力时，一半概率尝试"每次发帖重新生成"一张
        if self.ai_usable and self.rng.random() < 0.55:
            url = self._ai_image(scene, ref)
            if url:
                return url
        # 2) 平台已有图片
        feed = self._feed_images(feed_posts, feed_images)
        if self.img_mode == "feed" and feed:
            return self.rng.choice(feed)
        if self.img_mode == "remote":
            return self._remote_pool(scene)
        # auto：按场景给权重
        pool = []
        weights = []
        if feed:
            pool.extend(feed)
            weights.extend([2] * len(feed))
        remote = self._remote_pool(scene)
        for r in remote:
            if r not in pool:
                pool.append(r)
                weights.append(3)
        if not pool:
            return None
        return self.rng.choices(pool, weights=weights, k=1)[0]

    def _remote_pool(self, scene):
        """外链图池：车图走 Wikimedia，风景/日常走 Picsum"""
        if scene == "car":
            return list(WIKI_CAR_IMAGES)
        if scene == "scenery":
            return [self._picsum_url() for _ in range(3)]
        pool = list(WIKI_CAR_IMAGES[:5]) + [self._picsum_url() for _ in range(3)]
        self.rng.shuffle(pool)
        return pool

    def _picsum_url(self):
        seed = "n-{:d}".format(self.rng.randint(1, 999999))
        return "https://picsum.photos/seed/{}/1280/960".format(seed)

    def _ai_image(self, scene, ref=None):
        """AI 生成一张与场景匹配的图；返回最终可用的 URL 或 None"""
        style = self.rng.choice([
            "写实摄影风格，光线自然",
            "动漫/二次元插画风格，色彩明快",
            "写实风格，电影感色调",
        ])
        if scene == "car":
            prompt = ("一辆现代伊兰特N（2.0T，蓝色/白色的运动轿车，红色刹车卡钳，运动轮毂），"
                      "停在风景优美的山路边或海边公路，{}，高质量车图，汽车论坛分享图").format(style)
        elif scene == "scenery":
            prompt = ("开阔的自然风景：群山/湖泊/海岸线/落日，空旷的公路上没有车，"
                      "适合配在车主随手拍的帖子里，{}").format(style)
        else:
            prompt = ("现代N性能车与风景结合的壁纸级图片：运动轿车停在日出或日落的公路边，"
                      "{}").format(style)
        if ref and ref.get("title"):
            prompt += "。主题参考（仅灵感，不要出现文字）：{}".format(ref["title"][:40])

        payload = {
            "model": self.img_model or self.llm_model,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
            "response_format": "b64_json",
        }
        try:
            resp = requests.post(
                "{}/images/generations".format(self.img_base),
                json=payload, timeout=120,
                headers={"Authorization": "Bearer {}".format(self.img_key)})
            resp.raise_for_status()
            data = resp.json()["data"][0]
        except Exception:
            return None

        # 返回的是图片数据 → 走平台上图接口
        b64 = data.get("b64_json") or ""
        if b64 and self.uploader:
            try:
                raw = base64.b64decode(b64)
                if raw[:8] == b"\x89PNG\r\n\x1a\n":
                    ext, ctype = ".png", "image/png"
                elif raw[:3] == b"\xff\xd8\xff":
                    ext, ctype = ".jpg", "image/jpeg"
                else:
                    ext, ctype = ".jpg", "image/jpeg"
                url = self.uploader(raw, "n_share{}".format(ext), ctype)
                if url:
                    return url
            except Exception:
                pass
        # 返回的是远程 URL → 仅当显式允许时作为外链候选（部分厂商URL有时效）
        if self._ai_remote_ok:
            url = data.get("url") or ""
            if url.startswith("http"):
                return url
        return None
