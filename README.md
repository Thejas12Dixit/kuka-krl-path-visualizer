# KUKA KRL Path Visualizer

> Parse KUKA KRL `.src` / `.dat` robot programs and visualize the 3D motion path — with PDF/PNG export and a GUI.

![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square&logo=python)
![Matplotlib](https://img.shields.io/badge/Matplotlib-3D_Plot-orange?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)

---

## The Problem

When programming KUKA robots in WorkVisual or Process Simulate, it's hard to quickly audit a path from the raw `.src` / `.dat` files without a full simulation environment running. This tool lets you:

- **Instantly visualize** any KRL program as an interactive 3D path
- **Understand motion types** - PTP, LIN, CIRC — colour-coded at a glance
- **Audit workspace envelope** - check reachability without loading a full sim
- **Export documentation** - PDF reports + PNG images for engineering reviews

---

## Demo

![3D path visualization](docs/sample_path.png)

*Colour legend: 🔵 PTP · 🟢 LIN · 🟠 CIRC · 🔴 Process point · 🟣 HOME*

---

## Features

| Feature | Terminal | GUI | Jupyter |
|---|:---:|:---:|:---:|
| Parse `.src` + `.dat` files | ✅ | ✅ | ✅ |
| Interactive 3D path plot | ✅ | ✅ | ✅ |
| Motion sequence table | ✅ | — | ✅ |
| Workspace envelope stats | ✅ | ✅ | ✅ |
| Export PDF report (2-page) | ✅ | ✅ | ✅ |
| Export PNG image | ✅ | ✅ | ✅ |
| File browser GUI | — | ✅ | — |

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/Thejas12Dixit/kuka-krl-path-visualizer.git
cd kuka-krl-path-visualizer

# Install dependencies
pip install -r requirements.txt

# Run with sample file (terminal)
python visualize_path.py sample_welding.src

# Export PDF
python visualize_path.py sample_welding.src --pdf

# Launch GUI
python gui_visualizer.py

# Open Jupyter notebook
jupyter notebook krl_visualizer.ipynb
```

---

## KRL Syntax Supported

```krl
; Point-to-point (joint interpolated)
PTP P1 Vel=80% PDAT1 Tool[1] Base[1]

; Linear Cartesian motion
LIN P2 Vel=0.3 m/s CPDAT1 Tool[1] Base[1]

; Circular motion (intermediate + end point)
CIRC P3 P4 Vel=0.2 m/s CPDAT2 Tool[1] Base[1]

; HOME position
PTP HOME Vel=100% DEFAULT
```

Point coordinates are parsed from the paired `.dat` file:
```krl
DECL E6POS P1={X 850.0, Y -200.0, Z 1200.0, A -15.0, B 60.0, C 0.0}
```

---

## Project Structure

```
kuka-krl-path-visualizer/
├── krl_parser.py          # Core parser + visualizer module
├── visualize_path.py      # Terminal script (Version 1)
├── gui_visualizer.py      # Tkinter GUI (Version 2)
├── krl_visualizer.ipynb   # Jupyter notebook (Version 3)
├── sample_welding.src     # Sample KRL program (BIW spot welding)
├── sample_welding.dat     # Sample point data
├── requirements.txt
└── README.md
```

---

## Background

Built from real industry experience programming KUKA robots to **BMW standards** at **Strama-MPS** and developing simulation workflows at **Volkswagen AG**. The tool directly solves a practical problem: quickly auditing a robot path from KRL files without launching a full Process Simulate or WorkVisual session.

---

## Roadmap

- [ ] Joint-space animation playback
- [ ] Cycle time estimation from velocity data
- [ ] Multi-program overlay (compare path variants)
- [ ] RoboDK API integration for direct import
- [ ] FANUC and ABB dialect support

---

## Author

**Thejas Dixit Sathyanarayana** — Robotics Simulation Engineer  
🔗 [LinkedIn](https://www.linkedin.com/in/thejas-dixit-s/) · 📧 thejasds21@gmail.com · 🌍 Straubing, Germany
