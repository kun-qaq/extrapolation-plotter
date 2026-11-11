# -*- coding: utf-8 -*-
"""外推法作图 · matplotlib 绘图引擎。

界面只负责收集参数，出图全部在这里完成；同一套绘制逻辑既用于 WinUI3 实时预览，
也用于导出 PNG / SVG / PDF，保证「所见即所得」。
"""
from __future__ import annotations

import io
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import MultipleLocator, AutoMinorLocator

from core import FONTS, PlotConfig, Series, FitResult, _fmt_num

_FONT_CACHE: dict[str, list[str]] = {}


def font_stack(name: str) -> list[str]:
    """只保留本机真实存在的字体名，避免 matplotlib 缺字警告和中文方框。"""
    if name not in _FONT_CACHE:
        avail = {f.name for f in font_manager.fontManager.ttflist}
        stack = [f for f in FONTS.get(name, FONTS["微软雅黑"]) if f in avail]
        _FONT_CACHE[name] = stack or ["DejaVu Sans"]
    return _FONT_CACHE[name]


def _apply_font(config: PlotConfig) -> None:
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = font_stack(config.font)
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["mathtext.fontset"] = "dejavusans"


def _draw(config: PlotConfig, series: list[Series], fits: list[FitResult]):
    _apply_font(config)
    fig, ax = plt.subplots(figsize=(max(3.0, config.width_in), max(2.0, config.height_in)),
                           dpi=config.dpi)
    if config.transparent:
        fig.patch.set_alpha(0.0)
        ax.patch.set_alpha(0.0)
    else:
        fig.patch.set_facecolor("white")
        ax.patch.set_facecolor("white")

    # ---- 原始数据 ----------------------------------------------------
    for s in series:
        xs, ys, _ = s.points()
        if len(xs) < 1:
            continue
        errs = s.errors(len(xs))
        if errs:
            ax.errorbar(xs, ys, yerr=errs, fmt="none", ecolor=s.color,
                        elinewidth=1.0, capsize=3, alpha=0.65, zorder=1)
        ax.plot(xs, ys,
                label=s.name if config.show_legend else None,
                color=s.color, marker=s.marker,
                markersize=s.markersize, markeredgewidth=1.0,
                linestyle=s.linestyle, linewidth=s.linewidth, zorder=2)

    # ---- 拟合线与外推段 ----------------------------------------------
    eq_lines: list[str] = []
    vlines_x: set[float] = set()
    for f in fits:
        if not f.ok:
            continue
        color = f.color or "#333333"
        lo, hi = f.x_fit
        if hi <= lo:
            continue
        xf = [lo + (hi - lo) * i / 99 for i in range(100)]
        ax.plot(xf, [f.slope * x + f.intercept for x in xf],
                color=color, linestyle=f.linestyle, linewidth=f.linewidth,
                zorder=3, label=f"{f.label} 拟合" if f.show_in_legend else None)

        # 外推段：从拟合区间端点延伸到目标 x，用更疏的虚线区分
        if f.y_extrap is not None and f.x_extrap is not None:
            xe, ye = f.x_extrap, f.y_extrap
            if xe < lo:
                ex = [xe + (lo - xe) * i / 79 for i in range(80)]
            elif xe > hi:
                ex = [hi + (xe - hi) * i / 79 for i in range(80)]
            else:
                ex = []
            if ex:
                ax.plot(ex, [f.slope * x + f.intercept for x in ex],
                        color=color, linestyle=(0, (5, 4)), linewidth=f.linewidth,
                        alpha=0.95, zorder=3)
            if f.show_point:
                ax.plot([xe], [ye], marker="o", markersize=8, markerfacecolor="white",
                        markeredgecolor=color, markeredgewidth=2.0,
                        linestyle="none", zorder=6)
                ylo, yhi = ax.get_ylim()
                # 点靠近图顶时把文字放到左上方，避免压在右侧的数据线上
                upper = ye >= ylo + 0.80 * (yhi - ylo)
                ax.annotate(f"({xe:g}, {ye:.5g})", xy=(xe, ye),
                            xytext=(-9, 10) if upper else (8, 8),
                            ha="right" if upper else "left",
                            textcoords="offset points", fontsize=config.font_size - 1,
                            color=color, zorder=7)
                vlines_x.add(xe)

        if f.show_equation:
            eq_lines.append(f"{f.label}:  {f.equation()}   R²={f.r2:.5f}")
        if f.x_intercept is not None:
            eq_lines.append(f"{f.label}:  y=0  →  x={f.x_intercept:.5g}")

    # ---- 坐标轴 / 刻度 / 网格 ----------------------------------------
    xmin, xmax = _fmt_num(config.xmin), _fmt_num(config.xmax)
    ymin, ymax = _fmt_num(config.ymin), _fmt_num(config.ymax)
    if xmin is not None or xmax is not None:
        ax.set_xlim(left=xmin, right=xmax)
    if ymin is not None or ymax is not None:
        ax.set_ylim(bottom=ymin, top=ymax)

    xstep, ystep = _fmt_num(config.xstep), _fmt_num(config.ystep)
    if xstep and xstep > 0:
        ax.xaxis.set_major_locator(MultipleLocator(xstep))
    if ystep and ystep > 0:
        ax.yaxis.set_major_locator(MultipleLocator(ystep))
    if config.minor > 0:
        ax.xaxis.set_minor_locator(AutoMinorLocator(config.minor))
        ax.yaxis.set_minor_locator(AutoMinorLocator(config.minor))

    # 注意：给 grid() 传 visible=False 的同时又传线型参数，matplotlib 会强制打开网格
    if config.grid_major:
        ax.grid(which="major", visible=True, linestyle=config.grid_style,
                linewidth=0.8, alpha=config.grid_alpha, color="#888888")
    if config.grid_minor:
        ax.grid(which="minor", visible=True, linestyle=":",
                linewidth=0.6, alpha=config.grid_alpha * 0.7, color="#888888")
    ax.tick_params(axis="both", which="both",
                   direction="in" if config.ticks_in else "out",
                   top=config.show_top_right, right=config.show_top_right,
                   labelsize=config.font_size)
    for spine in ax.spines.values():
        spine.set_linewidth(config.spine_width)
    if not config.show_top_right:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    ax.set_title(config.title, fontsize=config.title_size, pad=12)
    ax.set_xlabel(config.xlabel, fontsize=config.font_size + 1)
    ax.set_ylabel(config.ylabel, fontsize=config.font_size + 1)

    # 外推时刻的竖直参考线（同一 x 只画一条，避免两段颜色叠在一起）
    for xe in sorted(vlines_x):
        ax.axvline(xe, color="#888888", linestyle=":", linewidth=1.0, alpha=0.5, zorder=1)

    if config.show_legend:
        if config.legend_pos == "outside":
            ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), frameon=False,
                      fontsize=max(7, config.font_size - 1))
        else:
            ax.legend(loc=config.legend_pos, frameon=False,
                      fontsize=max(7, config.font_size - 1))

    # 方程放在图外右侧：图内数据区保持干净，不会被文字压住；
    # bbox_inches="tight" 会在导出时把这块文字完整包进画布。
    if eq_lines:
        y_pos = 0.55 if (config.show_legend and config.legend_pos == "outside") else 0.98
        ax.text(1.02, y_pos, "\n".join(eq_lines), transform=ax.transAxes,
                va="top", ha="left", fontsize=max(7, config.font_size - 1),
                color="#222222", linespacing=1.5,
                bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                          edgecolor="#cccccc", alpha=0.9), zorder=10)

    fig.tight_layout()
    return fig, ax


_SAVE_KW = dict(bbox_inches="tight", pad_inches=0.12)


def render_png(config: PlotConfig, series: list[Series], fits: list[FitResult],
               dpi: int | None = None) -> bytes:
    """生成预览用 PNG 字节。"""
    fig, _ = _draw(config, series, fits)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi or config.dpi,
                transparent=config.transparent, **_SAVE_KW)
    plt.close(fig)
    return buf.getvalue()


def export_figure(config: PlotConfig, series: list[Series], fits: list[FitResult],
                  path: str | Path, dpi: int | None = None) -> Path:
    """导出图片，格式由扩展名决定：.png / .svg / .pdf。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    suffix = p.suffix.lower()
    if suffix not in (".png", ".svg", ".pdf"):
        raise ValueError("只支持 .png / .svg / .pdf，当前扩展名：%s" % suffix)
    fig, _ = _draw(config, series, fits)
    fig.savefig(p, format=suffix.lstrip("."), dpi=(dpi or config.dpi) if suffix == ".png" else None,
                transparent=config.transparent, **_SAVE_KW)
    plt.close(fig)
    return p
