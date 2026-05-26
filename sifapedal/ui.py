import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QComboBox, QPushButton, QCheckBox,
    QSlider, QFormLayout, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer


class SifaPedalUI(QMainWindow):
    def __init__(self, core):
        super().__init__()
        self.core = core

        self.setWindowTitle("SifaPedal")
        self.setMinimumSize(400, 470)
        self.setMaximumSize(400, 470)

        self.listening_for_key = False

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        self.create_widgets()
        self.refresh_joysticks()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_core)
        self.timer.start(20)

    def create_widgets(self):
        dev_group = QGroupBox("Device Configuration")
        dev_layout = QFormLayout()
        dev_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        dev_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        row1 = QHBoxLayout()
        self.joystick_cb = QComboBox()
        self.joystick_cb.currentIndexChanged.connect(self.on_joystick_selected)
        row1.addWidget(self.joystick_cb, 1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_joysticks)
        row1.addWidget(self.refresh_btn)

        dev_layout.addRow("Joystick:", row1)

        self.axis_cb = QComboBox()
        self.axis_cb.currentIndexChanged.connect(self.on_axis_selected)
        dev_layout.addRow("Axis:", self.axis_cb)

        dev_group.setLayout(dev_layout)
        self.main_layout.addWidget(dev_group)

        key_group = QGroupBox("Keybind")
        key_layout = QFormLayout()
        key_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        key_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        row_key = QHBoxLayout()
        self.key_lbl = QLabel(self.core.base_key)
        self.key_lbl.setStyleSheet(
            "font-weight: bold; padding: 4px; background-color: rgba(0,0,0,0.1); border-radius: 4px;")
        self.key_btn = QPushButton("Rebind")
        self.key_btn.clicked.connect(self.start_rebind)
        row_key.addWidget(self.key_lbl, 1)
        row_key.addWidget(self.key_btn)
        key_layout.addRow("Base Key:", row_key)

        row_mods = QHBoxLayout()
        self.ctrl_chk = QCheckBox("Ctrl")
        self.alt_chk = QCheckBox("Alt")
        self.shift_chk = QCheckBox("Shift")
        self.ctrl_chk.stateChanged.connect(self.on_modifiers_changed)
        self.alt_chk.stateChanged.connect(self.on_modifiers_changed)
        self.shift_chk.stateChanged.connect(self.on_modifiers_changed)
        row_mods.addWidget(self.ctrl_chk)
        row_mods.addWidget(self.alt_chk)
        row_mods.addWidget(self.shift_chk)
        row_mods.addStretch()
        key_layout.addRow("Modifiers:", row_mods)

        key_group.setLayout(key_layout)
        self.main_layout.addWidget(key_group)

        sens_group = QGroupBox("Sensitivity")
        sens_layout = QFormLayout()
        sens_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        sens_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.axis_prog = QProgressBar()
        self.axis_prog.setRange(0, 100)
        self.axis_prog.setValue(0)
        self.axis_prog.setFormat("%v%")
        sens_layout.addRow("Input:", self.axis_prog)

        row_thresh = QHBoxLayout()
        self.thresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.thresh_slider.setRange(0, 100)
        self.thresh_slider.setValue(50)
        self.thresh_slider.valueChanged.connect(self.on_sensitivity_changed)
        row_thresh.addWidget(self.thresh_slider)
        self.thresh_lbl = QLabel("0.50")
        row_thresh.addWidget(self.thresh_lbl)
        sens_layout.addRow("Threshold:", row_thresh)

        row_dead = QHBoxLayout()
        self.dead_slider = QSlider(Qt.Orientation.Horizontal)
        self.dead_slider.setRange(0, 100)
        self.dead_slider.setValue(5)
        self.dead_slider.valueChanged.connect(self.on_sensitivity_changed)
        row_dead.addWidget(self.dead_slider)
        self.dead_lbl = QLabel("0.05")
        row_dead.addWidget(self.dead_lbl)
        sens_layout.addRow("Deadzone:", row_dead)

        self.invert_chk = QCheckBox("Invert")
        self.invert_chk.stateChanged.connect(self.on_sensitivity_changed)
        sens_layout.addRow("", self.invert_chk)

        sens_group.setLayout(sens_layout)
        self.main_layout.addWidget(sens_group)

        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout()
        self.pressed_lbl = QLabel("Pedal State: RELEASED")
        self.pressed_lbl.setStyleSheet("color: red; font-weight: bold;")
        status_layout.addWidget(self.pressed_lbl)
        status_group.setLayout(status_layout)
        self.main_layout.addWidget(status_group)

        self.main_layout.addStretch()

    def start_rebind(self):
        self.listening_for_key = True
        self.key_lbl.setText("Press any key...")
        self.key_btn.setText("Cancel")
        self.key_btn.clicked.disconnect()
        self.key_btn.clicked.connect(self.cancel_rebind)
        self.setFocus()

    def cancel_rebind(self):
        self.listening_for_key = False
        self.key_lbl.setText(self.core.base_key)
        self.key_btn.setText("Rebind")
        self.key_btn.clicked.disconnect()
        self.key_btn.clicked.connect(self.start_rebind)

    def keyPressEvent(self, event):
        if not self.listening_for_key:
            super().keyPressEvent(event)
            return

        key = event.key()

        if key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return

        SPECIAL_KEYS = {
            Qt.Key.Key_Space: "space",
            Qt.Key.Key_Return: "enter",
            Qt.Key.Key_Enter: "enter",
            Qt.Key.Key_Backspace: "backspace",
            Qt.Key.Key_Escape: "esc",
            Qt.Key.Key_Tab: "tab",
            Qt.Key.Key_Up: "up",
            Qt.Key.Key_Down: "down",
            Qt.Key.Key_Left: "left",
            Qt.Key.Key_Right: "right",
        }

        if key in SPECIAL_KEYS:
            key_str = SPECIAL_KEYS[key]
        else:
            key_str = event.text().lower()
            if not key_str:
                return

        self.core.base_key = key_str
        self.cancel_rebind()

    def refresh_joysticks(self):
        self.joysticks_data = self.core.refresh_joysticks()
        self.joystick_cb.blockSignals(True)
        self.joystick_cb.clear()

        if self.joysticks_data:
            for idx, name in self.joysticks_data:
                self.joystick_cb.addItem(f"{idx}: {name}")
            self.joystick_cb.blockSignals(False)
            self.joystick_cb.setCurrentIndex(0)
            self.on_joystick_selected(0)
        else:
            self.joystick_cb.addItem("No joysticks found")
            self.joystick_cb.blockSignals(False)
            self.axis_cb.clear()
            self.axis_cb.addItem("")

    def on_joystick_selected(self, index):
        if 0 <= index < len(self.joysticks_data):
            joy_idx = self.joysticks_data[index][0]
            if self.core.select_joystick(joy_idx):
                num_axes = self.core.get_num_axes()
                self.axis_cb.blockSignals(True)
                self.axis_cb.clear()
                if num_axes > 0:
                    for i in range(num_axes):
                        self.axis_cb.addItem(f"Axis {i}")
                    self.axis_cb.blockSignals(False)
                    self.axis_cb.setCurrentIndex(0)
                    self.on_axis_selected(0)
                else:
                    self.axis_cb.addItem("No axes on this device")
                    self.axis_cb.blockSignals(False)

    def on_axis_selected(self, index):
        if index >= 0:
            self.core.axis_index = index

    def on_modifiers_changed(self):
        self.core.modifiers['ctrl'] = self.ctrl_chk.isChecked()
        self.core.modifiers['alt'] = self.alt_chk.isChecked()
        self.core.modifiers['shift'] = self.shift_chk.isChecked()

    def on_sensitivity_changed(self):
        t = self.thresh_slider.value() / 100.0
        d = self.dead_slider.value() / 100.0
        self.core.threshold = t
        self.core.deadzone = d
        self.core.invert = self.invert_chk.isChecked()
        self.thresh_lbl.setText(f"{t:.2f}")
        self.dead_lbl.setText(f"{d:.2f}")

    def poll_core(self):
        val = self.core.tick()
        self.axis_prog.setValue(int(val * 100))

        if self.core.is_pressed:
            self.pressed_lbl.setText("Pedal State: PRESSED")
            self.pressed_lbl.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.pressed_lbl.setText("Pedal State: RELEASED")
            self.pressed_lbl.setStyleSheet("color: red; font-weight: bold;")

    def closeEvent(self, event):
        self.core.cleanup()
        event.accept()


def run_ui(core):
    app = QApplication(sys.argv)
    window = SifaPedalUI(core)
    window.show()
    sys.exit(app.exec())
