"""
krl_parser.py
=============
KUKA KRL (.src / .dat) file parser and 3D path visualizer.

What this file does:
  1. Reads a KUKA robot program (.src file) and its point data (.dat file)
  2. Extracts all motion commands (PTP, LIN, CIRC) and their coordinates
  3. Visualizes the robot path in 3D using Mayavi (interactive) or Matplotlib (export)

KRL = KUKA Robot Language — the programming language used on KUKA controllers
.src = the program file containing motion commands like PTP, LIN, CIRC
.dat = the data file containing the actual X,Y,Z coordinates for each point

Visualisation:
  - Mayavi     -> interactive 3D viewer  ->  vis.plot_3d_mayavi()
  - Matplotlib -> PDF report + PNG       ->  vis.export_pdf() / vis.export_png()

Install dependencies:
  pip install matplotlib numpy pandas
  pip install mayavi PyQt5          # only needed for interactive Mayavi viewer

Author : Thejas Dixit Sathyanarayana
GitHub : https://github.com/Thejas12Dixit
"""

# ── Standard library imports ──────────────────────────────────────────────────
import re                        # 're' = regular expressions: used to search/match patterns in text (e.g. find "X 850.0" inside a .dat file)
import os                        # 'os' = operating system tools: used for file path operations like splitting filename from extension
import numpy as np               # 'numpy' = numerical Python: used for array math, distance calculations, coordinate arrays

# ── Matplotlib setup ──────────────────────────────────────────────────────────
import matplotlib                          # Main plotting library — used here ONLY for PDF/PNG export, not for interactive display
matplotlib.use("Agg")                      # "Agg" = non-interactive backend: renders to file (PNG/PDF) without opening a window. Must be set BEFORE importing pyplot
import matplotlib.pyplot as plt            # pyplot = the main plotting interface — creates figures, axes, plots
import matplotlib.patches as mpatches     # patches = used to create colored rectangles for the legend (e.g. blue square = PTP)
from mpl_toolkits.mplot3d import Axes3D   # Axes3D = enables 3D plotting on a matplotlib figure (imported for side-effect even if not used directly)
from matplotlib.backends.backend_pdf import PdfPages  # PdfPages = allows saving multiple matplotlib figures into one multi-page PDF file

# ── Mayavi setup (optional) ───────────────────────────────────────────────────
# We wrap the import in try/except because Mayavi is optional — if not installed, the code still works
try:
    from mayavi import mlab as _mlab      # mlab = Mayavi's scripting interface for 3D visualization (like pyplot but for 3D scenes)
    MAYAVI_AVAILABLE = True               # Flag: set to True if Mayavi loaded successfully
except ImportError:
    MAYAVI_AVAILABLE = False              # Flag: set to False if Mayavi is not installed — code falls back to matplotlib

# ── Utility imports ───────────────────────────────────────────────────────────
from dataclasses import dataclass, field  # dataclass = a decorator that auto-generates __init__, __repr__ etc. for simple data-holding classes
from typing import Optional               # Optional = type hint meaning "this value can be None or the specified type"
from datetime import datetime             # datetime = used to stamp the current date/time on exported PDF reports


# ═════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# These are simple containers (like structs) that hold parsed data.
# @dataclass automatically creates __init__ so we don't have to write it.
# ═════════════════════════════════════════════════════════════════════════════

@dataclass                    # @dataclass decorator: auto-generates __init__(self, name, x, y, z, ...) for this class
class KRLPoint:
    """Holds the Cartesian position and orientation of one robot point from the .dat file."""
    name: str                 # Point name as it appears in the .dat file, e.g. "P1", "HOME"
    x: float = 0.0            # X coordinate in mm (left-right in robot base frame)
    y: float = 0.0            # Y coordinate in mm (front-back in robot base frame)
    z: float = 0.0            # Z coordinate in mm (up-down in robot base frame)
    a: float = 0.0            # Rotation A in degrees (yaw — rotation around Z axis)
    b: float = 0.0            # Rotation B in degrees (pitch — rotation around Y axis)
    c: float = 0.0            # Rotation C in degrees (roll — rotation around X axis)


@dataclass
class KRLMotion:
    """Holds one motion command from the .src file, e.g. 'LIN P3 Vel=0.3 m/s CPDAT2'."""
    motion_type: str                    # Type of motion: "PTP", "LIN", or "CIRC"
    point_name: str                     # Name of the target point, e.g. "P3" or "HOME"
    velocity: Optional[float] = None   # Velocity value, e.g. 0.3 or 80 — None if not found
    velocity_unit: str = "%"            # Unit of velocity: "%" for PTP, "m/s" for LIN/CIRC
    aux_point: Optional[str] = None    # Only for CIRC: the intermediate via-point name
    point: Optional[KRLPoint] = None   # The actual coordinates, filled in after matching with .dat data


@dataclass
class KRLProgram:
    """Top-level container holding everything parsed from a .src + .dat file pair."""
    name: str = ""                               # Program name (taken from filename, e.g. "sample_welding")
    src_file: str = ""                           # Full path to the .src file
    dat_file: str = ""                           # Full path to the .dat file
    points: dict = field(default_factory=dict)   # Dictionary: point name (uppercase) -> KRLPoint object. field(default_factory=dict) creates a new empty dict for each instance
    motions: list = field(default_factory=list)  # Ordered list of KRLMotion objects — the robot's motion sequence
    warnings: list = field(default_factory=list) # List of warning strings for any parsing issues (e.g. point not found in .dat)


# ═════════════════════════════════════════════════════════════════════════════
# PARSER
# Reads .src and .dat files and fills a KRLProgram object with the data.
# ═════════════════════════════════════════════════════════════════════════════

class KRLParser:
    """Parses KUKA KRL .src and .dat files into structured Python objects."""

    # ── Regular expressions (regex) for finding data in the files ────────────
    # re.compile() pre-compiles the pattern for speed — it's reused many times
    # r"..." = raw string: backslashes are literal, not escape characters

    # Matches a Cartesian point declaration in the .dat file, e.g.:
    # DECL E6POS P1={X 850.0, Y -200.0, Z 1200.0, A -15.0, B 60.0, C 0.0}
    # Group 1 = point name (P1), Group 2 = X, Group 3 = Y, Group 4 = Z, Groups 5-7 = A, B, C
    _CART_RE = re.compile(
        r"DECL\s+E6POS\s+(\w+)\s*=\s*\{"       # Match "DECL E6POS P1={" — \s+ means one or more spaces, \w+ means word characters (letters/digits/_)
        r"[^}]*X\s+([-\d.]+).*?Y\s+([-\d.]+).*?Z\s+([-\d.]+)"  # Match X, Y, Z values — [-\d.]+ matches a number like -200.0 or 850
        r"(?:.*?A\s+([-\d.]+))?(?:.*?B\s+([-\d.]+))?(?:.*?C\s+([-\d.]+))?",  # Optionally match A, B, C — (?:...)? means optional non-capturing group
        re.IGNORECASE | re.DOTALL  # IGNORECASE: match regardless of upper/lowercase. DOTALL: "." also matches newlines
    )

    # Matches a PTP motion in .src, e.g.: PTP P1 Vel=80% PDAT1 Tool[1] Base[1]
    # Group 1 = point name, Group 2 = velocity number, Group 3 = unit (% or m/s)
    _PTP_RE  = re.compile(r"^\s*PTP\s+(\w+)\s+Vel\s*=\s*([\d.]+)(%|m/s)?",              re.IGNORECASE)

    # Matches a LIN motion in .src, e.g.: LIN P3 Vel=0.3 m/s CPDAT2 Tool[1] Base[1]
    _LIN_RE  = re.compile(r"^\s*LIN\s+(\w+)\s+Vel\s*=\s*([\d.]+)\s*(m/s|%)?",           re.IGNORECASE)

    # Matches a CIRC motion in .src, e.g.: CIRC P11 P12 Vel=0.2 m/s CPDAT8 ...
    # CIRC has TWO point names: Group 1 = intermediate (via) point, Group 2 = end point
    _CIRC_RE = re.compile(r"^\s*CIRC\s+(\w+)\s+(\w+)\s+Vel\s*=\s*([\d.]+)\s*(m/s|%)?", re.IGNORECASE)

    def parse(self, src_path: str, dat_path: str = None) -> KRLProgram:
        """
        Main entry point: parse a .src file (and its .dat) into a KRLProgram.
        Returns a fully populated KRLProgram object.
        """
        prog = KRLProgram()                                              # Create empty program container
        prog.src_file = src_path                                         # Store the path to the .src file
        prog.name = os.path.splitext(os.path.basename(src_path))[0]     # Extract program name: basename removes directory, splitext removes .src extension

        if dat_path is None:                                             # If no .dat path given...
            dat_path = os.path.splitext(src_path)[0] + ".dat"           # ...auto-detect it: same name, .dat extension

        if os.path.exists(dat_path):                                     # Check if the .dat file actually exists on disk
            prog.dat_file = dat_path                                     # Store the .dat path in the program
            self._parse_dat(dat_path, prog)                              # Parse the .dat file to extract point coordinates
        else:
            prog.warnings.append(f"No .dat file found at {dat_path}")   # Add warning if .dat is missing (program can still run but won't have coordinates)

        self._parse_src(src_path, prog)    # Parse the .src file to extract motion commands
        self._resolve_points(prog)         # Link each motion command to its coordinates from the .dat data
        return prog                        # Return the fully populated program

    def _parse_dat(self, path, prog):
        """Read the .dat file and extract all Cartesian point definitions into prog.points."""
        with open(path, "r", encoding="utf-8", errors="ignore") as f:  # Open file as UTF-8 text; ignore characters that can't be decoded
            content = f.read()                                          # Read entire file content as one string

        for m in self._CART_RE.finditer(content):  # finditer() scans the whole string and yields each regex match
            name = m.group(1)                       # Group 1 = point name (e.g. "P1")
            prog.points[name.upper()] = KRLPoint(  # Store in dict with UPPERCASE key for consistent lookup later
                name=name,
                x=float(m.group(2)),                # Convert matched string "850.0" to float 850.0
                y=float(m.group(3)),
                z=float(m.group(4)),
                a=float(m.group(5)) if m.group(5) else 0.0,  # A rotation — use 0.0 if not found in file
                b=float(m.group(6)) if m.group(6) else 0.0,  # B rotation — use 0.0 if not found
                c=float(m.group(7)) if m.group(7) else 0.0,  # C rotation — use 0.0 if not found
            )

    def _parse_src(self, path, prog):
        """Read the .src file line by line and extract all PTP, LIN, CIRC motion commands."""
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()          # Read all lines into a list — each element is one line including \n

        for line in lines:
            s = line.strip()               # Remove leading/trailing whitespace and newline characters
            if s.startswith(";"):          # In KRL, ";" marks a comment line — skip these entirely
                continue

            # Try CIRC first (must come before LIN/PTP because CIRC has two point names)
            m = self._CIRC_RE.match(s)     # match() only checks from the START of the string
            if m:
                prog.motions.append(KRLMotion(
                    motion_type="CIRC",
                    aux_point=m.group(1).upper(),     # Intermediate via-point for the arc (first point name)
                    point_name=m.group(2).upper(),    # End point of the arc (second point name)
                    velocity=float(m.group(3)),       # Velocity value
                    velocity_unit=m.group(4) or "m/s" # Unit — default to m/s if not captured
                ))
                continue                   # Skip to next line — don't try LIN or PTP patterns

            # Try LIN
            m = self._LIN_RE.match(s)
            if m:
                prog.motions.append(KRLMotion(
                    motion_type="LIN",
                    point_name=m.group(1).upper(),    # Target point name
                    velocity=float(m.group(2)),       # Velocity in m/s
                    velocity_unit=m.group(3) or "m/s"
                ))
                continue

            # Try PTP
            m = self._PTP_RE.match(s)
            if m:
                prog.motions.append(KRLMotion(
                    motion_type="PTP",
                    point_name=m.group(1).upper(),    # Target point name
                    velocity=float(m.group(2)),       # Velocity in % of max speed
                    velocity_unit=m.group(3) or "%"   # PTP uses % by default
                ))

    def _resolve_points(self, prog):
        """
        Link each motion command to its actual coordinates.
        After parsing .src and .dat separately, this step connects them:
        each KRLMotion.point_name is looked up in prog.points dict
        and the matching KRLPoint is assigned to KRLMotion.point.
        """
        for motion in prog.motions:                  # Loop through every parsed motion command
            key = motion.point_name.upper()          # Uppercase for consistent lookup (KRL is case-insensitive)
            if key in prog.points:                   # Check if this point name exists in the .dat data
                motion.point = prog.points[key]      # Assign the KRLPoint object directly to the motion
            else:
                prog.warnings.append(f"Point {motion.point_name} not found in .dat")  # Warn if point is in .src but missing from .dat


# ═════════════════════════════════════════════════════════════════════════════
# COLOR SCHEMES
# Two separate color sets: hex strings for matplotlib, RGB tuples for Mayavi
# ═════════════════════════════════════════════════════════════════════════════

# Matplotlib uses hex color strings like "#4A90D9" (same as CSS/HTML colors)
MOTION_COLORS = {"PTP": "#4A90D9", "LIN": "#27AE60", "CIRC": "#E67E22"}  # Blue=PTP, Green=LIN, Orange=CIRC
WELD_COLOR    = "#E74C3C"   # Red: marks process/weld points where the robot performs an action
START_COLOR   = "#9B59B6"   # Purple: marks HOME position and start/end points

# Mayavi uses RGB tuples with values between 0.0 and 1.0 (not 0-255)
MAYAVI_COLORS = {"PTP": (0.29, 0.56, 0.85), "LIN": (0.15, 0.68, 0.38), "CIRC": (0.90, 0.50, 0.13)}
MAYAVI_WELD   = (0.91, 0.30, 0.24)   # Red for weld/process points
MAYAVI_HOME   = (0.61, 0.35, 0.71)   # Purple for HOME position
MAYAVI_TEXT   = (1.0,  1.0,  1.0)    # White for all text labels in the 3D scene


# ═════════════════════════════════════════════════════════════════════════════
# VISUALIZER
# Takes a parsed KRLProgram and renders or exports the robot path.
# ═════════════════════════════════════════════════════════════════════════════

class KRLVisualizer:
    """
    Generates 3D visualizations and reports from a parsed KRLProgram.

    Use plot_3d_mayavi() for interactive viewing.
    Use export_pdf() / export_png() for documentation.
    """

    def __init__(self, program: KRLProgram):
        self.prog = program   # Store the parsed program so all methods can access it

    def _get_path_segments(self):
        """
        Build a list of consecutive motion segments for drawing lines between points.
        Returns: list of (motion, point_from, point_to) tuples
        Each tuple represents one line segment in the robot path.
        """
        resolved = [m for m in self.prog.motions if m.point is not None]  # Filter: only motions that have coordinates
        return [
            (resolved[i], resolved[i-1].point, resolved[i].point)         # Tuple: (motion object, start KRLPoint, end KRLPoint)
            for i in range(1, len(resolved))                               # Start from index 1 so we always have a previous point
            if resolved[i-1].point and resolved[i].point                   # Extra safety check: both points must exist
        ]

    def _all_coords(self):
        """
        Return all resolved point coordinates as a numpy array of shape (N, 3).
        Used for calculating workspace envelope (min/max X, Y, Z ranges).
        """
        pts = [m.point for m in self.prog.motions if m.point]                    # List of KRLPoint objects
        return np.array([[p.x, p.y, p.z] for p in pts]) if pts else np.zeros((1, 3))  # Convert to numpy array; return zeros if no points


    # ─────────────────────────────────────────────────────────────────────────
    # MAYAVI INTERACTIVE VIEWER
    # Opens a full 3D scene with tubes, spheres, labels and a dark background.
    # Requires: pip install mayavi PyQt5
    # ─────────────────────────────────────────────────────────────────────────

    def plot_3d_mayavi(self, title: str = None):
        """
        Open an interactive Mayavi 3D window showing the robot path.
        Controls: left-drag = rotate | scroll = zoom | right-drag = pan
        """
        if not MAYAVI_AVAILABLE:               # Check if Mayavi was successfully imported at the top of this file
            print(
                "\n[ERROR] Mayavi is not installed.\n"
                "Install with:  pip install mayavi PyQt5\n"
                "Tip: use export_pdf() or export_png() for non-interactive output.\n"
            )
            return                             # Exit the function early — nothing more to do without Mayavi

        resolved = [m for m in self.prog.motions if m.point is not None]  # Get only motions with valid coordinates
        if not resolved:                       # If no points found (empty or all unresolved), warn and exit
            print("[WARNING] No resolved points to visualize.")
            return

        fig_title = title or f"KUKA Path - {self.prog.name}"  # Use provided title or auto-generate from program name

        # Create the Mayavi 3D scene window
        _mlab.figure(
            figure=fig_title,          # Window title bar text
            bgcolor=(0.12, 0.14, 0.18),  # Background color: dark blue-grey (R, G, B values 0.0-1.0)
            fgcolor=(0.9,  0.9,  0.9),   # Foreground color: light grey — used for axes, text, etc.
            size=(1100, 750),            # Window size in pixels (width, height)
        )

        # Draw each path segment as a 3D tube colored by motion type
        for motion, pt_from, pt_to in self._get_path_segments():
            col = MAYAVI_COLORS.get(motion.motion_type, (0.6, 0.6, 0.6))  # Get color for this motion type; grey as fallback
            _mlab.plot3d(
                [pt_from.x, pt_to.x],   # X coordinates of start and end point (list of 2 values)
                [pt_from.y, pt_to.y],   # Y coordinates
                [pt_from.z, pt_to.z],   # Z coordinates
                color=col,              # Tube color (RGB tuple)
                tube_radius=5,          # Thickness of the tube in mm (scene units)
                tube_sides=12,          # Number of polygon sides on the tube — higher = smoother cylinder
                opacity=0.95,           # Transparency: 1.0 = fully opaque, 0.0 = invisible
            )

        # Draw a sphere and label at each point
        for motion in resolved:
            pt      = motion.point                          # Get the KRLPoint with coordinates
            is_home = "HOME" in motion.point_name          # Check if this is the HOME position
            col     = MAYAVI_HOME if is_home else MAYAVI_WELD  # Purple for HOME, red for process points
            scale   = 30 if is_home else 20                # HOME sphere slightly larger than regular points

            _mlab.points3d(
                pt.x, pt.y, pt.z,      # Position of the sphere in 3D space
                color=col,             # Sphere color
                scale_factor=scale,    # Diameter of the sphere in scene units (mm)
                resolution=20,         # Number of polygon segments — higher = smoother sphere
                opacity=1.0,           # Fully opaque
            )
            _mlab.text3d(
                pt.x, pt.y, pt.z + 25,  # Position: same X,Y as point but 25mm above in Z
                motion.point_name,       # Text to display (e.g. "P3", "HOME")
                color=MAYAVI_TEXT,       # White text
                scale=14,                # Text size in scene units
            )

        # Add coordinate axes, orientation cube, and title
        _mlab.axes(
            xlabel="X (mm)", ylabel="Y (mm)", zlabel="Z (mm)",  # Axis labels
            color=(0.65, 0.65, 0.65),  # Axis line color: medium grey
            line_width=1.0,            # Thickness of axis lines
        )
        _mlab.orientation_axes()       # Adds a small XYZ orientation cube in the corner — helps understand camera rotation
        _mlab.title(fig_title, size=0.25, color=(0.9, 0.9, 0.9), height=0.95)  # Title text at top of window

        # Add legend as text overlaid on the 3D scene (bottom-left area)
        legend = [
            ("PTP  - Point-to-point (joint)",  MAYAVI_COLORS["PTP"]),   # Joint-interpolated, fastest motion
            ("LIN  - Linear Cartesian",         MAYAVI_COLORS["LIN"]),   # Straight line in Cartesian space
            ("CIRC - Circular arc",             MAYAVI_COLORS["CIRC"]),  # Arc motion through a via-point
            ("  Process / weld point",           MAYAVI_WELD),            # Where the robot performs an action
            ("  HOME / start",                  MAYAVI_HOME),             # Home/start/end position
        ]
        for idx, (label, col) in enumerate(legend):
            _mlab.text(
                0.02,                      # X position in normalized screen coords (0=left, 1=right)
                0.04 + idx * 0.05,         # Y position — stacked upward with 5% gap between items
                label,                     # Text string to display
                color=col,                 # Color matching the path segment color
                width=0.28,                # Text width as fraction of screen width
            )

        _mlab.view(azimuth=-60, elevation=35, distance="auto")  # Set initial camera angle: azimuth=horizontal rotation, elevation=vertical angle, distance=auto-fit

        print(f"\n[Mayavi] {fig_title}")
        print("  Rotate: left-drag  |  Zoom: scroll  |  Pan: right-drag")
        print("  Close the window to continue.\n")
        _mlab.show()   # Open the window and block until user closes it


    # ─────────────────────────────────────────────────────────────────────────
    # MATPLOTLIB 3D (internal — used only for PDF/PNG export)
    # Simpler than Mayavi but works without any extra install.
    # ─────────────────────────────────────────────────────────────────────────

    def plot_3d(self, ax=None, title: str = None):
        """
        Draw robot path on a matplotlib 3D axes object.
        Used internally by export_pdf() and export_png() — not for interactive use.
        If ax is None, creates a new figure. Otherwise draws into the provided axes.
        """
        if ax is None:                                    # If no axes object was passed in...
            fig = plt.figure(figsize=(12, 8))             # ...create a new figure (12 inches wide, 8 tall)
            ax  = fig.add_subplot(111, projection="3d")   # Add a 3D subplot: 111 = 1 row, 1 col, subplot 1
        else:
            fig = ax.get_figure()                         # If axes was provided, get its parent figure

        # Draw lines between consecutive points, colored by motion type
        for motion, pt_from, pt_to in self._get_path_segments():
            color = MOTION_COLORS.get(motion.motion_type, "#999999")  # Get hex color; grey fallback
            ax.plot(
                [pt_from.x, pt_to.x],   # List of X values for start and end of segment
                [pt_from.y, pt_to.y],   # List of Y values
                [pt_from.z, pt_to.z],   # List of Z values
                color=color,
                linewidth=2,            # Line thickness in points
                alpha=0.85,             # Slight transparency to see overlapping paths
            )

        # Draw scatter dots and text labels at each point
        for motion in [m for m in self.prog.motions if m.point]:
            pt = motion.point
            c  = START_COLOR if "HOME" in motion.point_name else WELD_COLOR  # Purple for HOME, red for others
            s  = 80 if "HOME" in motion.point_name else 50                   # HOME dot slightly larger
            ax.scatter(pt.x, pt.y, pt.z, color=c, s=s, zorder=5, alpha=0.9) # zorder=5 draws dots on top of lines
            ax.text(pt.x, pt.y, pt.z + 15, motion.point_name,               # Label 15mm above the point
                    fontsize=7, color="#333333", ha="center", va="bottom")

        ax.set_xlabel("X (mm)", fontsize=9)   # Axis labels with units
        ax.set_ylabel("Y (mm)", fontsize=9)
        ax.set_zlabel("Z (mm)", fontsize=9)
        ax.set_title(title or f"Robot path - {self.prog.name}", fontsize=11, fontweight="bold")
        ax.tick_params(labelsize=7)           # Reduce tick label size to avoid clutter

        # Legend: colored patches explaining what each color means
        ax.legend(handles=[
            mpatches.Patch(color=MOTION_COLORS["PTP"],  label="PTP - Point-to-point"),
            mpatches.Patch(color=MOTION_COLORS["LIN"],  label="LIN - Linear"),
            mpatches.Patch(color=MOTION_COLORS["CIRC"], label="CIRC - Circular"),
            mpatches.Patch(color=WELD_COLOR,            label="Process point"),
            mpatches.Patch(color=START_COLOR,           label="HOME / Start"),
        ], loc="upper left", fontsize=8)

        ax.view_init(elev=25, azim=-60)  # Set default viewing angle: elev=degrees above horizontal, azim=horizontal rotation

        return fig, ax   # Return both so the caller can save or modify the figure


    # ─────────────────────────────────────────────────────────────────────────
    # STATISTICS
    # ─────────────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """
        Calculate and return program statistics as a dictionary.
        Includes motion counts, total path distance, workspace envelope, velocity range.
        """
        resolved = [m for m in self.prog.motions if m.point]    # Only count motions with valid coordinates
        counts = {"PTP": 0, "LIN": 0, "CIRC": 0}               # Counter dict for each motion type
        total_dist, min_vel, max_vel = 0.0, float("inf"), 0.0   # float("inf") = positive infinity, used as initial "min" value

        for motion, pt_from, pt_to in self._get_path_segments():
            counts[motion.motion_type] = counts.get(motion.motion_type, 0) + 1  # Increment counter for this motion type

            # Calculate Euclidean (straight-line) distance between the two points using Pythagorean theorem in 3D
            total_dist += float(np.sqrt(
                (pt_to.x - pt_from.x)**2 +   # Squared X difference
                (pt_to.y - pt_from.y)**2 +   # Squared Y difference
                (pt_to.z - pt_from.z)**2      # Squared Z difference
            ))                                # sqrt of sum = 3D distance in mm

            # Track velocity range — only for LIN/CIRC (which use m/s), not PTP (which uses %)
            if motion.velocity and motion.velocity_unit == "m/s":
                v = motion.velocity * 1000    # Convert m/s to mm/s for consistency with distance (mm)
                min_vel = min(min_vel, v)     # Keep track of slowest move
                max_vel = max(max_vel, v)     # Keep track of fastest move

        c = self._all_coords()   # Get all coordinates as numpy array for min/max calculations
        return {
            "program_name":     self.prog.name,
            "total_points":     len(resolved),                                          # How many points had valid coordinates
            "ptp_moves":        counts["PTP"],
            "lin_moves":        counts["LIN"],
            "circ_moves":       counts["CIRC"],
            "total_distance":   round(total_dist, 1),                                   # Round to 1 decimal place (mm)
            "x_range":          (round(float(c[:, 0].min()), 1), round(float(c[:, 0].max()), 1)),  # c[:,0] = all X values; min/max gives workspace extent
            "y_range":          (round(float(c[:, 1].min()), 1), round(float(c[:, 1].max()), 1)),
            "z_range":          (round(float(c[:, 2].min()), 1), round(float(c[:, 2].max()), 1)),
            "min_velocity_mms": round(min_vel, 1) if min_vel != float("inf") else "N/A",  # "N/A" if no LIN/CIRC found
            "max_velocity_mms": round(max_vel, 1) if max_vel > 0 else "N/A",
            "mayavi_available": MAYAVI_AVAILABLE,   # Tells the caller whether Mayavi is installed
            "warnings":         self.prog.warnings,  # Pass through any parsing warnings
        }


    # ─────────────────────────────────────────────────────────────────────────
    # PDF EXPORT (matplotlib only — no display needed)
    # Generates a 2-page A4 landscape PDF report
    # ─────────────────────────────────────────────────────────────────────────

    def export_pdf(self, output_path: str = None) -> str:
        """Save a 2-page PDF report: Page 1 = 3D path + stats panel, Page 2 = motion table."""
        if output_path is None:
            output_path = f"{self.prog.name}_path_report.pdf"  # Default filename if none given

        stats = self.get_stats()   # Calculate all stats once, reuse below

        with PdfPages(output_path) as pdf:   # PdfPages context manager: all figures saved inside become pages

            # ── PAGE 1: 3D path plot + statistics panel ──────────────────────
            fig = plt.figure(figsize=(11.69, 8.27))   # A4 landscape in inches (297mm x 210mm)
            fig.patch.set_facecolor("#F8F9FA")         # Set figure background to very light grey

            # Header text — placed using figure coordinates (0.0=left/bottom, 1.0=right/top)
            fig.text(0.05, 0.94, "KUKA Robot Path Visualizer",
                     fontsize=18, fontweight="bold", color="#2C3E50")
            fig.text(0.05, 0.90,
                     f"Program: {self.prog.name}  |  "
                     f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
                     f"Author: Thejas Dixit Sathyanarayana",
                     fontsize=9, color="#7F8C8D")

            # Thin horizontal rule under the header (using a tiny axes with axhline)
            la = fig.add_axes([0.05, 0.88, 0.90, 0.001])  # [left, bottom, width, height] in figure coordinates
            la.axhline(y=0, color="#BDC3C7", linewidth=0.8)  # Draw horizontal line at y=0
            la.axis("off")                                    # Hide the axes frame and ticks

            # 3D plot — takes up left 60% of the page
            ax3d = fig.add_axes([0.05, 0.12, 0.58, 0.72], projection="3d")  # [left, bottom, width, height]
            self.plot_3d(ax=ax3d, title="3D Robot Path")                      # Draw into this axes

            # Stats panel — positioned on right side of page
            sx, sy, lh = 0.67, 0.85, 0.052   # sx=x start, sy=y start, lh=line height (spacing between lines)

            def sl(label, value, y):
                """Helper: write a label-value pair at position (sx, y) on the figure."""
                fig.text(sx,        y, label,      fontsize=9, color="#7F8C8D")  # Grey label on left
                fig.text(sx + 0.17, y, str(value), fontsize=9, color="#2C3E50")  # Dark value on right

            fig.text(sx, sy, "Program Statistics", fontsize=11, fontweight="bold", color="#2C3E50")
            sl("Program",        stats["program_name"],           sy - lh * 1)   # Each sl() call steps down by lh
            sl("Total points",   stats["total_points"],           sy - lh * 2)
            sl("PTP moves",      stats["ptp_moves"],              sy - lh * 3)
            sl("LIN moves",      stats["lin_moves"],              sy - lh * 4)
            sl("CIRC moves",     stats["circ_moves"],             sy - lh * 5)
            sl("Total distance", f"{stats['total_distance']} mm", sy - lh * 6)

            fig.text(sx, sy - lh * 7.5, "Workspace Envelope", fontsize=10, fontweight="bold", color="#2C3E50")
            sl("X range", f"{stats['x_range'][0]} -> {stats['x_range'][1]} mm", sy - lh * 8.5)
            sl("Y range", f"{stats['y_range'][0]} -> {stats['y_range'][1]} mm", sy - lh * 9.5)
            sl("Z range", f"{stats['z_range'][0]} -> {stats['z_range'][1]} mm", sy - lh * 10.5)

            fig.text(sx, sy - lh * 12, "Velocity", fontsize=10, fontweight="bold", color="#2C3E50")
            sl("Min (LIN/CIRC)", f"{stats['min_velocity_mms']} mm/s", sy - lh * 13)
            sl("Max (LIN/CIRC)", f"{stats['max_velocity_mms']} mm/s", sy - lh * 14)

            fig.text(0.5, 0.03, "Generated by KUKA KRL Path Visualizer · github.com/Thejas12Dixit",
                     fontsize=8, color="#BDC3C7", ha="center")  # Footer centered at bottom

            pdf.savefig(fig, bbox_inches="tight")   # Save this figure as PDF page 1; bbox_inches="tight" removes excess whitespace
            plt.close(fig)                          # Free memory — important when generating many figures

            # ── PAGE 2: Motion sequence table ────────────────────────────────
            fig2, ax2 = plt.subplots(figsize=(11.69, 8.27))   # New A4 landscape figure
            fig2.patch.set_facecolor("#F8F9FA")
            ax2.axis("off")   # Hide the axes — we only want the table, no plot frame

            fig2.text(0.05, 0.95, "Motion Sequence Table", fontsize=14, fontweight="bold", color="#2C3E50")
            fig2.text(0.05, 0.91,
                      f"Program: {self.prog.name}  |  "
                      f"{len([m for m in self.prog.motions if m.point])} resolved points",
                      fontsize=9, color="#7F8C8D")

            la2 = fig2.add_axes([0.05, 0.89, 0.90, 0.001])
            la2.axhline(y=0, color="#BDC3C7", linewidth=0.8)
            la2.axis("off")

            # Build table rows — one row per motion that has valid coordinates
            rows = []
            for i, motion in enumerate(self.prog.motions):
                if not motion.point:    # Skip motions without coordinates (unresolved)
                    continue
                pt = motion.point
                vel_str = f"{motion.velocity} {motion.velocity_unit}" if motion.velocity else "-"
                rows.append([
                    str(i+1),              # Row number (1-based)
                    motion.motion_type,    # PTP / LIN / CIRC
                    motion.point_name,     # e.g. P3
                    f"{pt.x:.1f}",         # X coordinate formatted to 1 decimal
                    f"{pt.y:.1f}",
                    f"{pt.z:.1f}",
                    vel_str,               # e.g. "0.3 m/s" or "80 %"
                ])

            headers = ["#", "Type", "Point", "X (mm)", "Y (mm)", "Z (mm)", "Velocity"]
            table = ax2.table(
                cellText=rows,           # The data rows
                colLabels=headers,       # Column header row
                cellLoc="center",        # Center text in each cell
                loc="upper center",      # Table position within axes
                bbox=[0.0, 0.05, 1.0, 0.82],  # [left, bottom, width, height] in axes coordinates
            )
            table.auto_set_font_size(False)  # Disable auto font sizing so our set_fontsize() takes effect
            table.set_fontsize(9)

            # Style the header row (row index 0) with dark background + white text
            for j in range(len(headers)):
                c = table[0, j]                          # table[row, col] accesses a single cell
                c.set_facecolor("#2C3E50")               # Dark blue-grey header background
                c.set_text_props(color="white", fontweight="bold")

            # Style data rows: alternate light blue and white for readability
            for i in range(1, len(rows) + 1):
                for j in range(len(headers)):
                    cell = table[i, j]
                    cell.set_facecolor("#EAF0FB" if i % 2 == 0 else "white")  # i%2==0 = even rows get light blue
                    if j == 1:  # Column index 1 = "Type" column — color by motion type
                        cell.set_facecolor(MOTION_COLORS.get(rows[i-1][1], "#FFFFFF") + "44")  # "44" appended = 27% opacity hex alpha

            fig2.text(0.5, 0.03, "Generated by KUKA KRL Path Visualizer · github.com/Thejas12Dixit",
                      fontsize=8, color="#BDC3C7", ha="center")

            pdf.savefig(fig2, bbox_inches="tight")   # Save as page 2
            plt.close(fig2)

        return output_path   # Return the path so the caller knows where the file was saved


    # ─────────────────────────────────────────────────────────────────────────
    # PNG EXPORT
    # ─────────────────────────────────────────────────────────────────────────

    def export_png(self, output_path: str = None) -> str:
        """Save a single PNG image of the 3D robot path. Good for README and LinkedIn posts."""
        if output_path is None:
            output_path = f"{self.prog.name}_path.png"   # Default filename

        fig, ax = self.plot_3d()   # Generate the matplotlib 3D plot (returns figure and axes)
        fig.savefig(
            output_path,
            dpi=150,               # Resolution: 150 dots per inch — good balance of quality and file size
            bbox_inches="tight",   # Crop whitespace around the figure
            facecolor="#F8F9FA",   # Background color (same light grey as PDF)
        )
        plt.close(fig)             # Free memory after saving
        return output_path
