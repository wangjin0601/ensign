#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Elantran 交互式多账号登录与 Token 管理工具
默认使用 App 通道 (client_tpye="app") 获取 Token，避免平时打开微信小程序时触发静默登录把脚本 Token 顶掉
"""

import os
import sys
import json
import base64
from datetime import datetime
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://elantran.vintro.cn"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "elantran_tokens.json")

HEADERS = {
    "Host": "elantran.vintro.cn",
    "nversion": "196",
    "content-type": "application/json",
    "accept": "*/*",
    "user-agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
}


def decode_jwt(token):
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except Exception:
        return {}


def load_store():
    if not os.path.exists(CACHE_FILE):
        return {"accounts": {}, "elantran_auth": ""}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "accounts" not in data or not isinstance(data["accounts"], dict):
                data["accounts"] = {}
            return data
    except Exception as e:
        print(f"⚠️ 读取本地缓存失败 ({e})，将重新初始化")
        return {"accounts": {}, "elantran_auth": ""}


def save_store(store):
    tokens = [
        info["token"]
        for info in store["accounts"].values()
        if isinstance(info, dict) and info.get("token")
    ]
    store["elantran_auth"] = "&".join(tokens)
    store["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def check_online_status(token):
    try:
        headers = dict(HEADERS)
        headers["authorization"] = f"Bearer {token}"
        resp = requests.post(
            f"{BASE_URL}/home/user/get_my_stat_info",
            headers=headers,
            json={},
            verify=False,
            timeout=10,
        )
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"
        res = resp.json()
        if res.get("code") == 0:
            point = (res.get("data") or {}).get("total_point", 0)
            return True, f"在线有效 (积分: {point})"
        return False, f"已失效 ({res.get('message') or res.get('code')})"
    except Exception as e:
        return False, f"请求异常 ({e})"


def show_accounts(store, verify_online=True):
    accounts = store.get("accounts", {})
    if not accounts:
        print("\n📭 当前暂无已保存的登录账号")
        return

    print("\n" + "=" * 72)
    print(f"📋 已保存账号列表 (共 {len(accounts)} 个) | 缓存文件: {os.path.basename(CACHE_FILE)}")
    print("=" * 72)
    for idx, (mobile, info) in enumerate(accounts.items(), 1):
        token = info.get("token", "")
        jwt_data = decode_jwt(token)
        name = info.get("name") or jwt_data.get("name", "未知")
        uid = info.get("user_id") or jwt_data.get("id", "未知")
        client_type = jwt_data.get("client_type") or info.get("client_type", "未知")
        exp = jwt_data.get("exp", 0)
        exp_str = (
            datetime.fromtimestamp(exp / 1000).strftime("%Y-%m-%d %H:%M:%S")
            if exp > 0
            else info.get("expire", "未知")
        )
        login_at = info.get("login_at", "未知")

        status_str = ""
        if verify_online and token:
            ok, msg = check_online_status(token)
            status_str = f" | 状态: {'✅ ' + msg if ok else '❌ ' + msg}"

        print(f"[{idx}] 手机号: {mobile} | 昵称: {name} | UID: {uid} | 通道: {client_type}{status_str}")
        print(f"    登录时间: {login_at} | 过期时间: {exp_str}")
        print(f"    Token: {token[:36]}...{token[-16:] if len(token) > 52 else ''}")

    print("-" * 72)
    print("🔑 GitHub Secret [ELANTRAN_AUTH] 合并值（直接复制下方整行）：")
    print(store.get("elantran_auth", ""))
    print("=" * 72)


def send_sms_code(session, mobile):
    resp = session.post(
        f"{BASE_URL}/home/index/verify",
        headers=HEADERS,
        json={"mobile": mobile, "type": "login"},
        verify=False,
        timeout=15,
    )
    res = resp.json()
    if res.get("code") == 0:
        return True, "验证码已发送"
    return False, res.get("message") or f"发送失败: {res}"


def login_with_code(session, mobile, code, client_type="app"):
    cid = "appcid" if client_type == "app" else "spcid"
    payload = {
        "mobile": mobile,
        "code": code,
        "cid": cid,
        "client_tpye": client_type,
    }
    resp = session.post(
        f"{BASE_URL}/home/index/login",
        headers=HEADERS,
        json=payload,
        verify=False,
        timeout=15,
    )
    res = resp.json()
    if res.get("code") == 0 and res.get("data", {}).get("token"):
        return True, res["data"]
    return False, res.get("message") or f"登录失败: {res}"


def login_one_account(store, mobile=None, client_type="app"):
    session = requests.Session()
    if not mobile:
        mobile = input("\n📱 请输入 11 位手机号 (直接回车取消): ").strip()
    if not mobile:
        return
    if len(mobile) != 11 or not mobile.isdigit():
        print("❌ 手机号格式不正确，必须是 11 位数字")
        return

    if mobile in store.get("accounts", {}):
        old_name = store["accounts"][mobile].get("name", "")
        print(f"ℹ️ 账号 {mobile} ({old_name}) 已存在，本次登录将刷新并覆盖原 Token")

    send_choice = input(f"📨 是否向 {mobile} 发送短信验证码？[Y/n/或直接输入已收到的验证码]: ").strip()
    if send_choice.isdigit() and len(send_choice) >= 4:
        code = send_choice
    elif send_choice.lower() in ("", "y", "yes"):
        print(f"⏳ 正在向 {mobile} 发送验证码...")
        ok, msg = send_sms_code(session, mobile)
        if not ok:
            print(f"❌ {msg}")
            return
        print(f"✅ {msg}，请查收手机短信")
        code = input("🔢 请输入收到的短信验证码 (密码): ").strip()
    else:
        code = input("🔢 请输入短信验证码 (密码): ").strip()

    if not code:
        print("⚠️ 未输入验证码，已取消")
        return

    print(f"⏳ 正在通过 [{client_type}] 通道登录 {mobile}...")
    ok, data = login_with_code(session, mobile, code, client_type=client_type)
    if not ok:
        print(f"❌ 登录失败: {data}")
        return

    token = data.get("token", "")
    user = data.get("user") or {}
    jwt_data = decode_jwt(token)

    name = user.get("name") or jwt_data.get("name", "未知用户")
    uid = str(user.get("id") or jwt_data.get("id", ""))
    exp = jwt_data.get("exp", 0)
    exp_str = (
        datetime.fromtimestamp(exp / 1000).strftime("%Y-%m-%d %H:%M:%S")
        if exp > 0
        else data.get("expire", "")
    )

    store["accounts"][mobile] = {
        "mobile": mobile,
        "name": name,
        "user_id": uid,
        "identity": user.get("identity") or jwt_data.get("identity", ""),
        "client_type": jwt_data.get("client_type", client_type),
        "jwt_id": jwt_data.get("jwt_id", ""),
        "login_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expire": exp_str,
        "token": token,
    }
    save_store(store)
    print(f"🎉 登录成功！用户: {name} (ID: {uid})，已保存至 {CACHE_FILE}")


def batch_login(store, client_type="app"):
    while True:
        login_one_account(store, client_type=client_type)
        cont = input("\n➕ 是否继续登录下一个账号？[y/N]: ").strip().lower()
        if cont not in ("y", "yes"):
            break
    show_accounts(store, verify_online=False)


def relogin_existing(store, client_type="app"):
    accounts = list(store.get("accounts", {}).keys())
    if not accounts:
        print("\n📭 当前没有已保存的账号，请先选择新增登录")
        return

    print("\n📋 请选择要重新登录换 Token 的账号：")
    for idx, mobile in enumerate(accounts, 1):
        info = store["accounts"][mobile]
        print(f"  {idx}. {mobile} ({info.get('name', '未知')})")
    print("  a. 全部依次重新登录")

    choice = input("👉 请输入序号 (直接回车取消): ").strip().lower()
    if not choice:
        return
    if choice == "a":
        for mobile in accounts:
            login_one_account(store, mobile=mobile, client_type=client_type)
        show_accounts(store, verify_online=False)
    elif choice.isdigit() and 1 <= int(choice) <= len(accounts):
        mobile = accounts[int(choice) - 1]
        login_one_account(store, mobile=mobile, client_type=client_type)
        show_accounts(store, verify_online=False)
    else:
        print("❌ 无效的选择")


def remove_or_clear_accounts(store):
    accounts = list(store.get("accounts", {}).keys())
    if not accounts:
        print("\n📭 当前没有已保存的账号")
        return

    print("\n🗑️ 账号清理选项：")
    for idx, mobile in enumerate(accounts, 1):
        info = store["accounts"][mobile]
        print(f"  {idx}. 删除单账号: {mobile} ({info.get('name', '未知')})")
    print("  clear. 全部清空所有账号")

    choice = input("👉 请输入要删除的序号或输入 clear 清空全部 (直接回车取消): ").strip().lower()
    if not choice:
        return
    if choice == "clear":
        confirm = input("⚠️ 确认清空全部已保存的账号和 Token 吗？[y/N]: ").strip().lower()
        if confirm in ("y", "yes"):
            store["accounts"] = {}
            save_store(store)
            print("✅ 已清空全部账号记录")
    elif choice.isdigit() and 1 <= int(choice) <= len(accounts):
        mobile = accounts[int(choice) - 1]
        removed = store["accounts"].pop(mobile, None)
        save_store(store)
        print(f"✅ 已移除账号: {mobile} ({(removed or {}).get('name', '')})")
    else:
        print("❌ 无效的输入")


def main():
    store = load_store()
    client_type = "app"

    while True:
        count = len(store.get("accounts", {}))
        print("\n" + "=" * 54)
        print("🚗 现代N (ElantraN) 多账号登录与 Token 管理工具")
        print(f"📌 当前登录通道: {client_type.upper()} (隔离微信小程序，防日常打开小程序顶号)")
        print(f"📂 本地缓存文件: {os.path.basename(CACHE_FILE)} (已保存 {count} 个账号)")
        print("=" * 54)
        print("  1. 查询已登录账号信息 & 导出 GitHub Secret (含在线有效性检测)")
        print("  2. 登录账号 / 连续登录多个账号 (手机号 + 验证码)")
        print("  3. 已有账号再次登录换 Token")
        print("  4. 删除单个账号 / 全部清空")
        print(f"  5. 切换登录通道 (当前: {client_type}，可选 app / sp)")
        print("  0. 退出")
        print("-" * 54)

        choice = input("👉 请选择操作 [0-5]: ").strip()
        if choice == "1":
            show_accounts(store, verify_online=True)
        elif choice == "2":
            batch_login(store, client_type=client_type)
        elif choice == "3":
            relogin_existing(store, client_type=client_type)
        elif choice == "4":
            remove_or_clear_accounts(store)
        elif choice == "5":
            client_type = "sp" if client_type == "app" else "app"
            print(f"✅ 已切换登录通道为: {client_type}")
        elif choice in ("0", "q", "exit"):
            print("👋 已退出")
            break
        else:
            print("⚠️ 请输入 0-5 之间的数字")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 已退出")
        sys.exit(0)
