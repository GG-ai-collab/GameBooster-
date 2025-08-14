import sys
import os
import ctypes
import psutil
import time
from collections import deque
from threading import Event, Thread
from PyQt5 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import win32gui
import win32process
import win32con

# ---------------- Admin check ----------------
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def relaunch_as_admin():
    params = " ".join([f'"{arg}"' for arg in sys.argv])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    sys.exit(0)

# ---------------- Optimizer Thread ----------------
class OptimizerThread(QtCore.QThread):
    status_update = QtCore.pyqtSignal(dict)

    def __init__(self, stop_event):
        super().__init__()
        self.stop_event = stop_event

    def run(self):
        while not self.stop_event.is_set():
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            self.status_update.emit({
                "cpu": cpu,
                "ram_percent": mem.percent,
                "ram_used": mem.used // (1024*1024),
                "ram_free": mem.available // (1024*1024),
                "ram_total": mem.total // (1024*1024)
            })
            for _ in range(10):
                if self.stop_event.is_set():
                    break
                time.sleep(0.1)

# ---------------- Matplotlib Canvas ----------------
class MplCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(5, 4), dpi=100, facecolor="#121212")
        self.ax_cpu = self.fig.add_subplot(211, facecolor="#1e1e1e")
        self.ax_ram = self.fig.add_subplot(212, facecolor="#1e1e1e")
        super().__init__(self.fig)
        self.setParent(parent)
        self.cpu_history = deque(maxlen=100)
        self.ram_history = deque(maxlen=100)

        # Настройка осей
        for ax in [self.ax_cpu, self.ax_ram]:
            ax.set_facecolor("#1e1e1e")
            ax.tick_params(colors='white')
            ax.spines['bottom'].set_color('white')
            ax.spines['top'].set_color('white')
            ax.spines['left'].set_color('white')
            ax.spines['right'].set_color('white')

        self.ax_cpu.set_title("CPU Usage (%)", color='white')
        self.ax_cpu.set_ylim(0, 100)
        self.ax_cpu.set_ylabel("CPU %", color='white')

        self.ax_ram.set_title("RAM Usage (%)", color='white')
        self.ax_ram.set_ylim(0, 100)
        self.ax_ram.set_ylabel("RAM %", color='white')
        self.ax_ram.set_xlabel("Time", color='white')

    def update_plot(self, cpu, ram):
        self.cpu_history.append(cpu)
        self.ram_history.append(ram)

        # Очистка и перерисовка
        self.ax_cpu.cla()
        self.ax_ram.cla()

        # Настройка осей снова
        for ax in [self.ax_cpu, self.ax_ram]:
            ax.set_facecolor("#1e1e1e")
            ax.tick_params(colors='white')
            ax.spines['bottom'].set_color('white')
            ax.spines['top'].set_color('white')
            ax.spines['left'].set_color('white')
            ax.spines['right'].set_color('white')

        # CPU
        self.ax_cpu.plot(list(self.cpu_history), color='lime', linewidth=2, alpha=0.7, antialiased=True)
        self.ax_cpu.set_title("CPU Usage (%)", color='white')
        self.ax_cpu.set_ylim(0, 100)
        self.ax_cpu.set_ylabel("CPU %", color='white')

        # RAM
        self.ax_ram.plot(list(self.ram_history), color='cyan', linewidth=2, alpha=0.7, antialiased=True)
        self.ax_ram.set_title("RAM Usage (%)", color='white')
        self.ax_ram.set_ylim(0, 100)
        self.ax_ram.set_ylabel("RAM %", color='white')
        self.ax_ram.set_xlabel("Time", color='white')

        self.draw()

# ---------------- Priority booster ----------------
def set_high_priority_for_foreground():
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd == 0:
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        if proc.pid != os.getpid():  # не повышаем свой процесс
            proc.nice(psutil.HIGH_PRIORITY_CLASS)
    except Exception as e:
        pass  # можно логировать, но чтобы не ломалось

# ---------------- Main Window ----------------
class BoosterWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.language = "ru"
        self.setWindowTitle("Game Booster")
        self.setStyleSheet("""
            QWidget { background: #121212; color: #e6e6e6; font-family: Segoe UI; font-size: 16px; }
            QPushButton { background: #2a2a2a; border: 1px solid #353535; padding: 6px 10px; }
            QPushButton:hover { background: #333333; }
        """)

        layout = QtWidgets.QVBoxLayout(self)

        # Language button
        self.lang_btn = QtWidgets.QPushButton("English")
        self.lang_btn.clicked.connect(self.toggle_language)
        layout.addWidget(self.lang_btn, alignment=QtCore.Qt.AlignRight)

        # Info labels
        self.cpu_label = QtWidgets.QLabel()
        self.ram_label = QtWidgets.QLabel()
        self.mem_detail_label = QtWidgets.QLabel()
        layout.addWidget(self.cpu_label)
        layout.addWidget(self.ram_label)
        layout.addWidget(self.mem_detail_label)

        # Buttons
        self.start_btn = QtWidgets.QPushButton()
        self.stop_btn = QtWidgets.QPushButton()
        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setEnabled(False)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)

        # Graph
        self.canvas = MplCanvas(self)
        layout.addWidget(self.canvas)

        self.stop_event = Event()
        self.optimizer = None

        self.update_labels()

        # Таймер для проверки активного окна и приоритета
        self.priority_timer = QtCore.QTimer()
        self.priority_timer.timeout.connect(set_high_priority_for_foreground)
        self.priority_timer.start(500)  # каждые 0.5 сек

        self.showMaximized()

    def toggle_language(self):
        self.language = "en" if self.language == "ru" else "ru"
        self.update_labels()

    def update_labels(self, stats=None):
        if self.language == "ru":
            self.start_btn.setText("Запустить")
            self.stop_btn.setText("Остановить")
            self.lang_btn.setText("English")
            if stats:
                self.cpu_label.setText(f"Загрузка CPU: {stats['cpu']:.1f}%")
                self.ram_label.setText(f"Память: {stats['ram_percent']:.1f}%")
                self.mem_detail_label.setText(
                    f"Используется: {stats['ram_used']} МБ | Свободно: {stats['ram_free']} МБ | Всего: {stats['ram_total']} МБ"
                )
            else:
                self.cpu_label.setText("Загрузка CPU: —")
                self.ram_label.setText("Память: —")
                self.mem_detail_label.setText("Используется: — | Свободно: — | Всего: —")
        else:
            self.start_btn.setText("Start")
            self.stop_btn.setText("Stop")
            self.lang_btn.setText("Русский")
            if stats:
                self.cpu_label.setText(f"CPU Load: {stats['cpu']:.1f}%")
                self.ram_label.setText(f"Memory: {stats['ram_percent']:.1f}%")
                self.mem_detail_label.setText(
                    f"Used: {stats['ram_used']} MB | Free: {stats['ram_free']} MB | Total: {stats['ram_total']} MB"
                )
            else:
                self.cpu_label.setText("CPU Load: —")
                self.ram_label.setText("Memory: —")
                self.mem_detail_label.setText("Used: — | Free: — | Total: —")

    def start(self):
        self.stop_event.clear()
        self.optimizer = OptimizerThread(self.stop_event)
        self.optimizer.status_update.connect(
            lambda stats: [self.update_labels(stats), self.canvas.update_plot(stats['cpu'], stats['ram_percent'])]
        )
        self.optimizer.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop(self):
        self.stop_event.set()
        if self.optimizer:
            self.optimizer.wait()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

# ---------------- Entry Point ----------------
def main():
    app = QtWidgets.QApplication(sys.argv)

    if not is_admin():
        reply = QtWidgets.QMessageBox.question(None, "Windows",
            "Для работы нужно разрешение администратора",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            relaunch_as_admin()

    w = BoosterWindow()
    w.showMaximized()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
