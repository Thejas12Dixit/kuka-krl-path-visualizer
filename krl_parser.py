"""
krl_parser.py
=============
KUKA KRL (.src / .dat) file parser and 3D path visualizer.

Parses PTP, LIN, CIRC motion commands and extracts Cartesian positions
from paired .dat files.

Visualisation:
  - Mayavi     -> interactive 3D viewer  ->  vis.plot_3d_mayavi()
  - Matplotlib -> PDF report + PNG       ->  vis.export_pdf() / vis.export_png()

Install:
  pip install matplotlib numpy pandas
  pip install mayavi PyQt5          # for interactive Mayavi viewer

Author : Thejas Dixit Sathyanarayana
GitHub : https://github.com/Thejas12Dixit
"""

import re
import os
import numpy as np

# Matplotlib - Agg backend only (no display), used for PDF/PNG export
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from mpl_toolkits.mplot3d import Axes3D          # noqa: F401
from matplotlib.backends.backend_pdf import PdfPages

# Mayavi - optional, interactive viewer
try:
    from mayavi import mlab as _mlab
    MAYAVI_AVAILABLE = True
except ImportError:
    MAYAVI_AVAILABLE = False

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


# ─────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────

@dataclass
class KRLPoint:
    """A single Cartesian point extracted from a .dat file."""
    name: str
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    a: float = 0.0
    b: float = 0.0
    c: float = 0.0


@dataclass
class KRLMotion:
    """A single motion command from a .src file."""
    motion_type: str
    point_name: str
    velocity: Optional[float] = None
    velocity_unit: str = "%"
    aux_point: Optional[str] = None
    point: Optional[KRLPoint] = None


@dataclass
class KRLProgram:
    """Parsed result of a .src + .dat pair."""
    name: str = ""
    src_file: str = ""
    dat_file: str = ""
    points: dict = field(default_factory=dict)
    motions: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


# ─────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────

class KRLParser:
    """Parses KUKA KRL .src and .dat files."""

    _CART_RE = re.compile(
        r"DECL\s+E6POS\s+(\w+)\s*=\s*\{"
        r"[^}]*X\s+([-\d.]+).*?Y\s+([-\d.]+).*?Z\s+([-\d.]+)"
        r"(?:.*?A\s+([-\d.]+))?(?:.*?B\s+([-\d.]+))?(?:.*?C\s+([-\d.]+))?",
        re.IGNORECASE | re.DOTALL
    )
    _PTP_RE  = re.compile(r"^\s*PTP\s+(\w+)\s+Vel\s*=\s*([\d.]+)(%|m/s)?",              re.IGNORECASE)
    _LIN_RE  = re.compile(r"^\s*LIN\s+(\w+)\s+Vel\s*=\s*([\d.]+)\s*(m/s|%)?",           re.IGNORECASE)
    _CIRC_RE = re.compile(r"^\s*CIRC\s+(\w+)\s+(\w+)\s+Vel\s*=\s*([\d.]+)\s*(m/s|%)?", re.IGNORECASE)

    def parse(self, src_path: str, dat_path: str = None) -> KRLProgram:
        prog = KRLProgram()
        prog.src_file = src_path
        prog.name = os.path.splitext(os.path.basename(src_path))[0]
        if dat_path is None:
            dat_path = os.path.splitext(src_path)[0] + ".dat"
        if os.path.exists(dat_path):
            prog.dat_file = dat_path
            self._parse_dat(dat_path, prog)
        else:
            prog.warnings.append(f"No .dat file found at {dat_path}")
        self._parse_src(src_path, prog)
        self._resolve_points(prog)
        return prog

    def _parse_dat(self, path, prog):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for m in self._CART_RE.finditer(content):
            name = m.group(1)
            prog.points[name.upper()] = KRLPoint(
                name=name,
                x=float(m.group(2)), y=float(m.group(3)), z=float(m.group(4)),
                a=float(m.group(5)) if m.group(5) else 0.0,
                b=float(m.group(6)) if m.group(6) else 0.0,
                c=float(m.group(7)) if m.group(7) else 0.0,
            )

    def _parse_src(self, path, prog):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for line in lines:
            s = line.strip()
            if s.startswith(";"):
                continue
            m = self._CIRC_RE.match(s)
            if m:
                prog.motions.append(KRLMotion(
                    motion_type="CIRC", aux_point=m.group(1).upper(),
                    point_name=m.group(2).upper(), velocity=float(m.group(3)),
                    velocity_unit=m.group(4) or "m/s"))
                continue
            m = self._LIN_RE.match(s)
            if m:
                prog.motions.append(KRLMotion(
                    motion_type="LIN", point_name=m.group(1).upper(),
                    velocity=float(m.group(2)), velocity_unit=m.group(3) or "m/s"))
                continue
            m = self._PTP_RE.match(s)
            if m:
                prog.motions.append(KRLMotion(
                    motion_type="PTP", point_name=m.group(1).upper(),
                    velocity=float(m.group(2)), velocity_unit=m.group(3) or "%"))

    def _resolve_points(self, prog):
        for motion in prog.motions:
            key = motion.point_name.upper()
            if key in prog.points:
                motion.point = prog.points[key]
            else:
                prog.warnings.append(f"Point {motion.point_name} not found in .dat")


# ─────────────────────────────────────────────
# Color schemes
# ─────────────────────────────────────────────

# Matplotlib hex (PDF/PNG)
MOTION_COLORS = {"PTP": "#4A90D9", "LIN": "#27AE60", "CIRC": "#E67E22"}
WELD_COLOR    = "#E74C3C"
START_COLOR   = "#9B59B6"

# Mayavi RGB 0-1 (interactive)
MAYAVI_COLORS = {"PTP": (0.29, 0.56, 0.85), "LIN": (0.15, 0.68, 0.38), "CIRC": (0.90, 0.50, 0.13)}
MAYAVI_WELD   = (0.91, 0.30, 0.24)
MAYAVI_HOME   = (0.61, 0.35, 0.71)
MAYAVI_TEXT   = (1.0,  1.0,  1.0)


# ─────────────────────────────────────────────
# Visualizer
# ─────────────────────────────────────────────

class KRLVisualizer:
    """
    3D path visualizer for parsed KRL programs.

    Interactive:  vis.plot_3d_mayavi()   <- rich Mayavi window
    Export:       vis.export_pdf(path)   <- 2-page PDF report
                  vis.export_png(path)   <- PNG image
    """

    def __init__(self, program: KRLProgram):
        self.prog = program

    def _get_path_segments(self):
        resolved = [m for m in self.prog.motions if m.point is not None]
        return [
            (resolved[i], resolved[i-1].point, resolved[i].point)
            for i in range(1, len(resolved))
            if resolved[i-1].point and resolved[i].point
        ]

    def _all_coords(self):
        pts = [m.point for m in self.prog.motions if m.point]
        return np.array([[p.x, p.y, p.z] for p in pts]) if pts else np.zeros((1, 3))

    # ─────────────────────────────────────────
    # Mayavi interactive viewer
    # ─────────────────────────────────────────

    def plot_3d_mayavi(self, title: str = None):
        """
        Open a rich interactive Mayavi 3D window.

        Requires:  pip install mayavi PyQt5
        Controls:  left-drag = rotate | scroll = zoom | right-drag = pan
        """
        if not MAYAVI_AVAILABLE:
            print(
                "\n[ERROR] Mayavi is not installed.\n"
                "Install with:  pip install mayavi PyQt5\n"
                "Tip: use export_pdf() or export_png() for non-interactive output.\n"
            )
            return

        resolved = [m for m in self.prog.motions if m.point is not None]
        if not resolved:
            print("[WARNING] No resolved points to visualize.")
            return

        fig_title = title or f"KUKA Path — {self.prog.name}"

        # Dark figure
        _mlab.figure(
            figure=fig_title,
            bgcolor=(0.12, 0.14, 0.18),
            fgcolor=(0.9,  0.9,  0.9),
            size=(1100, 750),
        )

        # Path segments — tube coloured by motion type
        for motion, pt_from, pt_to in self._get_path_segments():
            col = MAYAVI_COLORS.get(motion.motion_type, (0.6, 0.6, 0.6))
            _mlab.plot3d(
                [pt_from.x, pt_to.x],
                [pt_from.y, pt_to.y],
                [pt_from.z, pt_to.z],
                color=col, tube_radius=5, tube_sides=12, opacity=0.95,
            )

        # Points and labels
        for motion in resolved:
            pt     = motion.point
            is_home = "HOME" in motion.point_name
            col    = MAYAVI_HOME if is_home else MAYAVI_WELD
            scale  = 30 if is_home else 20

            _mlab.points3d(pt.x, pt.y, pt.z,
                           color=col, scale_factor=scale,
                           resolution=20, opacity=1.0)
            _mlab.text3d(pt.x, pt.y, pt.z + 25,
                         motion.point_name,
                         color=MAYAVI_TEXT, scale=14)

        # Axes, orientation marker, title
        _mlab.axes(xlabel="X (mm)", ylabel="Y (mm)", zlabel="Z (mm)",
                   color=(0.65, 0.65, 0.65), line_width=1.0)
        _mlab.orientation_axes()
        _mlab.title(fig_title, size=0.25, color=(0.9, 0.9, 0.9), height=0.95)

        # Legend overlay (bottom-left)
        legend = [
            ("PTP  - Point-to-point (joint)",  MAYAVI_COLORS["PTP"]),
            ("LIN  - Linear Cartesian",         MAYAVI_COLORS["LIN"]),
            ("CIRC - Circular arc",             MAYAVI_COLORS["CIRC"]),
            ("  Process / weld point",           MAYAVI_WELD),
            ("  HOME / start",                  MAYAVI_HOME),
        ]
        for idx, (label, col) in enumerate(legend):
            _mlab.text(0.02, 0.04 + idx * 0.05, label, color=col, width=0.28)

        _mlab.view(azimuth=-60, elevation=35, distance="auto")

        print(f"\n[Mayavi] {fig_title}")
        print("  Rotate: left-drag  |  Zoom: scroll  |  Pan: right-drag")
        print("  Close the window to continue.\n")
        _mlab.show()

    # ─────────────────────────────────────────
    # Matplotlib 3D (internal — export only)
    # ─────────────────────────────────────────

    def plot_3d(self, ax=None, title: str = None):
        """Matplotlib 3D axes — used internally for PDF/PNG export only."""
        if ax is None:
            fig = plt.figure(figsize=(12, 8))
            ax  = fig.add_subplot(111, projection="3d")
        else:
            fig = ax.get_figure()

        for motion, pt_from, pt_to in self._get_path_segments():
            color = MOTION_COLORS.get(motion.motion_type, "#999999")
            ax.plot([pt_from.x, pt_to.x], [pt_from.y, pt_to.y], [pt_from.z, pt_to.z],
                    color=color, linewidth=2, alpha=0.85)

        for motion in [m for m in self.prog.motions if m.point]:
            pt = motion.point
            c  = START_COLOR if "HOME" in motion.point_name else WELD_COLOR
            s  = 80 if "HOME" in motion.point_name else 50
            ax.scatter(pt.x, pt.y, pt.z, color=c, s=s, zorder=5, alpha=0.9)
            ax.text(pt.x, pt.y, pt.z + 15, motion.point_name,
                    fontsize=7, color="#333333", ha="center", va="bottom")

        ax.set_xlabel("X (mm)", fontsize=9)
        ax.set_ylabel("Y (mm)", fontsize=9)
        ax.set_zlabel("Z (mm)", fontsize=9)
        ax.set_title(title or f"Robot path — {self.prog.name}",
                     fontsize=11, fontweight="bold")
        ax.tick_params(labelsize=7)
        ax.legend(handles=[
            mpatches.Patch(color=MOTION_COLORS["PTP"],  label="PTP — Point-to-point"),
            mpatches.Patch(color=MOTION_COLORS["LIN"],  label="LIN — Linear"),
            mpatches.Patch(color=MOTION_COLORS["CIRC"], label="CIRC — Circular"),
            mpatches.Patch(color=WELD_COLOR,            label="Process point"),
            mpatches.Patch(color=START_COLOR,           label="HOME / Start"),
        ], loc="upper left", fontsize=8)
        ax.view_init(elev=25, azim=-60)
        return fig, ax

    # ─────────────────────────────────────────
    # Statistics
    # ─────────────────────────────────────────

    def get_stats(self) -> dict:
        resolved = [m for m in self.prog.motions if m.point]
        counts = {"PTP": 0, "LIN": 0, "CIRC": 0}
        total_dist, min_vel, max_vel = 0.0, float("inf"), 0.0

        for motion, pt_from, pt_to in self._get_path_segments():
            counts[motion.motion_type] = counts.get(motion.motion_type, 0) + 1
            total_dist += float(np.sqrt(
                (pt_to.x - pt_from.x)**2 +
                (pt_to.y - pt_from.y)**2 +
                (pt_to.z - pt_from.z)**2
            ))
            if motion.velocity and motion.velocity_unit == "m/s":
                v = motion.velocity * 1000
                min_vel = min(min_vel, v)
                max_vel = max(max_vel, v)

        c = self._all_coords()
        return {
            "program_name":     self.prog.name,
            "total_points":     len(resolved),
            "ptp_moves":        counts["PTP"],
            "lin_moves":        counts["LIN"],
            "circ_moves":       counts["CIRC"],
            "total_distance":   round(total_dist, 1),
            "x_range":          (round(float(c[:, 0].min()), 1), round(float(c[:, 0].max()), 1)),
            "y_range":          (round(float(c[:, 1].min()), 1), round(float(c[:, 1].max()), 1)),
            "z_range":          (round(float(c[:, 2].min()), 1), round(float(c[:, 2].max()), 1)),
            "min_velocity_mms": round(min_vel, 1) if min_vel != float("inf") else "N/A",
            "max_velocity_mms": round(max_vel, 1) if max_vel > 0 else "N/A",
            "mayavi_available": MAYAVI_AVAILABLE,
            "warnings":         self.prog.warnings,
        }

    # ─────────────────────────────────────────
    # PDF export
    # ─────────────────────────────────────────

    def export_pdf(self, output_path: str = None) -> str:
        if output_path is None:
            output_path = f"{self.prog.name}_path_report.pdf"
        stats = self.get_stats()

        with PdfPages(output_path) as pdf:

            # Page 1 — 3D plot + stats
            fig = plt.figure(figsize=(11.69, 8.27))
            fig.patch.set_facecolor("#F8F9FA")
            fig.text(0.05, 0.94, "KUKA Robot Path Visualizer",
                     fontsize=18, fontweight="bold", color="#2C3E50")
            fig.text(0.05, 0.90,
                     f"Program: {self.prog.name}  |  "
                     f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
                     f"Author: Thejas Dixit Sathyanarayana",
                     fontsize=9, color="#7F8C8D")
            la = fig.add_axes([0.05, 0.88, 0.90, 0.001])
            la.axhline(y=0, color="#BDC3C7", linewidth=0.8)
            la.axis("off")

            ax3d = fig.add_axes([0.05, 0.12, 0.58, 0.72], projection="3d")
            self.plot_3d(ax=ax3d, title="3D Robot Path")

            sx, sy, lh = 0.67, 0.85, 0.052

            def sl(label, value, y):
                fig.text(sx,        y, label,      fontsize=9, color="#7F8C8D")
                fig.text(sx + 0.17, y, str(value), fontsize=9, color="#2C3E50")

            fig.text(sx, sy, "Program Statistics",
                     fontsize=11, fontweight="bold", color="#2C3E50")
            sl("Program",        stats["program_name"],           sy - lh * 1)
            sl("Total points",   stats["total_points"],           sy - lh * 2)
            sl("PTP moves",      stats["ptp_moves"],              sy - lh * 3)
            sl("LIN moves",      stats["lin_moves"],              sy - lh * 4)
            sl("CIRC moves",     stats["circ_moves"],             sy - lh * 5)
            sl("Total distance", f"{stats['total_distance']} mm", sy - lh * 6)
            fig.text(sx, sy - lh * 7.5, "Workspace Envelope",
                     fontsize=10, fontweight="bold", color="#2C3E50")
            sl("X range", f"{stats['x_range'][0]} -> {stats['x_range'][1]} mm", sy - lh * 8.5)
            sl("Y range", f"{stats['y_range'][0]} -> {stats['y_range'][1]} mm", sy - lh * 9.5)
            sl("Z range", f"{stats['z_range'][0]} -> {stats['z_range'][1]} mm", sy - lh * 10.5)
            fig.text(sx, sy - lh * 12, "Velocity",
                     fontsize=10, fontweight="bold", color="#2C3E50")
            sl("Min (LIN/CIRC)", f"{stats['min_velocity_mms']} mm/s", sy - lh * 13)
            sl("Max (LIN/CIRC)", f"{stats['max_velocity_mms']} mm/s", sy - lh * 14)
            fig.text(0.5, 0.03,
                     "Generated by KUKA KRL Path Visualizer · github.com/Thejas12Dixit",
                     fontsize=8, color="#BDC3C7", ha="center")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            # Page 2 — motion table
            fig2, ax2 = plt.subplots(figsize=(11.69, 8.27))
            fig2.patch.set_facecolor("#F8F9FA")
            ax2.axis("off")
            fig2.text(0.05, 0.95, "Motion Sequence Table",
                      fontsize=14, fontweight="bold", color="#2C3E50")
            fig2.text(0.05, 0.91,
                      f"Program: {self.prog.name}  |  "
                      f"{len([m for m in self.prog.motions if m.point])} resolved points",
                      fontsize=9, color="#7F8C8D")
            la2 = fig2.add_axes([0.05, 0.89, 0.90, 0.001])
            la2.axhline(y=0, color="#BDC3C7", linewidth=0.8)
            la2.axis("off")

            rows = []
            for i, motion in enumerate(self.prog.motions):
                if not motion.point:
                    continue
                pt = motion.point
                vel_str = f"{motion.velocity} {motion.velocity_unit}" if motion.velocity else "-"
                rows.append([str(i+1), motion.motion_type, motion.point_name,
                              f"{pt.x:.1f}", f"{pt.y:.1f}", f"{pt.z:.1f}", vel_str])

            headers = ["#", "Type", "Point", "X (mm)", "Y (mm)", "Z (mm)", "Velocity"]
            table = ax2.table(cellText=rows, colLabels=headers,
                              cellLoc="center", loc="upper center",
                              bbox=[0.0, 0.05, 1.0, 0.82])
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            for j in range(len(headers)):
                c = table[0, j]
                c.set_facecolor("#2C3E50")
                c.set_text_props(color="white", fontweight="bold")
            for i in range(1, len(rows) + 1):
                for j in range(len(headers)):
                    cell = table[i, j]
                    cell.set_facecolor("#EAF0FB" if i % 2 == 0 else "white")
                    if j == 1:
                        cell.set_facecolor(MOTION_COLORS.get(rows[i-1][1], "#FFFFFF") + "44")

            fig2.text(0.5, 0.03,
                      "Generated by KUKA KRL Path Visualizer · github.com/Thejas12Dixit",
                      fontsize=8, color="#BDC3C7", ha="center")
            pdf.savefig(fig2, bbox_inches="tight")
            plt.close(fig2)

        return output_path

    # ─────────────────────────────────────────
    # PNG export
    # ─────────────────────────────────────────

    def export_png(self, output_path: str = None) -> str:
        if output_path is None:
            output_path = f"{self.prog.name}_path.png"
        fig, ax = self.plot_3d()
        fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#F8F9FA")
        plt.close(fig)
        return output_path
