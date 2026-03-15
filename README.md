# KUKA KRL Path Visualizer

A Python tool for reading KUKA robot programs (.src and .dat files) and visualizing the motion path in 3D.

Built from real experience programming KUKA robots at Strama-MPS to BMW standards and working with robot simulation at Volkswagen AG. The idea came from a simple problem: when you want to quickly check a robot path from the raw KRL files, you normally need a full Process Simulate or WorkVisual session running. This skips that.

![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square&logo=python)
![Matplotlib](https://img.shields.io/badge/Matplotlib-3D_Plot-orange?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## What it does

- Reads a .src file (motion commands) and its paired .dat file (point coordinates)
- Matches each motion command to its coordinates
- Draws the 3D path with color coding: blue for PTP, green for LIN, orange for CIRC
- Shows workspace envelope stats (X, Y, Z ranges and total path distance)
- Exports a 2-page PDF report and a PNG image

---

## Files

```
kuka-krl-path-visualizer/
├── KUKA_krl_reader.py     # parser and visualizer
├── gui_visualizer.py      # desktop GUI built with Tkinter
├── sample_welding.src     # example KRL program (BIW spot welding)
├── sample_welding.dat     # example point data
├── requirements.txt
└── README.md
```

---

## Getting started

```bash
git clone https://github.com/Thejas12Dixit/kuka-krl-path-visualizer.git
cd kuka-krl-path-visualizer
pip install -r requirements.txt

# launch the GUI
python gui_visualizer.py
```

Load your .src file using the file browser in the GUI. The .dat file is picked up automatically if it is in the same folder.

---

## KRL syntax supported

```krl
PTP P1 Vel=80% PDAT1 Tool[1] Base[1]
LIN P2 Vel=0.3 m/s CPDAT1 Tool[1] Base[1]
CIRC P3 P4 Vel=0.2 m/s CPDAT2 Tool[1] Base[1]
PTP HOME Vel=100% DEFAULT
```

Point coordinates are read from the .dat file:
```krl
DECL E6POS P1={X 850.0, Y -200.0, Z 1200.0, A -15.0, B 60.0, C 0.0}
```

---

## Optional: interactive 3D viewer

By default the tool uses matplotlib for 3D output. If you install Mayavi you get a richer interactive viewer with rotation, zoom and pan.

```bash
pip install mayavi PyQt5
```

---

## Roadmap

- CAD - Robot Station Integration
- Cycle time estimation from velocity data
- Multi-program path overlay
- Joint-space animation playback
- RoboDK integration

---

## Author

Thejas Dixit Sathyanarayana - Robotics Simulation Engineer  
[LinkedIn](https://www.linkedin.com/in/thejas-dixit-s/) · thejasds21@gmail.com · Straubing, Germany
