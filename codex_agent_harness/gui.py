"""Small local launcher window; the terminal runs the real Codex TUI."""

from __future__ import annotations

import tkinter as tk
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .managed import (collect_managed, delete_exited, delete_instance, launch_terminal,
                      list_models, restart_instance, stop_instance, REASONING_EFFORTS)
from . import connection, local_tools, startup


LABELS = {
    "starting": "启动中", "working": "工作中", "idle": "空闲", "attention": "待处理",
    "unknown": "状态未确认", "exited": "已退出", "error": "错误",
}
LABELS_EN = {
    "starting": "Starting", "working": "Working", "idle": "Idle", "attention": "Needs attention",
    "unknown": "Unknown", "exited": "Exited", "error": "Error",
}
MODE_LABELS = {
    "default": "默认（Codex 配置）",
    "full_access": "完整访问（按需审批）",
    "bypass": "Bypass（跳过审批与沙箱）",
}
MODE_LABELS_EN = {
    "default": "Default (Codex settings)",
    "full_access": "Full access (approval as needed)",
    "bypass": "Bypass (no approvals or sandbox)",
}
MODE_HELP = {
    "default": "沿用 Codex 的沙箱和审批配置。",
    "full_access": "可访问完整文件系统和网络；Codex 仍可请求人工审批。",
    "bypass": "不使用沙箱，也不请求命令审批。",
}
MODE_HELP_EN = {
    "default": "Use Codex's sandbox and approval settings.",
    "full_access": "Access all files and the network; Codex may still request approval.",
    "bypass": "Run without sandboxing or command approvals.",
}
UI_EN = {
    "选择工作目录，然后启动一个可追踪的 Codex 终端。": "Choose a working directory, then launch a tracked Codex terminal.",
    "选择目录": "Choose folder", "启动权限": "Launch permissions", "启动模型": "Launch model",
    "显示 . 开头的隐藏文件夹": "Show hidden folders beginning with .",
    "上一级": "Parent folder", "使用此目录": "Use this folder", "取消": "Cancel",
    "无法读取目录": "Could not read folder",
    "推理力度": "Reasoning effort", "查询可用模型": "Find available models",
    "模型查询失败": "Model lookup failed", "启动失败": "Launch failed",
    "启动 Codex 实例": "Launch Codex instance",
    "后台 Agent 服务负责上报": "The background Agent service sends reports",
    "已配置向 Laptop 中控上报": "Reporting to the Laptop Master is configured",
    "本地模式：配置中控连接后才会上报": "Local mode: configure a Master connection to report status",
    "项目": "Project", "模型（最近/设置）": "Model (latest/selected)", "力度": "Effort",
    "状态": "Status", "进程 PID": "Process PID", "会话 ID": "Session ID",
    "选中项目权限": "Selected project permissions", "模型": "Model",
    "请先选择一个实例": "Select an instance first",
    "确认重启": "Confirm restart",
    "这会停止当前 Codex 实例，并按所选权限启动新会话。继续？":
        "This stops the current Codex instance and starts a new session with the selected permissions. Continue?",
    "重启失败": "Restart failed", "应用设置并重启": "Apply settings and restart",
    "停止实例": "Stop instance", "停止失败": "Stop failed",
    "删除选中历史": "Delete selected history", "删除失败": "Delete failed",
    "清理全部已退出记录": "Clear all exited records", "清理失败": "Cleanup failed",
    "实例实时内容（最近 40 条）": "Live instance activity (latest 40 items)",
    "当前实例暂无消息或工具活动。": "No messages or tool activity for this instance yet.",
    "外部 CLI（只读）": "External CLI (read only)", "未确认": "Unknown",
    "本地状态读取失败：": "Failed to read local status: ",
    "本机程序配置": "Local programs", "选择要由本机启动的程序；只保存你明确选定的路径。":
        "Choose the programs this machine may launch. Only paths you explicitly select are saved.",
    "自动搜索未找到以下程序，请手动选择。": "The following programs were not found automatically. Select them manually.",
    "已自动搜索本机程序；你可以修改搜索结果或手动选择路径。":
        "Local programs were searched automatically. You can change a result or choose a path manually.",
    "仍需选择：": "Still required: ",
    "Codex CLI": "Codex CLI", "终端程序": "Terminal program", "SSH 客户端": "SSH client",
    "浏览…": "Browse…", "建议搜索位置：": "Suggested locations: ", "保存配置": "Save settings",
    "配置未完成": "Setup incomplete", "先配置 Codex CLI 和终端程序，再启动实例。":
        "Configure Codex CLI and a terminal before launching an instance.",
    "程序路径无效": "Invalid program path", "本机程序路径已保存": "Local program paths saved",
    "中控连接": "Master connection", "SSH 主机别名或 user@host": "SSH host alias or user@host",
    "上报令牌": "Report token", "SSH 私钥（可选）": "SSH private key (optional)",
    "先在本机 SSH 配置中核对并固定 Master 主机密钥。保存后会自动尝试连接。":
        "Verify and pin the Master's SSH host key locally first. The Slave will try to connect after saving.",
    "选择私钥…": "Choose key…", "保存连接": "Save connection", "连接配置无效": "Invalid connection settings",
    "请先在“本机程序配置”中选定 SSH 客户端。": "Choose the SSH client in Local programs first.",
    "配置": "Settings", "配置页面": "Settings", "本机程序": "Local programs",
    "中控连接设置": "Master connection", "开机启动": "Start at login",
    "自动搜索本机程序；缺失项可在这里手动选择。": "Programs are searched automatically; choose any missing paths here.",
    "配置 SSH 目标、上报令牌和可选私钥。": "Set the SSH target, report token, and optional private key.",
    "登录后自动启动 CodexAgentHarness": "Start CodexAgentHarness automatically after login",
    "登录后启动 Slave 窗口；已配置中控连接时会自动上报。":
        "Start the Slave window after login. It reports automatically when a Master connection is configured.",
    "已启用：登录后自动启动。": "Enabled: starts automatically after login.",
    "未启用开机启动。": "Automatic startup is disabled.",
    "已成功注册为开机启动项。": "Registered to start automatically after login.",
    "已取消开机启动。": "Automatic startup has been disabled.",
    "设置失败": "Settings failed", "无法更改开机启动设置": "Could not change automatic startup settings",
}
LANGUAGE_PATH = Path.home() / ".config" / "codex-agent-harness" / "ui-language.txt"


def _load_language() -> str:
    try:
        value = LANGUAGE_PATH.read_text(encoding="utf-8").strip()
        return value if value in {"zh", "en"} else "zh"
    except OSError:
        return "zh"


def _save_language(language: str) -> None:
    LANGUAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LANGUAGE_PATH.write_text(language, encoding="utf-8")


def run_gui(reporting: bool, external_reporting: bool = False,
            connection_values: dict | None = None, on_connection_saved=None) -> None:
    language = _load_language()
    translated_widgets = []

    def t(value: str) -> str:
        return UI_EN.get(value, value) if language == "en" else value

    def modes() -> dict[str, str]:
        return MODE_LABELS_EN if language == "en" else MODE_LABELS

    def statuses() -> dict[str, str]:
        return LABELS_EN if language == "en" else LABELS

    def label(parent, value: str, **kwargs):
        widget = ttk.Label(parent, text=t(value), **kwargs)
        translated_widgets.append((widget, value))
        return widget

    def button(parent, value: str, **kwargs):
        widget = ttk.Button(parent, text=t(value), **kwargs)
        translated_widgets.append((widget, value))
        return widget

    root = tk.Tk()
    root.title("CodexAgentHarness")
    root.geometry("1120x720")
    root.minsize(850, 560)
    frame = ttk.Frame(root, padding=18)
    frame.pack(fill="both", expand=True)
    title_row = ttk.Frame(frame)
    title_row.pack(fill="x")
    label(title_row, "CodexAgentHarness", font=("Segoe UI", 16, "bold")).pack(side="left")
    language_selector = ttk.Combobox(title_row, state="readonly", width=10, values=("中文", "English"))
    language_selector.set("English" if language == "en" else "中文")
    language_selector.pack(side="right")

    def open_program_settings(missing_only: bool = False) -> None:
        missing_kinds = set(local_tools.missing(needed)) if missing_only else set(local_tools.KINDS)
        if missing_only and not missing_kinds:
            return
        dialog = tk.Toplevel(root)
        dialog.title(t("本机程序配置"))
        dialog.geometry("900x450" if not missing_only else "900x330")
        dialog.minsize(700, 380)
        dialog.transient(root)
        dialog.grab_set()
        content = ttk.Frame(dialog, padding=18)
        content.pack(fill="both", expand=True)
        explanation = ("自动搜索未找到以下程序，请手动选择。" if missing_only else
                       "已自动搜索本机程序；你可以修改搜索结果或手动选择路径。")
        ttk.Label(content, text=t(explanation),
                  wraplength=840).pack(anchor="w", pady=(0, 12))
        entries = {}
        current = local_tools.auto_configure()
        for kind, caption in (("codex", "Codex CLI"), ("terminal", "终端程序"), ("ssh", "SSH 客户端")):
            if kind not in missing_kinds:
                continue
            ttk.Label(content, text=t(caption)).pack(anchor="w", pady=(8, 2))
            line = ttk.Frame(content)
            line.pack(fill="x")
            choices = local_tools.suggestions(kind)
            entry = ttk.Combobox(line, values=choices)
            entry.set(current[kind])
            entry.pack(side="left", fill="x", expand=True)
            entries[kind] = entry

            def browse_program(target=entry) -> None:
                chosen = filedialog.askopenfilename(parent=dialog, initialdir=str(Path.home()))
                if chosen:
                    target.set(chosen)

            ttk.Button(line, text=t("浏览…"), command=browse_program).pack(side="left", padx=(8, 0))
            ttk.Label(content, text=t("建议搜索位置：") + "  ·  ".join(choices),
                      wraplength=840, foreground="#526372").pack(anchor="w", pady=(2, 0))

        def save_programs() -> None:
            try:
                values = {kind: entry.get().strip() for kind, entry in entries.items()}
                local_tools.save(values)
                remaining = local_tools.missing(needed)
                if remaining:
                    raise ValueError(t("仍需选择：") + ", ".join(remaining))
            except (OSError, ValueError) as exc:
                messagebox.showerror(t("程序路径无效"), str(exc), parent=dialog)
                return
            dialog.destroy()

        ttk.Button(content, text=t("保存配置"), command=save_programs).pack(anchor="e", pady=(14, 0))

    button(title_row, "本机程序配置", command=lambda: open_program_settings(False)).pack(side="right", padx=(0, 10))

    def open_connection_settings() -> None:
        dialog = tk.Toplevel(root)
        dialog.title(t("中控连接"))
        dialog.geometry("700x345")
        dialog.transient(root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        values = connection.load()
        if connection_values:
            values.update({key: str(connection_values.get(key) or "") for key in values})
        entries = {}
        for key, caption in (("ssh_target", "SSH 主机别名或 user@host"),
                             ("token", "上报令牌"), ("ssh_identity", "SSH 私钥（可选）")):
            ttk.Label(body, text=t(caption)).pack(anchor="w", pady=(7, 2))
            line = ttk.Frame(body)
            line.pack(fill="x")
            entry = ttk.Entry(line, show="*" if key == "token" else "")
            entry.insert(0, values[key])
            entry.pack(side="left", fill="x", expand=True)
            entries[key] = entry
            if key == "ssh_identity":
                def browse_key() -> None:
                    chosen = filedialog.askopenfilename(parent=dialog, initialdir=str(Path.home() / ".ssh"))
                    if chosen:
                        entry.delete(0, "end")
                        entry.insert(0, chosen)
                ttk.Button(line, text=t("选择私钥…"), command=browse_key).pack(side="left", padx=(8, 0))
        ttk.Label(body, text=t("先在本机 SSH 配置中核对并固定 Master 主机密钥。保存后会自动尝试连接。"),
                  wraplength=650).pack(anchor="w", pady=(12, 3))

        def save_connection() -> None:
            nonlocal reporting, report_status
            try:
                selected = {key: entry.get().strip() for key, entry in entries.items()}
                if selected["ssh_target"] and local_tools.missing(("ssh",)):
                    raise ValueError(t("请先在“本机程序配置”中选定 SSH 客户端。"))
                saved = connection.save(selected)
                if on_connection_saved:
                    on_connection_saved(saved)
                reporting = bool(saved["ssh_target"])
                report_status = "已配置向 Laptop 中控上报" if reporting else "本地模式：配置中控连接后才会上报"
                notice.set(t(report_status))
                if connection_values is not None:
                    connection_values.update(saved)
            except (OSError, ValueError) as exc:
                messagebox.showerror(t("连接配置无效"), str(exc), parent=dialog)
                return
            dialog.destroy()

        ttk.Button(body, text=t("保存连接"), command=save_connection).pack(anchor="e", pady=(10, 0))

    button(title_row, "中控连接", command=open_connection_settings).pack(side="right", padx=(0, 10))

    def open_configuration() -> None:
        dialog = tk.Toplevel(root)
        dialog.title(t("配置页面"))
        dialog.geometry("720x390")
        dialog.minsize(620, 340)
        dialog.transient(root)
        content = ttk.Frame(dialog, padding=20)
        content.pack(fill="both", expand=True)
        label(content, "配置", font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(0, 12))

        program_section = ttk.LabelFrame(content, text=t("本机程序"), padding=12)
        program_section.pack(fill="x", pady=(0, 12))
        ttk.Label(program_section, text=t("自动搜索本机程序；缺失项可在这里手动选择。"),
                  wraplength=640).pack(side="left", fill="x", expand=True)
        button(program_section, "本机程序配置", command=lambda: open_program_settings(False)).pack(side="right")

        connection_section = ttk.LabelFrame(content, text=t("中控连接设置"), padding=12)
        connection_section.pack(fill="x", pady=(0, 12))
        ttk.Label(connection_section, text=t("配置 SSH 目标、上报令牌和可选私钥。"),
                  wraplength=640).pack(side="left", fill="x", expand=True)
        button(connection_section, "中控连接", command=open_connection_settings).pack(side="right")

        startup_section = ttk.LabelFrame(content, text=t("开机启动"), padding=12)
        startup_section.pack(fill="both", expand=True)
        startup_value = tk.BooleanVar(value=startup.is_registered())
        status_text = tk.StringVar(value=t("已启用：登录后自动启动。") if startup_value.get()
                                   else t("未启用开机启动。"))

        def change_startup() -> None:
            enabled = startup_value.get()
            try:
                if (enabled and connection_values and connection_values.get("ssh_target")
                        and connection_values.get("token")):
                    connection.save(connection_values)
                startup.register() if enabled else startup.unregister()
                actual = startup.is_registered()
                if actual != enabled:
                    raise OSError(t("系统未确认启动项状态"))
            except Exception as exc:
                startup_value.set(startup.is_registered())
                status_text.set(t("未启用开机启动。") if not startup_value.get()
                                else t("已启用：登录后自动启动。"))
                messagebox.showerror(t("设置失败"), f"{t('无法更改开机启动设置')}：\n{exc}", parent=dialog)
                return
            if enabled:
                status_text.set(t("已启用：登录后自动启动。"))
                messagebox.showinfo(t("开机启动"), t("已成功注册为开机启动项。"), parent=dialog)
            else:
                status_text.set(t("未启用开机启动。"))
                messagebox.showinfo(t("开机启动"), t("已取消开机启动。"), parent=dialog)

        ttk.Checkbutton(startup_section, text=t("登录后自动启动 CodexAgentHarness"),
                        variable=startup_value, command=change_startup).pack(anchor="w")
        ttk.Label(startup_section, text=t("登录后启动 Slave 窗口；已配置中控连接时会自动上报。"),
                  wraplength=640).pack(anchor="w", pady=(6, 4))
        ttk.Label(startup_section, textvariable=status_text).pack(anchor="w")

    button(title_row, "配置", command=open_configuration).pack(side="right", padx=(0, 10))
    label(frame, "选择工作目录，然后启动一个可追踪的 Codex 终端。", padding=(0, 8)).pack(anchor="w")
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=(8, 12))
    cwd = tk.StringVar(value=str(Path.cwd()))
    ttk.Entry(row, textvariable=cwd).pack(side="left", fill="x", expand=True)

    def browse() -> None:
        initial = Path(cwd.get()).expanduser()
        if not initial.is_dir():
            initial = Path.home()
        picker = tk.Toplevel(root)
        picker.title(t("选择目录"))
        picker.transient(root)
        picker.grab_set()
        picker.geometry("680x480")
        picker.minsize(520, 360)
        current_path = tk.StringVar(value=str(initial))
        show_hidden = tk.BooleanVar(value=False)
        path_row = ttk.Frame(picker, padding=(12, 12, 12, 6))
        path_row.pack(fill="x")
        ttk.Label(path_row, textvariable=current_path).pack(side="left", fill="x", expand=True)
        listing = ttk.Treeview(picker, columns=("path",), show="tree", selectmode="browse")
        listing.pack(fill="both", expand=True, padx=12, pady=6)
        error = tk.StringVar(value="")
        ttk.Label(picker, textvariable=error, foreground="#b42318").pack(anchor="w", padx=12)

        def refresh(_value=None) -> None:
            path = Path(current_path.get())
            listing.delete(*listing.get_children())
            error.set("")
            try:
                directories = sorted(
                    (entry for entry in path.iterdir()
                     if entry.is_dir() and (show_hidden.get() or not entry.name.startswith("."))),
                    key=lambda entry: entry.name.casefold(),
                )
            except OSError as exc:
                error.set(f"{t('无法读取目录')}: {exc}")
                return
            for directory in directories:
                listing.insert("", "end", iid=str(directory), text=directory.name)

        def navigate_selected(_event=None) -> None:
            selected = listing.selection()
            if selected:
                current_path.set(selected[0])
                refresh()

        def go_parent() -> None:
            parent = Path(current_path.get()).parent
            current_path.set(str(parent))
            refresh()

        listing.bind("<Double-1>", navigate_selected)
        show_hidden_check = ttk.Checkbutton(
            picker, text=t("显示 . 开头的隐藏文件夹"), variable=show_hidden,
            command=refresh,
        )
        show_hidden_check.pack(anchor="w", padx=12, pady=(4, 8))
        actions = ttk.Frame(picker, padding=(12, 4, 12, 12))
        actions.pack(fill="x")
        button(actions, "上一级", command=go_parent).pack(side="left")
        button(actions, "取消", command=picker.destroy).pack(side="right")

        def choose_current() -> None:
            cwd.set(current_path.get())
            picker.destroy()

        button(actions, "使用此目录", command=choose_current).pack(side="right", padx=(0, 8))
        refresh()

    button(row, "选择目录", command=browse).pack(side="left", padx=(8, 0))

    mode = tk.StringVar(value="default")
    mode_row = ttk.Frame(frame)
    mode_row.pack(fill="x", pady=(0, 4))
    label(mode_row, "启动权限").pack(side="left", padx=(0, 10))
    mode_selector = ttk.Combobox(mode_row, state="readonly", width=30,
                                 values=list(modes().values()))
    mode_selector.current(0)
    mode_selector.pack(side="left")
    mode_hint = tk.StringVar(value=(MODE_HELP_EN if language == "en" else MODE_HELP)["default"])

    def mode_changed(_event=None) -> None:
        selected = next(key for key, text in modes().items() if text == mode_selector.get())
        mode.set(selected)
        mode_hint.set((MODE_HELP_EN if language == "en" else MODE_HELP)[selected])

    mode_selector.bind("<<ComboboxSelected>>", mode_changed)
    ttk.Label(frame, textvariable=mode_hint).pack(anchor="w", pady=(0, 12))
    model_row = ttk.Frame(frame)
    model_row.pack(fill="x", pady=(0, 8))
    label(model_row, "启动模型").pack(side="left", padx=(0, 8))
    model_selector = ttk.Combobox(model_row, width=27, values=[""])
    model_selector.pack(side="left", padx=(0, 8))
    label(model_row, "推理力度").pack(side="left", padx=(0, 8))
    effort_selector = ttk.Combobox(model_row, state="readonly", width=12,
                                   values=["", *REASONING_EFFORTS])
    effort_selector.current(0)
    effort_selector.pack(side="left", padx=(0, 8))

    def refresh_models() -> None:
        def work() -> None:
            try:
                models = list_models()["models"]
                root.after(0, lambda: (model_selector.configure(values=["", *[row["id"] for row in models]]),
                                       existing_model_selector.configure(values=["", *[row["id"] for row in models]])))
            except Exception as exc:
                message = str(exc)
                root.after(0, lambda: messagebox.showerror(t("模型查询失败"), message, parent=root))
        threading.Thread(target=work, daemon=True).start()

    button(model_row, "查询可用模型", command=refresh_models).pack(side="left")

    def start() -> None:
        try:
            launch_terminal(Path(cwd.get()), mode=mode.get(), model=model_selector.get().strip() or None,
                            effort=effort_selector.get() or None)
            refresh()
        except Exception as exc:
            messagebox.showerror(t("启动失败"), str(exc), parent=root)

    button(row, "启动 Codex 实例", command=start).pack(side="left", padx=(8, 0))
    report_status = ("后台 Agent 服务负责上报" if external_reporting else
                     "已配置向 Laptop 中控上报" if reporting else
                     "本地模式：配置中控连接后才会上报")
    notice = tk.StringVar(value=t(report_status))
    ttk.Label(frame, textvariable=notice).pack(anchor="w", pady=(0, 10))
    columns = ("project", "mode", "model", "effort", "status", "pid", "thread")
    table = ttk.Treeview(frame, columns=columns, show="headings")
    column_specs = (("project", "项目", 170), ("mode", "启动权限", 180),
                              ("model", "模型（最近/设置）", 135), ("effort", "力度", 75),
                              ("status", "状态", 100), ("pid", "进程 PID", 90),
                              ("thread", "会话 ID", 240))
    for key, title, width in column_specs:
        table.heading(key, text=t(title))
        table.column(key, width=width, stretch=key in {"project", "thread"})
    table.pack(fill="both", expand=True)

    actions = ttk.Frame(frame)
    actions.pack(fill="x", pady=(8, 0))
    label(actions, "选中项目权限").pack(side="left", padx=(0, 7))
    existing_mode_selector = ttk.Combobox(actions, state="readonly", width=26,
                                          values=list(modes().values()))
    existing_mode_selector.pack(side="left", padx=(0, 8))
    label(actions, "模型").pack(side="left", padx=(0, 5))
    existing_model_selector = ttk.Combobox(actions, width=19, values=[""])
    existing_model_selector.pack(side="left", padx=(0, 7))
    label(actions, "力度").pack(side="left", padx=(0, 5))
    existing_effort_selector = ttk.Combobox(actions, state="readonly", width=9,
                                            values=["", *REASONING_EFFORTS])
    existing_effort_selector.pack(side="left", padx=(0, 8))
    existing_mode_instance_id = None

    def selected_id() -> str:
        if not selected_instance_id:
            raise ValueError(t("请先选择一个实例"))
        return selected_instance_id

    def run_action(action, title: str) -> None:
        try:
            action()
            refresh()
        except Exception as exc:
            messagebox.showerror(t(title), str(exc), parent=root)

    def restart_selected() -> None:
        instance_id = selected_id()
        item = next((row for row in (current_snapshot or {}).get("instances", [])
                     if row["id"] == instance_id), None)
        if item and item["status"] not in {"exited", "error"}:
            if not messagebox.askyesno(t("确认重启"), t("这会停止当前 Codex 实例，并按所选权限启动新会话。继续？"), parent=root):
                return
        selected_mode = next(key for key, text in modes().items() if text == existing_mode_selector.get())
        run_action(lambda: restart_instance(instance_id, selected_mode,
                                            existing_model_selector.get().strip() or None,
                                            existing_effort_selector.get() or None), "重启失败")

    manage_buttons = ttk.Frame(frame)
    manage_buttons.pack(fill="x", pady=(6, 0))
    restart_button = button(manage_buttons, "应用设置并重启", command=restart_selected)
    restart_button.pack(side="left", padx=(0, 8))
    stop_button = button(manage_buttons, "停止实例",
                             command=lambda: run_action(lambda: stop_instance(selected_id()), "停止失败"))
    stop_button.pack(side="left", padx=(0, 8))
    delete_button = button(manage_buttons, "删除选中历史",
                               command=lambda: run_action(lambda: delete_instance(selected_id()), "删除失败"))
    delete_button.pack(side="left", padx=(0, 8))
    button(manage_buttons, "清理全部已退出记录",
           command=lambda: run_action(delete_exited, "清理失败")).pack(side="left")

    label(frame, "实例实时内容（最近 40 条）", padding=(0, 12, 0, 5)).pack(anchor="w")
    activity_frame = ttk.Frame(frame)
    activity_frame.pack(fill="both", expand=True)
    activity_text = tk.Text(activity_frame, wrap="word", height=11, state="disabled")
    activity_scroll = ttk.Scrollbar(activity_frame, orient="vertical", command=activity_text.yview)
    activity_text.configure(yscrollcommand=activity_scroll.set)
    activity_text.pack(side="left", fill="both", expand=True)
    activity_scroll.pack(side="right", fill="y")

    refresh_pending = False
    selected_instance_id = None
    current_snapshot = None

    def show_activity() -> None:
        item = next((row for row in (current_snapshot or {}).get("instances", [])
                     if row["id"] == selected_instance_id), None)
        entries = (item or {}).get("activity") or []
        content = "\n\n".join(
            f"[{entry['kind']}{' · ' + entry['status'] if entry.get('status') else ''}]\n{entry['text']}"
            for entry in entries
        ) or t("当前实例暂无消息或工具活动。")
        activity_text.configure(state="normal")
        activity_text.delete("1.0", "end")
        activity_text.insert("1.0", content)
        activity_text.configure(state="disabled")

    def select_instance(_event=None) -> None:
        nonlocal selected_instance_id, existing_mode_instance_id
        selection = table.selection()
        selected_instance_id = selection[0] if selection else None
        if selected_instance_id != existing_mode_instance_id:
            item = next((row for row in (current_snapshot or {}).get("instances", [])
                         if row["id"] == selected_instance_id), None)
            existing_mode_selector.set(modes().get((item or {}).get("launch_mode", "default"), modes()["default"]))
            existing_model_selector.set((item or {}).get("model") or "")
            existing_effort_selector.set((item or {}).get("reasoning_effort") or "")
            existing_mode_instance_id = selected_instance_id
        show_activity()
        update_actions()

    def update_actions() -> None:
        item = next((row for row in (current_snapshot or {}).get("instances", [])
                     if row["id"] == selected_instance_id), None)
        ended = item and item["status"] in {"exited", "error"}
        managed = bool(item and item.get("managed", True))
        restart_button.configure(state="normal" if managed and item["status"] != "starting" else "disabled")
        existing_mode_selector.configure(state="readonly" if managed else "disabled")
        existing_model_selector.configure(state="normal" if managed else "disabled")
        existing_effort_selector.configure(state="readonly" if managed else "disabled")
        stop_button.configure(state="normal" if managed and not ended else "disabled")
        delete_button.configure(state="normal" if managed and ended else "disabled")

    table.bind("<<TreeviewSelect>>", select_instance)

    def apply_snapshot(snapshot: dict | None, error: str | None) -> None:
        nonlocal refresh_pending, selected_instance_id, current_snapshot, existing_mode_instance_id
        refresh_pending = False
        if error:
            notice.set(f"{t('本地状态读取失败：')}{error}")
            return
        notice.set(t(report_status))
        assert snapshot is not None
        current_snapshot = snapshot
        table.delete(*table.get_children())
        for item in snapshot["instances"]:
            values = (item["project"], t("外部 CLI（只读）") if item.get("managed") is False else
                      modes().get(item.get("launch_mode"), modes()["default"]),
                      item.get("active_model") or item.get("model") or t("未确认"),
                      item.get("active_reasoning_effort") or item.get("reasoning_effort") or t("未确认"),
                      statuses().get(item["status"], item["status"]),
                      str(item["pid"]) if item.get("pid") else "—", item.get("thread_id") or "—")
            table.insert("", "end", iid=item["id"], values=values)
        ids = {item["id"] for item in snapshot["instances"]}
        if selected_instance_id not in ids:
            selected_instance_id = snapshot["instances"][0]["id"] if ids else None
        if selected_instance_id:
            table.selection_set(selected_instance_id)
        if selected_instance_id != existing_mode_instance_id:
            item = next((row for row in snapshot["instances"] if row["id"] == selected_instance_id), None)
            existing_mode_selector.set(modes().get((item or {}).get("launch_mode", "default"), modes()["default"]))
            existing_model_selector.set((item or {}).get("model") or "")
            existing_effort_selector.set((item or {}).get("reasoning_effort") or "")
            existing_mode_instance_id = selected_instance_id
        show_activity()
        update_actions()

    def refresh() -> None:
        nonlocal refresh_pending
        if refresh_pending:
            return
        refresh_pending = True

        def work() -> None:
            snapshot = None
            error = None
            try:
                snapshot = collect_managed()
            except Exception as exc:
                error = str(exc)
            try:
                root.after(0, apply_snapshot, snapshot, error)
            except RuntimeError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def schedule_refresh() -> None:
        refresh()
        root.after(3000, schedule_refresh)

    def change_language(_event=None) -> None:
        nonlocal language, existing_mode_instance_id
        previous_modes = MODE_LABELS_EN if language == "en" else MODE_LABELS
        selected_existing_mode = next((key for key, text in previous_modes.items()
                                       if text == existing_mode_selector.get()), "default")
        language = "en" if language_selector.get() == "English" else "zh"
        _save_language(language)
        for widget, source in translated_widgets:
            widget.configure(text=t(source))
        for key, title, _width in column_specs:
            table.heading(key, text=t(title))
        mode_selector.configure(values=list(modes().values()))
        mode_selector.set(modes()[mode.get()])
        mode_hint.set((MODE_HELP_EN if language == "en" else MODE_HELP)[mode.get()])
        existing_mode_selector.configure(values=list(modes().values()))
        existing_mode_selector.set(modes()[selected_existing_mode])
        notice.set(t(report_status))
        if current_snapshot is not None:
            existing_mode_instance_id = selected_instance_id
            apply_snapshot(current_snapshot, None)
        else:
            show_activity()

    language_selector.bind("<<ComboboxSelected>>", change_language)

    needed = ("codex", "terminal", "ssh") if (reporting or external_reporting) else ("codex", "terminal")
    if local_tools.missing(needed):
        root.after(250, lambda: open_program_settings(True))

    schedule_refresh()
    root.mainloop()
