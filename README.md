# CodexAgentHarness

## Portable Windows and Linux packages

The release has four folders under `dist/portable`: `windows-master`, `linux-master`, `windows-slave`, and `linux-slave`. Each contains its own executable and bundled Python runtime; each Master folder also contains the exported Godot desktop executable and a sibling `backend` folder. Copy the **whole folder** to a machine. You can also run `powershell -ExecutionPolicy Bypass -File scripts/archive_portable.ps1` to produce two Windows ZIPs and two Linux tarballs that preserve the folder layout. The target needs neither Python nor Godot installed. The current Linux x86_64 package is built on Ubuntu 24.04 with glibc 2.39; build on an older supported distribution if older Linux targets are required. Normal operating-system libraries and a graphical session are still needed for the desktop UI.

| Role | Launch from the copied folder |
| --- | --- |
| Windows Master | `CodexAgentHarness-Master.exe` |
| Linux Master | `./CodexAgentHarness-Master.x86_64` |
| Windows Slave | `codex-agent-harness-slave\codex-agent-harness-slave.exe` |
| Linux Slave | `./codex-agent-harness-slave/codex-agent-harness-slave` |

On first Master start, the backend creates `%USERPROFILE%\.codex-agent-harness\master-credentials.json` on Windows or `~/.codex-agent-harness/master-credentials.json` on Linux. The Godot window uses this file automatically. Use **登录信息 / Login details** when opening the optional browser dashboard. The file also holds `REPORT_TOKEN`; enter that value in each remote Slave's **中控连接 / Master connection** dialog. The Master listens only on `127.0.0.1:8000`; receiving remote reports also requires an SSH server permitted by the operating system and company policy.

Codex CLI, an SSH client, and a terminal are **external programs** that must already be available on the target machine. They are not bundled. On Windows and Linux, Master and Slave search `PATH` and common installation locations automatically. Valid paths you selected earlier are kept. The Slave shows a first-run dialog only for programs it could not find; the Master desktop window prompts for missing Codex CLI or terminal programs. Open **本机程序配置 / Local programs** to change a result manually. The dialogs suggest common locations, including Windows `powershell.exe`, `pwsh.exe`, and `wt.exe`, and Linux `x-terminal-emulator`, GNOME Terminal, Konsole, Xfce Terminal, and xterm. Windows also offers `windows-console` for a new system console. The Slave's **中控连接 / Master connection** dialog stores the SSH alias, report token, and optional private key in a user-owned configuration file; verify and pin the SSH host key before connecting. The report token is never embedded in a binary.

In the Slave **配置 / Settings** window, enable **开机启动 / Start at login** to register it for the current user's next graphical login. Windows uses the current-user startup registry entry; Linux writes `~/.config/autostart/codex-agent-harness.desktop`. The UI confirms success or shows the operating-system error. When a Master connection is configured, enabling startup also saves it so reporting continues after login.

Build on each target operating system: `powershell -ExecutionPolicy Bypass -File scripts/build_portable.ps1` produces the Windows Python binaries and uses the installed Godot 4.7 export templates for both desktop targets. `bash scripts/build_linux_portable.sh` builds the Linux Python binaries on Linux. The Windows build script can also run the Linux build in WSL when its configured WSL distribution and build environment are available. PyInstaller does not cross-compile between Windows and Linux. [PyInstaller platform guidance](https://pyinstaller.org/en/stable/), [Godot export guidance](https://docs.godotengine.org/en/4.6/tutorials/export/exporting_projects.html).

## Godot desktop Master (Windows or Linux)

For source development, import [`godot_master/project.godot`](godot_master/project.godot) in Godot 4.6 or newer, then press **Run Project** (F6/F5). The window is a full desktop control center: **运行总览** for connected machines and counts, **实例工作台** for activity, task messages, approvals, model/effort and permission settings, remote folder browsing, and instance start/restart/stop/delete, plus **机器列表**. Press **启动 Master** in the top bar to start the local API and built-in Slave; **停止 Master** closes both. The Godot window itself can remain open while the Master is stopped.

The desktop app connects only to `http://127.0.0.1:8000` and reads dashboard credentials from the user's `.codex-agent-harness/master-credentials.json`. Portable packages launch the bundled backend. A source checkout uses `scripts/start_master.ps1` and `scripts/stop_master.ps1` on Windows, or `python3 -m codex_agent_harness.master` and its `--stop` command on Linux. The local Slave runs inside that Master process. An external Codex CLI started outside the Harness is shown as read-only because the Master cannot attach to its interactive session.

The desktop app polls status every second. It preserves the selected machine, instance, dropdown values, and unsent task text while updating live data. The remote directory browser and model picker query the selected Agent through the Master command queue, so the target Slave must be online. Actual model/effort are shown separately from the requested settings; applying new settings restarts that managed instance. A source checkout needs Python and Godot; a portable release bundles them.

Use **中文 / English** in the Godot sidebar or the language selector in the web dashboard's top bar to switch the Master interface. The Linux/Windows Slave window has the same selector at the top right. Each interface remembers its own language choice; machine names, paths, and Codex conversation content stay in their original language.

For a headless UI regression check, run `godot --headless --path godot_master --script res://tests/ui_smoke.gd` from the repository root. It checks that status refresh preserves machine selection, permission choice, and a typed project path.

CodexAgentHarness has a local Slave App on each Windows or Linux machine. The VDI user starts this window, chooses a project folder, and launches tracked Codex CLI terminals from it. The Slave App reads those local instance states and sends complete machine snapshots to the Master dashboard and receiver **on the laptop** through an outbound SSH connection.

```text
Linux VDI: Codex terminals -> Slave App -> 127.0.0.1:temporary-port
                                      | encrypted SSH connection
Master machine (Windows/Linux): SSH server -> 127.0.0.1:8000 Master API + dashboard + local Slave
```

The Master API binds only to `127.0.0.1`. SSH is the only inbound service needed on the laptop. The Agent verifies the laptop SSH host key, uses noninteractive key authentication, and reconnects after the tunnel drops. The API also requires a report token. The laptop's changing VPN address still has to be updated in the VDI's SSH host configuration or resolved through a suitable company DNS name.

Multiple VDI Agents can report to the same Master at once. The Master also starts one built-in local Slave on its own machine, so local Codex instances can be launched and monitored from the same interface without a separate local Agent process. Each remote Agent uses its own temporary local SSH port. The Master stores one snapshot per `machine_id`; by default, each hostname has a separate persistent ID file, even when VDIs share a roaming home directory. Use `--machine-id` or `CODEX_AGENT_HARNESS_MACHINE_ID` if cloned machines have the same hostname. Give every machine a different ID and run one Agent per machine. This version uses one shared `REPORT_TOKEN` for all Agents.

## How an instance works

1. Select a working directory and a launch permissions mode in the local window, then click **启动 Codex 实例**.
2. A terminal opens. Its runner starts a dedicated Codex app-server bound to `127.0.0.1`, then starts the Codex CLI connected to that app-server.
3. The local GUI tracks the CLI process by PID and creation time. It asks that instance's app-server for its loaded thread and runtime status. Closing the Codex terminal ends the instance and its app-server.
4. The Agent sends a complete machine snapshot after a detected change and at least every 20 seconds. The dashboard checks for updates every two seconds.

Each button press creates one tracked instance. On Windows, the built-in local Slave also discovers Codex CLI processes started outside the Harness and shows their PID and working directory as read-only external instances. Process existence confirms liveness; without access to that process's authenticated app-server, its work state, conversation, approvals, and remote controls remain unavailable. The Codex `app-server` WebSocket transport and CLI `--remote` mode are currently experimental, so Codex upgrades may require an adapter update. See the [official app-server documentation](https://learn.chatgpt.com/docs/app-server).

The launch selector applies to each new instance. **Default** passes no permission override and uses the active Codex configuration. **Complete access with approvals** passes `--sandbox danger-full-access --ask-for-approval on-request`, allowing unrestricted filesystem and network access while Codex can still request approval. **Bypass** passes `--dangerously-bypass-approvals-and-sandbox`, removing both sandbox restrictions and command approval prompts. See the [official CLI flag reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli).

Select a local instance to stop it, restart a project, or delete its Harness history record. An existing project's launch permission can be changed by selecting a new mode and restarting it; this opens a new Codex conversation and records the new process ID. Deleting history does not remove Codex's own conversation files. The Master can queue the same instance actions, start a new project, and send a text task to a selected running instance on an online VDI. An idle thread receives a new turn; an active thread receives a steer request. The Slave App polls for those requests over its existing outbound SSH tunnel; the VDI does not expose a listening port. Remote commands require an online Slave App and an active graphical session to open a terminal.

The Slave App sends each instance's status and up to 40 recent activity entries to the laptop. These entries can include user prompts, Codex replies, commands and their output, and file change details. Each entry is capped at 1,600 characters. The Master keeps the latest reported snapshot in memory and shows the activity in a separate instance workbench. The managed Codex terminal connects directly to its local app-server. A separate persistent connection handles Master-originated text turns and their approvals. That bridge retains the latest task and completed reply when the Codex history API does not provide them, so a fast reply is not lost between reports. Approvals originating in the Codex terminal must be answered there. The Master polls for updates and shows partial agent text while it streams from Master-initiated turns.

## Install from source (developers only)

The following instructions are for running from source. Portable packages already include Python and the Tk runtime. A Codex CLI, an OpenSSH client, and a graphical terminal remain separate programs on each Agent machine; choose their executable paths in the application before using them.

Install this package on the laptop and VDI. For example, on Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install '.[master]'
```

On Linux VDI, use `python3 -m venv .venv`, `source .venv/bin/activate`, then `pip install .`. The VDI Agent install needs only `psutil` and `websockets`; FastAPI and Uvicorn are Master-only dependencies.

### Standalone Linux Agent

On an Ubuntu 24.04 x86_64 build machine with Python 3.12, Tk, and PyInstaller installed, run `bash scripts/build_linux_onedir.sh`. The release directory and tar archive are written to `dist/linux`. This layout keeps bundled libraries next to the executable and avoids one-file extraction under `/tmp`. The VDI does not need `pip install`. A Linux executable must be built on Linux; its shared-library compatibility should be checked on the target VDI. Keep the report token in a separate, owner-readable `agent.env` file rather than embedding it in the executable.

Copy the release archive, checksum file, and `install-linux-onedir.sh` to the VDI with `scp`, then run the installer. It checks the checksum, extracts the release under `~/.local/share/codex-agent-harness`, updates `~/.local/bin/codex-agent-harness`, loads the owner-readable `agent.env`, and opens the Slave App. The VDI initiates `scp` from the Laptop when only the VDI-to-Laptop SSH key is configured. Keep its window open while monitoring and launching Codex instances. The same process maintains the SSH tunnel and reports status to the Master. The older `scripts/build_linux.sh` remains available for one-file builds where temporary extraction is permitted.

An optional `--headless` mode and `deploy/codex-agent-harness.service` are available for machines that only report states. When that separate service is running, use `--launcher-only` for the local window so one machine has only one reporter. A user service normally runs while the user manager is active; keeping it active after logout depends on the VDI's lingering policy.

## Start the laptop Master

In a PowerShell window on the laptop:

```powershell
$env:REPORT_TOKEN = "choose-a-long-random-secret"
$env:DASHBOARD_USER = "admin"
$env:DASHBOARD_PASSWORD = "choose-a-different-long-secret"
codex-agent-harness-master
```

Open `http://127.0.0.1:8000` on the laptop and sign in. Keep the Master process running. The Master automatically starts a local Slave reporter and command processor in the same process; the laptop appears as an online machine in the dashboard. Select it to browse local folders, launch Codex, and monitor local instances. Its current state is held in memory; after a restart, connected Agents restore their snapshots on the next report. The laptop's SSH server must be running and reachable from the VDI. The Master command itself never binds to a VPN or public interface.

The web UI has four views: **运行总览** shows machine counts and a prioritized list of instances awaiting approval or reporting errors; **实例工作台** gives the selected instance a large activity stream, conversation/tool filters, pinned approval cards, and a task composer. Its optional inspector contains permissions, model and reasoning effort settings, restart/stop/delete actions, new-instance launch, a read-only remote directory browser, and recent commands. Model choices come from the target machine's Codex `model/list` response. The latest turn's actual model and effort come from that managed thread's Codex `turn_context` metadata when available; launch settings are shown separately. Changing settings on a running instance requires an explicit restart. **机器列表** supports search and status filters; **接入 Agent** shows laptop network addresses and generates VDI SSH configuration snippets. The workbench remembers the selected machine, instance, filter, and inspector state across refreshes. Use an address verified from the VDI, or an internal DNS name that resolves there to the laptop's reachable VPN address. The setup page never displays `REPORT_TOKEN`; enter the same token on each VDI yourself.

Do not start a second `codex-agent-harness --local-master` reporter on the laptop. If a separate local reporter is needed for troubleshooting, start the Master with `--no-local-slave` and run the separate Agent with the same report token.

## Connect a Linux VDI Agent

Create a dedicated SSH key for the Agent and arrange for its public key to be authorized for an appropriate Windows account on the laptop. Follow your company's SSH policy and the [Windows OpenSSH key instructions](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement). The SSH client must be able to log in without a password prompt. A passphrase-protected key can be loaded into `ssh-agent` before starting the Agent.

An example VDI `~/.ssh/config` entry is:

```sshconfig
Host codex-harness-laptop
    HostName YOUR_LAPTOP_INTERNAL_DNS_NAME
    User YOUR_WINDOWS_SSH_ACCOUNT
    IdentityFile ~/.ssh/codex-agent-harness
    IdentitiesOnly yes
    HostKeyAlias codex-harness-laptop
    StrictHostKeyChecking yes
```

On the laptop, read the SSH host fingerprint with `ssh-keyscan -T 5 -t ed25519 127.0.0.1 2>$null | ssh-keygen -lf - -E sha256`. On the VDI, compare it with `ssh-keyscan -T 5 -t ed25519 YOUR_VERIFIED_VPN_IP 2>/dev/null | ssh-keygen -lf - -E sha256`. **Only after the fingerprints match**, save that host key under the alias:

```bash
ssh-keyscan -T 5 -t ed25519 YOUR_VERIFIED_VPN_IP 2>/dev/null | sed 's/^[^ ]*/codex-harness-laptop/' >> ~/.ssh/known_hosts
chmod 600 ~/.ssh/known_hosts
ssh -o BatchMode=yes codex-harness-laptop exit
```

`HostKeyAlias` keeps the trusted host identity stable if the VPN IP changes. With a company DNS name that updates to the new VPN address, no SSH configuration edit is needed; otherwise, update only `HostName`. The SSH server must permit local port forwarding.

Set the same report token on the VDI and launch the Agent:

```bash
export CODEX_AGENT_HARNESS_SSH_TARGET=codex-harness-laptop
export CODEX_AGENT_HARNESS_REPORT_TOKEN='the-same-report-token-as-on-the-laptop'
codex-agent-harness
```

Use `codex-agent-harness --headless` for a machine without a GUI, or `--once` to send one snapshot and exit. The Agent starts and maintains the SSH forward automatically. It does not need a listening port on the VDI. `--master-port` and `--ssh-port` change the default laptop ports 8000 and 22. `--ssh-identity` can specify a key file instead of an SSH config entry.

## API and current limits

| Method | Path | Authentication | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/report` | `Authorization: Bearer <REPORT_TOKEN>` | Replace one machine's complete snapshot. |
| `GET` | `/api/status` | HTTP Basic dashboard credentials | Read current machine states. |
| `GET` | `/healthz` | None | Local health check through the tunnel. |
| `POST` | `/api/commands` | Dashboard credentials | Queue start, stop, restart with a selected permission mode, delete, text task, or approval response for an online machine. |
| `GET` | `/api/commands/pending` | Agent report token | Claim queued commands for one machine. |
| `POST` | `/api/commands/{id}/result` | Agent report token | Report command success or failure. |

The server keeps the latest snapshot and recent command results in memory, and marks a machine offline after 45 seconds without a report. Task text is delivered to the Agent but omitted from the Master status and command history response. Durable history and `GET /api/events` are not implemented yet. Run only one Master process, and keep the laptop awake and connected to the company network while monitoring.
