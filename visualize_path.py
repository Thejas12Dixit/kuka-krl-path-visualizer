"""
visualize_path.py
=================
Version 1 — Simple terminal (command line) script.

This is the quickest way to use the visualizer.
You run it from the terminal by pointing it at a .src file.

Usage examples:
  python visualize_path.py sample_welding.src              # Opens Mayavi interactive window
  python visualize_path.py sample_welding.src --matplotlib # Opens matplotlib window instead
  python visualize_path.py sample_welding.src --pdf        # Exports a PDF report
  python visualize_path.py sample_welding.src --png        # Exports a PNG image
  python visualize_path.py sample_welding.src --dat path/to/file.dat  # Specify .dat manually
"""

import argparse    # argparse = standard library module for parsing command-line arguments (the --pdf, --png flags etc.)
import os          # os = file system operations (checking if file exists)
import sys         # sys = system-level operations (sys.exit to stop the script with an error code)

# Import our own parser and visualizer from krl_parser.py (must be in the same folder)
from krl_parser import KRLParser, KRLVisualizer, MAYAVI_AVAILABLE


def main():
    """Main function — entry point when script is run from terminal."""

    # ── Set up argument parser ────────────────────────────────────────────────
    # argparse reads what the user typed after "python visualize_path.py ..."
    parser = argparse.ArgumentParser(
        description="KUKA KRL Path Visualizer — parse and visualize KRL robot programs"
    )

    # Positional argument: required, no -- prefix. User must provide the .src file path.
    parser.add_argument("src_file", help="Path to the KUKA .src program file")

    # Optional arguments (flags): these are optional and have -- prefix
    parser.add_argument("--dat",        help="Path to .dat file (auto-detected from .src name if not given)")
    parser.add_argument("--pdf",        action="store_true", help="Export a 2-page PDF report instead of opening a window")
    parser.add_argument("--png",        action="store_true", help="Export a PNG image instead of opening a window")
    parser.add_argument("--matplotlib", action="store_true", help="Use matplotlib viewer instead of Mayavi (simpler, no install needed)")

    args = parser.parse_args()   # Parse what was actually typed — stores results in args.src_file, args.pdf etc.

    # ── Validate input file ───────────────────────────────────────────────────
    if not os.path.exists(args.src_file):          # Check the file actually exists on disk
        print(f"[ERROR] File not found: {args.src_file}")
        sys.exit(1)                                # Exit with error code 1 (non-zero = error in Unix convention)

    # ── Parse the KRL files ───────────────────────────────────────────────────
    print(f"\n-- Parsing {args.src_file} --")
    prog = KRLParser().parse(args.src_file, args.dat)  # args.dat is None if not provided — parser auto-detects
    vis  = KRLVisualizer(prog)                         # Create visualizer with the parsed program

    # Print any warnings (e.g. points in .src that weren't found in .dat)
    if prog.warnings:
        print("\n[WARNINGS]")
        for w in prog.warnings:
            print(f"  !  {w}")

    # ── Print statistics to terminal ──────────────────────────────────────────
    stats = vis.get_stats()   # Calculate all stats
    print(f"\n-- Program Statistics --")
    print(f"  Program         : {stats['program_name']}")
    print(f"  Total points    : {stats['total_points']}")
    print(f"  PTP / LIN / CIRC: {stats['ptp_moves']} / {stats['lin_moves']} / {stats['circ_moves']}")
    print(f"  Total distance  : {stats['total_distance']} mm")
    print(f"  X: {stats['x_range'][0]} -> {stats['x_range'][1]} mm")   # Workspace extent in X
    print(f"  Y: {stats['y_range'][0]} -> {stats['y_range'][1]} mm")
    print(f"  Z: {stats['z_range'][0]} -> {stats['z_range'][1]} mm")
    print(f"  Mayavi available: {MAYAVI_AVAILABLE}")                     # Tells user if Mayavi is installed

    # ── Handle export flags ───────────────────────────────────────────────────
    if args.pdf:   # User passed --pdf flag
        path = vis.export_pdf()   # Generate and save the PDF (auto-named from program name)
        print(f"\n  PDF saved -> {path}")

    if args.png:   # User passed --png flag
        path = vis.export_png()   # Generate and save the PNG
        print(f"\n  PNG saved -> {path}")

    # ── Handle interactive viewer ─────────────────────────────────────────────
    # Only open a window if the user did NOT request --pdf or --png export
    if not args.pdf and not args.png:

        if args.matplotlib or not MAYAVI_AVAILABLE:
            # Use matplotlib viewer if user forced --matplotlib OR if Mayavi is not installed
            if not MAYAVI_AVAILABLE and not args.matplotlib:
                print("\n[INFO] Mayavi not found — falling back to matplotlib viewer.")
                print("       To use Mayavi: pip install mayavi PyQt5")

            import matplotlib              # Import here (not at top) because we only need it for interactive display
            matplotlib.use("TkAgg")        # TkAgg backend: opens a real interactive window using Tkinter. Must be set before importing pyplot
            import matplotlib.pyplot as plt
            fig, ax = vis.plot_3d()        # Generate the 3D matplotlib plot
            plt.show()                     # Open the interactive window — blocks until user closes it

        else:
            # Use Mayavi (default if installed) — richer, more interactive
            vis.plot_3d_mayavi()           # Opens Mayavi window; blocks until closed

    print("\n-- Done --\n")   # Confirmation message when everything finishes


# ── Script entry point ────────────────────────────────────────────────────────
# This block only runs when the script is executed directly (python visualize_path.py ...)
# It does NOT run if this file is imported as a module by another script
if __name__ == "__main__":
    main()
