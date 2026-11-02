extends RefCounted

# UI strings only. Machine names, paths, and Codex output remain as reported.
const EN := {
    "⚙  本机程序配置": "⚙  Local programs", "本机程序配置": "Local programs",
    "网页登录信息": "Web login details", "登录信息": "Login details",
    "请先启动 Master 以生成登录信息。": "Start Master to generate login details.",
    "登录信息文件无效。": "The login details file is invalid.",
    "选择本机允许启动的程序。下列位置只是搜索建议，需由你选择并保存。": "Choose which local programs may be launched. These are suggested search locations; select and save each path yourself.",
    "自动搜索未找到以下程序，请手动选择。": "These programs were not found automatically. Select them manually.",
    "已自动搜索本机程序；你可以修改搜索结果或手动选择路径。": "Local programs were searched automatically. Change a result or choose a path manually.",
    "终端程序": "Terminal program", "SSH 客户端": "SSH client", "浏览…": "Browse…",
    "建议搜索位置：": "Suggested locations: ", "保存配置": "Save settings",
    "请先启动 Master，再配置本机程序。": "Start Master before configuring local programs.",
    "本机程序已保存": "Local programs saved", "无法启动 Master 程序": "Could not start Master program",
    "◫  运行总览": "◫  Overview", "▤  实例工作台": "▤  Instance workbench",
    "⌘  机器列表": "⌘  Machines",
    "确认操作": "Confirm action", "运行总览": "Overview", "实例工作台": "Instance workbench",
    "重命名": "Rename", "重命名机器": "Rename machine", "机器名称": "Machine name",
    "输入机器在中控界面中的自定义名称。留空可恢复主机名。": "Set a custom name for this machine in the Master. Leave it empty to restore its reported hostname.",
    "保存失败": "Save failed",
    "机器列表": "Machines", "Master + 本机 Slave": "Master + local Slave",
    "所有连接均使用本机回环地址": "All connections use the local loopback address",
    "本机 Master · 多机器 Codex 工作台": "Local Master · multi-machine Codex workbench",
    "检查连接中…": "Checking connection…", "启动 Master": "Start Master", "停止 Master": "Stop Master",
    "浏览器打开": "Open in browser", "集中查看机器、实例和需要处理的任务。": "View machines, instances, and items needing attention.",
    "在线机器": "Online machines", "受管实例": "Managed instances", "工作中": "Working",
    "需要处理": "Needs attention", "已接入机器": "Connected machines",
    "选择一台机器进入实例工作台。": "Select a machine to open its workbench.",
    "实时活动、任务、审批与实例设置。": "Live activity, tasks, approvals, and instance settings.",
    "刷新": "Refresh", "Codex 实例": "Codex instances",
    "外部 CLI 只读显示；受管实例可互动。": "External CLI instances are read only; managed instances support interaction.",
    "选择一个实例": "Select an instance", "继续对话": "Continue conversation",
    "输入任务。Ctrl+Enter 发送。": "Enter a task. Press Ctrl+Enter to send.",
    "下达任务": "Send task", "实例管理": "Instance management",
    "选择受管实例以调整配置。": "Select a managed instance to change settings.",
    "权限": "Permissions", "模型": "Model", "推理力度": "Reasoning effort",
    "应用并重启": "Apply and restart", "停止": "Stop", "删除历史": "Delete history",
    "信任此目录并重启": "Trust folder and restart", "重新写入目录信任并重启": "Renew folder trust and restart",
    "Codex 会保存所选目录的信任。之后从该目录启动的会话也会使用此设置；项目配置和钩子可能自动运行。": "Codex saves trust for this folder. Future sessions here inherit it; project settings and hooks may run automatically.",
    "启动新实例": "Start new instance", "目标机器上的工作目录": "Working directory on target machine",
    "浏览目标文件夹": "Browse target folders", "读取模型列表": "Load model list",
    "启动 Codex": "Start Codex", "筛选目录": "Filter folders",
    "显示 . 开头的隐藏文件夹": "Show folders beginning with .",
    "上一级": "Parent folder", "使用此目录": "Use this folder", "最近操作": "Recent actions",
    "沿用 Codex 权限配置": "Use Codex permission settings", "完整访问 · 按需审批": "Full access · approval as needed",
    "Bypass（绕过沙箱与审批）": "Bypass (skip sandbox and approvals)",
    "沿用 Codex 配置模型": "Use the model from Codex settings",
    "沿用模型默认推理力度": "Use the model's default reasoning effort",
    "● Master 运行中": "● Master running",
    "● Master 未连接": "● Master disconnected", "暂无 Codex 实例": "No Codex instances",
    "● 在线": "● Online", "● 离线": "● Offline", "在线": "Online", "离线": "Offline",
    "尚未收到": "Not received yet", "未知机器": "Unknown machine", "打开工作台": "Open workbench",
    "选择机器后查看实例状态与活动。": "Select a machine to view instances and activity.",
    "启动中": "Starting", "空闲": "Idle", "待处理": "Needs attention", "未确认": "Unknown",
    "已退出": "Exited", "错误": "Error", "模型未确认": "Model unknown", "力度未确认": "Effort unknown",
    "选择左侧实例查看状态和对话。": "Select an instance on the left to view status and conversation.",
    "Codex 进程已启动，但会话尚未就绪。若终端显示 Folder access，请在右侧确认“信任此目录并重启”；登录等其他提示仍需在目标终端处理。": "Codex started, but the session is not ready. If the terminal shows Folder access, use Trust folder and restart. Handle login or other prompts in the target terminal.",
    "机器已离线；下面显示的是最后一次上报的快照。": "Machine offline; showing the last reported snapshot.",
    "这是外部启动的 CLI，仅显示进程状态。": "This CLI was started externally; only process status is available.",
    "允许本次": "Allow once", "本会话允许": "Allow for this session", "拒绝": "Reject",
    "用户": "User", "等待审批": "Awaiting approval",
    "已收到实例状态；当前快照没有可显示的对话内容。": "Instance status received; no conversation content is available in this snapshot.",
    "实时输出": "Live output", "请先选择机器": "Select a machine first",
    "停止当前 Codex 实例？": "Stop this Codex instance?",
    "删除此实例的本地历史记录？该操作无法撤销。": "Delete this instance's local history? This cannot be undone.",
    "选中的实例已变化，请重新确认。": "The selected instance changed. Please confirm again.",
    "请先选择工作目录": "Select a working directory first", "请先选择目标机器": "Select a target machine first",
    "无法运行 PowerShell 脚本": "Could not run the PowerShell script",
}

static func translate(source: String, language: String) -> String:
    if language != "en":
        return source
    if EN.has(source):
        return EN[source]
    if source.contains("模型未确认") or source.contains("力度未确认"):
        return source.replace("模型未确认", "Model unknown").replace("力度未确认", "Effort unknown")
    if source.begins_with("已执行 Master 操作 · PID "):
        return source.replace("已执行 Master 操作 · PID ", "Master action completed · PID ")
    var failure_separator := source.find(" 失败：")
    if failure_separator >= 0:
        var action := source.substr(0, failure_separator)
        var action_names := {"browse": "Folder browse", "models": "Model lookup"}
        var action_name: String = action_names.get(action, action)
        return "%s failed: %s" % [action_name, source.substr(failure_separator + " 失败：".length())]
    if source.begins_with("● "):
        return "● " + translate(source.substr(2), language)
    if source.contains(" 个 CLI 进程 · "):
        return source.replace(" 个 CLI 进程 · ", " CLI processes · ").replace(" 个实例", " instances")
    if source.contains(" · 最近上报 "):
        return source.replace(" · 最近上报 ", " · Last report ").replace(" 个实例", " instances").replace(" · 在线", " · Online").replace(" · 离线", " · Offline")
    if source.contains(" · 在线") or source.contains(" · 离线"):
        return source.replace(" · 在线", " · Online").replace(" · 离线", " · Offline")
    if source.begins_with("等待审批 · "):
        return source.replace("等待审批 · ", "Awaiting approval · ")
    if source.begins_with("每 ") and source.contains(" 秒同步 · "):
        var sync_index := source.find(" 秒同步")
        var seconds := source.substr(2, sync_index - 2)
        var rest := source.substr(sync_index + " 秒同步 · ".length())
        var unit := " second" if seconds == "1" else " seconds"
        return "Sync every %s%s · %s" % [seconds, unit, rest.replace(" 台机器", " machines")]
    if source.begins_with("最近上报："):
        return source.replace("最近上报：", "Last report: ")
    if source.begins_with("启动错误："):
        return source.replace("启动错误：", "Launch error: ")
    if source.begins_with("操作失败："):
        return source.replace("操作失败：", "Action failed: ")
    if source.begins_with("命令已排队："):
        return source.replace("命令已排队：", "Command queued: ")
    if source.begins_with("已读取 ") and source.ends_with(" 个可用模型"):
        return source.replace("已读取 ", "Loaded ").replace(" 个可用模型", " available models")
    if source.begins_with("找不到脚本："):
        return source.replace("找不到脚本：", "Script not found: ")
    if source.begins_with("建议搜索位置："):
        return source.replace("建议搜索位置：", "Suggested locations: ")
    if source.begins_with("本机程序读取失败："):
        return source.replace("本机程序读取失败：", "Could not load local programs: ")
    if source.begins_with("保存失败："):
        return source.replace("保存失败：", "Save failed: ")
    if source.begins_with("已执行 "):
        return source.replace("已执行 ", "Started ")
    return source


static func status_label(status: String, language: String) -> String:
    const STATUS_ZH := {
        "starting": "启动中", "working": "工作中", "idle": "空闲", "attention": "待处理",
        "unknown": "未确认", "exited": "已退出", "error": "错误", "offline": "离线"
    }
    return translate(str(STATUS_ZH.get(status, status)), language)


static func command_label(value: String, language: String) -> String:
    const COMMAND_ZH := {
        "start": "启动实例", "restart": "重启实例", "stop": "停止实例", "delete": "删除历史",
        "task": "下达任务", "approval": "审批", "browse": "浏览目录", "models": "读取模型",
        "trust_project": "信任目录", "queued": "排队中", "running": "执行中",
        "succeeded": "已完成", "failed": "失败", "cancelled": "已取消"
    }
    return translate(str(COMMAND_ZH.get(value, value)), language)
