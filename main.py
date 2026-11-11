# -*- coding: utf-8 -*-
"""外推法作图 · WinUI3 (Microsoft.UI.Xaml) 主程序

纯 Python 通过 PyWinRT 调用 Windows App SDK 的 WinUI3 XAML 控件；
界面在 ui.xaml 里，数据/拟合在 core.py，出图在 plotter.py。
启动：.venv\\Scripts\\python.exe main.py   （或直接双击 run.bat）
"""
from __future__ import annotations

import math
import os
import re
import sys
import tempfile
import traceback
from datetime import timedelta
from pathlib import Path

from typing_extensions import override

from winrt.microsoft.ui.xaml import (
    Application, ApplicationInitializationCallbackParams,
    FrameworkElement, LaunchActivatedEventArgs, Window, Visibility,
)
from winrt.microsoft.ui.xaml.controls import (
    XamlControlsResources, NavigationView, NavigationViewItem, Button,
    TextBox, TextBlock, ComboBox, NumberBox, CheckBox, Slider,
    Image as XamlImage, ToggleSwitch, StackPanel,
)
from winrt.microsoft.ui.xaml.markup import (
    IXamlMetadataProvider, IXamlType, XamlReader, XmlnsDefinition,
)
from winrt.microsoft.ui.xaml.xamltypeinfo import XamlControlsXamlMetaDataProvider
from winrt.microsoft.ui.xaml.media.imaging import BitmapImage
from winrt.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import (
    InitializeOptions, initialize,
)
from winrt.microsoft.ui.dispatching import DispatcherQueue
from winrt.runtime import ApartmentType, init_apartment
from winrt.system import Array
from winrt.windows.ui.xaml.interop import TypeKind, TypeName
from winrt.windows.foundation import Uri
from winrt.windows.graphics import SizeInt32

import core
from core import (FONTS, LEGEND_POS, LINESTYLES, MARKERS, PALETTE,
                  FitSegment, PlotConfig, Series, _fmt_num,
                  compute_fits, fit_report)
from plotter import export_figure, render_png

# 源码运行与 PyInstaller 冻结运行用不同的基准目录：
#   APP_DIR    = 用户可见目录（源码目录 / exe 所在目录）→ 日志、输出、工程文件
#   BUNDLE_DIR = 资源目录（源码目录 / _MEIPASS）→ ui.xaml 等随包资源
#   CACHE      = 系统临时目录，避免往只读的解压目录写预览位图
FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = (Path(sys.executable).resolve().parent if FROZEN
           else Path(__file__).resolve().parent)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", str(APP_DIR)))
ROOT = APP_DIR
XAML_PATH = BUNDLE_DIR / "ui.xaml"
ICON_PATH = BUNDLE_DIR / "sakura.ico"
CACHE = Path(tempfile.gettempdir()) / "extrapolation_preview"
OUTPUT = APP_DIR / "output"
SMOKE = "--smoke" in sys.argv          # 冻结版回归自测：出图+导出后自动退出
PAGES = ["data", "axes", "style", "fit", "output"]
SLOTS = 6

MARKER_ORDER = list(MARKERS.values())          # o s ^ D x none
LINE_ORDER = list(LINESTYLES.values())         # - -- -. : none
FIT_LINE_ORDER = ["-", "--", "-.", ":"]        # 拟合段 ComboBox 的前 4 项
GRID_ORDER = ["-", "--", ":", "-."]            # XAML 里网格线型的顺序
LEGEND_ORDER = list(LEGEND_POS.values())
FONT_ORDER = list(FONTS.keys())
DPI_ORDER = [130, 200, 300, 600]

DEMO_A = """0\t296.20
30\t296.28
60\t296.37
90\t296.45
120\t296.53"""
DEMO_B = """180\t305.10
210\t305.00
240\t304.90
270\t304.80
300\t304.70"""

WIDGET_TYPES = {
    "nav": NavigationView,
    "page_data": StackPanel, "page_axes": StackPanel, "page_style": StackPanel,
    "page_fit": StackPanel, "page_output": StackPanel,
    "series_combo": ComboBox, "series_name": TextBox, "data_text": TextBox,
    "data_status": TextBlock, "csv_path": TextBox,
    "title": TextBox, "xlabel": TextBox, "ylabel": TextBox,
    "xmin": NumberBox, "xmax": NumberBox, "ymin": NumberBox, "ymax": NumberBox,
    "xstep": NumberBox, "ystep": NumberBox, "minor": NumberBox,
    "spine_width": NumberBox, "grid_alpha": Slider,
    "grid_major": CheckBox, "grid_minor": CheckBox,
    "ticks_in": CheckBox, "show_top_right": CheckBox, "grid_style": ComboBox,
    "style_marker": ComboBox, "style_msize": NumberBox,
    "style_linestyle": ComboBox, "style_lwidth": NumberBox,
    "style_color": ComboBox, "style_errorbar": CheckBox, "style_error": TextBox,
    "style_font": ComboBox, "font_size": NumberBox, "title_size": NumberBox,
    "width_in": NumberBox, "height_in": NumberBox, "dpi": NumberBox,
    "show_legend": CheckBox, "legend_pos": ComboBox, "transparent": CheckBox,
    "show_x_intercept": CheckBox, "show_delta": CheckBox,
    "out_dir": TextBox, "out_name": TextBox, "out_dpi": ComboBox,
    "project_path": TextBox,
    "auto_preview": ToggleSwitch, "status": TextBlock,
    "preview": XamlImage, "result_text": TextBlock,
}
for _t in ("A", "B"):
    _p = "fit" + _t
    WIDGET_TYPES.update({
        _p + "_enabled": CheckBox, _p + "_label": TextBox,
        _p + "_series": ComboBox, _p + "_from": NumberBox, _p + "_to": NumberBox,
        _p + "_extrap": NumberBox, _p + "_linestyle": ComboBox,
        _p + "_equation": CheckBox, _p + "_point": CheckBox,
    })

BUTTONS = [
    "btn_add_series", "btn_del_series", "btn_demo", "btn_load_csv",
    "btn_export_png", "btn_export_svg", "btn_export_pdf", "btn_export_txt",
    "btn_open_dir", "btn_save_project", "btn_load_project", "btn_refresh",
]
for _n in BUTTONS:
    WIDGET_TYPES[_n] = Button


def load_window() -> Window:
    """加载 XAML；若个别内联 XAML 属性不被 XamlReader 支持，自动降级重试。"""
    text = XAML_PATH.read_text(encoding="utf-8")
    # XamlReader 用严格 XML 注释解析：注释体内出现 "--" 会报 incorrect comment syntax。
    # 界面文件里的分隔注释只给人看，加载前统一剥离。
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    notes = []
    for attempt in range(3):
        try:
            return XamlReader.load(text).as_(Window)
        except Exception as e:
            notes.append(f"第 {attempt + 1} 次 XAML 解析失败: {e}")
            if attempt == 0:
                text = re.sub(r'\s+Icon="[^"]*"', "", text)
                text = re.sub(r'\s+Style="\{ThemeResource [^"]*\}"', "", text)
            elif attempt == 1:
                text = re.sub(r'\s+(ZoomMode|MinZoomFactor|MaxZoomFactor|'
                              r'CompactModeThresholdWidth|OpenPaneLength|'
                              r'IsTextSelectionEnabled|FontWeight)="[^"]*"', "", text)
            else:
                break
    (ROOT / "xaml_error.log").write_text("\n".join(notes), encoding="utf-8")
    raise RuntimeError("XAML 无法解析，详见 xaml_error.log\n" + "\n".join(notes))


class ExtrapolationApp(Application, IXamlMetadataProvider):
    def __init__(self):
        super().__init__()
        self._provider = XamlControlsXamlMetaDataProvider()
        self.c: dict[str, object] = {}
        self.series: list[Series] = []
        self._cur_slot = 0
        self._ready = False
        self._tick = 0
        self._nav_items: list[NavigationViewItem] = []

    # ------------------------------------------------------------ 小工具
    @staticmethod
    def _b(w) -> bool:
        v = w.is_checked
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        try:
            return bool(v.value)
        except Exception:
            return bool(v)

    def _idx(self, name: str, n: int) -> int:
        try:
            i = int(self.c[name].selected_index)
        except Exception:
            return 0
        return max(0, min(n - 1, i))

    def _num(self, name: str) -> float:
        try:
            return float(self.c[name].value)
        except Exception:
            return float("nan")

    def _numstr(self, name: str) -> str:
        v = self._num(name)
        return "" if math.isnan(v) else f"{v:g}"

    def _set_num(self, name: str, value) -> None:
        f = _fmt_num(str(value)) if value not in (None, "") else None
        try:
            self.c[name].value = f if f is not None else float("nan")
        except Exception:
            pass

    def _set_check(self, name: str, value: bool) -> None:
        try:
            self.c[name].is_checked = bool(value)
        except Exception:
            pass

    def _set_index(self, name: str, value: int) -> None:
        try:
            self.c[name].selected_index = int(value)
        except Exception:
            pass

    def _set_text(self, name: str, value: str) -> None:
        try:
            self.c[name].text = str(value or "")
        except Exception:
            pass

    def set_status(self, msg: str) -> None:
        self._set_text("status", msg)

    # ------------------------------------------------------------ 状态收集
    def _sync_series_from_ui(self, slot: int) -> None:
        """把「当前序列」相关控件的值写回指定槽位。"""
        s = self.series[slot]
        s.name = self.c["series_name"].text or f"序列 {slot + 1}"
        s.raw = self.c["data_text"].text or ""
        s.marker = MARKER_ORDER[self._idx("style_marker", len(MARKER_ORDER))]
        s.markersize = self._num("style_msize")
        s.linestyle = LINE_ORDER[self._idx("style_linestyle", len(LINE_ORDER))]
        s.linewidth = self._num("style_lwidth")
        s.color = PALETTE[self._idx("style_color", len(PALETTE))]
        s.show_errorbar = self._b(self.c["style_errorbar"])
        s.error = self.c["style_error"].text or ""

    def _sync_style_controls(self, slot: int) -> None:
        """切换槽位时，把该槽的样式填回控件。"""
        s = self.series[slot]
        self._set_text("series_name", s.name)
        self._set_text("data_text", s.raw)
        self._set_index("style_marker", MARKER_ORDER.index(s.marker) if s.marker in MARKER_ORDER else 0)
        self._set_index("style_linestyle", LINE_ORDER.index(s.linestyle) if s.linestyle in LINE_ORDER else 0)
        self._set_index("style_color", PALETTE.index(s.color) if s.color in PALETTE else 0)
        self._set_num("style_msize", s.markersize)
        self._set_num("style_lwidth", s.linewidth)
        self._set_check("style_errorbar", s.show_errorbar)
        self._set_text("style_error", s.error)

    def collect(self) -> tuple[PlotConfig, list[Series]]:
        self._sync_series_from_ui(self._cur_slot)
        segs = []
        for t in ("A", "B"):
            p = "fit" + t
            segs.append(FitSegment(
                enabled=self._b(self.c[p + "_enabled"]),
                label=self.c[p + "_label"].text or f"拟合 {t}",
                series=self._idx(p + "_series", SLOTS),
                x_from=self._numstr(p + "_from"),
                x_to=self._numstr(p + "_to"),
                extrap_to=self._numstr(p + "_extrap"),
                linestyle=FIT_LINE_ORDER[self._idx(p + "_linestyle", len(FIT_LINE_ORDER))],
                linewidth=1.6,
                show_equation=self._b(self.c[p + "_equation"]),
                show_point=self._b(self.c[p + "_point"]),
            ))
        cfg = PlotConfig(
            title=self.c["title"].text,
            xlabel=self.c["xlabel"].text,
            ylabel=self.c["ylabel"].text,
            font=FONT_ORDER[self._idx("style_font", len(FONT_ORDER))],
            font_size=self._num("font_size"),
            title_size=self._num("title_size"),
            width_in=self._num("width_in"),
            height_in=self._num("height_in"),
            dpi=int(self._num("dpi") or 130),
            transparent=self._b(self.c["transparent"]),
            xmin=self._numstr("xmin"), xmax=self._numstr("xmax"),
            ymin=self._numstr("ymin"), ymax=self._numstr("ymax"),
            xstep=self._numstr("xstep"), ystep=self._numstr("ystep"),
            minor=int(self._num("minor") or 0),
            grid_major=self._b(self.c["grid_major"]),
            grid_minor=self._b(self.c["grid_minor"]),
            grid_style=GRID_ORDER[self._idx("grid_style", len(GRID_ORDER))],
            grid_alpha=self._num("grid_alpha"),
            ticks_in=self._b(self.c["ticks_in"]),
            show_top_right=self._b(self.c["show_top_right"]),
            spine_width=self._num("spine_width") or 1.0,
            show_legend=self._b(self.c["show_legend"]),
            legend_pos=LEGEND_ORDER[self._idx("legend_pos", len(LEGEND_ORDER))],
            segments=segs,
            show_x_intercept=self._b(self.c["show_x_intercept"]),
            show_delta=self._b(self.c["show_delta"]),
        )
        return cfg, self.series

    def apply_config_to_ui(self, cfg: PlotConfig) -> None:
        """载入工程 / 载入示例时，把配置写回所有控件。"""
        for n in ("title", "xlabel", "ylabel"):
            self._set_text(n, getattr(cfg, n))
        for n in ("xmin", "xmax", "ymin", "ymax", "xstep", "ystep"):
            self._set_num(n, getattr(cfg, n))
        self._set_num("minor", cfg.minor)
        self._set_num("spine_width", cfg.spine_width)
        try:
            self.c["grid_alpha"].value = cfg.grid_alpha
        except Exception:
            pass
        for n in ("grid_major", "grid_minor", "ticks_in", "show_top_right",
                  "show_legend", "transparent", "show_x_intercept", "show_delta"):
            self._set_check(n, getattr(cfg, n))
        self._set_index("grid_style", GRID_ORDER.index(cfg.grid_style) if cfg.grid_style in GRID_ORDER else 1)
        self._set_index("legend_pos", LEGEND_ORDER.index(cfg.legend_pos) if cfg.legend_pos in LEGEND_ORDER else 0)
        self._set_index("style_font", FONT_ORDER.index(cfg.font) if cfg.font in FONT_ORDER else 0)
        for n in ("font_size", "title_size", "width_in", "height_in", "dpi"):
            self._set_num(n, getattr(cfg, n))
        for i, t in enumerate(("A", "B")):
            p = "fit" + t
            seg = cfg.segments[i] if i < len(cfg.segments) else FitSegment()
            self._set_check(p + "_enabled", seg.enabled)
            self._set_text(p + "_label", seg.label)
            self._set_index(p + "_series", seg.series)
            self._set_num(p + "_from", seg.x_from)
            self._set_num(p + "_to", seg.x_to)
            self._set_num(p + "_extrap", seg.extrap_to)
            self._set_index(p + "_linestyle",
                            FIT_LINE_ORDER.index(seg.linestyle) if seg.linestyle in FIT_LINE_ORDER else 1)
            self._set_check(p + "_equation", seg.show_equation)
            self._set_check(p + "_point", seg.show_point)

    # ------------------------------------------------------------ 刷新 / 出图
    def schedule(self) -> None:
        """参数变化 → 防抖 230ms 后重画，避免拖滑块时狂刷 matplotlib。"""
        if not self._ready:
            return
        try:
            if self.c["auto_preview"].is_on:
                self._timer.stop()
                self._timer.start()
        except Exception:
            self.refresh()

    def refresh(self) -> None:
        if not self._ready:
            return
        try:
            cfg, series = self.collect()
            fits = compute_fits(cfg, series)
            png = render_png(cfg, series, fits)
            CACHE.mkdir(parents=True, exist_ok=True)
            self._tick += 1
            p = CACHE / f"preview_{self._tick % 3}.png"
            p.write_bytes(png)
            bmp = BitmapImage()
            bmp.uri_source = Uri(p.as_uri())
            self.c["preview"].source = bmp
            self.c["result_text"].text = fit_report(fits, cfg)
            xs, ys, skipped = series[self._cur_slot].points()
            tip = f"当前序列：{len(xs)} 个有效点"
            if skipped:
                tip += f"（跳过 {len(skipped)} 行表头/无效行）"
            self.c["data_status"].text = tip
            self.set_status(f"预览已更新 · {len(png) // 1024} KB · {cfg.font}")
        except Exception as e:
            (ROOT / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
            self.set_status(f"出图失败：{e}")

    # ------------------------------------------------------------ 动作
    def on_series_changed(self) -> None:
        new = self._idx("series_combo", SLOTS)
        self._sync_series_from_ui(self._cur_slot)
        self._cur_slot = new
        self._sync_style_controls(new)
        self.schedule()

    def switch_page(self, key: str) -> None:
        for k in PAGES:
            self.c["page_" + k].visibility = (
                Visibility.VISIBLE if k == key else Visibility.COLLAPSED)

    def on_nav(self, sender, args) -> None:
        for i, key in enumerate(PAGES):
            try:
                if self._nav_items[i].is_selected:
                    self.switch_page(key)
                    break
            except Exception:
                continue

    def load_demo(self) -> None:
        self.series = [Series(name=f"序列 {i + 1}", raw="", color=PALETTE[i % 6])
                       for i in range(SLOTS)]
        self.series[0] = Series(name="投样前 · 升温段", raw=DEMO_A,
                                color=PALETTE[0], marker="o", linestyle="-")
        self.series[1] = Series(name="反应后 · 降温段", raw=DEMO_B,
                                color=PALETTE[1], marker="s", linestyle="-")
        cfg = PlotConfig(
            title="量热实验 T–t 曲线（外推法散热修正）",
            xlabel="t / s", ylabel="T / K",
            xmin="0", xmax="330", xstep="50", ystep="2",
            segments=[
                FitSegment(enabled=True, label="升温段外推", series=0, extrap_to="150"),
                FitSegment(enabled=True, label="降温段外推", series=1, extrap_to="150"),
            ],
            show_delta=True,
        )
        self.apply_config_to_ui(cfg)
        self._cur_slot = 0
        self._set_index("series_combo", 0)
        self._sync_style_controls(0)
        self.set_status("已载入示例：两段直线外推到 t = 150 s，Δy 即修正后的温升")
        self.refresh()

    def _smoke(self) -> None:
        """冻结版回归自测：验证 XAML / 预览 / PNG / SVG 导出与输出目录。"""
        lines = []
        try:
            OUTPUT.mkdir(parents=True, exist_ok=True)
            self.export("png")
            self.export("svg")
            lines = [
                f"frozen={FROZEN}",
                f"app_dir={APP_DIR}",
                f"xaml={XAML_PATH} exists={XAML_PATH.is_file()}",
                f"preview_source={bool(self.c['preview'].source)}",
                f"result_len={len(self.c['result_text'].text or '')}",
                "png=" + ", ".join(p.name for p in OUTPUT.glob("*.png")),
                "svg=" + ", ".join(p.name for p in OUTPUT.glob("*.svg")),
            ]
        except Exception:
            lines.append(traceback.format_exc())
        (OUTPUT / "smoke_result.txt").write_text("\n".join(lines), encoding="utf-8")
        os._exit(0)

    def _out_dir(self) -> Path:
        d = self.c["out_dir"].text.strip().strip('"') or str(OUTPUT)
        return Path(d)

    def export(self, ext: str) -> None:
        try:
            cfg, series = self.collect()
            fits = compute_fits(cfg, series)
            d = self._out_dir()
            d.mkdir(parents=True, exist_ok=True)
            name = self.c["out_name"].text.strip() or "外推法作图"
            dpi = DPI_ORDER[self._idx("out_dpi", len(DPI_ORDER))]
            if ext == "txt":
                core.export_result_text(d / f"{name}.txt", cfg,
                                        [s for s in series if s.raw.strip()], fits)
                self.set_status(f"已导出结果：{d / (name + '.txt')}")
            else:
                p = export_figure(cfg, series, fits, d / f"{name}.{ext}", dpi=dpi)
                self.set_status(f"已导出：{p}（{dpi} DPI）")
        except Exception as e:
            (ROOT / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
            self.set_status(f"导出失败：{e}")

    def save_project(self) -> None:
        try:
            cfg, series = self.collect()
            p = Path(self.c["project_path"].text.strip().strip('"') or str(OUTPUT / "project.json"))
            p.parent.mkdir(parents=True, exist_ok=True)
            core.save_project(p, cfg, series)
            self.set_status(f"工程已保存：{p}")
        except Exception as e:
            self.set_status(f"保存失败：{e}")

    def load_project(self) -> None:
        try:
            p = Path(self.c["project_path"].text.strip().strip('"'))
            cfg, ss = core.load_project(p)
            self.series = (ss + [Series(name=f"序列 {i + 1}", raw="", color=PALETTE[i % 6])
                                 for i in range(len(ss), SLOTS)])[:SLOTS]
            self.apply_config_to_ui(cfg)
            self._cur_slot = 0
            self._set_index("series_combo", 0)
            self._sync_style_controls(0)
            self.set_status(f"工程已载入：{p}")
            self.refresh()
        except Exception as e:
            (ROOT / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
            self.set_status(f"载入失败：{e}")

    # ------------------------------------------------------------ UI 装配
    def bind_widgets(self, root: FrameworkElement) -> None:
        for name, typ in WIDGET_TYPES.items():
            obj = root.find_name(name)
            self.c[name] = obj.as_(typ) if typ is not None else obj
        self._nav_items = [root.find_name("nav_" + k).as_(NavigationViewItem)
                           for k in PAGES]

    def _watch(self, w) -> None:
        cb = lambda s, e: self.schedule()
        if isinstance(w, TextBox):
            w.add_text_changed(cb)
        elif isinstance(w, (NumberBox, Slider)):
            try:
                w.add_value_changed(cb)
            except Exception:
                pass
        elif isinstance(w, ComboBox):
            w.add_selection_changed(cb)
        elif isinstance(w, CheckBox):
            for m in ("add_checked", "add_unchecked", "add_click"):
                try:
                    getattr(w, m)(cb)
                except Exception:
                    pass
        elif isinstance(w, ToggleSwitch):
            try:
                w.add_toggled(cb)
            except Exception:
                pass

    def bind_events(self) -> None:
        for name, w in self.c.items():
            if name == "series_combo":
                continue
            if isinstance(w, (TextBox, NumberBox, ComboBox, Slider, CheckBox, ToggleSwitch)):
                self._watch(w)
        self.c["series_combo"].add_selection_changed(lambda s, e: self.on_series_changed())
        self.c["nav"].add_selection_changed(self.on_nav)

        actions = {
            "btn_add_series": self.add_series,
            "btn_del_series": self.clear_series,
            "btn_demo": self.load_demo,
            "btn_load_csv": self.load_csv,
            "btn_refresh": self.refresh,
            "btn_export_png": lambda: self.export("png"),
            "btn_export_svg": lambda: self.export("svg"),
            "btn_export_pdf": lambda: self.export("pdf"),
            "btn_export_txt": lambda: self.export("txt"),
            "btn_open_dir": self.open_dir,
            "btn_save_project": self.save_project,
            "btn_load_project": self.load_project,
        }
        for name, fn in actions.items():
            self.c[name].add_click(lambda s, e, f=fn: f())

    def add_series(self) -> None:
        self._sync_series_from_ui(self._cur_slot)
        for i in range(SLOTS):
            if not self.series[i].raw.strip():
                self._cur_slot = i
                self._set_index("series_combo", i)
                self._sync_style_controls(i)
                self.set_status(f"已切换到空槽位：序列 {i + 1}")
                self.refresh()
                return
        self.set_status("6 个序列槽位都用满了，可先「清空当前」释放一个")

    def clear_series(self) -> None:
        i = self._cur_slot
        self.series[i].raw = ""
        self._set_text("data_text", "")
        self.set_status(f"已清空序列 {i + 1} 的数据")
        self.refresh()

    def load_csv(self) -> None:
        try:
            p = Path(self.c["csv_path"].text.strip().strip('"'))
            if not p.exists():
                self.set_status(f"文件不存在：{p}")
                return
            self._set_text("data_text", p.read_text(encoding="utf-8-sig", errors="replace"))
            self.set_status(f"已载入 {p.name}")
            self.refresh()
        except Exception as e:
            self.set_status(f"载入失败：{e}")

    def open_dir(self) -> None:
        try:
            d = self._out_dir()
            d.mkdir(parents=True, exist_ok=True)
            os.startfile(str(d))
        except Exception as e:
            self.set_status(f"打开目录失败：{e}")

    # ------------------------------------------------------------ 生命周期
    @override
    def _on_launched(self, args: LaunchActivatedEventArgs) -> None:
        try:
            self.resources.merged_dictionaries.append(XamlControlsResources())
            window = load_window()
            window.title = "外推法作图 · Extrapolation Plotter (WinUI3)"
            try:
                window.app_window.resize(SizeInt32(1520, 960))
            except Exception:
                pass
            # 标题栏 / 任务栏图标（Windows App SDK 1.5+ 的 AppWindow.set_icon）
            try:
                if ICON_PATH.exists():
                    window.app_window.set_icon(str(ICON_PATH))
            except Exception:
                pass
            root = window.content.as_(FrameworkElement)
            self.bind_widgets(root)
            self.bind_events()

            self.series = [Series(name=f"序列 {i + 1}", raw="", color=PALETTE[i % 6])
                           for i in range(SLOTS)]
            self._cur_slot = 0
            self.apply_config_to_ui(PlotConfig())
            self._sync_style_controls(0)
            self._set_text("out_dir", str(OUTPUT))
            self._set_text("project_path", str(OUTPUT / "project.json"))

            # UI 线程定时器做防抖；必须挂在 self 上防止被 GC 回收
            dq = DispatcherQueue.get_for_current_thread()
            self._timer = dq.create_timer()
            self._timer.interval = timedelta(milliseconds=230)
            self._timer.is_repeating = False
            self._timer.add_tick(lambda s, e: self.refresh())

            self._ready = True
            window.add_closed(lambda s, e: os._exit(0))
            window.activate()
            try:
                self.c["nav"].selected_item = self._nav_items[0]
            except Exception:
                pass
            self.switch_page("data")
            self.load_demo()
            if SMOKE:
                self._smoke_timer = dq.create_timer()
                self._smoke_timer.interval = timedelta(milliseconds=1200)
                self._smoke_timer.is_repeating = False
                self._smoke_timer.add_tick(lambda s, e: self._smoke())
                self._smoke_timer.start()
        except Exception:
            (ROOT / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
            print(traceback.format_exc(), flush=True)

    @override
    def get_xaml_type(self, type: TypeName | tuple[str, TypeKind]) -> IXamlType:
        return self._provider.get_xaml_type(type)

    @override
    def get_xaml_type_by_full_name(self, full_name: str) -> IXamlType:
        return self._provider.get_xaml_type_by_full_name(full_name)

    @override
    def get_xmlns_definitions(self) -> Array[XmlnsDefinition]:
        return self._provider.get_xmlns_definitions()


def init(_: ApplicationInitializationCallbackParams) -> None:
    ExtrapolationApp()


if __name__ == "__main__":
    init_apartment(ApartmentType.SINGLE_THREADED)
    with initialize(options=InitializeOptions.ON_NO_MATCH_SHOW_UI):
        Application.start(init)
