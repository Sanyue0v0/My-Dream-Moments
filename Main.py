import json
import os
import requests

flora_api = {}  # 顾名思义,FloraBot的API,载入(若插件已设为禁用则不载入)后会赋值上


def occupying_function(*values):  # 该函数仅用于占位,并没有任何意义
    pass


send_msg = occupying_function
call_api = occupying_function
administrator = []
ds_api_url = "https://api.deepseek.com"
ds_api_key = ""
ds_model = "deepseek-chat"
ds_max_token = 2000
ds_temperature = 1.2

prompt_content = ""
atri_history_msgs = {}


def init():  # 插件初始化函数,在载入(若插件已设为禁用则不载入)或启用插件时会调用一次,API可能没有那么快更新,可等待,无传入参数
    global send_msg, call_api, administrator, ds_api_url, ds_api_key, ds_model, ds_max_token, ds_temperature, prompt_content, atri_history_msgs
    with open(f"{flora_api.get('ThePluginPath')}/Plugin.json", "r", encoding="UTF-8") as open_plugin_config:
        plugin_config = json.loads(open_plugin_config.read())
        ds_api_url = plugin_config.get("DeepSeekApiUrl")
        ds_api_key = plugin_config.get("DeepSeekApiKey")
        ds_model = plugin_config.get("DeepSeekModel")
        ds_max_token = plugin_config.get("DeepSeekMaxToken")
        ds_temperature = plugin_config.get("DeepSeekTemperature")
    send_msg = flora_api.get("SendMsg")
    call_api = flora_api.get("CallApi")
    administrator = flora_api.get("Administrator")
    with open(f"{flora_api.get('ThePluginPath')}/Prompt.md", "r", encoding="UTF-8") as open_prompt_content:
        prompt_content = open_prompt_content.read()
    if os.path.isfile(f"{flora_api.get('ThePluginPath')}/AtriHistoryMessages.json"):
        with open(f"{flora_api.get('ThePluginPath')}/AtriHistoryMessages.json", "r", encoding="UTF-8") as open_history_msgs:
            atri_history_msgs = json.loads(open_history_msgs.read())
    print("MyDreamMoments 加载成功")


def deepseek(msgs: list):
    headers = {"Authorization": f"Bearer {ds_api_key}", "Content-Type": "application/json"}
    data = {"model": ds_model, "messages": msgs, "max_tokens": ds_max_token, "temperature": ds_temperature}
    try:
        response = requests.post(ds_api_url, headers=headers, json=data)
        response.raise_for_status()
        return response.json().get("choices")[0].get("message")
    except requests.exceptions.HTTPError as error:
        return f"Api异常\n状态码: {error.response.status_code}\n响应内容: {json.dumps(error.response.json(), ensure_ascii=False, indent=4)}"
    except requests.exceptions.RequestException as error:
        return f"请求异常\n详细信息: {error}"
    pass


def event(data: dict):  # 事件函数,FloraBot每收到一个事件都会调用这个函数(若插件已设为禁用则不调用),传入原消息JSON参数
    global ds_api_url, ds_api_key
    send_type = data.get("SendType")
    send_address = data.get("SendAddress")
    ws_client = send_address.get("WebSocketClient")
    ws_server = send_address.get("WebSocketServer")
    send_host = send_address.get("SendHost")
    send_port = send_address.get("SendPort")
    uid = data.get("user_id")  # 事件对象QQ号
    gid = data.get("group_id")  # 事件对象群号
    mid = data.get("message_id")  # 消息ID
    msg = data.get("raw_message")  # 消息内容
    if msg is not None:
        msg = msg.replace("&#91;", "[").replace("&#93;", "]").replace("&amp;", "&").replace("&#44;", ",")  # 消息需要将URL编码替换到正确内容
        if msg.startswith("/Atri "):
            if ds_api_key == "" or ds_api_key is None:
                send_msg(send_type, "异常: ApiKey 为空, 无法调用 DeepSeek\n\n可以去修改插件配置文件进行设置 ApiKey, 也使用以下指令进行设置 ApiKey(警告: ApiKey 是很重要的东西, 请不要在群聊内设置 ApiKey, 发在群聊内可能会被他人恶意利用!!!):\n/DeepSeekApiKey + [空格] + [ApiKey]", uid, gid, None, ws_client, ws_server, send_host, send_port)
            else:
                msg = msg.replace("/Atri ", "", 1)
                if msg == "" or msg.isspace():
                    send_msg(send_type, "内容不能为空", uid, gid, mid, ws_client, ws_server, send_host, send_port)
                else:
                    get_mid = send_msg(send_type, "回答可能需要点时间，请耐心等待...", uid, gid, mid, ws_client, ws_server, send_host, send_port)
                    msgs = []
                    str_uid = str(uid)
                    if str_uid in atri_history_msgs:
                        msgs = atri_history_msgs.get(str_uid)
                    else:
                        msgs.append({"role": "system", "content": prompt_content})
                    msgs.append({"role": "user", "content": msg})
                    ds_msg = deepseek(msgs)
                    if type(ds_msg) is str:
                        msgs.pop()
                        if get_mid is not None:
                            # noinspection PyUnresolvedReferences
                            call_api(send_type, "delete_msg", {"message_id": get_mid.get("data").get("message_id")}, ws_client, ws_server, send_host, send_port)
                        send_msg(send_type, f"异常: {ds_msg}", uid, gid, None, ws_client, ws_server, send_host, send_port)
                    else:
                        msgs.append(ds_msg)
                        atri_history_msgs.update({str_uid: msgs})
                        if get_mid is not None:
                            # noinspection PyUnresolvedReferences
                            call_api(send_type, "delete_msg", {"message_id": get_mid.get("data").get("message_id")}, ws_client, ws_server, send_host, send_port)
                        for a_msg in ds_msg.get("content").split(r"${\}"):
                            if a_msg == "" and a_msg.isspace():
                                continue
                            send_msg(send_type, a_msg, uid, gid, mid, ws_client, ws_server, send_host, send_port)
                        with open(f"{flora_api.get('ThePluginPath')}/AtriHistoryMessages.json", "w", encoding="UTF-8") as open_history_msgs:
                            open_history_msgs.write(json.dumps(atri_history_msgs, ensure_ascii=False))
        elif msg == "/Atri新的会话":
            atri_history_msgs.pop(str(uid))
            with open(f"{flora_api.get('ThePluginPath')}/AtriHistoryMessages.json", "w", encoding="UTF-8") as open_history_msgs:
                open_history_msgs.write(json.dumps(atri_history_msgs, ensure_ascii=False))
            send_msg(send_type, "已清除聊天记录, 让我们重新开始吧", uid, gid, mid, ws_client, ws_server, send_host, send_port)
        elif msg.startswith("/DeepSeekApiKey "):
            if uid in administrator:
                if gid is not None:
                    send_msg(send_type, "警告: ApiKey 是很重要的东西, 发在群聊内可能会被他人恶意利用, 建议删除该密钥重新创建一个, 然后在私聊使用指令或直接修改插件配置!!!", uid, gid, mid, ws_client, ws_server, send_host, send_port)
                msg = msg.replace("/DeepSeekApiKey ", "", 1)
                if msg == "" or msg.isspace():
                    send_msg(send_type, "异常: ApiKey 为空, ApiKey 设置失败", uid, gid, mid, ws_client, ws_server, send_host, send_port)
                else:
                    ds_api_key = msg
                    with open(f"{flora_api.get('ThePluginPath')}/Plugin.json", "r+", encoding="UTF-8") as open_plugin_config:
                        plugin_config = json.loads(open_plugin_config.read())
                        plugin_config.update({"DeepSeekApiKey": ds_api_key})
                        open_plugin_config.seek(0)
                        open_plugin_config.write(json.dumps(plugin_config, ensure_ascii=False, indent=4))
                        open_plugin_config.truncate()
                    send_msg(send_type, "ApiKey 设置完成", uid, gid, mid, ws_client, ws_server, send_host, send_port)
