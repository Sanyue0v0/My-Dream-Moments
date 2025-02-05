import json
import os
import requests
import time
import traceback
import sqlite3
import threading
from datetime import datetime
import re  # 导入正则表达式库

flora_api = {}

def occupying_function(*values):
    pass

send_msg = occupying_function
call_api = occupying_function
administrator = []
prompt_content = ""
db_file = "atri_history.db"
db_path = ""
user_states = {}
qweather_api_key = ""
url_api_weather = 'https://devapi.qweather.com/v7/weather/'
url_api_geo = 'https://geoapi.qweather.com/v2/city/'
url_api_air = 'https://devapi.qweather.com/v7/air/now'
city_list = []


def init():
    global send_msg, call_api, administrator, prompt_content, db_path, qweather_api_key, city_list
    with open(f"{flora_api.get('ThePluginPath')}/Plugin.json", "r", encoding="UTF-8") as open_plugin_config:
        plugin_config = json.loads(open_plugin_config.read())
        globals().update({
            "ds_api_key": plugin_config.get("DeepSeekApiKey"),
            "ds_model": plugin_config.get("DeepSeekModel"),
            "ds_max_token": plugin_config.get("DeepSeekMaxToken"),
            "ds_temperature": plugin_config.get("DeepSeekTemperature"),
            "qweather_api_key": plugin_config.get("QWeatherApiKey")
        })
    send_msg = flora_api.get("SendMsg")
    call_api = flora_api.get("CallApi")
    administrator = flora_api.get("Administrator")
    with open(f"{flora_api.get('ThePluginPath')}/Prompt.md", "r", encoding="UTF-8") as open_prompt_content:
        prompt_content = open_prompt_content.read()
    try:
        with open(f"{flora_api.get('ThePluginPath')}/cities.json", "r", encoding="UTF-8") as open_cities_file:
            cities_data = json.load(open_cities_file)
            city_list = cities_data.get("cities", [])
    except (FileNotFoundError, json.JSONDecodeError):
        city_list = []
    plugin_path = flora_api.get('ThePluginPath')
    if not os.path.exists(plugin_path):
        os.makedirs(plugin_path)
    db_path = os.path.join(plugin_path, db_file)
    init_db()
    print("MyDreamMoments 加载成功")


def init_db():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_location (
            user_id TEXT NOT NULL PRIMARY KEY,
            city_name TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_history(user_id: str) -> list:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM chat_history WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"role": role, "content": content} for role, content in rows]


def add_message(user_id: str, role: str, content: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)", (user_id, role, content))
    conn.commit()
    conn.close()


def deepseek(msgs: list, ds_api_url, use_tools: bool):
    headers = {"Authorization": f"Bearer {ds_api_key}", "Content-Type": "application/json"}
    data = {"model": ds_model, "messages": msgs, "max_tokens": ds_max_token, "temperature": ds_temperature}
    if use_tools:
        data["tools"] = [{"type": "function", "function": {"name": "googleSearch"}}]
    try:
        response = requests.post(ds_api_url, headers=headers, json=data)
        response.raise_for_status()
        return response.json().get("choices")[0].get("message")
    except requests.exceptions.HTTPError as error:
        return f"Api异常\n状态码: {error.response.status_code}\n响应内容: {json.dumps(error.response.json(), ensure_ascii=False, indent=4)}"
    except requests.exceptions.RequestException as error:
        return f"请求异常\n详细信息: {error}"


def store_user_location(user_id, city_name):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO user_location (user_id, city_name) VALUES (?, ?)", (user_id, city_name))
    conn.commit()
    conn.close()


def get_user_location(user_id):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT city_name FROM user_location WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def process_message_queue(user_state_key, send_type, uid, gid, mid, ws_client, ws_server, send_host, send_port,
                          qweather_enabled, gemini_enabled):
    user_state = user_states.get(user_state_key)
    if not user_state or not user_state.get("message_queue"):
        return
    message_queue = user_state["message_queue"]
    initial_msg_id = user_state.get("initial_msg_id")
    msgs = []
    history = get_history(user_state_key.split('_')[0] if '_' in user_state_key else user_state_key)
    msgs.extend(history)
    current_datetime = datetime.now().strftime("%Y-%m-%d %A %H:%M:%S")
    system_prompt_with_time = f"{prompt_content}\n\n当前时间: {current_datetime}"
    user_id_for_location = user_state_key.split('_')[0] if '_' in user_state_key else user_state_key
    stored_city_name = get_user_location(user_id_for_location)

    if qweather_enabled:
        if stored_city_name:
            weather_data = get_weather(stored_city_name)
            if weather_data:
                weather_info = format_weather_info_concise(stored_city_name, weather_data)
                system_prompt_with_time += f"\n\n用户信息 地区: {stored_city_name}\n{weather_info}"
            else:
                system_prompt_with_time += f"\n\n用户信息 地区: {stored_city_name}\n抱歉，无法获取到该城市的天气信息。"

        full_message_content = "\n".join(message_queue)
        city_name = extract_city_name(full_message_content)
        if city_name:
            weather_data = get_weather(city_name)
            if weather_data:
                weather_info = format_weather_info_concise(city_name, weather_data)
                system_prompt_with_time += f"\n\n用户信息 地区: {city_name}\n{weather_info}"
                store_user_location(user_id_for_location, city_name)
            else:
                system_prompt_with_time += f"\n\n用户信息 地区: {city_name}\n抱歉，无法获取到该城市的天气信息。"

    msgs.insert(0, {"role": "system", "content": system_prompt_with_time})
    for msg_content in message_queue:
        msgs.append({"role": "user", "content": msg_content})

    ds_api_url = get_ds_api_url()
    ds_msg = deepseek(msgs, ds_api_url, gemini_enabled)

    if isinstance(ds_msg, str):
        msgs.pop()
        send_msg(send_type, f"异常: {ds_msg}", uid, gid, None, ws_client, ws_server, send_host, send_port)
    else:
        reply = ds_msg.get("content")
        if initial_msg_id:
            try:
                call_api(send_type, "delete_msg", {"message_id": initial_msg_id}, ws_client, ws_server, send_host,
                         send_port)
            except Exception as e:
                print(f"Error deleting initial message: {e}")
                traceback.print_exc()

        if '\\' in reply:
            parts = [p.strip() for p in reply.split('\\') if p.strip()]
            for part in parts:
                if part:
                    try:
                        send_msg(send_type, part, uid, gid, None, ws_client, ws_server, send_host, send_port)
                        time.sleep(1)
                    except Exception as e:
                        print(f"Error sending split message to target: {e}")
                        traceback.print_exc()
        else:
            try:
                send_msg(send_type, reply, uid, gid, None, ws_client, ws_server, send_host, send_port)
            except Exception as e:
                print(f"Error sending message to target: {e}")
                traceback.print_exc()

        for msg_content in message_queue:
            add_message(user_state_key.split('_')[0] if '_' in user_state_key else user_state_key, "user",
                        msg_content)
        add_message(user_state_key.split('_')[0] if '_' in user_state_key else user_state_key, "assistant", reply)

    user_states.pop(user_state_key, None)


def extract_city_name(text):
    for city in city_list:
        if city in text:
            return city
    return None


def get_weather(city_name):
    if not qweather_api_key:
        print("Error: QWeather API Key is not set in Plugin.json")
        return None
    try:
        city_id_info = get_city_id(city_name)
        if not city_id_info:
            print(f"Error: Could not get city ID for '{city_name}'")
            return None
        city_id = city_id_info[0]
        get_daily = get_qweather_api('7d', city_id)
        get_air_now = get_air_quality(city_id)
        if get_daily:
            return {
                "daily": get_daily.get('daily', []),
                "air_now": get_air_now.get('now', {}) if get_air_now and get_air_now.get('now') else {},
            }
        else:
            print(f"Error: Could not retrieve complete weather data for '{city_name}'")
            return None
    except Exception as e:
        print(f"Error fetching weather data for '{city_name}': {e}")
        traceback.print_exc()
        return None


def format_weather_info_concise(city_name, weather_data):
    daily_data = weather_data.get("daily", [])
    if not daily_data:
        return "无法获取到详细的7日天气预报。"
    concise_info = f"{city_name}未来7天天气预报：\n"
    for i in range(7):
        forecast = daily_data[i]
        day_of_week = datetime.strptime(forecast.get('fxDate'), '%Y-%m-%d').strftime('%w')
        day_names = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
        day_name = day_names[int(day_of_week)]
        concise_info += f"{day_name}({forecast.get('fxDate')[5:]})：{forecast.get('textDay', '未知')}转{forecast.get('textNight', '未知')}，"
        concise_info += f"温度{forecast.get('tempMin', '未知')}-{forecast.get('tempMax', '未知')}°C，"
        concise_info += f"风力{forecast.get('windScaleDay', '未知')}级，湿度{forecast.get('humidity', '未知')}%，紫外线{forecast.get('uvIndex', '未知')}级\n"
    air_now_data = weather_data.get("air_now", {})
    if air_now_data:
        concise_info += "\n实时空气质量：\n"
        concise_info += f"空气质量指数（AQI）：{air_now_data.get('aqi', '未知')}，"
    else:
        concise_info += "\n无法获取到实时空气质量信息。\n"
    return concise_info


def get_city_id(city_kw):
    mykey = '&key=' + qweather_api_key
    url_v2 = url_api_geo + 'lookup?location=' + city_kw + mykey
    try:
        city_response = requests.get(url_v2)
        city_response.raise_for_status()
        city_data = city_response.json()
        if city_data.get('location'):
            city = city_data['location'][0]
            city_id = city['id']
            district_name = city['name']
            city_name = city['adm2']
            province_name = city['adm1']
            country_name = city['country']
            lat = city['lat']
            lon = city['lon']
            return city_id, district_name, city_name, province_name, country_name, lat, lon
        else:
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error in get_city_id for '{city_kw}': {e}")
        traceback.print_exc()
        return None


def get_qweather_api(api_type, city_id):
    mykey = '&key=' + qweather_api_key
    url = url_api_weather + api_type + '?location=' + city_id + mykey
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error in get_qweather_api for type '{api_type}' and city_id '{city_id}': {e}")
        traceback.print_exc()
        return None


def get_air_quality(city_id):
    mykey = '&key=' + qweather_api_key
    url = url_api_air + '?location=' + city_id + mykey
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error in get_air_quality for city_id '{city_id}': {e}")
        traceback.print_exc()
        return None


def get_ds_api_url():
    with open(f"{flora_api.get('ThePluginPath')}/Plugin.json", "r", encoding="UTF-8") as open_plugin_config:
        plugin_config = json.loads(open_plugin_config.read())
        return plugin_config.get("DeepSeekApiUrl")


def get_config_values():
    with open(f"{flora_api.get('ThePluginPath')}/Plugin.json", "r", encoding="UTF-8") as open_plugin_config:
        plugin_config = json.loads(open_plugin_config.read())
        gemini_enabled = plugin_config.get("Gemini", False)
        qweather_enabled = plugin_config.get("Qweather", False)
    return gemini_enabled, qweather_enabled


def event(data: dict):
    global ds_api_key
    send_type = data.get("SendType")
    send_address = data.get("SendAddress")
    ws_client = send_address.get("WebSocketClient")
    ws_server = send_address.get("WebSocketServer")
    send_host = send_address.get("SendHost")
    send_port = data.get("SendPort")
    uid = data.get("user_id")
    gid = data.get("group_id")
    mid = data.get("message_id")
    msg = data.get("raw_message")
    message_type = data.get("message_type")
    ds_api_url = get_ds_api_url()
    ds_api_key = get_ds_api_key()
    gemini_enabled, qweather_enabled = get_config_values()

    if msg is not None:
        str_uid = str(uid)
        str_gid = str(gid)
        user_state_key = str_uid if message_type == "private" else f"{str_uid}_{str_gid}"
        msg = msg.replace("&#91;", "[").replace("&#93;", "]").replace("&amp;", "&").replace("&#44;", ",")

        if msg in ["新的会话", "Atri新的会话"]:
            clear_history(str_uid)
            send_msg(send_type, "你是？ 不能忘记的人，很重要的人…… 你是？", uid, gid, mid, ws_client, ws_server, send_host,
                     send_port)
            return

        process_atri = message_type == "private" or msg.startswith("Atri ")
        if process_atri:
            if message_type == "group" and msg.startswith("Atri "):
                msg = msg.replace("Atri ", "", 1)
            if not ds_api_key:
                send_msg(send_type,
                         "异常: ApiKey 为空, 无法调用 DeepSeek\n\n请前往修改插件配置文件进行设置 ApiKey, 也使用以下指令进行设置 ApiKey(警告: ApiKey 是很重要的东西 请确保在安全的环境下修改):\n/DeepSeekApiKey + [空格] + [ApiKey]",
                         uid, gid, None, ws_client, ws_server, send_host, send_port)
            elif msg.startswith("DeepSeekApiKey "):
                if uid in administrator:
                    if gid:
                        send_msg(send_type, "警告: ApiKey 是很重要的东西 请确保在安全的环境下修改", uid, gid, mid,
                                 ws_client, ws_server, send_host, send_port)
                    msg = msg.replace("DeepSeekApiKey ", "", 1)
                    if not msg.strip():
                        send_msg(send_type, "异常: ApiKey 为空, ApiKey 设置失败", uid, gid, mid, ws_client, ws_server,
                                 send_host, send_port)
                    else:
                        update_api_key(msg)
                        send_msg(send_type, "ApiKey 设置完成", uid, gid, mid, ws_client, ws_server, send_host,
                                 send_port)
            elif not msg.strip():
                send_msg(send_type, "内容不能为空", uid, gid, mid, ws_client, ws_server, send_host, send_port)
            else:
                user_state = user_states.get(user_state_key)
                if user_state and user_state.get("timer"):
                    user_state["timer"].cancel()
                    user_state["timer"] = threading.Timer(7, process_message_queue, args=(
                        user_state_key, send_type, uid, gid, mid, ws_client, ws_server, send_host, send_port,
                        qweather_enabled, gemini_enabled))
                    user_state["timer"].start()
                    user_state["message_queue"].append(msg)
                else:
                    try:
                        initial_msg_result = send_msg(send_type, "少女祈祷中….", uid, gid, mid, ws_client, ws_server,
                                                     send_host, send_port)
                        initial_msg_id = initial_msg_result.get("data").get("message_id") if initial_msg_result and initial_msg_result.get("data") else None
                    except Exception as e:
                        print(f"Error sending initial message: {e}")
                        traceback.print_exc()
                        initial_msg_id = None

                    user_states[user_state_key] = {
                        "message_queue": [msg],
                        "timer": threading.Timer(7, process_message_queue, args=(
                            user_state_key, send_type, uid, gid, mid, ws_client, ws_server, send_host, send_port,
                            qweather_enabled, gemini_enabled)),
                        "initial_msg_id": initial_msg_id
                    }
                    user_states[user_state_key]["timer"].start()
        elif message_type == "group" and user_states.get(f"{str_uid}_{str_gid}") and user_states[f"{str_uid}_{str_gid}"].get("timer"):
            user_state = user_states[f"{str_uid}_{str_gid}"]
            user_state["timer"].cancel()
            user_state["timer"] = threading.Timer(7, process_message_queue, args=(
                f"{str_uid}_{str_gid}", send_type, uid, gid, mid, ws_client, ws_server, send_host, send_port,
                qweather_enabled, gemini_enabled))
            user_state["timer"].start()
            user_state["message_queue"].append(msg)


def clear_history(user_id: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_ds_api_key():
    with open(f"{flora_api.get('ThePluginPath')}/Plugin.json", "r", encoding="UTF-8") as open_plugin_config:
        plugin_config = json.loads(open_plugin_config.read())
        return plugin_config.get("DeepSeekApiKey")


def update_api_key(api_key):
    with open(f"{flora_api.get('ThePluginPath')}/Plugin.json", "r+", encoding="UTF-8") as open_plugin_config:
        plugin_config = json.loads(open_plugin_config.read())
        plugin_config.update({"DeepSeekApiKey": api_key})
        open_plugin_config.seek(0)
        open_plugin_config.write(json.dumps(plugin_config, ensure_ascii=False, indent=4))
        open_plugin_config.truncate()