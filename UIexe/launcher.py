import os
import queue
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

BG, PANEL, BORDER = '#0c1015', '#171c24', '#29313e'
TEXT, MUTED, BLUE = '#eef2f8', '#929dad', '#3478f6'


def project_root():
    base = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
    for candidate in (base, *base.parents):
        if (candidate / 'scripts/start-all.ps1').is_file():
            return candidate
    raise FileNotFoundError('找不到项目 scripts/start-all.ps1')


class App:
    def __init__(self, root):
        self.r, self.home = root, project_root()
        self.events, self.entries = queue.Queue(), []
        self.state, self.since, self.filter = '未启动', None, '全部'
        self.busy = False
        self.url = 'http://127.0.0.1:8000/login'
        root.title('系统控制中心 | Ruralland Contract Extension')
        root.geometry('1180x760')
        root.minsize(960, 640)
        root.configure(bg=BG)
        root.protocol('WM_DELETE_WINDOW', self.close)
        assets = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'UI'
        if (assets / 'startup.ico').exists():
            root.iconbitmap(str(assets / 'startup.ico'))
        header = self.frame(root, BG)
        header.pack(fill='x', padx=26, pady=24)
        if (assets / 'startup.png').exists():
            self.logo = tk.PhotoImage(file=str(assets / 'startup.png'))
            tk.Label(header, image=self.logo, bg=BG).pack(side='left', padx=(0, 16))
        title = self.frame(header, BG)
        title.pack(side='left')
        self.label(title, '系统控制中心', 24, True, BG).pack(anchor='w')
        self.label(title, 'Ruralland Contract Extension', 11, bg=BG, fg=MUTED).pack(anchor='w', pady=(5, 0))
        self.badge = self.label(header, '● 未启动', 12, bg=PANEL)
        self.badge.pack(side='right', ipadx=16, ipady=9)
        controls = self.frame(root)
        controls.pack(fill='x', padx=26)
        self.label(controls, '控制面板', 14, True).pack(anchor='w', padx=20, pady=16)
        self.line(controls)
        actions = self.frame(controls)
        actions.pack(fill='x', padx=20, pady=20)
        self.start_btn = self.button(actions, '▶  启动系统', self.start, BLUE)
        self.open_btn = self.button(actions, '打开系统', self.open_system)
        self.stop_btn = self.button(actions, '■  停止系统', self.stop)
        self.restart_btn = self.button(actions, '↻  重启', lambda: self.stop(True))
        self.button(actions, '打开日志目录', self.open_logs)
        self.button(actions, '清空数据', self.clear_data)
        self.button(actions, '自检', self.check, side='right')
        self.address = self.label(controls, '● 未启动', 11, fg=MUTED)
        self.address.pack(anchor='w', padx=20, pady=(0, 20))
        stats = self.frame(root, BG)
        stats.pack(fill='x', padx=26, pady=18)
        self.values = []
        for i, (name, value) in enumerate([('运行状态', '未启动'), ('已运行时长', '--:--:--'), ('服务模块', '-- / 4'), ('日志条目', '0')]):
            stats.columnconfigure(i, weight=1, uniform='stats')
            tile = self.frame(stats)
            tile.grid(row=0, column=i, sticky='nsew', padx=(0 if i == 0 else 8, 0))
            self.label(tile, name, 11, fg=MUTED).pack(anchor='w', padx=16, pady=(14, 6))
            value_label = self.label(tile, value, 20, True)
            value_label.pack(anchor='w', padx=16, pady=(0, 14))
            self.values.append(value_label)
        logs = self.frame(root)
        logs.pack(fill='both', expand=True, padx=26, pady=(0, 24))
        toolbar = self.frame(logs)
        toolbar.pack(fill='x', padx=16, pady=14)
        self.label(toolbar, '运行日志', 14, True).pack(side='left', padx=(0, 12))
        self.tabs = {}
        for level in ['全部', '信息', '警告', '错误']:
            self.tabs[level] = self.button(toolbar, level, lambda v=level: self.select(v))
        self.button(toolbar, '清空', self.clear, side='right')
        self.button(toolbar, '复制', self.copy, side='right')
        self.auto = tk.BooleanVar(value=True)
        tk.Checkbutton(toolbar, text='自动滚动', variable=self.auto, bg=PANEL, fg=MUTED, selectcolor=BG, activebackground=PANEL).pack(side='right')
        self.line(logs)
        body = self.frame(logs, BG)
        body.pack(fill='both', expand=True)
        scroll = tk.Scrollbar(body)
        scroll.pack(side='right', fill='y')
        self.log = tk.Text(body, bg=BG, fg=MUTED, relief='flat', state='disabled', font=('Microsoft YaHei UI', 10), padx=18, pady=16, wrap='word', yscrollcommand=scroll.set)
        self.log.pack(fill='both', expand=True)
        scroll.config(command=self.log.yview)
        for level, color in [('信息', MUTED), ('警告', '#e9bc6c'), ('错误', '#ff777d')]:
            self.log.tag_configure(level, foreground=color)
        root.bind('<Control-Return>', lambda _: self.start())
        root.bind('<Escape>', lambda _: self.stop())
        self.out('控制台已就绪')
        self.set_state('未启动')
        # 重开启动器时探测既有服务：后端已在监听则恢复「运行中」状态，
        # 避免服务实际在跑、界面却显示「未启动」的误导（停止/自检本就不依赖界面状态）。
        def detect_existing():
            try:
                with socket.create_connection(('127.0.0.1', 8000), timeout=1):
                    self.events.put(('resumed', None))
            except OSError:
                pass
        threading.Thread(target=detect_existing, daemon=True).start()
        root.after(150, self.poll)

    def frame(self, parent, bg=PANEL):
        return tk.Frame(parent, bg=bg)

    def label(self, parent, text, size=11, bold=False, bg=PANEL, fg=TEXT):
        return tk.Label(parent, text=text, bg=bg, fg=fg, font=('Microsoft YaHei UI', size, 'bold' if bold else 'normal'))

    def line(self, parent):
        tk.Frame(parent, height=1, bg=BORDER).pack(fill='x')

    def button(self, parent, text, command, bg=PANEL, side='left'):
        button = tk.Button(parent, text=text, command=command, bg=bg, fg=TEXT, activebackground=BLUE, activeforeground='white', disabledforeground='#525c69', relief='flat', bd=0, padx=12, pady=9, cursor='hand2', font=('Microsoft YaHei UI', 10))
        button.pack(side=side, padx=3)
        return button

    def set_state(self, state):
        self.state = state
        self.badge.config(text='● ' + state, fg='#6ad4ad' if state == '运行中' else MUTED)
        self.values[0].config(text=state)
        self.start_btn.config(state='normal' if not self.busy and state != '运行中' else 'disabled')
        # 停止/重启不依赖界面状态：服务可能是启动器之外拉起的（或启动器重开后状态回到未启动），
        # 只要当前没有操作在执行，就允许停止，避免有残留进程却点不动按钮。
        for button in (self.stop_btn, self.restart_btn):
            button.config(state='normal' if not self.busy else 'disabled')

    def out(self, text):
        for line in text.splitlines():
            level = '错误' if any(x in line.lower() for x in ['error', 'exception', '失败', '错误']) else '警告' if any(x in line.lower() for x in ['warn', '警告']) else '信息'
            self.entries.append((level, time.strftime('%H:%M:%S') + '  ' + line))
        self.entries = self.entries[-5000:]
        self.render()

    def render(self):
        self.log.config(state='normal')
        self.log.delete('1.0', 'end')
        for level, line in self.entries:
            if self.filter in ('全部', level):
                self.log.insert('end', line + '\n', level)
        self.log.config(state='disabled')
        if self.auto.get():
            self.log.see('end')
        self.values[3].config(text=str(len(self.entries)))
        for level, button in self.tabs.items():
            count = sum(1 for item in self.entries if level == '全部' or item[0] == level)
            button.config(text=f'{level} {count}', bg=BORDER if level == self.filter else PANEL)

    def select(self, level):
        self.filter = level
        self.render()

    def clear(self):
        self.entries.clear()
        self.render()

    def copy(self):
        self.r.clipboard_clear()
        self.r.clipboard_append(self.log.get('1.0', 'end-1c'))

    def open_logs(self):
        path = self.home / 'runtime/logs'
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def system_url(self):
        """系统访问地址：优先用当前机器 IP，取不到时退回本机回环地址。"""
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            ip = '127.0.0.1'
        return f'http://{ip}:8000/login'

    def active_services(self):
        """返回仍在监听的服务名，用于阻止「未启动」状态误删正在使用的数据。"""
        active = []
        for name, port in [('PostgreSQL', 15432), ('Redis', 16379), ('GeoServer', 8080), ('后端', 8000)]:
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                    active.append(f'{name}({port})')
            except OSError:
                continue
        return active

    @staticmethod
    def _force_remove(func, path, _exc_info):
        """删除只读文件时先去掉只读属性再重试。"""
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            raise

    def clear_data(self):
        """清空 runtime/data 下的全部文件和文件夹（仅系统未启动时可用）。"""
        if self.busy or self.state in ('启动中', '停止中'):
            messagebox.showinfo('清空数据', '系统正在启动或停止，请稍后再试。')
            return
        if self.state == '运行中':
            messagebox.showinfo('清空数据', '请先点击「停止系统」，停止后再清空数据。')
            return
        # 状态可能是启动器启动前就已存在的外部服务，再按端口兜底确认一次。
        active = self.active_services()
        if active:
            messagebox.showinfo('清空数据', '以下服务仍在运行：' + '、'.join(active) + '\n请先停止系统后再清空数据。')
            return
        data_dir = self.home / 'runtime' / 'data'
        if not data_dir.is_dir():
            messagebox.showinfo('清空数据', f'数据目录不存在：\n{data_dir}')
            return
        if not messagebox.askyesno('清空数据', '本操作将删除当前系统下的所有数据，请慎重检查后操作！！！'):
            return
        # 顺带重跑安装配置：坐标系/行政区码固化在数据库里，清空后正好可以重新选。
        # 不真的重跑 install.ps1——启动器的 PowerShell 是无窗口非交互宿主，Read-Host 拿不到输入；
        # install.ps1 的体力活（initdb、建库）由 start-all.ps1 在下次启动时自动补齐。
        reconfigure = messagebox.askyesno(
            '清空数据',
            '清空完成后是否重新进行安装配置（目标坐标系 / 行政区划代码）？\n\n'
            '选「是」：清空后弹出配置窗口，下次启动按新配置重建空环境。\n'
            '选「否」：保留现有配置，下次启动按原配置重建。')
        self.busy = True
        self.address.config(text='正在清空数据...')
        self.out('开始清空数据目录：' + str(data_dir))

        def worker():
            removed, errors = 0, []
            for item in list(data_dir.iterdir()):
                try:
                    if item.is_dir() and not item.is_symlink():
                        shutil.rmtree(item, onerror=self._force_remove)
                    else:
                        item.unlink()
                    removed += 1
                except OSError as exc:
                    errors.append(f'{item.name}: {exc}')
            self.events.put(('cleared', (removed, errors, reconfigure)))

        threading.Thread(target=worker, daemon=True).start()

    def reconfigure(self):
        """清空数据后重新收集安装配置（坐标系 / 行政区划码），写入 backend\\.env。

        等价于重跑 install.ps1 的交互部分；initdb、建库等体力活由 start-all.ps1
        在下次启动时自动补齐（pgdata 已清空会重新 initdb，空间表由后端 bootstrap 重建）。
        """
        self.out('开始重新安装配置（目标坐标系 / 行政区划代码）...')
        result = self.setup_dialog(
            title='重新安装配置',
            confirm_text='✔  保存配置',
            heading='请确认部署地的两项配置（将写入 backend\\.env，坐标系首次启动后固化不可改）')
        if result is None:
            self.out('已取消重新配置：backend\\.env 保留原 TARGET_SRID / REGION_SEED_COUNTIES，下次启动仍按原配置初始化。')
            return
        srid, counties = result
        self.write_env_value('TARGET_SRID', str(srid))
        if counties:
            self.write_env_value('REGION_SEED_COUNTIES', counties)
        else:
            # 这次明确选择不自动建区域树：必须清掉旧码，否则残留配置会把旧区域树灌回"空环境"。
            self.remove_env_key('REGION_SEED_COUNTIES')
        self.out('新安装配置已写入 backend\\.env：TARGET_SRID=' + str(srid)
                 + '，REGION_SEED_COUNTIES=' + (counties if counties else '（未配置，跳过区域自动建树）'))
        messagebox.showinfo('重新安装配置', '配置已保存。点击「启动系统」即可按新配置重建空环境。')

    def open_system(self):
        """在默认浏览器中打开系统界面。"""
        url = self.url or self.system_url()
        try:
            with urlopen(url, timeout=2):
                pass
        except HTTPError:
            # 服务有响应（如 401/403）说明已启动，照常打开浏览器。
            pass
        except (URLError, OSError):
            messagebox.showinfo('打开系统', '系统尚未启动，请先点击「启动系统」。')
            return
        webbrowser.open(url)
        self.out('已在浏览器打开：' + url)

    def check(self):
        def worker():
            count = 0
            for name, port in [('PostgreSQL', 15432), ('Redis', 16379), ('GeoServer', 8080), ('后端', 8000)]:
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=1):
                        count += 1
                    self.events.put(('log', f'{name}: 端口 {port} 可连接'))
                except OSError:
                    self.events.put(('log', f'警告：{name} 端口 {port} 无响应'))
            self.events.put(('modules', count))
        threading.Thread(target=worker, daemon=True).start()

    # ── 首次安装配置：控制中心是非交互宿主，install.ps1 的 Read-Host 拿不到输入
    # （2026-11-10 实踩：目标机直接点「启动系统」报"目标坐标系尚未配置"）。
    # 预检到未安装且未配置 TARGET_SRID 时，先弹窗收集配置写入 backend\.env，
    # 再走正常启动，install.ps1 读到配置即全程零输入。

    @staticmethod
    def parse_srid(text):
        """带号 25-45 → EPSG 4488+带号；或直接接受 EPSG 4513-4533。"""
        if not text or not text.isdigit():
            raise ValueError('带号必须是数字：25-45 的带号，或 EPSG 代码 4513-4533。')
        value = int(text)
        if 25 <= value <= 45:
            return 4488 + value
        if 4513 <= value <= 4533:
            return value
        raise ValueError('带号超出范围：请输入 25-45 的带号，或 EPSG 代码 4513-4533。')

    @staticmethod
    def parse_counties(text):
        """区县码：6 位数字，多个用逗号分隔；空 = 跳过区域自动建树。"""
        if not text:
            return None
        parts = [p.strip() for p in re.split(r'[，,;；、]', text) if p.strip()]
        bad = [p for p in parts if not re.match(r'^\d{6}$', p)]
        if bad:
            raise ValueError('行政区划码必须是 6 位数字，收到：' + '、'.join(bad))
        return ','.join(parts) if parts else None

    def read_env_text(self):
        path = self.home / 'backend' / '.env'
        if path.is_file():
            return path.read_text(encoding='utf-8-sig')
        return ''

    @staticmethod
    def env_value(text, key):
        match = re.search(rf'^\s*{key}\s*=\s*(.*)$', text, re.MULTILINE)
        return match.group(1).strip() if match else None

    def write_env_value(self, key, value):
        """覆盖写单个键，保留 .env 其余行；UTF-8 无 BOM（pydantic-settings 不认 BOM）。"""
        path = self.home / 'backend' / '.env'
        lines = [l for l in self.read_env_text().splitlines() if not re.match(rf'^\s*{key}\s*=', l)]
        lines.append(f'{key}={value}')
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def remove_env_key(self, key):
        """从 .env 删除单个键；键不存在或文件不在时静默返回。"""
        path = self.home / 'backend' / '.env'
        if not path.is_file():
            return
        lines = [l for l in self.read_env_text().splitlines() if not re.match(rf'^\s*{key}\s*=', l)]
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def needs_setup(self):
        """已安装（有 installed.json 标记）或已配置 TARGET_SRID 都视为不用弹窗。"""
        if (self.home / 'runtime' / '.state' / 'installed.json').is_file():
            return False
        return not self.env_value(self.read_env_text(), 'TARGET_SRID')

    def setup_dialog(self, title='首次安装配置', confirm_text='✔  保存并启动', heading='首次安装需要两项配置（将写入 backend\\.env）'):
        """模态对话框收集安装配置，返回 (srid, counties) 或取消时 None。"""
        dialog = tk.Toplevel(self.r)
        dialog.title(title)
        dialog.geometry('620x540')
        dialog.minsize(620, 540)
        dialog.configure(bg=BG)
        dialog.transient(self.r)
        dialog.grab_set()

        header = tk.Frame(dialog, bg=BG)
        header.pack(fill='x', padx=24, pady=(20, 4))
        self.label(header, heading, 13, True, bg=BG).pack(anchor='w')
        tk.Label(header, text='目标坐标系用于地图投影，初始化后不可更改，请按项目所在县经度选择。',
                 bg=BG, fg=MUTED, font=('Microsoft YaHei UI', 10)).pack(anchor='w', pady=(4, 0))

        body = tk.Frame(dialog, bg=PANEL)
        body.pack(fill='both', expand=True, padx=24, pady=(12, 0))

        self.label(body, '① 目标坐标系带号（必填）', 11, True).pack(anchor='w', padx=16, pady=(14, 4))
        srid_entry = tk.Entry(body, font=('Microsoft YaHei UI', 11), relief='flat', bd=0, highlightthickness=1, highlightbackground=BORDER)
        srid_entry.pack(fill='x', padx=16, ipady=6)
        tk.Label(body, text='3 度带：填 25-45 的带号（中央子午线 = 带号×3°），或直接填 EPSG 代码 4513-4533。\nEPSG = 4488 + 带号。例：39 带（117°E）= 4527，40 带（120°E）= 4528。',
                 bg=PANEL, fg=MUTED, font=('Microsoft YaHei UI', 9), wraplength=540, justify='left').pack(anchor='w', padx=16, pady=(4, 10))

        self.label(body, '② 区县行政区划代码（可选，6 位数字）', 11, True).pack(anchor='w', padx=16, pady=(0, 4))
        county_entry = tk.Entry(body, font=('Microsoft YaHei UI', 11), relief='flat', bd=0, highlightthickness=1, highlightbackground=BORDER)
        county_entry.pack(fill='x', padx=16, ipady=6)
        tk.Label(body, text='国家统计局县级码（如 150523）或市级码（末两位 00，初始化全市旗县），多个用逗号分隔。\n留空则跳过区域自动建树，之后可在系统「区域管理」里手工维护。',
                 bg=PANEL, fg=MUTED, font=('Microsoft YaHei UI', 9), wraplength=540, justify='left').pack(anchor='w', padx=16, pady=(4, 10))

        result = {'srid': None, 'counties': None}

        def confirm(_event=None):
            try:
                srid = self.parse_srid(srid_entry.get().strip())
                counties = self.parse_counties(county_entry.get().strip())
            except ValueError as exc:
                messagebox.showwarning('首次安装配置', str(exc), parent=dialog)
                return
            result['srid'], result['counties'] = srid, counties
            dialog.destroy()

        buttons = tk.Frame(dialog, bg=BG)
        buttons.pack(fill='x', padx=24, pady=16)
        ok_btn = self.button(buttons, confirm_text, confirm, bg=BLUE)
        self.button(buttons, '取消', dialog.destroy)
        dialog.bind('<Return>', confirm)
        dialog.bind('<Escape>', lambda _: dialog.destroy())
        srid_entry.focus_set()
        self.r.wait_window(dialog)
        return (result['srid'], result['counties']) if result['srid'] else None

    def start(self):
        if not self.busy and self.state != '运行中':
            if self.needs_setup():
                result = self.setup_dialog()
                if result is None:
                    self.out('已取消首次安装配置，系统未启动。也可在命令行运行 scripts\\install.ps1 完成安装。')
                    return
                srid, counties = result
                self.write_env_value('TARGET_SRID', str(srid))
                if counties:
                    self.write_env_value('REGION_SEED_COUNTIES', counties)
                message = '首次安装配置已写入 backend\\.env：TARGET_SRID=' + str(srid)
                if counties:
                    message += '，REGION_SEED_COUNTIES=' + counties
                self.out(message)
            self.run('start-all.ps1')

    def stop(self, restart=False):
        # 未启动状态下也允许停止：用于清理启动器之外遗留的进程。
        if not self.busy:
            self.run('stop-all.ps1', restart)

    def run(self, script, restart=False):
        self.busy = True
        starting = script.startswith('start')
        self.set_state('启动中' if starting else '停止中')
        self.address.config(text=self.state + '...')
        self.out(self.state + '...')
        def worker():
            try:
                path = self.home / 'scripts' / script
                command = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); & '" + str(path).replace("'", "''") + "'" + (" -NonInteractive" if starting else "")
                process = subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', command], cwd=self.home, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
                for line in process.stdout:
                    self.events.put(('log', line))
                if process.wait() != 0:
                    raise RuntimeError('脚本执行失败，请查看日志')
                if starting:
                    for _ in range(90):
                        try:
                            with urlopen('http://127.0.0.1:8000/login', timeout=2) as response:
                                if response.status == 200:
                                    break
                        except OSError:
                            pass
                        time.sleep(1)
                    else:
                        raise RuntimeError('登录页面等待超时')
                self.events.put(('started' if starting else 'stopped', restart))
            except Exception as exc:
                self.events.put(('failed', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        for _ in range(200):
            try:
                event, value = self.events.get_nowait()
            except queue.Empty:
                break
            if event == 'log':
                self.out(value)
            elif event == 'modules':
                self.values[2].config(text=f'{value} / 4')
            elif event == 'cleared':
                removed, errors, reconfigure = value
                self.busy = False
                if self.state == '未启动':
                    self.address.config(text='● 已停止')
                if errors:
                    self.out(f'清空数据完成：已删除 {removed} 项，{len(errors)} 项未能删除')
                    for line in errors:
                        self.out('  清理失败：' + line)
                    messagebox.showwarning('清空数据', f'已删除 {removed} 项，{len(errors)} 项未能删除（可能被占用），详情见运行日志。')
                    if reconfigure:
                        # 旧库没删干净时 system_config 里还固化着旧坐标系，此时换 .env
                        # 会和库内固化值打架（启动校验不一致），宁可跳过让用户先处理。
                        self.out('警告：数据目录未清空彻底，本次跳过重新配置（新旧配置混用会导致坐标系校验冲突）。')
                else:
                    self.out(f'数据目录已清空（{removed} 项）')
                    messagebox.showinfo('清空数据', f'已清空数据目录（{removed} 项）。')
                    if reconfigure:
                        self.reconfigure()
            else:
                self.busy = False
                if event == 'started':
                    self.since = time.monotonic()
                    self.set_state('运行中')
                    try:
                        ip = socket.gethostbyname(socket.gethostname())
                        self.url = url = f'http://{ip}:8000/login'
                        self.address.config(text='系统访问地址：' + url)
                        webbrowser.open(url)
                    except OSError as exc:
                        self.out('警告：' + str(exc))
                    self.check()
                elif event == 'resumed':
                    # 重开启动器时服务已在跑：恢复状态，但不自动弹浏览器、
                    # 不重置计时（已运行时长未知，保持 --:--:--）。
                    self.set_state('运行中')
                    self.url = self.system_url()
                    self.address.config(text='系统已在运行（启动器重开），访问地址：' + self.url)
                    self.out('检测到后端已在运行，状态已恢复为「运行中」')
                    self.check()
                elif event == 'stopped':
                    self.since = None
                    self.set_state('未启动')
                    self.address.config(text='● 已停止')
                    self.values[2].config(text='0 / 4')
                    if value:
                        self.start()
                elif event == 'failed':
                    self.set_state('异常')
                    self.address.config(text='执行失败，请查看运行日志')
                    self.out('错误：' + value)
        elapsed = int(time.monotonic() - self.since) if self.since else None
        self.values[1].config(text=f'{elapsed // 3600:02}:{elapsed // 60 % 60:02}:{elapsed % 60:02}' if elapsed is not None else '--:--:--')
        self.r.after(150, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('系统控制中心', '服务操作正在执行，请等待完成。')
        elif self.state == '运行中':
            if messagebox.askyesno('关闭控制中心', '关闭窗口后服务仍会继续运行，确认关闭？'):
                self.r.destroy()
        else:
            self.r.destroy()


if __name__ == '__main__':
    window = tk.Tk()
    App(window)
    window.mainloop()
