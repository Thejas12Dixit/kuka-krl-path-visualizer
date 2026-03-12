"""
KUKA_krl_reader.py

Reads KUKA robot program files (.src and .dat) and visualizes the path in 3D.

Steps:
  1. Read the .dat file to get the X, Y, Z coordinates for each point
  2. Read the .src file to get the motion commands (PTP, LIN, CIRC)
  3. Match each motion command to its coordinates
  4. Draw the path or export it as a PDF or PNG

Author: Thejas Dixit Sathyanarayana
GitHub: https://github.com/Thejas12Dixit
"""

import os
import numpy as np

import matplotlib
matplotlib.use("Agg")  # save to file mode, no popup window
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401, needed for 3D plotting
from matplotlib.backends.backend_pdf import PdfPages

# Mayavi is optional, only needed for the interactive 3D window
try:
    from mayavi import mlab as _mlab
    MAYAVI_AVAILABLE = True
except ImportError:
    MAYAVI_AVAILABLE = False

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


# Data containers
# Simple boxes that hold the data we read from the files.
# @dataclass saves us from writing __init__ manually.

@dataclass
class KRLPoint:
    """One robot point from the .dat file, e.g. P1 at X=850, Y=-200, Z=1200."""
    name: str
    x: float = 0.0  # mm
    y: float = 0.0  # mm
    z: float = 0.0  # mm
    a: float = 0.0  # wrist rotation yaw
    b: float = 0.0  # wrist tilt pitch
    c: float = 0.0  # wrist roll


@dataclass
class KRLMotion:
    """One motion command from the .src file, e.g. LIN P3 Vel=0.3 m/s."""
    motion_type: str                    # PTP, LIN, or CIRC
    point_name: str                     # target point name, e.g. P3
    velocity: Optional[float] = None   # speed value, e.g. 0.3
    velocity_unit: str = "%"            # % for PTP, m/s for LIN and CIRC
    aux_point: Optional[str] = None    # CIRC only: the via-point name
    point: Optional[KRLPoint] = None   # filled in later when we match to .dat data


@dataclass
class KRLProgram:
    """Holds everything parsed from one .src and .dat file pair."""
    name: str = ""
    src_file: str = ""
    dat_file: str = ""
    points: dict = field(default_factory=dict)   # point name -> KRLPoint
    motions: list = field(default_factory=list)  # list of KRLMotion in order
    warnings: list = field(default_factory=list) # any issues found during parsing


# Parser
# Opens the files and fills a KRLProgram with data.
# No regex used here, just plain string operations:
#   line.split()       splits a line into words
#   line.startswith()  checks how a line begins
#   float("850.0")     converts text to a number

class KRLParser:
    """Reads .src and .dat files and returns a KRLProgram object."""

    def parse(self, src_path: str, dat_path: str = None) -> KRLProgram:
        """Main entry point. Call this to parse a KRL program."""
        prog = KRLProgram()
        prog.src_file = src_path
        prog.name = os.path.splitext(os.path.basename(src_path))[0]
        # basename removes the folder path, splitext removes the .src extension

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

    def _parse_dat(self, path: str, prog: KRLProgram):
        """
        Read point coordinates from the .dat file.

        Looks for lines like:
            DECL E6POS P1={X 850.0, Y -200.0, Z 1200.0, A -15.0, B 60.0, C 0.0}

        Steps:
            1. Skip any line that does not contain E6POS
            2. Get the point name (the word after E6POS)
            3. Extract the numbers after X, Y, Z, A, B, C
        """
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line in lines:
            if "E6POS" not in line.upper():
                continue

            try:
                parts = line.split()
                name_raw = parts[2]            # e.g. "P1={X"
                name = name_raw.split("=")[0]  # remove the "={..." part, keep "P1"
                name = name.strip()
            except IndexError:
                continue

            x = self._extract_value(line, "X")
            y = self._extract_value(line, "Y")
            z = self._extract_value(line, "Z")
            a = self._extract_value(line, "A")
            b = self._extract_value(line, "B")
            c = self._extract_value(line, "C")

            if x is not None and y is not None and z is not None:
                prog.points[name.upper()] = KRLPoint(
                    name=name,
                    x=x, y=y, z=z,
                    a=a or 0.0,
                    b=b or 0.0,
                    c=c or 0.0,
                )

    def _extract_value(self, line: str, key: str) -> Optional[float]:
        """
        Find the number after a given letter in a line.

        Example: line = "...X 850.0, Y -200.0..."
                 key  = "X"
                 returns 850.0

        We check a few different separators to handle variations in file formatting.
        """
        for separator in [f" {key} ", f" {key}=", f"{{{key} ", f",{key} "]:
            idx = line.upper().find(separator.upper())
            if idx == -1:
                continue

            after = line[idx + len(separator):].strip()

            num_str = ""
            for ch in after:
                if ch in "0123456789.-":
                    num_str += ch
                elif num_str:
                    break

            if num_str and num_str not in ("-", "."):
                try:
                    return float(num_str)
                except ValueError:
                    pass

        return None

    def _parse_src(self, path: str, prog: KRLProgram):
        """
        Read motion commands from the .src file.

        Looks for lines like:
            PTP  P1  Vel=80%             move joint-to-joint to P1 at 80% speed
            LIN  P3  Vel=0.3 m/s        move in a straight line to P3
            CIRC P11 P12 Vel=0.2 m/s    move in an arc via P11, ending at P12

        Steps:
            1. Skip comment lines (lines starting with ;)
            2. Check if the line starts with PTP, LIN, or CIRC
            3. Get the point name and velocity from the words on that line
        """
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line in lines:
            stripped = line.strip()

            if stripped.upper().startswith(";"):
                continue  # skip comment lines

            words = stripped.split()
            if len(words) < 2:
                continue

            motion_type = words[0].upper()

            if motion_type not in ("PTP", "LIN", "CIRC"):
                continue

            velocity = None
            velocity_unit = "%" if motion_type == "PTP" else "m/s"

            for word in words:
                if "VEL=" in word.upper():
                    val_str = word.upper().replace("VEL=", "")
                    if "%" in val_str:
                        velocity_unit = "%"
                        val_str = val_str.replace("%", "")
                    elif "M/S" in val_str:
                        velocity_unit = "m/s"
                        val_str = val_str.replace("M/S", "")
                    try:
                        velocity = float(val_str)
                    except ValueError:
                        pass
                    break

            if motion_type == "CIRC" and len(words) >= 3:
                # CIRC has two point names: words[1] = via-point, words[2] = end point
                prog.motions.append(KRLMotion(
                    motion_type="CIRC",
                    aux_point=words[1].upper(),
                    point_name=words[2].upper(),
                    velocity=velocity,
                    velocity_unit=velocity_unit,
                ))
            else:
                prog.motions.append(KRLMotion(
                    motion_type=motion_type,
                    point_name=words[1].upper(),
                    velocity=velocity,
                    velocity_unit=velocity_unit,
                ))

    def _resolve_points(self, prog: KRLProgram):
        """
        Link each motion command to its coordinates.

        The .src file says "go to P3" but has no coordinates.
        The .dat file has the coordinates for P3 but no timing.
        This step connects them by looking up each point name in the dictionary.
        """
        for motion in prog.motions:
            key = motion.point_name.upper()
            if key in prog.points:
                motion.point = prog.points[key]
            else:
                prog.warnings.append(f"Point {motion.point_name} not found in .dat")


# Colors used in the plots
# Two sets: hex strings for matplotlib, RGB tuples for Mayavi

MOTION_COLORS = {
    "PTP":  "#4A90D9",  # blue
    "LIN":  "#27AE60",  # green
    "CIRC": "#E67E22",  # orange
}
WELD_COLOR  = "#E74C3C"  # red, for process/weld points
START_COLOR = "#9B59B6"  # purple, for HOME position

MAYAVI_COLORS = {
    "PTP":  (0.29, 0.56, 0.85),
    "LIN":  (0.15, 0.68, 0.38),
    "CIRC": (0.90, 0.50, 0.13),
}
MAYAVI_WELD = (0.91, 0.30, 0.24)
MAYAVI_HOME = (0.61, 0.35, 0.71)
MAYAVI_TEXT = (1.0,  1.0,  1.0)


# Visualizer
# Takes the parsed data and draws the robot path.
#
# Basic idea of how matplotlib drawing works:
#   ax.plot()     draws a line between two points
#   ax.scatter()  draws a dot at a point
#   ax.text()     writes a label at a position
#   plt.savefig() saves everything to a file

class KRLVisualizer:
    """Draws the robot path and exports PDF and PNG reports."""

    def __init__(self, program: KRLProgram):
        self.prog = program

    def _get_path_segments(self):
        """
        Build a list of segments to draw, one per motion command.
        Each segment is a tuple of (motion, start point, end point).
        Skips any motions where coordinates are missing.
        """
        resolved = [m for m in self.prog.motions if m.point is not None]

        segments = []
        for i in range(1, len(resolved)):
            prev = resolved[i - 1]
            curr = resolved[i]
            if prev.point and curr.point:
                segments.append((curr, prev.point, curr.point))

        return segments

    def _all_coords(self):
        """Return all point coordinates as a numpy array, shape (N, 3)."""
        pts = [m.point for m in self.prog.motions if m.point]
        if not pts:
            return np.zeros((1, 3))
        return np.array([[p.x, p.y, p.z] for p in pts])

    def plot_3d_mayavi(self, title: str = None):
        """
        Open an interactive Mayavi 3D window.
        Requires: pip install mayavi PyQt5
        Controls: left-drag to rotate, scroll to zoom, right-drag to pan.
        """
        if not MAYAVI_AVAILABLE:
            print(
                "\nMayavi is not installed.\n"
                "Install with: pip install mayavi PyQt5\n"
                "You can also use export_pdf() or export_png() instead.\n"
            )
            return

        resolved = [m for m in self.prog.motions if m.point is not None]
        if not resolved:
            print("No points to visualize.")
            return

        fig_title = title or f"KUKA Path - {self.prog.name}"

        _mlab.figure(
            figure=fig_title,
            bgcolor=(0.12, 0.14, 0.18),
            fgcolor=(0.9, 0.9, 0.9),
            size=(1100, 750),
        )

        for motion, pt_from, pt_to in self._get_path_segments():
            col = MAYAVI_COLORS.get(motion.motion_type, (0.6, 0.6, 0.6))
            _mlab.plot3d(
                [pt_from.x, pt_to.x],
                [pt_from.y, pt_to.y],
                [pt_from.z, pt_to.z],
                color=col,
                tube_radius=5,
                tube_sides=12,
                opacity=0.95,
            )

        for motion in resolved:
            pt = motion.point
            is_home = "HOME" in motion.point_name
            col   = MAYAVI_HOME if is_home else MAYAVI_WELD
            scale = 30 if is_home else 20

            _mlab.points3d(pt.x, pt.y, pt.z, color=col, scale_factor=scale,
                           resolution=20, opacity=1.0)
            _mlab.text3d(pt.x, pt.y, pt.z + 25, motion.point_name,
                         color=MAYAVI_TEXT, scale=14)

        _mlab.axes(xlabel="X (mm)", ylabel="Y (mm)", zlabel="Z (mm)",
                   color=(0.65, 0.65, 0.65), line_width=1.0)
        _mlab.orientation_axes()
        _mlab.title(fig_title, size=0.25, color=(0.9, 0.9, 0.9), height=0.95)

        legend = [
            ("PTP  - Point-to-point",  MAYAVI_COLORS["PTP"]),
            ("LIN  - Linear",          MAYAVI_COLORS["LIN"]),
            ("CIRC - Circular arc",    MAYAVI_COLORS["CIRC"]),
            ("Process / weld point",   MAYAVI_WELD),
            ("HOME / start",           MAYAVI_HOME),
        ]
        for idx, (label, col) in enumerate(legend):
            _mlab.text(0.02, 0.04 + idx * 0.05, label, color=col, width=0.28)

        _mlab.view(azimuth=-60, elevation=35, distance="auto")
        print(f"\n{fig_title}")
        print("Rotate: left-drag  |  Zoom: scroll  |  Pan: right-drag\n")
        _mlab.show()

    def plot_3d(self, ax=None, title: str = None):
        """
        Draw the robot path on a matplotlib 3D axes.
        Used internally for PDF and PNG export.

        For each pair of consecutive points, a colored line is drawn between them.
        Blue for PTP, green for LIN, orange for CIRC.
        A dot and label are added at each point.
        """
        if ax is None:
            fig = plt.figure(figsize=(12, 8))
            ax  = fig.add_subplot(111, projection="3d")
        else:
            fig = ax.get_figure()

        for motion, pt_from, pt_to in self._get_path_segments():
            color = MOTION_COLORS.get(motion.motion_type, "#999999")
            ax.plot(
                [pt_from.x, pt_to.x],
                [pt_from.y, pt_to.y],
                [pt_from.z, pt_to.z],
                color=color,
                linewidth=2,
                alpha=0.85,
            )

        for motion in [m for m in self.prog.motions if m.point]:
            pt = motion.point
            is_home = "HOME" in motion.point_name
            dot_color = START_COLOR if is_home else WELD_COLOR
            dot_size  = 80 if is_home else 50

            ax.scatter(pt.x, pt.y, pt.z, color=dot_color, s=dot_size,
                       zorder=5, alpha=0.9)
            ax.text(pt.x, pt.y, pt.z + 15, motion.point_name,
                    fontsize=7, color="#333333", ha="center", va="bottom")

        ax.set_xlabel("X (mm)", fontsize=9)
        ax.set_ylabel("Y (mm)", fontsize=9)
        ax.set_zlabel("Z (mm)", fontsize=9)
        ax.set_title(title or f"Robot path - {self.prog.name}",
                     fontsize=11, fontweight="bold")
        ax.tick_params(labelsize=7)

        ax.legend(handles=[
            mpatches.Patch(color=MOTION_COLORS["PTP"],  label="PTP - Point-to-point"),
            mpatches.Patch(color=MOTION_COLORS["LIN"],  label="LIN - Linear"),
            mpatches.Patch(color=MOTION_COLORS["CIRC"], label="CIRC - Circular"),
            mpatches.Patch(color=WELD_COLOR,            label="Process point"),
            mpatches.Patch(color=START_COLOR,           label="HOME / Start"),
        ], loc="upper left", fontsize=8)

        ax.view_init(elev=25, azim=-60)

        return fig, ax

    def get_stats(self) -> dict:
        """
        Calculate and return program statistics.

        Loops through each consecutive pair of points, calculates the
        straight-line distance using the 3D Pythagorean theorem, and
        adds them all up for the total path length.
        """
        resolved = [m for m in self.prog.motions if m.point]
        counts = {"PTP": 0, "LIN": 0, "CIRC": 0}
        total_dist = 0.0
        min_vel = float("inf")
        max_vel = 0.0

        for motion, pt_from, pt_to in self._get_path_segments():
            counts[motion.motion_type] = counts.get(motion.motion_type, 0) + 1

            dx = pt_to.x - pt_from.x
            dy = pt_to.y - pt_from.y
            dz = pt_to.z - pt_from.z
            total_dist += float(np.sqrt(dx**2 + dy**2 + dz**2))

            if motion.velocity and motion.velocity_unit == "m/s":
                v = motion.velocity * 1000  # convert to mm/s
                min_vel = min(min_vel, v)
                max_vel = max(max_vel, v)

        coords = self._all_coords()

        return {
            "program_name":     self.prog.name,
            "total_points":     len(resolved),
            "ptp_moves":        counts["PTP"],
            "lin_moves":        counts["LIN"],
            "circ_moves":       counts["CIRC"],
            "total_distance":   round(total_dist, 1),
            "x_range":          (round(float(coords[:, 0].min()), 1),
                                  round(float(coords[:, 0].max()), 1)),
            "y_range":          (round(float(coords[:, 1].min()), 1),
                                  round(float(coords[:, 1].max()), 1)),
            "z_range":          (round(float(coords[:, 2].min()), 1),
                                  round(float(coords[:, 2].max()), 1)),
            "min_velocity_mms": round(min_vel, 1) if min_vel != float("inf") else "N/A",
            "max_velocity_mms": round(max_vel, 1) if max_vel > 0 else "N/A",
            "mayavi_available": MAYAVI_AVAILABLE,
            "warnings":         self.prog.warnings,
        }

    def export_pdf(self, output_path: str = None) -> str:
        """
        Save a 2-page PDF report.
        Page 1 has the 3D path plot and statistics.
        Page 2 has the full motion sequence table.
        """
        if output_path is None:
            output_path = f"{self.prog.name}_path_report.pdf"

        stats = self.get_stats()

        with PdfPages(output_path) as pdf:

            # Page 1: 3D plot and stats panel
            fig = plt.figure(figsize=(11.69, 8.27))  # A4 landscape
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

            def stat_line(label, value, y):
                fig.text(sx,        y, label,      fontsize=9, color="#7F8C8D")
                fig.text(sx + 0.17, y, str(value), fontsize=9, color="#2C3E50")

            fig.text(sx, sy, "Program Statistics",
                     fontsize=11, fontweight="bold", color="#2C3E50")
            stat_line("Program",        stats["program_name"],           sy - lh * 1)
            stat_line("Total points",   stats["total_points"],           sy - lh * 2)
            stat_line("PTP moves",      stats["ptp_moves"],              sy - lh * 3)
            stat_line("LIN moves",      stats["lin_moves"],              sy - lh * 4)
            stat_line("CIRC moves",     stats["circ_moves"],             sy - lh * 5)
            stat_line("Total distance", f"{stats['total_distance']} mm", sy - lh * 6)

            fig.text(sx, sy - lh * 7.5, "Workspace Envelope",
                     fontsize=10, fontweight="bold", color="#2C3E50")
            stat_line("X range", f"{stats['x_range'][0]} to {stats['x_range'][1]} mm", sy - lh * 8.5)
            stat_line("Y range", f"{stats['y_range'][0]} to {stats['y_range'][1]} mm", sy - lh * 9.5)
            stat_line("Z range", f"{stats['z_range'][0]} to {stats['z_range'][1]} mm", sy - lh * 10.5)

            fig.text(sx, sy - lh * 12, "Velocity",
                     fontsize=10, fontweight="bold", color="#2C3E50")
            stat_line("Min (LIN/CIRC)", f"{stats['min_velocity_mms']} mm/s", sy - lh * 13)
            stat_line("Max (LIN/CIRC)", f"{stats['max_velocity_mms']} mm/s", sy - lh * 14)

            fig.text(0.5, 0.03,
                     "Generated by KUKA KRL Path Visualizer - github.com/Thejas12Dixit",
                     fontsize=8, color="#BDC3C7", ha="center")

            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            # Page 2: motion sequence table
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
                rows.append([
                    str(i + 1), motion.motion_type, motion.point_name,
                    f"{pt.x:.1f}", f"{pt.y:.1f}", f"{pt.z:.1f}", vel_str,
                ])

            headers = ["#", "Type", "Point", "X (mm)", "Y (mm)", "Z (mm)", "Velocity"]
            table = ax2.table(cellText=rows, colLabels=headers,
                              cellLoc="center", loc="upper center",
                              bbox=[0.0, 0.05, 1.0, 0.82])
            table.auto_set_font_size(False)
            table.set_fontsize(9)

            for j in range(len(headers)):
                cell = table[0, j]
                cell.set_facecolor("#2C3E50")
                cell.set_text_props(color="white", fontweight="bold")

            for i in range(1, len(rows) + 1):
                for j in range(len(headers)):
                    cell = table[i, j]
                    cell.set_facecolor("#EAF0FB" if i % 2 == 0 else "white")
                    if j == 1:
                        cell.set_facecolor(MOTION_COLORS.get(rows[i-1][1], "#FFFFFF") + "44")

            fig2.text(0.5, 0.03,
                      "Generated by KUKA KRL Path Visualizer - github.com/Thejas12Dixit",
                      fontsize=8, color="#BDC3C7", ha="center")

            pdf.savefig(fig2, bbox_inches="tight")
            plt.close(fig2)

        return output_path

    def export_png(self, output_path: str = None) -> str:
        """Save a single PNG image of the 3D robot path."""
        if output_path is None:
            output_path = f"{self.prog.name}_path.png"
        fig, ax = self.plot_3d()
        fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#F8F9FA")
        plt.close(fig)
        return output_path
