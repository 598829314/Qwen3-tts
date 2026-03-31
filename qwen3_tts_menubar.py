from __future__ import annotations

import json
import subprocess
import webbrowser
from pathlib import Path
from typing import Any

try:
    import objc
    from AppKit import (
        NSApp,
        NSAlert,
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSBackingStoreBuffered,
        NSButton,
        NSControlStateValueOff,
        NSControlStateValueOn,
        NSFont,
        NSImage,
        NSMakeRect,
        NSMenu,
        NSMenuItem,
        NSStatusBar,
        NSTextField,
        NSVariableStatusItemLength,
        NSWindow,
        NSWindowStyleMaskClosable,
        NSWindowStyleMaskTitled,
    )
    from Foundation import NSData, NSObject, NSBundle, NSRunLoop, NSRunLoopCommonModes, NSTimer
except ImportError as exc:  # pragma: no cover - depends on local PyObjC install
    raise SystemExit(
        "菜单栏应用需要 PyObjC。请先在 ~/venvs/tts 中安装 requirements-app.txt。"
    ) from exc

from qwen3_tts_api import SERVICE_VERSION
from qwen3_tts_paths import get_app_support_dir, get_bundle_resources_dir
from qwen3_tts_service import (
    ServerManager,
    ServiceConfig,
    ServerStatus,
    get_config_path,
    get_log_path,
)


STATUS_TITLE = {
    ServerStatus.STOPPED.value: "已停止",
    ServerStatus.STARTING.value: "启动中",
    ServerStatus.RUNNING.value: "运行中",
    ServerStatus.STOPPING.value: "停止中",
    ServerStatus.ERROR.value: "错误",
    ServerStatus.UNRESPONSIVE.value: "无响应",
}


class SettingsWindowController(NSObject):
    def initWithManager_delegate_(self, manager: ServerManager, delegate: Any):
        self = objc.super(SettingsWindowController, self).init()
        if self is None:
            return None

        self.manager = manager
        self.delegate = delegate
        self.window = None
        self.message_label = None
        self.host_field = None
        self.port_field = None
        self.api_key_field = None
        self.model_root_field = None
        self.prompt_cache_dir_field = None
        self.preload_model_field = None
        self.python_field = None
        self.workspace_field = None
        self.launch_checkbox = None
        self.autostart_checkbox = None
        return self

    def _make_label(self, frame, text):
        label = NSTextField.alloc().initWithFrame_(frame)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setStringValue_(text)
        label.setFont_(NSFont.systemFontOfSize_(12))
        return label

    def _make_field(self, frame, value: str, secure: bool = False):
        field = NSTextField.alloc().initWithFrame_(frame)
        field.setStringValue_(value)
        field.setFont_(NSFont.systemFontOfSize_(12))
        return field

    def _make_checkbox(self, frame, title: str, checked: bool):
        checkbox = NSButton.alloc().initWithFrame_(frame)
        checkbox.setButtonType_(3)
        checkbox.setTitle_(title)
        checkbox.setState_(NSControlStateValueOn if checked else NSControlStateValueOff)
        checkbox.setFont_(NSFont.systemFontOfSize_(12))
        return checkbox

    def _load_config(self):
        config = self.manager.config
        self.host_field.setStringValue_(config.host)
        self.port_field.setStringValue_(str(config.port))
        self.api_key_field.setStringValue_(config.api_key)
        self.model_root_field.setStringValue_(config.model_root)
        self.prompt_cache_dir_field.setStringValue_(config.prompt_cache_dir)
        self.preload_model_field.setStringValue_(config.preload_model)
        self.python_field.setStringValue_(config.python_executable)
        self.workspace_field.setStringValue_(config.workspace_dir)
        self.launch_checkbox.setState_(
            NSControlStateValueOn if config.launch_at_login else NSControlStateValueOff
        )
        self.autostart_checkbox.setState_(
            NSControlStateValueOn
            if config.start_server_on_launch
            else NSControlStateValueOff
        )
        self.message_label.setStringValue_("")

    def _build_window(self):
        if self.window is not None:
            return

        width = 760
        height = 440
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, width, height),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("Qwen3-TTS 设置")
        content = self.window.contentView()

        labels = [
            ("主机", "host_field"),
            ("端口", "port_field"),
            ("API 密钥", "api_key_field"),
            ("模型目录", "model_root_field"),
            ("提示缓存目录", "prompt_cache_dir_field"),
            ("预加载模型", "preload_model_field"),
            ("Python 可执行文件", "python_field"),
            ("工作目录", "workspace_field"),
        ]

        y = height - 50
        for title, attr in labels:
            label = self._make_label(NSMakeRect(20, y, 160, 20), title)
            content.addSubview_(label)
            field = self._make_field(NSMakeRect(190, y - 2, 540, 24), "")
            setattr(self, attr, field)
            content.addSubview_(field)
            y -= 40

        self.launch_checkbox = self._make_checkbox(
            NSMakeRect(20, y - 5, 250, 24),
            "登录时启动应用",
            False,
        )
        content.addSubview_(self.launch_checkbox)
        self.autostart_checkbox = self._make_checkbox(
            NSMakeRect(280, y - 5, 250, 24),
            "打开应用后自动启动服务",
            False,
        )
        content.addSubview_(self.autostart_checkbox)

        self.message_label = self._make_label(NSMakeRect(20, 20, 470, 24), "")
        content.addSubview_(self.message_label)

        save_button = NSButton.alloc().initWithFrame_(NSMakeRect(width - 190, 16, 80, 32))
        save_button.setTitle_("保存")
        save_button.setTarget_(self)
        save_button.setAction_("saveSettings:")
        content.addSubview_(save_button)

        cancel_button = NSButton.alloc().initWithFrame_(NSMakeRect(width - 100, 16, 80, 32))
        cancel_button.setTitle_("关闭")
        cancel_button.setTarget_(self)
        cancel_button.setAction_("closeWindow:")
        content.addSubview_(cancel_button)

        self._load_config()

    def showWindow(self):
        self._build_window()
        self._load_config()
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def closeWindow_(self, _sender):
        if self.window is not None:
            self.window.orderOut_(None)

    def saveSettings_(self, _sender):
        try:
            config = self.manager.config
            config.host = self.host_field.stringValue().strip() or "127.0.0.1"
            config.port = int(self.port_field.stringValue().strip())
            config.api_key = self.api_key_field.stringValue()
            config.model_root = self.model_root_field.stringValue().strip()
            config.prompt_cache_dir = self.prompt_cache_dir_field.stringValue().strip()
            config.preload_model = self.preload_model_field.stringValue().strip()
            config.python_executable = self.python_field.stringValue().strip()
            config.workspace_dir = self.workspace_field.stringValue().strip()
            config.launch_at_login = self.launch_checkbox.state() == NSControlStateValueOn
            config.start_server_on_launch = (
                self.autostart_checkbox.state() == NSControlStateValueOn
            )
            self.manager.save_config()
            if config.launch_at_login:
                self.manager.install_login()
            else:
                self.manager.uninstall_login()
            self.message_label.setStringValue_("已保存。")
            if self.delegate is not None:
                self.delegate.refreshStatus_(None)
        except Exception as exc:
            self.message_label.setStringValue_(f"保存失败：{exc}")


class Qwen3TTSAppDelegate(NSObject):
    def init(self):
        self = objc.super(Qwen3TTSAppDelegate, self).init()
        if self is None:
            return None
        self.manager = ServerManager(ServiceConfig.load())
        self.status_item = None
        self.menu = None
        self.status_header = None
        self.api_header = None
        self.model_header = None
        self.cache_header = None
        self.start_item = None
        self.stop_item = None
        self.restart_item = None
        self.timer = None
        self.settings_controller = None
        self._icon_outline = None
        self._icon_filled = None
        self._icon_warning = None
        return self

    def applicationDidFinishLaunching_(self, _notification):
        self._icon_outline = self._load_menubar_icon("menubar-outline.svg")
        self._icon_filled = self._load_menubar_icon("menubar-filled.svg")
        self._icon_warning = self._load_menubar_icon("menubar-filled.svg")
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        self._build_menu()
        self.refreshStatus_(None)
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            5.0,
            self,
            "refreshStatus:",
            None,
            True,
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        NSApp.activateIgnoringOtherApps_(True)
        if self.manager.config.start_server_on_launch:
            try:
                self.manager.start()
            except Exception:
                pass
            self.refreshStatus_(None)

    def _resources_dir(self) -> Path:
        bundle_resources = get_bundle_resources_dir()
        if bundle_resources is not None:
            asset_dir = bundle_resources / "assets"
            if asset_dir.exists():
                return asset_dir

        direct = Path(__file__).resolve().parent / "assets"
        if direct.exists():
            return direct
        fallback = Path(__file__).resolve().parent / "packaging" / "assets"
        if fallback.exists():
            return fallback

        bundle = NSBundle.mainBundle()
        if bundle and bundle.resourcePath():
            resource_path = Path(str(bundle.resourcePath()))
            asset_dir = resource_path / "assets"
            if asset_dir.exists():
                return asset_dir
        return Path(__file__).resolve().parent

    def _load_menubar_icon(self, filename: str):
        path = self._resources_dir() / filename
        if not path.exists():
            return None
        data = NSData.dataWithContentsOfFile_(str(path))
        if data is None:
            return None
        image = NSImage.alloc().initWithData_(data)
        if image is None:
            return None
        image.setSize_((18, 18))
        image.setTemplate_(True)
        return image

    def _build_menu(self):
        self.menu = NSMenu.alloc().init()

        self.status_header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Qwen3-TTS {SERVICE_VERSION}",
            None,
            "",
        )
        self.status_header.setEnabled_(False)
        self.menu.addItem_(self.status_header)

        self.api_header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"接口：{self.manager.config.api_url}",
            None,
            "",
        )
        self.api_header.setEnabled_(False)
        self.menu.addItem_(self.api_header)

        self.model_header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "模型：-",
            None,
            "",
        )
        self.model_header.setEnabled_(False)
        self.menu.addItem_(self.model_header)

        self.cache_header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "克隆提示：-",
            None,
            "",
        )
        self.cache_header.setEnabled_(False)
        self.menu.addItem_(self.cache_header)
        self.menu.addItem_(NSMenuItem.separatorItem())

        self.start_item = self._make_item("启动服务", "startServer:")
        self.stop_item = self._make_item("停止服务", "stopServer:")
        self.restart_item = self._make_item("重启服务", "restartServer:")
        self.menu.addItem_(self.start_item)
        self.menu.addItem_(self.stop_item)
        self.menu.addItem_(self.restart_item)
        self.menu.addItem_(NSMenuItem.separatorItem())
        self.menu.addItem_(self._make_item("复制接口地址", "copyApiUrl:"))
        self.menu.addItem_(self._make_item("打开配置文件", "openConfig:"))
        self.menu.addItem_(self._make_item("打开日志", "openLogs:"))
        self.menu.addItem_(self._make_item("打开应用目录", "openAppSupport:"))
        self.menu.addItem_(self._make_item("打开模型目录", "openModelsFolder:"))
        self.menu.addItem_(self._make_item("打开设置", "openSettings:"))
        self.menu.addItem_(self._make_item("打开 API 文档", "openApiDocs:"))
        self.menu.addItem_(NSMenuItem.separatorItem())
        self.menu.addItem_(self._make_item("退出", "quitApp:"))
        self.status_item.setMenu_(self.menu)

    def _make_item(self, title: str, action: str):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
        item.setTarget_(self)
        return item

    def _button_title(self, state: dict[str, Any]) -> str:
        status = state["status"]
        if status == ServerStatus.RUNNING.value:
            return "Q3T"
        if status == ServerStatus.STARTING.value:
            return "Q3…"
        if status == ServerStatus.UNRESPONSIVE.value:
            return "Q3!"
        return "Q3t"

    def _status_icon(self, state: dict[str, Any]):
        status = state["status"]
        if status in {ServerStatus.RUNNING.value, ServerStatus.STARTING.value}:
            return self._icon_filled
        if status in {ServerStatus.UNRESPONSIVE.value, ServerStatus.ERROR.value}:
            return self._icon_warning
        return self._icon_outline

    def _reveal_path(self, path: Path):
        subprocess.Popen(["open", "-R", str(path)])

    def _show_alert(self, title: str, message: str):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        alert.runModal()

    def refreshStatus_(self, _sender):
        state = self.manager.status()
        self.status_header.setTitle_(
            f"状态：{STATUS_TITLE.get(state['status'], state['status'])}"
        )
        self.api_header.setTitle_(f"接口：{state['api_url']}")
        self.model_header.setTitle_(f"模型：{state['loaded_model'] or '-'}")
        prompt_cache_count = state["prompt_cache_count"]
        if prompt_cache_count is None:
            self.cache_header.setTitle_("克隆提示：-")
        else:
            self.cache_header.setTitle_(f"克隆提示：{prompt_cache_count}")
        self.start_item.setEnabled_(state["status"] in {ServerStatus.STOPPED.value, ServerStatus.ERROR.value})
        self.stop_item.setEnabled_(
            state["status"] in {ServerStatus.RUNNING.value, ServerStatus.UNRESPONSIVE.value}
        )
        self.restart_item.setEnabled_(
            state["status"] in {ServerStatus.RUNNING.value, ServerStatus.UNRESPONSIVE.value}
        )
        button = self.status_item.button()
        icon = self._status_icon(state)
        if icon is not None:
            button.setImage_(icon)
            button.setTitle_("")
        else:
            button.setTitle_(self._button_title(state))

    def startServer_(self, _sender):
        try:
            self.manager.start()
        except Exception as exc:
            self._append_error(exc)
            self._show_alert("启动服务失败", str(exc))
        self.refreshStatus_(None)

    def stopServer_(self, _sender):
        try:
            self.manager.stop()
        except Exception as exc:
            self._append_error(exc)
            self._show_alert("停止服务失败", str(exc))
        self.refreshStatus_(None)

    def restartServer_(self, _sender):
        try:
            self.manager.restart()
        except Exception as exc:
            self._append_error(exc)
            self._show_alert("重启服务失败", str(exc))
        self.refreshStatus_(None)

    def copyApiUrl_(self, _sender):
        from AppKit import NSPasteboard, NSPasteboardTypeString

        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(self.manager.config.api_url, NSPasteboardTypeString)

    def openConfig_(self, _sender):
        config_path = get_config_path()
        if not config_path.exists():
            self.manager.save_config()
        self._reveal_path(config_path)

    def openLogs_(self, _sender):
        log_path = get_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if not log_path.exists():
            log_path.write_text("", encoding="utf-8")
        self._reveal_path(log_path)

    def openAppSupport_(self, _sender):
        subprocess.Popen(["open", str(get_app_support_dir())])

    def openModelsFolder_(self, _sender):
        subprocess.Popen(["open", self.manager.config.model_root])

    def openSettings_(self, _sender):
        if self.settings_controller is None:
            self.settings_controller = SettingsWindowController.alloc().initWithManager_delegate_(
                self.manager,
                self,
            )
        self.settings_controller.showWindow()

    def openApiDocs_(self, _sender):
        webbrowser.open(f"{self.manager.config.api_url}/docs")

    def quitApp_(self, _sender):
        if self.timer is not None:
            self.timer.invalidate()
        NSApp.terminate_(None)

    def _append_error(self, exc: Exception):
        log_path = get_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event": "menubar-error", "error": str(exc)}) + "\n")


def main() -> int:
    app = NSApplication.sharedApplication()
    delegate = Qwen3TTSAppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
