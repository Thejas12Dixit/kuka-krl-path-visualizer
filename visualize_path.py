"""
visualize_path.py
=================
Terminal script - Version 1.

Usage:
  python visualize_path.py sample_welding.src              # Mayavi interactive window
  python visualize_path.py sample_welding.src --matplotlib # matplotlib window (fallback)
  python visualize_path.py sample_welding.src --pdf        # export PDF report
  python visualize_path.py sample_welding.src --png        # export PNG image
"""

import argparse
import os
import sys
from krl_parser import KRLParser, KRLVisualizer, MAYAVI_AVAILABLE


def main():
    parser = argparse.ArgumentParser(description="KUKA KRL Path Visualizer")
    parser.add_argument("src_file",      help="Path to .src KRL file")
    parser.add_argument("--dat",         help=".dat file (auto-detected if omitted)")
    parser.add_argument("--pdf",         action="store_true", help="Export PDF report")
    parser.add_argument("--png",         action="store_true", help="Export PNG image")
    parser.add_argument("--matplotlib",  action="store_true", help="Use matplotlib viewer instead of Mayavi")
    args = parser.parse_args()

    if not os.path.exists(args.src_file):
        print(f"[ERROR] File not found: {args.src_file}")
        sys.exit(1)

    print(f"\n-- Parsing {args.src_file} --")
    prog = KRLParser().parse(args.src_file, args.dat)
    vis  = KRLVisualizer(prog)

    if prog.warnings:
        print("\n[WARNINGS]")
        for w in prog.warnings:
            print(f"  !  {w}")

    stats = vis.get_stats()
    print(f"\n-- Program Statistics --")
    print(f"  Program       : {stats['program_name']}")
    print(f"  Total points  : {stats['total_points']}")
    print(f"  PTP / LIN / CIRC: {stats['ptp_moves']} / {stats['lin_moves']} / {stats['circ_moves']}")
    print(f"  Total distance: {stats['total_distance']} mm")
    print(f"  X: {stats['x_range'][0]} -> {stats['x_range'][1]} mm")
    print(f"  Y: {stats['y_range'][0]} -> {stats['y_range'][1]} mm")
    print(f"  Z: {stats['z_range'][0]} -> {stats['z_range'][1]} mm")
    print(f"  Mayavi available: {MAYAVI_AVAILABLE}")

    if args.pdf:
        path = vis.export_pdf()
        print(f"\n  PDF saved -> {path}")

    if args.png:
        path = vis.export_png()
        print(f"\n  PNG saved -> {path}")

    # Interactive viewer
    if not args.pdf and not args.png:
        if args.matplotlib or not MAYAVI_AVAILABLE:
            if not MAYAVI_AVAILABLE and not args.matplotlib:
                print("\n[INFO] Mayavi not found, falling back to matplotlib.")
                print("       Install Mayavi:  pip install mayavi PyQt5")
            import matplotlib
            matplotlib.use("TkAgg")
            import matplotlib.pyplot as plt
            fig, ax = vis.plot_3d()
            plt.show()
        else:
            vis.plot_3d_mayavi()

    print("\n-- Done --\n")


if __name__ == "__main__":
    main()
