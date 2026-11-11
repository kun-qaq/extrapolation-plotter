# -*- coding: utf-8 -*-
"""外推法作图 · 数据模型 / 最小二乘拟合 / 外推计算 / 工程文件读写。

这个模块不依赖任何 UI，可单独用 Python 测试：
    python -c "import core; print(core.parse_points('0 1\\n1 2\\n2 3'))"
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import numpy as np

# ---------------------------------------------------------------- 常量表
PALETTE = ["#2E86DE", "#E5484D", "#30A46C", "#F76B15", "#8E4EC6", "#0091A7"]

LINESTYLES = {"实线": "-", "虚线": "--", "点划线": "-.", "点线": ":", "无线": "none"}
LINESTYLE_NAMES = {v: k for k, v in LINESTYLES.items()}
MARKERS = {"圆点": "o", "方块": "s", "上三角": "^", "菱形": "D", "十字": "x", "无标记": "none"}
MARKER_NAMES = {v: k for k, v in MARKERS.items()}
FONTS = {
    "微软雅黑": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
    "宋体 + Times New Roman": ["Times New Roman", "SimSun", "Microsoft YaHei", "DejaVu Sans"],
    "黑体 + Times New Roman": ["Times New Roman", "SimHei", "Microsoft YaHei", "DejaVu Sans"],
    "Times New Roman（纯英文）": ["Times New Roman", "DejaVu Sans"],
    "DejaVu Sans（纯英文）": ["DejaVu Sans"],
}
LEGEND_POS = {
    "自动": "best", "右上": "upper right", "左上": "upper left",
    "右下": "lower right", "左下": "lower left", "图外右侧": "outside",
}
GRID_STYLES = {"实线": "-", "虚线": "--", "点线": ":", "点划线": "-."}

NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


# ---------------------------------------------------------------- 数据结构
@dataclass
class Series:
    """一组 XY 数据。raw 保存用户粘贴的原文，渲染时再解析，避免状态不同步。"""
    name: str = "数据 1"
    raw: str = ""
    color: str = PALETTE[0]
    marker: str = "o"
    markersize: float = 5.0
    linestyle: str = "-"
    linewidth: float = 1.6
    show_errorbar: bool = False
    error: str = ""

    def points(self) -> tuple[list[float], list[float], list[str]]:
        return parse_points(self.raw)

    def errors(self, n: int) -> list[float] | None:
        """误差棒：可以是单个常数，也可以是一列数值（个数需与数据一致）。"""
        if not self.show_errorbar or not self.error.strip():
            return None
        vals = [float(m.group()) for m in NUM_RE.finditer(self.error)]
        if not vals:
            return None
        if len(vals) == 1:
            return [abs(vals[0])] * n
        if len(vals) == n:
            return [abs(v) for v in vals]
        return None


@dataclass
class FitSegment:
    """一段线性拟合 + 外推。热学实验里通常就是「升温段」「降温段」两条外推线。"""
    enabled: bool = False
    label: str = "拟合 A"
    series: int = 0                 # 对哪一组数据做拟合
    x_from: str = ""                # 拟合区间起点（空 = 数据最小 x）
    x_to: str = ""                  # 拟合区间终点（空 = 数据最大 x）
    extrap_to: str = ""             # 外推目标 x（空 = 不外推）；填 0 即外推到 t=0
    color: str = ""                 # 空 = 跟随数据序列颜色
    linestyle: str = "--"
    linewidth: float = 1.6
    show_equation: bool = True
    show_point: bool = True
    show_in_legend: bool = False


@dataclass
class FitResult:
    ok: bool
    label: str
    message: str = ""
    slope: float = math.nan
    intercept: float = math.nan
    r2: float = math.nan
    n: int = 0
    x_fit: tuple[float, float] = (math.nan, math.nan)
    x_extrap: float | None = None
    y_extrap: float | None = None
    x_intercept: float | None = None        # y = 0 处的 x
    sigma_slope: float = math.nan
    sigma_intercept: float = math.nan
    color: str = ""
    linestyle: str = "--"
    linewidth: float = 1.6
    show_equation: bool = True
    show_point: bool = True
    show_in_legend: bool = False
    series: int = 0

    def equation(self) -> str:
        b = self.intercept
        sign = "+" if b >= 0 else "-"
        return f"y = {self.slope:.6g} x {sign} {abs(b):.6g}"


@dataclass
class PlotConfig:
    # 文字 / 画布
    title: str = "温度—时间曲线（外推法）"
    xlabel: str = "t / s"
    ylabel: str = "T / K"
    font: str = "微软雅黑"
    font_size: float = 12.0
    title_size: float = 15.0
    width_in: float = 8.0
    height_in: float = 5.2
    dpi: int = 130
    transparent: bool = False
    # 坐标轴范围与刻度
    xmin: str = ""
    xmax: str = ""
    ymin: str = ""
    ymax: str = ""
    xstep: str = ""
    ystep: str = ""
    minor: int = 0
    grid_major: bool = True
    grid_minor: bool = False
    grid_style: str = "--"
    grid_alpha: float = 0.45
    ticks_in: bool = False
    show_top_right: bool = True
    spine_width: float = 1.0
    # 图例
    show_legend: bool = True
    legend_pos: str = "best"
    # 外推
    segments: list[FitSegment] = field(default_factory=lambda: [
        FitSegment(), FitSegment(enabled=False, label="拟合 B", linestyle="--")
    ])
    show_x_intercept: bool = False
    show_delta: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PlotConfig":
        segs = d.pop("segments", None)
        obj = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        if segs:
            obj.segments = [FitSegment(**{k: v for k, v in s.items()
                                          if k in FitSegment.__dataclass_fields__})
                            for s in segs]
        return obj


# ---------------------------------------------------------------- 数据解析
def parse_points(text: str) -> tuple[list[float], list[float], list[str]]:
    """把粘贴的文本解析成 X、Y 两列。

    支持：Excel 直接粘贴（Tab）、空格 / 逗号 / 中文逗号 / 分号分隔、
    科学计数法、带单位的行（自动抽取数字）、表头行自动跳过。
    只给一列 Y 时，X 自动取 1, 2, 3 ...
    返回 (xs, ys, 被跳过的行)。
    """
    xs: list[float] = []
    ys: list[float] = []
    skipped: list[str] = []
    single_column = None

    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        nums = [float(m.group()) for m in NUM_RE.finditer(line)]
        if not nums:
            skipped.append(line)
            continue
        if len(nums) == 1:
            if single_column is None:
                single_column = not xs
            if single_column:
                xs.append(float(len(xs) + 1))
                ys.append(nums[0])
            else:
                skipped.append(line)
            continue
        x, y = nums[0], nums[1]
        # 表头里偶尔混进数字（如 "T1 T2"），用「本行字母比例」粗判
        letters = sum(c.isalpha() for c in line)
        if letters > 0 and not any(c in line for c in "eE+-."):
            skipped.append(line)
            continue
        xs.append(x)
        ys.append(y)

    return xs, ys, skipped


def _fmt_num(s: str) -> float | None:
    try:
        v = float(str(s).strip())
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- 拟合 / 外推
def linear_fit(xs: list[float], ys: list[float]) -> dict[str, float]:
    """最小二乘 y = kx + b，同时给出 R² 与斜率/截距的标准不确定度。"""
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    n = len(x)
    if n < 2:
        raise ValueError("拟合至少需要 2 个数据点")
    k, b = np.polyfit(x, y, 1)
    yhat = k * x + b
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    sxx = float(np.sum((x - np.mean(x)) ** 2))
    if n > 2 and sxx > 0:
        s2 = ss_res / (n - 2)
        xm = float(np.mean(x))
        sigma_k = math.sqrt(s2 / sxx)
        sigma_b = math.sqrt(s2 * (1.0 / n + xm * xm / sxx))
    else:
        sigma_k = sigma_b = 0.0
    return {"slope": float(k), "intercept": float(b), "r2": r2,
            "sigma_slope": sigma_k, "sigma_intercept": sigma_b, "n": n}


def compute_fits(config: PlotConfig, series: list[Series]) -> list[FitResult]:
    """按配置计算所有启用的拟合段。"""
    results: list[FitResult] = []
    for seg in config.segments:
        label = seg.label or "拟合"
        if not seg.enabled:
            continue
        if seg.series < 0 or seg.series >= len(series):
            results.append(FitResult(False, label, "数据序列不存在"))
            continue
        xs, ys, _ = series[seg.series].points()
        if len(xs) < 2:
            results.append(FitResult(False, label, "该序列有效数据不足 2 点"))
            continue

        lo = _fmt_num(seg.x_from)
        hi = _fmt_num(seg.x_to)
        lo = min(xs) if lo is None else lo
        hi = max(xs) if hi is None else hi
        if lo > hi:
            lo, hi = hi, lo
        fx = [x for x in xs if lo <= x <= hi]
        fy = [y for x, y in zip(xs, ys) if lo <= x <= hi]
        try:
            st = linear_fit(fx, fy)
        except Exception as e:
            results.append(FitResult(False, label, str(e)))
            continue

        x_ext = _fmt_num(seg.extrap_to)
        y_ext = st["slope"] * x_ext + st["intercept"] if x_ext is not None else None
        x_int = (-st["intercept"] / st["slope"]) if (config.show_x_intercept and st["slope"] != 0) else None

        results.append(FitResult(
            ok=True, label=label,
            slope=st["slope"], intercept=st["intercept"], r2=st["r2"],
            n=st["n"], x_fit=(lo, hi),
            x_extrap=x_ext, y_extrap=y_ext, x_intercept=x_int,
            sigma_slope=st["sigma_slope"], sigma_intercept=st["sigma_intercept"],
            color=seg.color or series[seg.series].color,
            linestyle=seg.linestyle, linewidth=seg.linewidth,
            show_equation=seg.show_equation, show_point=seg.show_point,
            show_in_legend=seg.show_in_legend, series=seg.series,
        ))
    return results


def fit_report(fits: list[FitResult], config: PlotConfig) -> str:
    """给界面右下角的结果面板用的文字报告。"""
    oks = [f for f in fits if f.ok]
    bad = [f for f in fits if not f.ok]
    if not oks and not bad:
        return "尚未启用拟合段。到「外推拟合」页勾选即可做线性外推。"

    lines: list[str] = []
    for f in fits:
        lines.append(f"【{f.label}】")
        if not f.ok:
            lines.append(f"  {f.message}")
            continue
        lines.append(f"  {f.equation()}")
        lines.append(f"  R² = {f.r2:.6f}   n = {f.n}   拟合区间 x ∈ [{f.x_fit[0]:g}, {f.x_fit[1]:g}]")
        lines.append(f"  k = {f.slope:.6g} ± {f.sigma_slope:.3g}    b = {f.intercept:.6g} ± {f.sigma_intercept:.3g}")
        if f.y_extrap is not None:
            lines.append(f"  外推 x = {f.x_extrap:g}  →  y = {f.y_extrap:.6g}")
        if f.x_intercept is not None:
            lines.append(f"  y = 0 时  x = {f.x_intercept:.6g}")
        lines.append("")

    if config.show_delta and len(oks) == 2:
        a, b = oks
        if a.y_extrap is not None and b.y_extrap is not None:
            lines.append(f"【外推差值】Δy = {a.y_extrap - b.y_extrap:+.6g}"
                         f"   （{a.label} − {b.label}）")
            if a.x_extrap is not None and b.x_extrap is not None and abs(a.x_extrap - b.x_extrap) > 1e-12:
                lines.append("  注意：两段外推目标 x 不同，Δy 仅供参考")
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------- 工程文件
def save_project(path: str | Path, config: PlotConfig, series: list[Series]) -> None:
    Path(path).write_text(json.dumps({
        "version": 1,
        "config": config.to_dict(),
        "series": [asdict(s) for s in series],
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project(path: str | Path) -> tuple[PlotConfig, list[Series]]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    cfg = PlotConfig.from_dict(dict(d.get("config", {})))
    ss = [Series(**{k: v for k, v in s.items() if k in Series.__dataclass_fields__})
          for s in d.get("series", [])]
    return cfg, ss


def export_result_text(path: str | Path, config: PlotConfig,
                       series: list[Series], fits: list[FitResult]) -> None:
    out = [config.title, "=" * 48, ""]
    for i, s in enumerate(series):
        xs, ys, skipped = s.points()
        out.append(f"[{i}] {s.name}  ({len(xs)} 点)")
        out.append("x, y")
        out += [f"{x:.10g}, {y:.10g}" for x, y in zip(xs, ys)]
        if skipped:
            out.append(f"（跳过 {len(skipped)} 行表头/无效行）")
        out.append("")
    out.append("=" * 48)
    out.append(fit_report(fits, config))
    Path(path).write_text("\n".join(out), encoding="utf-8")
