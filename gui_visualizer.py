"""
gui_visualizer.py
=================
Version 2 — Graphical User Interface (GUI) built with Tkinter.

This gives you a proper desktop app with:
  - A file browser to load .src / .dat files
  - A statistics panel on the left
  - An interactive 3D plot on the right
  - Buttons to export PDF and PNG

Run:  python gui_visualizer.py

No command line arguments needed — everything is done via the GUI.
Tkinter is built into Python — no extra install required for the GUI itself.
"""

# ── Standard library ──────────────────────────────────────────────────────────
import tkinter as tk                                      # tkinter = Python's built-in GUI toolkit. 'tk' is the alias we'll use to access it
from tkinter import ttk, filedialog, messagebox           # ttk = themed widgets (nicer looking than plain tk). filedialog = file open/save dialogs. messagebox = popup alert windows
import os                                                 # os = for file path operations (checking if .dat exists next to .src)

# ── Matplotlib with Tkinter backend ──────────────────────────────────────────
import matplotlib                                         # Main plotting library
matplotlib.use("TkAgg")                                   # "TkAgg" backend: renders matplotlib plots inside a Tkinter window. Must be set BEFORE importing pyplot
import matplotlib.pyplot as plt                           # pyplot = plotting interface
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,       # FigureCanvasTkAgg: embeds a matplotlib Figure as a widget inside a Tkinter frame
    NavigationToolbar2Tk,    # NavigationToolbar2Tk: the standard matplotlib toolbar (zoom, pan, save buttons) adapted for Tkinter
)
from mpl_toolkits.mplot3d import Axes3D                   # Enables 3D plotting (imported for side-effect)

# ── Our own parser — must be in the same folder ───────────────────────────────
from krl_parser import KRLParser, KRLVisualizer           # Import the parser and visualizer we built in krl_parser.py


# ═════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION CLASS
# Inherits from tk.Tk — so this class IS the main window
# ═════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    """
    Main application window.
    Inheriting tk.Tk means this class IS the root window — no separate root needed.
    """

    def __init__(self):
        super().__init__()                         # Call tk.Tk.__init__() to initialize the window properly

        # ── Window setup ──────────────────────────────────────────────────────
        self.title("KUKA KRL Path Visualizer")     # Text shown in the title bar
        self.geometry("1200x750")                  # Initial window size: 1200 pixels wide x 750 tall
        self.configure(bg="#F0F2F5")               # Window background color (light grey)
        self.resizable(True, True)                 # Allow user to resize the window in both directions

        # ── State variables ───────────────────────────────────────────────────
        self.prog = None   # Will hold the KRLProgram object after parsing. None = nothing loaded yet
        self.vis  = None   # Will hold the KRLVisualizer object. None = nothing loaded yet

        # ── Build all UI widgets ──────────────────────────────────────────────
        self._build_ui()   # Calls the method below that creates all buttons, labels, panels etc.


    # ─────────────────────────────────────────────────────────────────────────
    # UI LAYOUT
    # Builds all the visual elements of the application window
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        """Create and arrange all widgets in the window."""

        # ── LEFT PANEL (dark sidebar) ─────────────────────────────────────────
        # This panel contains the file inputs, stats display, and export buttons
        left = tk.Frame(self, bg="#2C3E50", width=280)   # Frame = invisible container. Dark blue-grey background, fixed 280px wide
        left.pack(side="left", fill="y")                 # pack = layout manager. side="left" = attach to left edge. fill="y" = stretch vertically to fill window height
        left.pack_propagate(False)                        # Prevent the frame from shrinking to fit its children — keeps width=280 fixed

        # App title label at top of sidebar
        tk.Label(
            left,
            text="KUKA KRL\nPath Visualizer",   # \n = newline, splits into two lines
            bg="#2C3E50", fg="white",            # bg = background color, fg = foreground (text) color
            font=("Helvetica", 14, "bold"),      # Font: family, size, weight
            pady=20,                             # Vertical internal padding (space above and below text)
        ).pack(fill="x")                         # fill="x" = stretch to full width of parent

        # Thin horizontal divider line
        tk.Frame(left, bg="#3D5166", height=1).pack(fill="x", padx=20)  # 1px tall frame = divider line. padx=20 = 20px margin on left and right

        # ── File input section ────────────────────────────────────────────────

        # Label above the .src input
        tk.Label(
            left, text="KRL .src file",
            bg="#2C3E50", fg="#BDC3C7",          # Slightly lighter grey text for secondary labels
            font=("Helvetica", 9),
        ).pack(anchor="w", padx=20, pady=(16, 2))   # anchor="w" = align text to west (left). pady=(top, bottom) padding

        # Row containing the .src path entry box + browse button side by side
        src_frame = tk.Frame(left, bg="#2C3E50")   # Container frame for the row
        src_frame.pack(fill="x", padx=20)

        self.src_var = tk.StringVar()              # StringVar = a tkinter variable that can be linked to a widget. When user types, self.src_var.get() returns the current text
        tk.Entry(
            src_frame,
            textvariable=self.src_var,             # Link the entry box to self.src_var so we can read its value
            font=("Helvetica", 9),
            width=18,                              # Width in characters
        ).pack(side="left", fill="x", expand=True) # expand=True = take up all remaining horizontal space

        tk.Button(
            src_frame,
            text="…",                              # "…" = ellipsis — standard convention for "open file dialog"
            command=self._browse_src,              # command = function called when button is clicked
            bg="#3D5166", fg="white",
            relief="flat",                         # relief="flat" = no 3D border effect (modern flat style)
            padx=6,                                # Internal horizontal padding inside button
        ).pack(side="right")

        # Same pattern for the optional .dat file input
        tk.Label(
            left, text=".dat file (optional)",
            bg="#2C3E50", fg="#BDC3C7",
            font=("Helvetica", 9),
        ).pack(anchor="w", padx=20, pady=(10, 2))

        dat_frame = tk.Frame(left, bg="#2C3E50")
        dat_frame.pack(fill="x", padx=20)

        self.dat_var = tk.StringVar()              # Separate StringVar for the .dat path
        tk.Entry(
            dat_frame,
            textvariable=self.dat_var,
            font=("Helvetica", 9),
            width=18,
        ).pack(side="left", fill="x", expand=True)

        tk.Button(
            dat_frame,
            text="…",
            command=self._browse_dat,
            bg="#3D5166", fg="white",
            relief="flat", padx=6,
        ).pack(side="right")

        # ── Load & Visualize button ───────────────────────────────────────────
        tk.Button(
            left,
            text="▶  Load & Visualize",
            command=self._load,                    # Calls _load() when clicked — parses files and draws plot
            bg="#27AE60", fg="white",              # Green background — draws attention as the primary action
            font=("Helvetica", 10, "bold"),
            relief="flat",
            pady=10,                               # Extra vertical padding to make the button taller
            cursor="hand2",                        # Changes mouse cursor to a hand pointer when hovering
        ).pack(fill="x", padx=20, pady=16)

        # Divider
        tk.Frame(left, bg="#3D5166", height=1).pack(fill="x", padx=20)

        # ── Statistics display ────────────────────────────────────────────────
        tk.Label(
            left, text="Statistics",
            bg="#2C3E50", fg="#BDC3C7",
            font=("Helvetica", 9, "bold"),
        ).pack(anchor="w", padx=20, pady=(12, 4))

        # Text widget to display the stats — like a read-only text area
        self.stats_text = tk.Text(
            left,
            bg="#1A252F", fg="#ECF0F1",            # Very dark background, near-white text — like a terminal
            font=("Courier", 8),                   # Courier = monospace font so values line up in columns
            relief="flat",
            padx=8, pady=8,                        # Internal padding inside the text area
            state="disabled",                      # "disabled" = read-only. Users can't type in it. We enable/disable it programmatically when updating
            height=14,                             # Height in lines of text
        )
        self.stats_text.pack(fill="x", padx=20)

        # ── Export buttons ────────────────────────────────────────────────────
        tk.Frame(left, bg="#3D5166", height=1).pack(fill="x", padx=20, pady=12)

        tk.Button(
            left,
            text="⬇  Export PDF report",
            command=self._export_pdf,              # Opens save dialog then calls vis.export_pdf()
            bg="#2980B9", fg="white",              # Blue button
            font=("Helvetica", 9),
            relief="flat", pady=7,
            cursor="hand2",
        ).pack(fill="x", padx=20, pady=2)

        tk.Button(
            left,
            text="⬇  Export PNG image",
            command=self._export_png,              # Opens save dialog then calls vis.export_png()
            bg="#8E44AD", fg="white",              # Purple button
            font=("Helvetica", 9),
            relief="flat", pady=7,
            cursor="hand2",
        ).pack(fill="x", padx=20, pady=2)

        # Footer credit at very bottom of sidebar
        tk.Label(
            left,
            text="github.com/Thejas12Dixit",
            bg="#2C3E50", fg="#566573",            # Darker, subtle grey — not important info
            font=("Helvetica", 8),
        ).pack(side="bottom", pady=10)             # side="bottom" = stick to bottom of sidebar


        # ── RIGHT PANEL (plot area) ───────────────────────────────────────────
        right = tk.Frame(self, bg="#F0F2F5")       # Light grey frame, takes up remaining space
        right.pack(side="right", fill="both", expand=True)  # fill="both" + expand=True = fill all remaining space

        # Create a matplotlib Figure and embed it inside the Tkinter frame
        self.fig = plt.Figure(figsize=(9, 6), facecolor="#F8F9FA")  # matplotlib Figure object (not a window, just a figure)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)     # Wrap the figure as a Tkinter widget. master=right = place it inside the right panel
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)  # get_tk_widget() returns the actual Tkinter widget; pack it to fill the space

        # Add the matplotlib navigation toolbar (zoom, pan, save buttons) below the plot
        toolbar_frame = tk.Frame(right, bg="#F0F2F5")   # Separate frame for the toolbar
        toolbar_frame.pack(fill="x", padx=10)
        NavigationToolbar2Tk(self.canvas, toolbar_frame)  # Attach toolbar to our canvas, place it in toolbar_frame

        # Show placeholder text before any file is loaded
        self._draw_placeholder()


    # ─────────────────────────────────────────────────────────────────────────
    # ACTION METHODS
    # These are called when buttons are clicked
    # ─────────────────────────────────────────────────────────────────────────

    def _browse_src(self):
        """Open a file dialog to select the .src file. Auto-fills .dat path if found."""
        path = filedialog.askopenfilename(
            filetypes=[("KRL source", "*.src"), ("All files", "*.*")]  # Filter: show .src files first
        )
        if path:                                           # If user selected a file (didn't cancel)
            self.src_var.set(path)                         # Put the selected path into the .src entry box
            dat = os.path.splitext(path)[0] + ".dat"      # Build the expected .dat path (same name, different extension)
            if os.path.exists(dat):                        # Check if the .dat file actually exists
                self.dat_var.set(dat)                      # Auto-fill the .dat entry box if found

    def _browse_dat(self):
        """Open a file dialog to manually select the .dat file."""
        path = filedialog.askopenfilename(
            filetypes=[("KRL data", "*.dat"), ("All files", "*.*")]
        )
        if path:
            self.dat_var.set(path)                         # Put selected path into the .dat entry box

    def _load(self):
        """Parse the selected KRL files and update the 3D plot and stats panel."""
        src = self.src_var.get()           # Read current value from the .src entry box
        dat = self.dat_var.get() or None   # Read .dat entry box; convert empty string to None (parser handles None = auto-detect)

        if not src:                        # If no file was selected yet
            messagebox.showwarning("No file", "Please select a .src file first.")
            return                         # Exit the function — nothing to parse

        try:
            parser    = KRLParser()                    # Create a fresh parser instance
            self.prog = parser.parse(src, dat)         # Parse the .src (and .dat) files into a KRLProgram object
            self.vis  = KRLVisualizer(self.prog)       # Create visualizer from the parsed program
            self._update_stats()                       # Refresh the statistics panel on the left
            self._draw_3d()                            # Draw the 3D path in the right panel
        except Exception as e:
            messagebox.showerror("Parse error", str(e))  # Show error popup if anything goes wrong (bad file format, etc.)

    def _update_stats(self):
        """Recalculate and display statistics in the stats text area."""
        stats = self.vis.get_stats()   # Get dict of stats from the visualizer

        # Build list of text lines to display
        lines = [
            f"Program : {stats['program_name']}",
            f"Points  : {stats['total_points']}",
            f"PTP     : {stats['ptp_moves']}",
            f"LIN     : {stats['lin_moves']}",
            f"CIRC    : {stats['circ_moves']}",
            f"Dist    : {stats['total_distance']} mm",
            f"",                                        # Empty line as separator
            f"X  {stats['x_range'][0]}→{stats['x_range'][1]}",
            f"Y  {stats['y_range'][0]}→{stats['y_range'][1]}",
            f"Z  {stats['z_range'][0]}→{stats['z_range'][1]}",
        ]
        if stats["warnings"]:                          # If there were any parsing warnings
            lines += ["", "⚠ Warnings:"] + [f"  {w}" for w in stats["warnings"]]  # Append warning lines

        # Update the Text widget:
        self.stats_text.configure(state="normal")      # Temporarily enable editing so we can insert text
        self.stats_text.delete("1.0", "end")           # Clear existing text. "1.0" = line 1, char 0 (start). "end" = end of text
        self.stats_text.insert("end", "\n".join(lines))  # Insert all lines joined by newlines
        self.stats_text.configure(state="disabled")    # Set back to read-only

    def _draw_3d(self):
        """Clear the canvas and redraw the 3D path plot for the currently loaded program."""
        self.fig.clear()                               # Remove everything from the figure
        ax = self.fig.add_subplot(111, projection="3d")  # Add a fresh 3D subplot
        self.vis.plot_3d(ax=ax)                        # Draw the robot path into this subplot
        self.canvas.draw()                             # Tell Tkinter to repaint the canvas with the new figure content

    def _draw_placeholder(self):
        """Show a message before any file is loaded."""
        self.fig.clear()
        ax = self.fig.add_subplot(111)                 # Regular 2D axes (just for showing text)
        ax.text(
            0.5, 0.5,                                  # Position: center of axes (0=left/bottom, 1=right/top in axes coordinates)
            "Load a KRL .src file to visualize the robot path",
            ha="center", va="center",                  # ha = horizontal alignment, va = vertical alignment
            fontsize=12, color="#95A5A6",              # Grey text — subtle placeholder
            transform=ax.transAxes,                    # transAxes = coordinates are relative to axes (0-1), not data values
        )
        ax.axis("off")                                 # Hide the axes frame, ticks, and labels
        self.canvas.draw()                             # Repaint canvas

    def _export_pdf(self):
        """Open a save dialog and export the current program as a PDF report."""
        if not self.vis:                               # Check if a program has been loaded yet
            messagebox.showwarning("No data", "Load a KRL file first.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",                   # Automatically append .pdf if user doesn't type it
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"{self.prog.name}_report.pdf" # Suggest a default filename based on program name
        )
        if path:                                       # If user confirmed the save (didn't cancel)
            self.vis.export_pdf(path)                  # Generate and save the PDF
            messagebox.showinfo("Exported", f"PDF saved:\n{path}")  # Confirm with a popup

    def _export_png(self):
        """Open a save dialog and export the current program path as a PNG image."""
        if not self.vis:
            messagebox.showwarning("No data", "Load a KRL file first.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            initialfile=f"{self.prog.name}_path.png"
        )
        if path:
            self.vis.export_png(path)
            messagebox.showinfo("Exported", f"PNG saved:\n{path}")


# ── Entry point ───────────────────────────────────────────────────────────────
# Only runs when this script is executed directly (python gui_visualizer.py)
# Does NOT run if this file is imported as a module
if __name__ == "__main__":
    app = App()       # Create the App instance — this builds the entire window
    app.mainloop()    # Start the Tkinter event loop — keeps the window open and responds to clicks/keypresses until window is closed
