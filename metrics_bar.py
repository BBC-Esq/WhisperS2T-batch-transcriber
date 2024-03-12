import sys
import time
from collections import deque
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget, QGridLayout, QProgressBar, QLabel
import psutil
import torch

def is_nvidia_gpu_available():
    return torch.cuda.is_available() and "nvidia" in torch.cuda.get_device_name(0).lower()

if is_nvidia_gpu_available():
    import pynvml
    pynvml.nvmlInit()
    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
else:
    handle = None

class MetricsCollector(QThread):
    metrics_updated = Signal(tuple)

    def run(self):
        while True:
            cpu_usage = collect_cpu_metrics()
            ram_usage_percent, _ = collect_ram_metrics()
            gpu_utilization, vram_usage_percent, power_usage_percent, power_limit_percent = (0, 0, 0, 0)

            if handle:
                gpu_utilization, vram_usage_percent, power_usage_percent, power_limit_percent = collect_gpu_metrics(handle)

            self.metrics_updated.emit((cpu_usage, ram_usage_percent, gpu_utilization, vram_usage_percent, power_usage_percent, power_limit_percent))
            time.sleep(0.2)

class MetricsBar(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.setup_metrics_buffers()
        self.start_metrics_collector()

    def initUI(self):
        grid_layout = QGridLayout(self)
        grid_layout.setSpacing(0)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        self.cpu_bar, self.cpu_percent_label = self.add_metric_to_grid("CPU Usage:", "#FF4136", grid_layout, 0)
        self.ram_bar, self.ram_percent_label = self.add_metric_to_grid("RAM Usage:", "#B10DC9", grid_layout, 1)

        if handle:
            self.gpu_bar, self.gpu_percent_label = self.add_metric_to_grid("GPU Usage:", "#0074D9", grid_layout, 2)
            self.vram_bar, self.vram_percent_label = self.add_metric_to_grid("VRAM Usage:", "#2ECC40", grid_layout, 3)
            self.power_bar, self.power_percent_label = self.add_metric_to_grid("GPU Power:", "#FFD700", grid_layout, 4)

    def add_metric_to_grid(self, label_text, color, grid_layout, row):
        label = QLabel(label_text)
        grid_layout.addWidget(label, row, 0)

        percent_label = QLabel("0%")
        grid_layout.addWidget(percent_label, row, 1)

        progress_bar = self.create_progress_bar(color)
        grid_layout.addWidget(progress_bar, row, 2)

        return progress_bar, percent_label

    def create_progress_bar(self, color):
        bar = QProgressBar()
        bar.setMaximum(100)
        bar.setMaximumHeight(11)
        bar.setStyleSheet(
            f"QProgressBar {{ background-color: #1e2126; border: none; }}"
            f"QProgressBar::chunk {{ background-color: {color}; }}"
        )
        bar.setTextVisible(False)
        return bar

    def update_metrics(self, metrics):
        cpu_usage, ram_usage_percent, gpu_utilization, vram_usage_percent, power_usage_percent, power_limit_percent = metrics

        self.cpu_buffer.append(cpu_usage)
        self.ram_buffer.append(ram_usage_percent)

        if handle:
            self.gpu_buffer.append(gpu_utilization)
            self.vram_buffer.append(vram_usage_percent)
            self.power_buffer.append(power_usage_percent)

        self.update_progress_bar(self.cpu_bar, self.cpu_buffer, self.cpu_percent_label)
        self.update_progress_bar(self.ram_bar, self.ram_buffer, self.ram_percent_label)

        if handle:
            self.update_progress_bar(self.gpu_bar, self.gpu_buffer, self.gpu_percent_label)
            self.update_progress_bar(self.vram_bar, self.vram_buffer, self.vram_percent_label)
            self.update_progress_bar(self.power_bar, self.power_buffer, self.power_percent_label)

    def update_progress_bar(self, bar, buffer, label):
        avg_value = int(sum(buffer) / len(buffer))
        bar.setValue(avg_value)
        label.setText(f"{avg_value}%")

    def setup_metrics_buffers(self):
        self.cpu_buffer = deque(maxlen=10)
        self.ram_buffer = deque(maxlen=10)

        if handle:
            self.gpu_buffer = deque(maxlen=10)
            self.vram_buffer = deque(maxlen=10)
            self.power_buffer = deque(maxlen=10)

    def start_metrics_collector(self):
        self.metrics_collector = MetricsCollector()
        self.metrics_collector.metrics_updated.connect(self.update_metrics)
        self.metrics_collector.start()

    def stop_metrics_collector(self):
        if hasattr(self, 'metrics_collector'):
            self.metrics_collector.terminate()
            self.metrics_collector.wait()

def collect_cpu_metrics():
    percentages = psutil.cpu_percent(interval=0.2, percpu=True)
    return sum(percentages) / len(percentages)

def collect_ram_metrics():
    ram = psutil.virtual_memory()
    return ram.percent, ram.used

def collect_gpu_metrics(handle):
    if handle:
        memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        gpu_utilization = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
        vram_usage_percent = (memory_info.used / memory_info.total) * 100 if memory_info.total > 0 else 0
        power_usage_percent, power_limit_percent = collect_power_metrics(handle)
        return gpu_utilization, vram_usage_percent, power_usage_percent, power_limit_percent
    else:
        return 0, 0, 0, 0

def collect_power_metrics(handle):
    if handle:
        power_usage = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
        power_limit = pynvml.nvmlDeviceGetPowerManagementLimit(handle) / 1000.0
        power_percentage = (power_usage / power_limit) * 100 if power_limit > 0 else 0
        return power_percentage, power_limit
    else:
        return 0, 0
