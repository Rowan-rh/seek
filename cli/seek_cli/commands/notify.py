"""通知触达查询命令 — 封装 roar noti-query 接口

按下游任务 queryId（如 ali-ivr-xxx）查询通知投递状态，
并内置 deliveryState 状态码与运营商回执错误码的中文解读。
"""

from seek_cli.integrations import roar_client
from seek_cli.output import success, error

# 通知中心内部投递状态码（deliveryState）
DELIVERY_STATE_MAP = {
    "1000": "初始入库并投递中",
    "1100": "命中用户操作报警暂停规则，被拦截",
    "1110": "发钉钉后抑制邮件和旺旺",
    "1120": "警报被收敛",
    "2000": "发送到目标系统成功",
    "3000": "发送到目标系统失败(调用HSF服务异常)",
    "3001": "发送成功但返回系统调用不成功",
    "3002": "获取调用结果超时",
    "3003": "请求数据格式不正确，不需要重复投递",
    "4000": "接受目标回执消息成功",
    "4001": "订阅消息返回未接听，目标用户未成功接收到消息(IVR/网络不通等)",
    "5000": "发送结果返回下游客户消息成功(dingchat=投递成功未读; 语音=电话接听)",
    "5010": "dingchat 渠道回查消息后已读",
    "9000": "超时不需要投递",
}

# 运营商异步回执错误码（语音呼叫）
CARRIER_CODE_MAP = {
    "200000": "用户听完语音",
    "200001": "用户提前挂机未完整收听",
    "200002": "用户占线",
    "200003": "用户收到呼叫但未接听",
    "200004": "用户号码不合法",
    "200005": "被叫用户无法接通(运营商问题/防骚扰拒接/外呼号码被标记骚扰)",
    "200006": "语音播放失败铃声格式有误",
    "200007": "用户无法接通(不在服务区)",
    "200008": "获取按键超时",
    "200010": "关机",
    "200011": "停机",
    "200100": "呼叫结束(双呼)",
    "200101": "正在接通主叫",
    "200102": "成功接通主叫，正在接通被叫",
    "200103": "呼叫建立，正在通话",
    "200104": "主叫号码受限",
    "200105": "被叫号码受限",
    "200111": "被叫无法接通(拒绝)",
    "200112": "被叫占线",
    "200113": "被叫收到呼叫但未接听",
    "200116": "被叫号码不合法",
    "200117": "来电显示号码不合法",
    "200118": "供应商时间段限呼",
    "200119": "供应商超频限呼",
    "200120": "被叫无法接通(不在服务区)",
    "200121": "呼叫超并发",
    "300000": "DTMF按键消息",
    "9996": "呼叫未建立或呼叫已结束(apus)",
    "999999": "系统错误(未能定位的故障)",
    "500": "运营商错误(运营商侧未能定位的故障)",
    "400": "网元繁忙",
    "482": "被叫号码不可用",
    "476": "号码强制回收",
}


def _decode_state(code) -> str:
    """解读 deliveryState：先查内部状态码，再查运营商回执码"""
    if code is None or code == "":
        return ""
    key = str(code)
    if key in DELIVERY_STATE_MAP:
        return DELIVERY_STATE_MAP[key]
    if key in CARRIER_CODE_MAP:
        return f"运营商回执: {CARRIER_CODE_MAP[key]}"
    return f"未知状态码({key})"


def _decode_output(output) -> str:
    """解读 output 字段（实测格式如 'fail:200005' / 'success:200000'）"""
    if not output or not isinstance(output, str) or ":" not in output:
        return ""
    prefix, _, code = output.partition(":")
    desc = CARRIER_CODE_MAP.get(code.strip())
    return f"{prefix}:{code} ({desc})" if desc else output


def _mask_receiver(receiver) -> str:
    """手机号脱敏（中间4位打码），避免敏感信息进入报告/日志"""
    if not receiver or not isinstance(receiver, str) or len(receiver) < 7:
        return receiver or ""
    return receiver[:3] + "****" + receiver[-4:]


def _find_records(raw):
    """从接口响应中容错提取记录（结构以 roar 实际返回为准）

    实测 noti-query 返回: {"result":"Success","details":{...单条记录...}}
    details 为 dict(单条)或 list(多条)均兼容。

    Returns:
        list[dict]，无记录时为 []
    """
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []
    for key in ("details", "data", "result", "dataList", "records", "list"):
        val = raw.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            # "result":"Success" 这类字符串包装跳过；dict 且含投递字段则视为单条记录
            if "deliveryState" in val or "dateOut" in val:
                return [val]
            nested = _find_records(val)
            if nested:
                return nested
    return []


def _mask_in_place(obj):
    """递归脱敏 dict/list 中所有 receiver 字段（手机号）"""
    if isinstance(obj, dict):
        if isinstance(obj.get("receiver"), str):
            obj["receiver"] = _mask_receiver(obj["receiver"])
        for v in obj.values():
            _mask_in_place(v)
    elif isinstance(obj, list):
        for v in obj:
            _mask_in_place(v)


def cmd_notify_query(args) -> dict:
    """按 queryId 查询通知触达状态"""
    try:
        raw = roar_client.query_delivery(args.query_id)
    except RuntimeError as e:
        return error(str(e), code="ROAR_API_ERROR")

    # 全量脱敏后再输出，避免手机号进入报告/错误日志
    _mask_in_place(raw)

    records = _find_records(raw)
    # 响应顶层本身即单条记录（无列表包装）时也解读
    if not records and isinstance(raw, dict) and "deliveryState" in raw:
        records = [raw]
    decoded = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        state = rec.get("deliveryState", rec.get("state"))
        item = dict(rec)
        item["deliveryStateDesc"] = _decode_state(state)
        if item.get("output"):
            item["outputDesc"] = _decode_output(item["output"])
        decoded.append(item)

    data = {
        "queryId": args.query_id,
        "records": decoded,
        "count": len(decoded),
        "raw": raw,
        "retentionDays": 7,
    }
    if not decoded:
        # 接口层 result 非 Success（实测无记录时 result=Error, errorCode=700044）
        # 不能作为「平台未投递」证据——可能是 queryId 无效或超 7 天留存期
        api_result = raw.get("result") if isinstance(raw, dict) else None
        if api_result not in (None, "Success"):
            return success(
                data,
                message=(
                    f"queryId={args.query_id} 未查到触达记录: "
                    f"接口返回 result={api_result}, errorCode={raw.get('errorCode')}, "
                    f"content={str(raw.get('content', ''))[:100]}。"
                    f"可能是 queryId 无效或已超 7 天留存期，不能据此判定平台未投递"
                ),
            )
        return success(
            data,
            message=(
                f"queryId={args.query_id} 未查到触达记录。"
                f"注意: noti-query 仅保留近 7 天数据，超期记录查不到；"
                f"若通知发生在 7 天内仍无记录，可判定平台侧未实际投递（对照根因模式库「平台未发出」）"
            ),
        )
    return success(data, message=f"查到 {len(decoded)} 条触达记录（deliveryState 已解读）")
