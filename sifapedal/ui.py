import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QComboBox, QPushButton, QCheckBox,
    QSlider, QFormLayout, QProgressBar, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QTimer

from sifapedal import __version__, PedalState


class SifaPedalUI(QMainWindow):
    def __init__(self, core):
        super().__init__()
        self.core = core

        self.setWindowTitle(f"SifaPedal {__version__}")
        self.setMinimumSize(400, 760)
        self.setMaximumSize(400, 760)

        self.rebind_target = None

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
        self.joystick_cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.joystick_cb.setMinimumContentsLength(10)
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

        sens_group = QGroupBox("Pedal Configuration")
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
        self.thresh_slider.setValue(int(self.core.threshold * 100))
        self.thresh_slider.valueChanged.connect(self.on_sensitivity_changed)
        row_thresh.addWidget(self.thresh_slider)
        self.thresh_lbl = QLabel(f"{self.core.threshold:.2f}")
        row_thresh.addWidget(self.thresh_lbl)
        sens_layout.addRow("Threshold:", row_thresh)

        row_dead = QHBoxLayout()
        self.dead_slider = QSlider(Qt.Orientation.Horizontal)
        self.dead_slider.setRange(0, 100)
        self.dead_slider.setValue(int(self.core.deadzone * 100))
        self.dead_slider.valueChanged.connect(self.on_sensitivity_changed)
        row_dead.addWidget(self.dead_slider)
        self.dead_lbl = QLabel(f"{self.core.deadzone:.2f}")
        row_dead.addWidget(self.dead_lbl)
        sens_layout.addRow("Deadzone:", row_dead)

        self.invert_chk = QCheckBox("Invert")
        self.invert_chk.setChecked(self.core.invert)
        self.invert_chk.stateChanged.connect(self.on_sensitivity_changed)
        sens_layout.addRow("", self.invert_chk)

        sens_group.setLayout(sens_layout)
        self.main_layout.addWidget(sens_group)

        key_group = QGroupBox("In-game Sifa")
        key_layout = QFormLayout()
        key_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        key_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        row_key = QHBoxLayout()
        self.key_lbl = QLabel(self.core.sifa_base_key)
        self.key_lbl.setStyleSheet(
            "font-weight: bold; padding: 4px; background-color: rgba(0,0,0,0.1); border-radius: 4px;")
        self.key_btn = QPushButton("Rebind")
        self.key_btn.clicked.connect(self.start_rebind_sifa)
        row_key.addWidget(self.key_lbl, 1)
        row_key.addWidget(self.key_btn)
        key_layout.addRow("Base Key:", row_key)

        row_mods = QHBoxLayout()
        self.ctrl_chk = QCheckBox("Ctrl")
        self.alt_chk = QCheckBox("Alt")
        self.shift_chk = QCheckBox("Shift")
        self.ctrl_chk.setChecked(self.core.sifa_modifiers['ctrl'])
        self.alt_chk.setChecked(self.core.sifa_modifiers['alt'])
        self.shift_chk.setChecked(self.core.sifa_modifiers['shift'])
        self.ctrl_chk.stateChanged.connect(self.on_sifa_modifiers_changed)
        self.alt_chk.stateChanged.connect(self.on_sifa_modifiers_changed)
        self.shift_chk.stateChanged.connect(self.on_sifa_modifiers_changed)
        row_mods.addWidget(self.ctrl_chk)
        row_mods.addWidget(self.alt_chk)
        row_mods.addWidget(self.shift_chk)
        row_mods.addStretch()
        key_layout.addRow("Modifiers:", row_mods)

        key_group.setLayout(key_layout)
        self.main_layout.addWidget(key_group)

        ebrake_group = QGroupBox("In-game Emergency Brake")
        ebrake_layout = QVBoxLayout()

        self.ebrake_chk = QCheckBox("Enable Emergency Brake on no pedal repress")
        self.ebrake_chk.setChecked(self.core.emergency_brake_enabled)
        self.ebrake_chk.stateChanged.connect(self.on_ebrake_toggled)
        ebrake_layout.addWidget(self.ebrake_chk)

        self.ebrake_inner_widget = QWidget()
        ebrake_inner_layout = QFormLayout(self.ebrake_inner_widget)
        ebrake_inner_layout.setContentsMargins(0, 0, 0, 0)
        ebrake_inner_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        ebrake_inner_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.ebrake_spin = QDoubleSpinBox()
        self.ebrake_spin.setRange(0.1, 60.0)
        self.ebrake_spin.setSingleStep(0.5)
        self.ebrake_spin.setSuffix("s")
        self.ebrake_spin.setValue(self.core.emergency_brake_timeout)
        self.ebrake_spin.valueChanged.connect(self.on_ebrake_config_changed)
        ebrake_inner_layout.addRow("Timeout:", self.ebrake_spin)

        row_ebrake_key = QHBoxLayout()
        self.ebrake_key_lbl = QLabel(self.core.emergency_brake_key)
        self.ebrake_key_lbl.setStyleSheet(
            "font-weight: bold; padding: 4px; background-color: rgba(0,0,0,0.1); border-radius: 4px;")
        self.ebrake_key_btn = QPushButton("Rebind")
        self.ebrake_key_btn.clicked.connect(self.start_rebind_ebrake)
        row_ebrake_key.addWidget(self.ebrake_key_lbl, 1)
        row_ebrake_key.addWidget(self.ebrake_key_btn)
        ebrake_inner_layout.addRow("Base Key:", row_ebrake_key)

        row_ebrake_mods = QHBoxLayout()
        self.ebrake_ctrl_chk = QCheckBox("Ctrl")
        self.ebrake_alt_chk = QCheckBox("Alt")
        self.ebrake_shift_chk = QCheckBox("Shift")
        self.ebrake_ctrl_chk.setChecked(self.core.emergency_brake_modifiers['ctrl'])
        self.ebrake_alt_chk.setChecked(self.core.emergency_brake_modifiers['alt'])
        self.ebrake_shift_chk.setChecked(self.core.emergency_brake_modifiers['shift'])
        self.ebrake_ctrl_chk.stateChanged.connect(self.on_ebrake_config_changed)
        self.ebrake_alt_chk.stateChanged.connect(self.on_ebrake_config_changed)
        self.ebrake_shift_chk.stateChanged.connect(self.on_ebrake_config_changed)
        row_ebrake_mods.addWidget(self.ebrake_ctrl_chk)
        row_ebrake_mods.addWidget(self.ebrake_alt_chk)
        row_ebrake_mods.addWidget(self.ebrake_shift_chk)
        row_ebrake_mods.addStretch()
        ebrake_inner_layout.addRow("Modifiers:", row_ebrake_mods)

        ebrake_layout.addWidget(self.ebrake_inner_widget)
        ebrake_group.setLayout(ebrake_layout)
        self.main_layout.addWidget(ebrake_group)

        self.on_ebrake_toggled()

        station_group = QGroupBox("Station Mode (Sifa Pause)")
        station_layout = QFormLayout()
        station_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        station_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        desc_lbl = QLabel(
            "Temporarily prevents emergency brake activation caused by releasing the pedal while stopped at a station."
            "\nPress the selected below keybind when you stop at the station and leave the station or disable automatic"
            " emergency break.")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: gray; font-style: italic; margin-bottom: 4px;")
        station_layout.addRow(desc_lbl)

        row_station_key = QHBoxLayout()
        self.station_key_lbl = QLabel(self.core.station_mode_key)
        self.station_key_lbl.setStyleSheet(
            "font-weight: bold; padding: 4px; background-color: rgba(0,0,0,0.1); border-radius: 4px;")
        self.station_key_btn = QPushButton("Rebind")
        self.station_key_btn.clicked.connect(self.start_rebind_station)
        row_station_key.addWidget(self.station_key_lbl, 1)
        row_station_key.addWidget(self.station_key_btn)
        station_layout.addRow("Toggle Key:", row_station_key)

        row_station_mods = QHBoxLayout()
        self.station_ctrl_chk = QCheckBox("Ctrl")
        self.station_alt_chk = QCheckBox("Alt")
        self.station_shift_chk = QCheckBox("Shift")
        self.station_ctrl_chk.setChecked(self.core.station_mode_modifiers['ctrl'])
        self.station_alt_chk.setChecked(self.core.station_mode_modifiers['alt'])
        self.station_shift_chk.setChecked(self.core.station_mode_modifiers['shift'])
        self.station_ctrl_chk.stateChanged.connect(self.on_station_mods_changed)
        self.station_alt_chk.stateChanged.connect(self.on_station_mods_changed)
        self.station_shift_chk.stateChanged.connect(self.on_station_mods_changed)
        row_station_mods.addWidget(self.station_ctrl_chk)
        row_station_mods.addWidget(self.station_alt_chk)
        row_station_mods.addWidget(self.station_shift_chk)
        row_station_mods.addStretch()
        station_layout.addRow("Modifiers:", row_station_mods)

        station_group.setLayout(station_layout)
        self.main_layout.addWidget(station_group)

        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout()
        self.pressed_lbl = QLabel("Ready")
        self.pressed_lbl.setStyleSheet("color: gray; font-weight: bold;")
        status_layout.addWidget(self.pressed_lbl)
        status_group.setLayout(status_layout)
        self.main_layout.addWidget(status_group)

        self.main_layout.addStretch()

    def on_ebrake_toggled(self):
        enabled = self.ebrake_chk.isChecked()
        self.core.emergency_brake_enabled = enabled
        self.ebrake_inner_widget.setEnabled(enabled)
        self.core.save_config()

    def on_ebrake_config_changed(self):
        self.core.emergency_brake_timeout = self.ebrake_spin.value()
        self.core.emergency_brake_modifiers['ctrl'] = self.ebrake_ctrl_chk.isChecked()
        self.core.emergency_brake_modifiers['alt'] = self.ebrake_alt_chk.isChecked()
        self.core.emergency_brake_modifiers['shift'] = self.ebrake_shift_chk.isChecked()
        self.core.save_config()

    def start_rebind_sifa(self):
        self.rebind_target = 'sifa'
        self.key_lbl.setText("Press any key...")
        self.key_btn.setText("Cancel")
        self.key_btn.clicked.disconnect()
        self.key_btn.clicked.connect(self.cancel_rebind_sifa)
        self.setFocus()

    def cancel_rebind_sifa(self):
        self.rebind_target = None
        self.key_lbl.setText(self.core.sifa_base_key)
        self.key_btn.setText("Rebind")
        self.key_btn.clicked.disconnect()
        self.key_btn.clicked.connect(self.start_rebind_sifa)
        self.core.save_config()

    def start_rebind_ebrake(self):
        self.rebind_target = 'ebrake'
        self.ebrake_key_lbl.setText("Press any key...")
        self.ebrake_key_btn.setText("Cancel")
        self.ebrake_key_btn.clicked.disconnect()
        self.ebrake_key_btn.clicked.connect(self.cancel_rebind_ebrake)
        self.setFocus()

    def cancel_rebind_ebrake(self):
        self.rebind_target = None
        self.ebrake_key_lbl.setText(self.core.emergency_brake_key)
        self.ebrake_key_btn.setText("Rebind")
        self.ebrake_key_btn.clicked.disconnect()
        self.ebrake_key_btn.clicked.connect(self.start_rebind_ebrake)
        self.core.save_config()

    def on_station_mods_changed(self):
        self.core.station_mode_modifiers['ctrl'] = self.station_ctrl_chk.isChecked()
        self.core.station_mode_modifiers['alt'] = self.station_alt_chk.isChecked()
        self.core.station_mode_modifiers['shift'] = self.station_shift_chk.isChecked()
        self.core.save_config()

    def start_rebind_station(self):
        self.rebind_target = 'station'
        self.station_key_lbl.setText("Press any key...")
        self.station_key_btn.setText("Cancel")
        self.station_key_btn.clicked.disconnect()
        self.station_key_btn.clicked.connect(self.cancel_rebind_station)
        self.setFocus()

    def cancel_rebind_station(self):
        self.rebind_target = None
        self.station_key_lbl.setText(self.core.station_mode_key)
        self.station_key_btn.setText("Rebind")
        self.station_key_btn.clicked.disconnect()
        self.station_key_btn.clicked.connect(self.start_rebind_station)
        self.core.save_config()

    def keyPressEvent(self, event):
        if not self.rebind_target:
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

        if self.rebind_target == 'sifa':
            self.core.sifa_base_key = key_str
            self.cancel_rebind_sifa()
        elif self.rebind_target == 'ebrake':
            self.core.emergency_brake_key = key_str
            self.cancel_rebind_ebrake()
        elif self.rebind_target == 'station':
            self.core.station_mode_key = key_str
            self.cancel_rebind_station()

    def refresh_joysticks(self):
        self.joysticks_data = self.core.refresh_joysticks()
        self.joystick_cb.blockSignals(True)
        self.joystick_cb.clear()

        if self.joysticks_data:
            target_idx = 0
            for i, (idx, name) in enumerate(self.joysticks_data):
                self.joystick_cb.addItem(f"{idx}: {name}")
                if name == self.core.target_joystick_name:
                    target_idx = i
            self.joystick_cb.blockSignals(False)
            self.joystick_cb.setCurrentIndex(target_idx)
            self.on_joystick_selected(target_idx)
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
                    if self.core.axis_index < num_axes:
                        self.axis_cb.setCurrentIndex(self.core.axis_index)
                        self.on_axis_selected(self.core.axis_index)
                    else:
                        self.axis_cb.setCurrentIndex(0)
                        self.on_axis_selected(0)
                else:
                    self.axis_cb.addItem("No axes on this device")
                    self.axis_cb.blockSignals(False)
            self.core.save_config()

    def on_axis_selected(self, index):
        if index >= 0:
            self.core.axis_index = index
            self.core.save_config()

    def on_sifa_modifiers_changed(self):
        self.core.sifa_modifiers['ctrl'] = self.ctrl_chk.isChecked()
        self.core.sifa_modifiers['alt'] = self.alt_chk.isChecked()
        self.core.sifa_modifiers['shift'] = self.shift_chk.isChecked()
        self.core.save_config()

    def on_sensitivity_changed(self):
        t = self.thresh_slider.value() / 100.0
        d = self.dead_slider.value() / 100.0
        self.core.threshold = t
        self.core.deadzone = d
        self.core.invert = self.invert_chk.isChecked()
        self.thresh_lbl.setText(f"{t:.2f}")
        self.dead_lbl.setText(f"{d:.2f}")
        self.core.save_config()

    def poll_core(self):
        val = self.core.tick()
        self.axis_prog.setValue(int(val * 100))

        self.pressed_lbl.setText(self.core.state.value)
        if self.core.state in (PedalState.READY, PedalState.PAUSED):
            self.pressed_lbl.setStyleSheet("color: gray; font-weight: bold;")
        elif self.core.state in (PedalState.PEDAL_PRESSED, PedalState.SIFA_ACKNOWLEDGED):
            self.pressed_lbl.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.pressed_lbl.setStyleSheet("color: red; font-weight: bold;")

    def closeEvent(self, event):
        self.core.cleanup()
        event.accept()


def run_ui(core):
    app = QApplication(sys.argv)
    window = SifaPedalUI(core)
    window.show()
    sys.exit(app.exec())
