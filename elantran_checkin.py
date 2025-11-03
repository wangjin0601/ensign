#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ElantraN
日期：2025-07-14

环境变量配置：
- ELANTRAN_AUTH: 认证Token
- PUSHPLUS_TOKEN: PushPlus消息推送Token
"""

import os
import sys
import json
import time
import base64
import random
import requests
import pytz
from datetime import datetime, timedelta
from urllib3.exceptions import InsecureRequestWarning

# 禁用SSL警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class ElantranCheckin:
    def __init__(self, auth_token=None):
        self.session = requests.Session()
        self.session.verify = False
        self.session.timeout = 30
        
        # 从参数或环境变量获取配置
        self.auth_token = auth_token or os.getenv('ELANTRAN_AUTH', '')
        self.pushplus_token = os.getenv('PUSHPLUS_TOKEN', '')
        
        # 解析用户信息
        self.user_name = "未知用户"
        token_data = self.decode_jwt_token(self.auth_token)
        if token_data:
            self.user_name = token_data.get('name', '未知用户')
        
        # API配置
        self.base_url = 'https://elantran.vintro.cn'
        self.headers = {
            'Host': 'elantran.vintro.cn',
            'xweb_xhr': '1',
            'nversion': '169',
            'authorization': f'Bearer {self.auth_token}',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090c33)XWEB/14185',
            'content-type': 'application/json',
            'accept': '*/*',
            'sec-fetch-site': 'cross-site',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'accept-language': 'zh-CN,zh;q=0.9',
            'priority': 'u=1, i'
        }
        
        self.session.headers.update(self.headers)
    
    def log(self, message, level='INFO'):
        """日志输出"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print("[{}] [{}] [{}] {}".format(timestamp, level, self.user_name, message))
    
    def decode_jwt_token(self, token):
        """解码JWT Token"""
        try:
            # JWT格式：header.payload.signature
            parts = token.split('.')
            if len(parts) != 3:
                return None
            
            # 解码payload部分
            payload = parts[1]
            # 添加必要的填充
            payload += '=' * (4 - len(payload) % 4)
            
            decoded_bytes = base64.urlsafe_b64decode(payload)
            payload_data = json.loads(decoded_bytes.decode('utf-8'))
            
            return payload_data
        except Exception as e:
            self.log("JWT解码失败: {}".format(e), 'ERROR')
            return None
    
    def check_token_status(self):
        """检查Token状态"""
        if not self.auth_token:
            self.log("❌ 未配置认证Token", 'ERROR')
            return False, "未配置Token"
        
        # 解码JWT Token
        token_data = self.decode_jwt_token(self.auth_token)
        if not token_data:
            self.log("❌ Token格式无效", 'ERROR')
            return False, "Token格式无效"
        
        # 检查Token信息
        user_id = token_data.get('id', '')
        identity = token_data.get('identity', '')
        not_login = token_data.get('not_login', '')
        exp = token_data.get('exp', 0)
        name = token_data.get('name', '')
        
        self.log("📋 Token信息: 用户={}, ID={}, 身份={}".format(name, user_id, identity))
        
        # 检查Token过期时间
        if exp > 0:
            exp_time = datetime.fromtimestamp(exp / 1000)
            current_time = datetime.now()
            
            if current_time >= exp_time:
                self.log("❌ Token已过期: {}".format(exp_time), 'ERROR')
                return False, "Token已过期: {}".format(exp_time)
            
            # 检查是否即将过期（7天内）
            days_left = (exp_time - current_time).days
            if days_left <= 7:
                self.log("⚠️ Token将在{}天后过期: {}".format(days_left, exp_time), 'WARNING')
                return True, "Token将在{}天后过期".format(days_left)
            
            self.log("✅ Token有效，过期时间: {}".format(exp_time))
        
        return True, "Token有效"
    
    def check_signin_status(self):
        """检查签到状态"""
        try:
            url = "{}/home/bbs/sign_today_user_status".format(self.base_url)
            response = self.session.post(url, json={})
            
            self.log("📡 状态检查请求: {}".format(response.status_code))
            
            if response.status_code == 200:
                data = response.json()
                self.log("📊 状态检查响应: {}".format(json.dumps(data, ensure_ascii=False)))
                
                code = data.get('code', -1)
                message = data.get('message', '未知状态')
                
                if code == 403:
                    return False, "Cookie已失效，请重新获取认证信息"
                
                if code == 0:
                    status = data.get('data', {}).get('status', 'UNKNOWN')
                    if status == 'IS':
                        return True, "今日已签到"
                    elif status == 'NOT':
                        return False, "今日未签到"
                    else:
                        return False, "状态未知: {}".format(status)
                else:
                    return False, "检查失败: {}".format(message)
            else:
                return False, "请求失败: HTTP {}".format(response.status_code)
                
        except Exception as e:
            self.log("❌ 状态检查异常: {}".format(e), 'ERROR')
            return False, "检查异常: {}".format(e)
    
    def perform_signin(self):
        """执行签到"""
        try:
            url = "{}/home/bbs/sign".format(self.base_url)
            response = self.session.post(url, json={})
            
            self.log("📡 签到请求: {}".format(response.status_code))
            
            if response.status_code == 200:
                data = response.json()
                self.log("📊 签到响应: {}".format(json.dumps(data, ensure_ascii=False)))
                
                code = data.get('code', -1)
                message = data.get('message', '未知结果')
                
                if code == 403:
                    return False, "Cookie已失效，请重新获取认证信息"
                
                if code == 0:
                    signin_data = data.get('data', {})
                    title = signin_data.get('title', '签到成功')
                    msg = signin_data.get('msg', '')
                    
                    tomorrow_point = self.get_signin_detail()
                    
                    result_msg = "{}".format(title)
                    if msg:
                        result_msg += "\n{}".format(msg.replace('<br>', '\n'))
                    if tomorrow_point:
                        result_msg += "\n明日签到可获得: {}积分".format(tomorrow_point)
                    
                    return True, result_msg
                else:
                    return False, "签到失败: {}".format(message)
            else:
                return False, "请求失败: HTTP {}".format(response.status_code)
                
        except Exception as e:
            self.log("❌ 签到异常: {}".format(e), 'ERROR')
            return False, "签到异常: {}".format(e)
    
    def get_post_list(self, page=1):
        """获取帖子列表"""
        try:
            url = "{}/home/bbs/get_post_list".format(self.base_url)
            data = {"is_choice": "IS", "page": page, "limit": 10}
            response = self.session.post(url, json=data)
            
            self.log("📡 获取帖子列表请求: {}".format(response.status_code))
            
            if response.status_code == 200:
                result = response.json()
                self.log("📊 帖子列表响应: code={}".format(result.get('code', -1)))
                
                if result.get('code') == 0:
                    posts = result.get('data', {}).get('list', [])
                    return True, posts
                else:
                    return False, "获取失败: {}".format(result.get('message', '未知错误'))
            else:
                return False, "请求失败: HTTP {}".format(response.status_code)
                
        except Exception as e:
            self.log("❌ 获取帖子列表异常: {}".format(e), 'ERROR')
            return False, "获取异常: {}".format(e)
    
    def like_post(self, post_id):
        """点赞帖子"""
        try:
            url = "{}/home/bbs/like_post".format(self.base_url)
            data = {"id": post_id}
            response = self.session.post(url, json=data)
            
            self.log("📡 点赞帖子请求: {}".format(response.status_code))
            
            if response.status_code == 200:
                result = response.json()
                self.log("📊 点赞响应: code={}".format(result.get('code', -1)))
                
                if result.get('code') == 0:
                    return True, "点赞成功"
                else:
                    return False, "点赞失败: {}".format(result.get('message', '未知错误'))
            else:
                return False, "请求失败: HTTP {}".format(response.status_code)
                
        except Exception as e:
            self.log("❌ 点赞异常: {}".format(e), 'ERROR')
            return False, "点赞异常: {}".format(e)
    
    def create_post(self, title="早上好", content="早上好"):
        """发布帖子"""
        try:
            url = "{}/home/bbs/save_post_info".format(self.base_url)
            data = {
                "forum_id": "e51bcafdf3f8b55bae08b4bcb816faa9",
                "topic_id": "",
                "title": title,
                "content": "<p>{}<br></p>".format(content),
            "content_origin": json.dumps({"ops": [{"insert": "{}\n".format(content)}]}),
                "cover": ""
            }
            response = self.session.post(url, json=data)
            
            self.log("📡 发布帖子请求: {}".format(response.status_code))
            
            if response.status_code == 200:
                result = response.json()
                self.log("📊 发布帖子响应: code={}".format(result.get('code', -1)))
                
                if result.get('code') == 0:
                    return True, "发布成功"
                else:
                    return False, "发布失败: {}".format(result.get('message', '未知错误'))
            else:
                return False, "请求失败: HTTP {}".format(response.status_code)
                
        except Exception as e:
            self.log("❌ 发布帖子异常: {}".format(e), 'ERROR')
            return False, "发布异常: {}".format(e)
    
    def get_post_detail(self, post_id):
        """获取帖子详情"""
        try:
            url = "{}/home/bbs/get_post_detail".format(self.base_url)
            data = {"id": post_id}
            response = self.session.post(url, json=data)
            
            self.log("📡 获取帖子详情请求: {}".format(response.status_code))
            
            if response.status_code == 200:
                result = response.json()
                self.log("📊 帖子详情响应: code={}".format(result.get('code', -1)))
                
                if result.get('code') == 0:
                    return True, result.get('data', {})
                else:
                    return False, "获取失败: {}".format(result.get('message', '未知错误'))
            else:
                return False, "请求失败: HTTP {}".format(response.status_code)
                
        except Exception as e:
            self.log("❌ 获取帖子详情异常: {}".format(e), 'ERROR')
            return False, "获取异常: {}".format(e)
    
    def comment_post(self, post_id, comment="帅气"):
        """评论帖子"""
        try:
            url = "{}/home/bbs/save_post_comment_info".format(self.base_url)
            data = {
                "post_id": post_id,
                "comment_id": "",
                "content": "<p>{}<br></p>".format(comment),
            "content_origin": json.dumps({"ops": [{"insert": "{}\n".format(comment)}]}),
                "at_uid": ""
            }
            response = self.session.post(url, json=data)
            
            self.log("📡 评论帖子请求: {}".format(response.status_code))
            
            if response.status_code == 200:
                result = response.json()
                self.log("📊 评论响应: code={}".format(result.get('code', -1)))
                
                if result.get('code') == 0:
                    return True, "评论成功"
                else:
                    return False, "评论失败: {}".format(result.get('message', '未知错误'))
            else:
                return False, "请求失败: HTTP {}".format(response.status_code)
                
        except Exception as e:
            self.log("❌ 评论异常: {}".format(e), 'ERROR')
            return False, "评论异常: {}".format(e)
    
    def get_signin_detail(self):
        """获取签到明细信息"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            url = "{}/home/bbs/sign_detail".format(self.base_url)
            data = {"day_type": "WEEK", "day": today}
            response = self.session.post(url, json=data)
            
            self.log("📡 获取签到明细请求: {}".format(response.status_code))
            
            if response.status_code == 200:
                result = response.json()
                self.log("📊 签到明细响应: code={}".format(result.get('code', -1)))
                
                if result.get('code') == 0:
                    detail_data = result.get('data', {})
                    tomorrow_point = detail_data.get('tomorrow_point', 0)
                    return tomorrow_point
                else:
                    self.log("获取签到明细失败: {}".format(result.get('message', '未知错误')))
                    return None
            else:
                self.log("签到明细请求失败: HTTP {}".format(response.status_code))
                return None
                
        except Exception as e:
            self.log("❌ 获取签到明细异常: {}".format(e), 'ERROR')
            return None
    
    def get_my_stat_info(self):
        """获取用户积分信息"""
        try:
            url = "{}/home/user/get_my_stat_info".format(self.base_url)
            data = {}
            response = self.session.post(url, json=data)
            
            self.log("📡 获取积分信息请求: {}".format(response.status_code))
            
            if response.status_code == 200:
                result = response.json()
                self.log("📊 积分信息响应: code={}".format(result.get('code', -1)))
                
                if result.get('code') == 0:
                    total_point = result.get('data', {}).get('total_point', 0)
                    return True, total_point
                else:
                    return False, "获取失败: {}".format(result.get('message', '未知错误'))
            else:
                return False, "请求失败: HTTP {}".format(response.status_code)
                
        except Exception as e:
            self.log("❌ 获取积分信息异常: {}".format(e), 'ERROR')
            return False, "获取异常: {}".format(e)
    
    def perform_weekly_actions(self):
        """根据星期几执行不同的操作"""
        current_weekday = datetime.now().weekday()  # 0=周一, 1=周二, 2=周三, ..., 6=周日
        weekday_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        
        self.log("📅 今天是{}".format(weekday_names[current_weekday]))
        
        if current_weekday in [5, 6]:  # 周六、周日
            self.log("🎯 执行{}任务: 发帖 + 评论".format(weekday_names[current_weekday]))
            return self._weekend_actions()
        elif current_weekday == 4:  # 周五
            self.log("🎯 执行周五任务: 点赞3个帖子 + 发帖 + 评论")
            return self._friday_actions()
        else:
            self.log("📝 {}无特殊任务".format(weekday_names[current_weekday]))
            return True, "{}无特殊任务".format(weekday_names[current_weekday])
    
    def _friday_actions(self):
        """周五的操作：获取帖子列表并点赞3个帖子 + 发帖 + 评论"""
        results = []
        
        # 1. 获取帖子列表并点赞3个帖子
        self.log("📋 开始获取帖子列表...")
        
        # 翻页查找未点赞的帖子
        all_unliked_posts = []
        page = 1
        max_pages = 5  # 最多翻5页
        
        while len(all_unliked_posts) < 3 and page <= max_pages:
            self.log("📄 正在获取第{}页帖子...".format(page))
            success, posts = self.get_post_list(page=page)
            
            if not success:
                self.log("❌ 获取第{}页失败: {}".format(page, posts))
                break
                
            if not posts:
                self.log("📄 第{}页没有帖子，停止翻页".format(page))
                break
            
            # 找到未点赞的帖子
            unliked_posts = [post for post in posts if post.get('has_like') == 'NOT']
            all_unliked_posts.extend(unliked_posts)
            
            self.log("📊 第{}页找到{}个未点赞的帖子".format(page, len(unliked_posts)))
            page += 1
            
            # 如果已经找到足够的帖子就停止
            if len(all_unliked_posts) >= 3:
                break
                
            time.sleep(random.uniform(0.5, 1.5))
        
        self.log("📊 总共找到{}个未点赞的帖子".format(len(all_unliked_posts)))
        
        # 点赞前3个未点赞的帖子
        liked_count = 0
        for post in all_unliked_posts[:3]:
            post_id = post.get('id')
            post_title = post.get('title', '未知标题')[:20]
            
            success, msg = self.like_post(post_id)
            if success:
                liked_count += 1
                self.log("👍 点赞成功: {}".format(post_title))
                results.append("点赞成功: {}".format(post_title))
            else:
                self.log("❌ 点赞失败: {} - {}".format(post_title, msg))
                results.append("点赞失败: {} - {}".format(post_title, msg))
            
            delay = random.uniform(60, 600)
            self.log("⏰ 点赞操作延迟 {:.1f} 分钟".format(delay/60))
            time.sleep(delay)
        
        if liked_count == 0:
            results.append("没有可点赞的帖子")
        
        # 2. 发帖
        self.log("📝 开始发布帖子...")
        success, msg = self.create_post("早上好", "早上好")
        if success:
            self.log("✅ {}".format(msg))
            results.append(msg)
        else:
            self.log("❌ {}".format(msg))
            results.append(msg)
        
        # 发帖后延迟
        delay = random.uniform(60, 600)
        self.log("⏰ 发帖操作延迟 {:.1f} 分钟".format(delay/60))
        time.sleep(delay)
        
        # 3. 随机选择帖子进行评论
        self.log("💬 开始随机评论帖子...")
        if all_unliked_posts:
            random_post = random.choice(all_unliked_posts)
            post_id = random_post.get('id')
            post_title = random_post.get('title', '未知标题')[:20]
            
            success, msg = self.comment_post(post_id, "帅气")
            if success:
                self.log("✅ 评论成功: {}".format(post_title))
                results.append("评论成功: {}".format(post_title))
            else:
                self.log("❌ 评论失败: {} - {}".format(post_title, msg))
                results.append("评论失败: {} - {}".format(post_title, msg))
            
            delay = random.uniform(60, 600)
            self.log("⏰ 评论操作延迟 {:.1f} 分钟".format(delay/60))
            time.sleep(delay)
        else:
            results.append("没有可评论的帖子")
        
        return True, "\n".join(results)
    
    def _weekend_actions(self):
        """周六、周日的操作：发帖 + 评论"""
        results = []
        
        # 1. 发帖
        self.log("📝 开始发布帖子...")
        success, msg = self.create_post("早上好", "早上好")
        if success:
            self.log("✅ {}".format(msg))
            results.append(msg)
        else:
            self.log("❌ {}".format(msg))
            results.append(msg)
        
        delay = random.uniform(60, 600)
        self.log("⏰ 发帖操作延迟 {:.1f} 分钟".format(delay/60))
        time.sleep(delay)
        
        # 2. 获取帖子列表用于评论
        self.log("📋 获取帖子列表用于评论...")
        success, posts = self.get_post_list()
        if not success:
            results.append("获取帖子列表失败: {}".format(posts))
        else:
            # 随机选择帖子进行评论
            self.log("💬 开始随机评论帖子...")
            if posts:
                random_post = random.choice(posts)
                post_id = random_post.get('id')
                post_title = random_post.get('title', '未知标题')[:20]
                
                success, msg = self.comment_post(post_id, "帅气")
                if success:
                    self.log("✅ 评论成功: {}".format(post_title))
                    results.append("评论成功: {}".format(post_title))
                else:
                    self.log("❌ 评论失败: {} - {}".format(post_title, msg))
                    results.append("评论失败: {} - {}".format(post_title, msg))
                
                delay = random.uniform(60, 600)
                self.log("⏰ 评论操作延迟 {:.1f} 分钟".format(delay/60))
                time.sleep(delay)
            else:
                results.append("没有可评论的帖子")
        
        return True, "\n".join(results)

    def send_notification(self, title, content):
        """PushPlus消息推送"""
        if not self.pushplus_token:
            self.log("⚠️ 未配置PushPlus Token，跳过消息推送")
            return
        
        attempts = 3
        pushplus_url = "http://www.pushplus.plus/send"
        
        # 在标题和内容中加入用户名称
        title_with_user = "[{}] {}".format(self.user_name, title)
        content_with_user = "👤 账号: {}\n\n{}".format(self.user_name, content)
        
        for attempt in range(attempts):
            try:
                response = requests.post(
                    pushplus_url,
                    data=json.dumps({
                        "token": self.pushplus_token,
                        "title": title_with_user,
                        "content": content_with_user
                    }).encode('utf-8'),
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )
                response.raise_for_status()
                self.log("✅ PushPlus响应: {}".format(response.text))
                break
            except requests.exceptions.RequestException as e:
                self.log("❌ PushPlus推送失败: {}".format(e), 'ERROR')
                if attempt < attempts - 1:
                    sleep_time = random.randint(30, 60)
                    self.log("将在 {} 秒后重试...".format(sleep_time))
                    time.sleep(sleep_time)

    def run(self):
        """主运行函数"""
        self.log("🚀 开始执行Elantran小程序签到任务")
        
        # 1. 检查Token状态
        token_valid, token_msg = self.check_token_status()
        if not token_valid:
            error_msg = "Token验证失败: {}".format(token_msg)
            self.log("❌ {}".format(error_msg), 'ERROR')
            self.send_notification("Elantran签到失败", error_msg)
            return False
        
        # 如果Token即将过期，发送提醒
        if "将在" in token_msg and "天后过期" in token_msg:
            self.send_notification("Elantran Token即将过期", token_msg)
        
        # 2. 检查签到状态
        signed_in, status_msg = self.check_signin_status()
        self.log("📋 签到状态: {}".format(status_msg))    
        
        # 3. 执行签到
        signin_success = False
        if signed_in:
            self.log("✅ 今日已签到，无需重复签到")
            signin_success = True
        else:
            self.log("📝 开始执行签到...")
            success, signin_msg = self.perform_signin()
            
            if success:
                self.log("✅ {}".format(signin_msg))
                signin_success = True
            else:
                self.log("❌ {}".format(signin_msg), 'ERROR')
                self.send_notification("Elantran签到失败", signin_msg)
                return False
        
        # 4. 执行周几相关任务
        self.log("🎯 开始执行周几相关任务...")
        weekly_success, weekly_msg = self.perform_weekly_actions()
        
        # 5. 获取积分信息
        self.log("💰 获取积分信息...")
        point_success, total_point = self.get_my_stat_info()
        point_msg = "\n💰 当前总积分: {}".format(total_point) if point_success else "\n❌ 获取积分失败"
        
        # 6. 发送通知
        if signin_success and weekly_success:
            notification_msg = "签到成功\n" + weekly_msg + point_msg
            self.log("✅ 所有任务执行完成")
            self.send_notification("Elantran任务完成", notification_msg)
            return True
        elif signin_success:
            notification_msg = "签到成功\n" + weekly_msg + point_msg
            self.log("⚠️ 签到成功，但周几任务有问题")
            self.send_notification("Elantran任务部分完成", notification_msg)
            return True
        else:
            self.log("❌ 任务执行失败")
            return False


def random_delay():
    delay_minutes = random.randint(0, 60)
    delay_seconds = delay_minutes * 60
    
    if delay_minutes > 0:
        current_time = datetime.now(pytz.timezone('Asia/Shanghai'))
        estimated_start = current_time + timedelta(minutes=delay_minutes)
        
        print(f"🕐 随机延迟 {delay_minutes} 分钟后开始执行任务...")
        print(f"⏰ 预计开始时间: {estimated_start.strftime('%H:%M:%S')}")
        time.sleep(delay_seconds)
        print(f"✅ 延迟结束，开始执行签到任务")
    else:
        print(f"🚀 无需延迟，立即开始执行签到任务")


def main():
    """主函数"""
    try:
        random_delay()
        
        # 获取环境变量中的认证Token
        auth_tokens_str = os.getenv('ELANTRAN_AUTH', '')
        if not auth_tokens_str:
            print("❌ 未配置ELANTRAN_AUTH环境变量")
            sys.exit(1)
        
        # 按&分割多个Token
        auth_tokens = [token.strip() for token in auth_tokens_str.split('&') if token.strip()]
        
        if not auth_tokens:
            print("❌ 未找到有效的认证Token")
            sys.exit(1)
        
        print("🔍 发现 {} 个账户，开始循环处理...".format(len(auth_tokens)))
        
        success_count = 0
        total_count = len(auth_tokens)
        
        for i, auth_token in enumerate(auth_tokens, 1):
            print("\n{}".format('='*50))
            print("🚀 开始处理第 {}/{} 个账户".format(i, total_count))
            print("{}".format('='*50))
            
            try:
                checker = ElantranCheckin(auth_token)
                success = checker.run()
                
                if success:
                    print("✅ 第 {} 个账户 [{}] 任务执行成功".format(i, checker.user_name))
                    success_count += 1
                else:
                    print("❌ 第 {} 个账户 [{}] 任务执行失败".format(i, checker.user_name))
                    
            except Exception as e:
                print("💥 第 {} 个账户处理异常: {}".format(i, e))
            
            # 账户间添加延迟，避免请求过快
            if i < total_count:
                delay = 600  # 10分钟延迟
                print("⏰ 等待 {} 分钟后处理下一个账户...".format(delay/60))
                time.sleep(delay)
        
        print("\n{}".format('='*50))
        print("📊 任务执行完成: {}/{} 个账户成功".format(success_count, total_count))
        print("{}".format('='*50))
        
        if success_count == total_count:
            print("\n🎉 所有账户任务执行成功")
            sys.exit(0)
        elif success_count > 0:
            print("\n⚠️ 部分账户任务执行成功 ({}/{})".format(success_count, total_count))
            sys.exit(0)
        else:
            print("\n❌ 所有账户任务执行失败")
            sys.exit(1)
            
    except Exception as e:
        print("\n💥 程序异常: {}".format(e))
        sys.exit(1)

if __name__ == '__main__':
    main()