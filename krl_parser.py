"""
krl_parser.py
=============
KUKA KRL (.src / .dat) file parser and 3D path visualizer.

What this file does:
  1. Reads a KUKA robot program (.src file) and its point data (.dat file)
  2. Extracts all motion commands (PTP, LIN, CIRC) and their coordinates
  3. Visualizes the robot path in 3D

HOW THE PARSER WORKS (simple version):
  - We open the files and read them line by line
  - For the .dat file: we look for lines containing "X", "Y", "Z" and pull out the numbers
  - For the .src file: we look for lines starting with PTP, LIN, or CIRC
  - We then match each motion command to its coordinates

Author : Thejas Dixit Sathyanarayana
GitHub : https://github.com/Thejas12Dixit
"""

# ── Imports ───────────────────────────────────────────────────────────────────
import os                        # os = file path tools (e.g. check if a file exists, get filename)
import numpy as np               # numpy = math library for arrays and distance calculations

import matplotlib                # matplotlib = plotting library for drawing the 3D path
matplotlib.use("Agg")            # "Agg" = save-to-file mode (no popup window) — needed for PDF/PNG export
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from mpl_toolkits.mplot3d import Axes3D          # noqa: F401 — enables 3D plotting
from matplotlib.backends.backend_pdf import PdfPages

# Mayavi is optional — only needed for the interactive 3D window
try:
    from mayavi import mlab as _mlab
    MAYAVI_AVAILABLE = True
except ImportError:
    MAYAVI_AVAILABLE = False

from dataclasses import dataclass, field   # dataclass = auto-creates simple data containers
from typing import Optional                # Optional = this value can be None or a real value
from datetime import datetime              # datetime = used to timestamp the PDF report


# ═════════════════════════════════════════════════════════════════════════════
# DATA CONTAINERS
# These are simple "boxes" that hold data — like a row in a spreadsheet.
# @dataclass automatically creates the __init__ method so we don't have to.
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class KRLPoint:
    """
    Stores the position of ONE robot point from the .dat file.
    Example: P1 is at X=850, Y=-200, Z=1200
    """
    name: str        # The point's name, e.g. "P1" or "HOME"
    x: float = 0.0  # X coordinate in mm
    y: float = 0.0  # Y coordinate in mm
    z: float = 0.0  # Z coordinate in mm
    a: float = 0.0  # Rotation A (yaw)   — how the robot wrist is rotated
    b: float = 0.0  # Rotation B (pitch) — how the robot wrist is tilted
    c: float = 0.0  # Rotation C (roll)  — how the robot wrist is rolled


@dataclass
class KRLMotion:
    """
    Stores ONE motion command from the .src file.
    Example: LIN P3 Vel=0.3 m/s  →  move to point P3 in a straight line at 0.3 m/s
    """
    motion_type: str                    # "PTP", "LIN", or "CIRC"
    point_name: str                     # Name of the target point, e.g. "P3"
    velocity: Optional[float] = None   # Speed value, e.g. 0.3
    velocity_unit: str = "%"            # Speed unit: "%" for PTP, "m/s" for LIN/CIRC
    aux_point: Optional[str] = None    # CIRC only: the via-point name (midpoint of the arc)
    point: Optional[KRLPoint] = None   # The actual coordinates — filled in later by _resolve_points()


@dataclass
class KRLProgram:
    """
    The top-level container — holds everything from one .src + .dat pair.
    Think of it as the complete parsed result.
    """
    name: str = ""                               # Program name, e.g. "sample_welding"
    src_file: str = ""                           # Path to the .src file
    dat_file: str = ""                           # Path to the .dat file
    points: dict = field(default_factory=dict)   # Dictionary: "P1" → KRLPoint(x=850, y=-200, ...)
    motions: list = field(default_factory=list)  # List of KRLMotion objects in order
    warnings: list = field(default_factory=list) # Any problems found during parsing


# ═════════════════════════════════════════════════════════════════════════════
# PARSER
# Reads the files and fills a KRLProgram with data.
#
# HOW IT WORKS — no regex, plain string operations:
#   "line.startswith()" — checks how a line begins
#   "line.split()"      — splits a line into words by spaces
#   "float()"           — converts a string like "850.0" into a number 850.0
# ═════════════════════════════════════════════════════════════════════════════

class KRLParser:
    """
    Reads .src and .dat files and returns a populated KRLProgram object.

    Interview explanation:
    'I open the files line by line. For the .dat I look for lines that
     contain X, Y, Z coordinate data. For the .src I look for lines
     starting with PTP, LIN, or CIRC. Then I link them together.'
    """

    def parse(self, src_path: str, dat_path: str = None) -> KRLProgram:
        """Main entry point — call this to parse a KRL program."""
        prog = KRLProgram()
        prog.src_file = src_path
        prog.name = os.path.splitext(os.path.basename(src_path))[0]
        # os.path.basename removes the folder path → "sample_welding.src"
        # os.path.splitext removes the extension  → "sample_welding"

        # Auto-detect the .dat file if not provided
        if dat_path is None:
            dat_path = os.path.splitext(src_path)[0] + ".dat"
            # If src is "sample_welding.src", dat becomes "sample_welding.dat"

        if os.path.exists(dat_path):
            prog.dat_file = dat_path
            self._parse_dat(dat_path, prog)   # Step 1: read coordinates from .dat
        else:
            prog.warnings.append(f"No .dat file found at {dat_path}")

        self._parse_src(src_path, prog)   # Step 2: read motion commands from .src
        self._resolve_points(prog)        # Step 3: match each motion to its coordinates
        return prog

    # ── Step 1: Read the .dat file ────────────────────────────────────────────

    def _parse_dat(self, path: str, prog: KRLProgram):
        """
        Read point coordinates from the .dat file.

        We look for lines like:
            DECL E6POS P1={X 850.0, Y -200.0, Z 1200.0, A -15.0, B 60.0, C 0.0}

        Strategy (no regex):
            1. Find lines that contain "E6POS" — that marks a point definition
            2. Extract the point name (word after "E6POS")
            3. Find the numbers after X, Y, Z, A, B, C using simple string splitting
        """
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()   # Read all lines into a list

        for line in lines:
            upper = line.upper()   # Convert to uppercase so "e6pos" matches "E6POS"

            # Skip lines that don't define a point
            if "E6POS" not in upper:
                continue

            # ── Extract point name ────────────────────────────────────────────
            # Line looks like: DECL E6POS P1={X 850.0, ...}
            # We split by spaces to get: ["DECL", "E6POS", "P1={X", "850.0,", ...]
            # The point name is at index 2, but it might have "={..." attached
            try:
                parts = line.split()          # Split line into words by whitespace
                name_raw = parts[2]           # "P1={X" or just "P1"
                name = name_raw.split("=")[0] # Remove everything from "=" onwards → "P1"
                name = name.strip()           # Remove any extra spaces
            except IndexError:
                continue   # Skip malformed lines

            # ── Extract X, Y, Z, A, B, C values ──────────────────────────────
            # We use a helper function to find each value
            x = self._extract_value(line, "X")
            y = self._extract_value(line, "Y")
            z = self._extract_value(line, "Z")
            a = self._extract_value(line, "A")
            b = self._extract_value(line, "B")
            c = self._extract_value(line, "C")

            # Only save the point if we found at least X, Y, Z
            if x is not None and y is not None and z is not None:
                prog.points[name.upper()] = KRLPoint(
                    name=name,
                    x=x, y=y, z=z,
                    a=a or 0.0,   # Use 0.0 if A was not found
                    b=b or 0.0,
                    c=c or 0.0,
                )

    def _extract_value(self, line: str, key: str) -> Optional[float]:
        """
        Find a number after a specific letter in a line.

        Example: line = "...X 850.0, Y -200.0..."
                 key  = "X"
                 returns 850.0

        How it works:
            1. Find where the letter appears (e.g. where "X" is)
            2. Take the text after it
            3. Extract the first number we find
        """
        # We look for the key followed by a space or equals sign
        # to avoid matching "MAX" when looking for "A"
        for separator in [f" {key} ", f" {key}=", f"{{{key} ", f",{key} "]:
            idx = line.upper().find(separator.upper())
            if idx == -1:
                continue   # This separator wasn't found, try next one

            # Take everything after the key+separator
            after = line[idx + len(separator):].strip()

            # Read characters until we hit something that's not a number
            num_str = ""
            for ch in after:
                if ch in "0123456789.-":   # Valid number characters
                    num_str += ch
                elif num_str:              # We already started reading a number — stop here
                    break

            if num_str and num_str not in ("-", "."):   # Make sure we got a real number
                try:
                    return float(num_str)
                except ValueError:
                    pass

        return None   # Return None if the key wasn't found

    # ── Step 2: Read the .src file ────────────────────────────────────────────

    def _parse_src(self, path: str, prog: KRLProgram):
        """
        Read motion commands from the .src file.

        We look for lines starting with PTP, LIN, or CIRC:
            PTP  P1  Vel=80%  PDAT1          → move joint-to-joint to P1 at 80% speed
            LIN  P3  Vel=0.3 m/s  CPDAT2     → move in a straight line to P3 at 0.3 m/s
            CIRC P11 P12 Vel=0.2 m/s CPDAT8  → move in an arc via P11 to P12

        Strategy:
            1. Check if the line starts with PTP, LIN, or CIRC (ignore case)
            2. Split the line into words
            3. Word at index 1 = point name (or for CIRC: index 1 = via-point, index 2 = end point)
            4. Find "Vel=" to extract the velocity
        """
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line in lines:
            stripped = line.strip()          # Remove leading/trailing whitespace
            upper = stripped.upper()         # Uppercase for comparison

            if upper.startswith(";"):        # ";" = comment line in KRL — skip it
                continue

            words = stripped.split()         # Split into a list of words
            if len(words) < 2:               # Need at least "PTP P1" — skip short lines
                continue

            motion_type = words[0].upper()   # First word = motion type

            if motion_type not in ("PTP", "LIN", "CIRC"):
                continue   # Not a motion command — skip this line

            # ── Extract velocity ──────────────────────────────────────────────
            velocity = None
            velocity_unit = "%" if motion_type == "PTP" else "m/s"

            for word in words:
                if "VEL=" in word.upper():
                    # word looks like "Vel=0.3" or "Vel=80%"
                    val_str = word.upper().replace("VEL=", "")  # Remove "Vel=" → "0.3" or "80%"
                    if "%" in val_str:
                        velocity_unit = "%"
                        val_str = val_str.replace("%", "")       # Remove "%" → "80"
                    elif "M/S" in val_str:
                        velocity_unit = "m/s"
                        val_str = val_str.replace("M/S", "")     # Remove "m/s" → "0.3"
                    try:
                        velocity = float(val_str)
                    except ValueError:
                        pass   # If conversion fails, leave velocity as None
                    break      # Found velocity — no need to keep searching words

            # ── CIRC: two point names ─────────────────────────────────────────
            if motion_type == "CIRC" and len(words) >= 3:
                # CIRC P11 P12 Vel=...
                # words[1] = via-point (intermediate), words[2] = end-point
                prog.motions.append(KRLMotion(
                    motion_type="CIRC",
                    aux_point=words[1].upper(),    # Via-point
                    point_name=words[2].upper(),   # End-point
                    velocity=velocity,
                    velocity_unit=velocity_unit,
                ))

            # ── PTP / LIN: one point name ─────────────────────────────────────
            else:
                # PTP P1 Vel=...  or  LIN P3 Vel=...
                # words[1] = target point name
                prog.motions.append(KRLMotion(
                    motion_type=motion_type,
                    point_name=words[1].upper(),
                    velocity=velocity,
                    velocity_unit=velocity_unit,
                ))

    # ── Step 3: Link motions to coordinates ───────────────────────────────────

    def _resolve_points(self, prog: KRLProgram):
        """
        Match each motion command to its actual X,Y,Z coordinates.

        After parsing .src and .dat separately, we now connect them:
        For each motion, look up its point_name in prog.points dictionary.
        If found, attach the KRLPoint to the motion.

        Interview explanation:
        'The .src file says "go to P3" but doesn't have coordinates.
         The .dat file has the coordinates for P3 but doesn't say when to go there.
         This step links them together.'
        """
        for motion in prog.motions:
            key = motion.point_name.upper()   # Uppercase for consistent lookup
            if key in prog.points:
                motion.point = prog.points[key]   # Attach the coordinates to this motion
            else:
                prog.warnings.append(f"Point {motion.point_name} not found in .dat")


# ═════════════════════════════════════════════════════════════════════════════
# COLOR SCHEME
# Two sets: hex strings for matplotlib, RGB tuples for Mayavi
# ═════════════════════════════════════════════════════════════════════════════

MOTION_COLORS = {
    "PTP":  "#4A90D9",   # Blue  — joint-space move
    "LIN":  "#27AE60",   # Green — linear Cartesian move
    "CIRC": "#E67E22",   # Orange — circular arc move
}
WELD_COLOR  = "#E74C3C"   # Red    — process/weld points
START_COLOR = "#9B59B6"   # Purple — HOME position

MAYAVI_COLORS = {
    "PTP":  (0.29, 0.56, 0.85),
    "LIN":  (0.15, 0.68, 0.38),
    "CIRC": (0.90, 0.50, 0.13),
}
MAYAVI_WELD = (0.91, 0.30, 0.24)
MAYAVI_HOME = (0.61, 0.35, 0.71)
MAYAVI_TEXT = (1.0,  1.0,  1.0)


# ═════════════════════════════════════════════════════════════════════════════
# VISUALIZER
# Takes parsed data and draws the 3D robot path.
#
# HOW MATPLOTLIB DRAWING WORKS (simple version):
#   Think of it like MS Paint but in code:
#   - ax.plot()     = draw a line between two points
#   - ax.scatter()  = draw a dot at a point
#   - ax.text()     = write a label at a position
#   - plt.savefig() = save the drawing to a file
# ═════════════════════════════════════════════════════════════════════════════

class KRLVisualizer:
    """
    Draws the robot path and exports reports.

    Interview explanation:
    'I loop through the list of motion commands. For each consecutive pair
     of points, I draw a colored line between them. The color depends on
     the motion type — blue for PTP, green for LIN, orange for CIRC.
     Then I add dots at each point and labels above them.'
    """

    def __init__(self, program: KRLProgram):
        self.prog = program   # Store the program so all methods can use it

    def _get_path_segments(self):
        """
        Build a list of line segments to draw.

        Each segment = one move = a line from point A to point B.
        We skip any motions that don't have coordinates (unresolved points).

        Returns a list of tuples: (motion, start_point, end_point)
        """
        # Only keep motions that have valid coordinates
        resolved = [m for m in self.prog.motions if m.point is not None]

        segments = []
        for i in range(1, len(resolved)):
            prev = resolved[i - 1]   # The previous motion (start of segment)
            curr = resolved[i]       # The current motion (end of segment)
            if prev.point and curr.point:
                segments.append((curr, prev.point, curr.point))
                # Tuple: (motion object, start KRLPoint, end KRLPoint)

        return segments

    def _all_coords(self):
        """
        Collect all point coordinates into a numpy array.
        Used for calculating the workspace envelope (min/max X, Y, Z).
        Shape: (number_of_points, 3) — each row is [x, y, z]
        """
        pts = [m.point for m in self.prog.motions if m.point]
        if not pts:
            return np.zeros((1, 3))   # Return a single zero row if no points found
        return np.array([[p.x, p.y, p.z] for p in pts])

    # ─────────────────────────────────────────────────────────────────────────
    # MAYAVI — interactive 3D viewer
    # ─────────────────────────────────────────────────────────────────────────

    def plot_3d_mayavi(self, title: str = None):
        """
        Open a rich interactive Mayavi 3D window.
        Requires: pip install mayavi PyQt5
        Controls: left-drag = rotate | scroll = zoom | right-drag = pan
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

        # Create the dark 3D scene window
        _mlab.figure(
            figure=fig_title,
            bgcolor=(0.12, 0.14, 0.18),   # Dark background color (R, G, B between 0-1)
            fgcolor=(0.9, 0.9, 0.9),      # Light grey for text/axes
            size=(1100, 750),             # Window size in pixels
        )

        # Draw each path segment as a colored tube
        for motion, pt_from, pt_to in self._get_path_segments():
            col = MAYAVI_COLORS.get(motion.motion_type, (0.6, 0.6, 0.6))
            _mlab.plot3d(
                [pt_from.x, pt_to.x],   # X start and end
                [pt_from.y, pt_to.y],   # Y start and end
                [pt_from.z, pt_to.z],   # Z start and end
                color=col,
                tube_radius=5,          # How thick the tube is (in mm)
                tube_sides=12,          # How smooth the tube looks
                opacity=0.95,
            )

        # Draw a sphere and label at each point
        for motion in resolved:
            pt = motion.point
            is_home = "HOME" in motion.point_name
            col   = MAYAVI_HOME if is_home else MAYAVI_WELD
            scale = 30 if is_home else 20   # HOME sphere is slightly bigger

            _mlab.points3d(pt.x, pt.y, pt.z,
                           color=col, scale_factor=scale,
                           resolution=20, opacity=1.0)
            _mlab.text3d(pt.x, pt.y, pt.z + 25,   # Label floats 25mm above the sphere
                         motion.point_name,
                         color=MAYAVI_TEXT, scale=14)

        # Add axis labels and orientation marker
        _mlab.axes(xlabel="X (mm)", ylabel="Y (mm)", zlabel="Z (mm)",
                   color=(0.65, 0.65, 0.65), line_width=1.0)
        _mlab.orientation_axes()   # Small XYZ cube in the corner
        _mlab.title(fig_title, size=0.25, color=(0.9, 0.9, 0.9), height=0.95)

        # Legend text in the bottom-left of the screen
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
        _mlab.show()   # Open window — blocks until user closes it

    # ─────────────────────────────────────────────────────────────────────────
    # MATPLOTLIB 3D — used only for PDF/PNG export
    #
    # HOW IT WORKS:
    #   1. Create a blank 3D canvas (figure + axes)
    #   2. Loop through path segments → draw a colored line for each
    #   3. Loop through points → draw a dot and label for each
    #   4. Add axis labels, legend, title
    #   5. Return the figure so the caller can save it
    # ─────────────────────────────────────────────────────────────────────────

    def plot_3d(self, ax=None, title: str = None):
        """
        Draw the robot path on a matplotlib 3D axes.
        Used internally for PDF/PNG export — not for interactive viewing.

        Interview explanation:
        'I create a 3D canvas, then loop through every consecutive pair
         of points and draw a line between them. Blue for PTP, green for LIN,
         orange for CIRC. Then I add dots and labels at each point.'
        """
        # ── Create or reuse a figure ──────────────────────────────────────────
        if ax is None:
            # No axes provided — create a new figure from scratch
            fig = plt.figure(figsize=(12, 8))             # figsize = width x height in inches
            ax  = fig.add_subplot(111, projection="3d")   # "3d" = enables 3D mode
        else:
            # Axes was passed in (e.g. from export_pdf) — use the existing figure
            fig = ax.get_figure()

        # ── Draw lines between consecutive points ─────────────────────────────
        for motion, pt_from, pt_to in self._get_path_segments():
            color = MOTION_COLORS.get(motion.motion_type, "#999999")   # Grey if unknown type

            ax.plot(
                [pt_from.x, pt_to.x],   # A list of 2 X values = start X and end X
                [pt_from.y, pt_to.y],   # A list of 2 Y values
                [pt_from.z, pt_to.z],   # A list of 2 Z values
                color=color,
                linewidth=2,            # Line thickness
                alpha=0.85,             # Slight transparency (1.0 = fully solid)
            )

        # ── Draw a dot and label at each point ────────────────────────────────
        for motion in [m for m in self.prog.motions if m.point]:
            pt = motion.point
            is_home = "HOME" in motion.point_name

            dot_color = START_COLOR if is_home else WELD_COLOR   # Purple for HOME, red for others
            dot_size  = 80 if is_home else 50                    # HOME dot is slightly bigger

            ax.scatter(pt.x, pt.y, pt.z,
                       color=dot_color, s=dot_size,
                       zorder=5,       # zorder=5 = draw dots ON TOP of lines (not behind)
                       alpha=0.9)

            ax.text(pt.x, pt.y, pt.z + 15,   # Place label 15mm above the dot
                    motion.point_name,
                    fontsize=7, color="#333333",
                    ha="center",    # ha = horizontal alignment: center the text on the point
                    va="bottom")    # va = vertical alignment: text sits above the position

        # ── Labels, title, legend ─────────────────────────────────────────────
        ax.set_xlabel("X (mm)", fontsize=9)
        ax.set_ylabel("Y (mm)", fontsize=9)
        ax.set_zlabel("Z (mm)", fontsize=9)
        ax.set_title(title or f"Robot path — {self.prog.name}",
                     fontsize=11, fontweight="bold")
        ax.tick_params(labelsize=7)   # Make axis tick numbers smaller

        # Legend: colored rectangles explaining what each color means
        # mpatches.Patch = a colored rectangle used as a legend item
        ax.legend(handles=[
            mpatches.Patch(color=MOTION_COLORS["PTP"],  label="PTP — Point-to-point"),
            mpatches.Patch(color=MOTION_COLORS["LIN"],  label="LIN — Linear"),
            mpatches.Patch(color=MOTION_COLORS["CIRC"], label="CIRC — Circular"),
            mpatches.Patch(color=WELD_COLOR,            label="Process point"),
            mpatches.Patch(color=START_COLOR,           label="HOME / Start"),
        ], loc="upper left", fontsize=8)

        ax.view_init(elev=25, azim=-60)
        # elev = camera elevation angle (degrees above horizontal)
        # azim = camera azimuth angle (horizontal rotation)

        return fig, ax

    # ─────────────────────────────────────────────────────────────────────────
    # STATISTICS
    # ─────────────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """
        Calculate program statistics and return them as a dictionary.

        Interview explanation:
        'I loop through every consecutive pair of points, calculate the
         straight-line distance using the 3D Pythagorean theorem, and
         add them all up to get total path length.'
        """
        resolved = [m for m in self.prog.motions if m.point]
        counts = {"PTP": 0, "LIN": 0, "CIRC": 0}
        total_dist = 0.0
        min_vel = float("inf")   # Start at infinity so any real value will be smaller
        max_vel = 0.0

        for motion, pt_from, pt_to in self._get_path_segments():
            # Count each motion type
            counts[motion.motion_type] = counts.get(motion.motion_type, 0) + 1

            # 3D Pythagorean theorem: distance = sqrt(dx² + dy² + dz²)
            dx = pt_to.x - pt_from.x
            dy = pt_to.y - pt_from.y
            dz = pt_to.z - pt_from.z
            distance = float(np.sqrt(dx**2 + dy**2 + dz**2))
            total_dist += distance

            # Track velocity range (LIN/CIRC only — PTP uses % not m/s)
            if motion.velocity and motion.velocity_unit == "m/s":
                v = motion.velocity * 1000   # Convert m/s → mm/s (same unit as distance)
                min_vel = min(min_vel, v)
                max_vel = max(max_vel, v)

        # Get all coordinates as a numpy array to find min/max per axis
        coords = self._all_coords()   # Shape: (N, 3)

        return {
            "program_name":     self.prog.name,
            "total_points":     len(resolved),
            "ptp_moves":        counts["PTP"],
            "lin_moves":        counts["LIN"],
            "circ_moves":       counts["CIRC"],
            "total_distance":   round(total_dist, 1),
            "x_range":          (round(float(coords[:, 0].min()), 1),   # coords[:,0] = all X values
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

    # ─────────────────────────────────────────────────────────────────────────
    # PDF EXPORT
    # Generates a 2-page A4 landscape PDF report
    # ─────────────────────────────────────────────────────────────────────────

    def export_pdf(self, output_path: str = None) -> str:
        """
        Save a 2-page PDF:
          Page 1 = 3D path plot + statistics panel
          Page 2 = motion sequence table
        """
        if output_path is None:
            output_path = f"{self.prog.name}_path_report.pdf"

        stats = self.get_stats()

        with PdfPages(output_path) as pdf:
            # PdfPages = context manager that collects figures and saves them as pages

            # ── PAGE 1: 3D plot + stats ───────────────────────────────────────
            fig = plt.figure(figsize=(11.69, 8.27))   # A4 landscape size in inches
            fig.patch.set_facecolor("#F8F9FA")         # Light grey background

            # Header text (positioned using figure coordinates: 0=left/bottom, 1=right/top)
            fig.text(0.05, 0.94, "KUKA Robot Path Visualizer",
                     fontsize=18, fontweight="bold", color="#2C3E50")
            fig.text(0.05, 0.90,
                     f"Program: {self.prog.name}  |  "
                     f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
                     f"Author: Thejas Dixit Sathyanarayana",
                     fontsize=9, color="#7F8C8D")

            # Thin divider line under the header
            la = fig.add_axes([0.05, 0.88, 0.90, 0.001])
            la.axhline(y=0, color="#BDC3C7", linewidth=0.8)
            la.axis("off")

            # 3D plot on the left side of the page
            ax3d = fig.add_axes([0.05, 0.12, 0.58, 0.72], projection="3d")
            self.plot_3d(ax=ax3d, title="3D Robot Path")

            # Stats text on the right side
            sx, sy, lh = 0.67, 0.85, 0.052   # x position, y start, line height

            def stat_line(label, value, y):
                """Write one label=value pair on the figure."""
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
            stat_line("X range", f"{stats['x_range'][0]} -> {stats['x_range'][1]} mm", sy - lh * 8.5)
            stat_line("Y range", f"{stats['y_range'][0]} -> {stats['y_range'][1]} mm", sy - lh * 9.5)
            stat_line("Z range", f"{stats['z_range'][0]} -> {stats['z_range'][1]} mm", sy - lh * 10.5)

            fig.text(sx, sy - lh * 12, "Velocity",
                     fontsize=10, fontweight="bold", color="#2C3E50")
            stat_line("Min (LIN/CIRC)", f"{stats['min_velocity_mms']} mm/s", sy - lh * 13)
            stat_line("Max (LIN/CIRC)", f"{stats['max_velocity_mms']} mm/s", sy - lh * 14)

            fig.text(0.5, 0.03,
                     "Generated by KUKA KRL Path Visualizer · github.com/Thejas12Dixit",
                     fontsize=8, color="#BDC3C7", ha="center")

            pdf.savefig(fig, bbox_inches="tight")   # Save as page 1
            plt.close(fig)                          # Free memory

            # ── PAGE 2: Motion table ──────────────────────────────────────────
            fig2, ax2 = plt.subplots(figsize=(11.69, 8.27))
            fig2.patch.set_facecolor("#F8F9FA")
            ax2.axis("off")   # Hide axes — we only want the table

            fig2.text(0.05, 0.95, "Motion Sequence Table",
                      fontsize=14, fontweight="bold", color="#2C3E50")
            fig2.text(0.05, 0.91,
                      f"Program: {self.prog.name}  |  "
                      f"{len([m for m in self.prog.motions if m.point])} resolved points",
                      fontsize=9, color="#7F8C8D")

            la2 = fig2.add_axes([0.05, 0.89, 0.90, 0.001])
            la2.axhline(y=0, color="#BDC3C7", linewidth=0.8)
            la2.axis("off")

            # Build table rows
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

            # Style header row: dark background, white text
            for j in range(len(headers)):
                cell = table[0, j]
                cell.set_facecolor("#2C3E50")
                cell.set_text_props(color="white", fontweight="bold")

            # Style data rows: alternate white/light-blue for readability
            for i in range(1, len(rows) + 1):
                for j in range(len(headers)):
                    cell = table[i, j]
                    cell.set_facecolor("#EAF0FB" if i % 2 == 0 else "white")
                    if j == 1:   # "Type" column — color by motion type
                        cell.set_facecolor(MOTION_COLORS.get(rows[i-1][1], "#FFFFFF") + "44")
                        # "44" at the end = hex for 27% opacity (makes color lighter)

            fig2.text(0.5, 0.03,
                      "Generated by KUKA KRL Path Visualizer · github.com/Thejas12Dixit",
                      fontsize=8, color="#BDC3C7", ha="center")

            pdf.savefig(fig2, bbox_inches="tight")   # Save as page 2
            plt.close(fig2)

        return output_path

    # ─────────────────────────────────────────────────────────────────────────
    # PNG EXPORT
    # ─────────────────────────────────────────────────────────────────────────

    def export_png(self, output_path: str = None) -> str:
        """Save a single PNG image of the 3D robot path."""
        if output_path is None:
            output_path = f"{self.prog.name}_path.png"
        fig, ax = self.plot_3d()
        fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#F8F9FA")
        plt.close(fig)
        return output_path
