"""
gui_visualizer.py
=================
Tkinter GUI — Version 2.
Run:  python gui_visualizer.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from mpl_toolkits.mplot3d import Axes3D
import os

from krl_parser import KRLParser, KRLVisualizer


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("KUKA KRL Path Visualizer")
        self.geometry("1200x750")
        self.configure(bg="#F0F2F5")
        self.resizable(True, True)

        self.prog = None
        self.vis  = None

        self._build_ui()

    # ── UI layout ─────────────────────────────

    def _build_ui(self):
        # ── Left panel ──
        left = tk.Frame(self, bg="#2C3E50", width=280)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        tk.Label(left, text="KUKA KRL\nPath Visualizer",
                 bg="#2C3E50", fg="white",
                 font=("Helvetica", 14, "bold"),
                 pady=20).pack(fill="x")

        tk.Frame(left, bg="#3D5166", height=1).pack(fill="x", padx=20)

        # File selection
        tk.Label(left, text="KRL .src file",
                 bg="#2C3E50", fg="#BDC3C7",
                 font=("Helvetica", 9)).pack(anchor="w", padx=20, pady=(16, 2))

        src_frame = tk.Frame(left, bg="#2C3E50")
        src_frame.pack(fill="x", padx=20)
        self.src_var = tk.StringVar()
        tk.Entry(src_frame, textvariable=self.src_var,
                 font=("Helvetica", 9), width=18).pack(side="left", fill="x", expand=True)
        tk.Button(src_frame, text="…", command=self._browse_src,
                  bg="#3D5166", fg="white", relief="flat",
                  padx=6).pack(side="right")

        tk.Label(left, text=".dat file (optional)",
                 bg="#2C3E50", fg="#BDC3C7",
                 font=("Helvetica", 9)).pack(anchor="w", padx=20, pady=(10, 2))

        dat_frame = tk.Frame(left, bg="#2C3E50")
        dat_frame.pack(fill="x", padx=20)
        self.dat_var = tk.StringVar()
        tk.Entry(dat_frame, textvariable=self.dat_var,
                 font=("Helvetica", 9), width=18).pack(side="left", fill="x", expand=True)
        tk.Button(dat_frame, text="…", command=self._browse_dat,
                  bg="#3D5166", fg="white", relief="flat",
                  padx=6).pack(side="right")

        tk.Button(left, text="▶  Load & Visualize",
                  command=self._load,
                  bg="#27AE60", fg="white",
                  font=("Helvetica", 10, "bold"),
                  relief="flat", pady=10,
                  cursor="hand2").pack(fill="x", padx=20, pady=16)

        tk.Frame(left, bg="#3D5166", height=1).pack(fill="x", padx=20)

        # Stats
        tk.Label(left, text="Statistics",
                 bg="#2C3E50", fg="#BDC3C7",
                 font=("Helvetica", 9, "bold")).pack(anchor="w", padx=20, pady=(12, 4))

        self.stats_text = tk.Text(left, bg="#1A252F", fg="#ECF0F1",
                                  font=("Courier", 8),
                                  relief="flat", padx=8, pady=8,
                                  state="disabled", height=14)
        self.stats_text.pack(fill="x", padx=20)

        # Export buttons
        tk.Frame(left, bg="#3D5166", height=1).pack(fill="x", padx=20, pady=12)

        tk.Button(left, text="⬇  Export PDF report",
                  command=self._export_pdf,
                  bg="#2980B9", fg="white",
                  font=("Helvetica", 9), relief="flat",
                  pady=7, cursor="hand2").pack(fill="x", padx=20, pady=2)

        tk.Button(left, text="⬇  Export PNG image",
                  command=self._export_png,
                  bg="#8E44AD", fg="white",
                  font=("Helvetica", 9), relief="flat",
                  pady=7, cursor="hand2").pack(fill="x", padx=20, pady=2)

        tk.Label(left, text="github.com/Thejas12Dixit",
                 bg="#2C3E50", fg="#566573",
                 font=("Helvetica", 8)).pack(side="bottom", pady=10)

        # ── Right panel — plot area ──
        right = tk.Frame(self, bg="#F0F2F5")
        right.pack(side="right", fill="both", expand=True)

        self.fig = plt.Figure(figsize=(9, 6), facecolor="#F8F9FA")
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

        toolbar_frame = tk.Frame(right, bg="#F0F2F5")
        toolbar_frame.pack(fill="x", padx=10)
        NavigationToolbar2Tk(self.canvas, toolbar_frame)

        self._draw_placeholder()

    # ── Actions ───────────────────────────────

    def _browse_src(self):
        path = filedialog.askopenfilename(
            filetypes=[("KRL source", "*.src"), ("All files", "*.*")])
        if path:
            self.src_var.set(path)
            dat = os.path.splitext(path)[0] + ".dat"
            if os.path.exists(dat):
                self.dat_var.set(dat)

    def _browse_dat(self):
        path = filedialog.askopenfilename(
            filetypes=[("KRL data", "*.dat"), ("All files", "*.*")])
        if path:
            self.dat_var.set(path)

    def _load(self):
        src = self.src_var.get()
        dat = self.dat_var.get() or None
        if not src:
            messagebox.showwarning("No file", "Please select a .src file first.")
            return
        try:
            parser = KRLParser()
            self.prog = parser.parse(src, dat)
            self.vis  = KRLVisualizer(self.prog)
            self._update_stats()
            self._draw_3d()
        except Exception as e:
            messagebox.showerror("Parse error", str(e))

    def _update_stats(self):
        stats = self.vis.get_stats()
        lines = [
            f"Program : {stats['program_name']}",
            f"Points  : {stats['total_points']}",
            f"PTP     : {stats['ptp_moves']}",
            f"LIN     : {stats['lin_moves']}",
            f"CIRC    : {stats['circ_moves']}",
            f"Dist    : {stats['total_distance']} mm",
            f"",
            f"X  {stats['x_range'][0]}→{stats['x_range'][1]}",
            f"Y  {stats['y_range'][0]}→{stats['y_range'][1]}",
            f"Z  {stats['z_range'][0]}→{stats['z_range'][1]}",
        ]
        if stats["warnings"]:
            lines += ["", "⚠ Warnings:"] + [f"  {w}" for w in stats["warnings"]]

        self.stats_text.configure(state="normal")
        self.stats_text.delete("1.0", "end")
        self.stats_text.insert("end", "\n".join(lines))
        self.stats_text.configure(state="disabled")

    def _draw_3d(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111, projection="3d")
        self.vis.plot_3d(ax=ax)
        self.canvas.draw()

    def _draw_placeholder(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.text(0.5, 0.5, "Load a KRL .src file to visualize the robot path",
                ha="center", va="center", fontsize=12,
                color="#95A5A6", transform=ax.transAxes)
        ax.axis("off")
        self.canvas.draw()

    def _export_pdf(self):
        if not self.vis:
            messagebox.showwarning("No data", "Load a KRL file first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"{self.prog.name}_report.pdf")
        if path:
            self.vis.export_pdf(path)
            messagebox.showinfo("Exported", f"PDF saved:\n{path}")

    def _export_png(self):
        if not self.vis:
            messagebox.showwarning("No data", "Load a KRL file first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            initialfile=f"{self.prog.name}_path.png")
        if path:
            self.vis.export_png(path)
            messagebox.showinfo("Exported", f"PNG saved:\n{path}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
