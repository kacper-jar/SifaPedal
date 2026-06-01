import os

os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame
from pynput.keyboard import Controller, Key, KeyCode, Listener
import threading
import time
import json
from enum import Enum
from sifapedal import Utils


class PedalState(Enum):
    NO_JOYSTICK = "No joystick/axis selected"
    READY = "Ready"
    PEDAL_PRESSED = "Pedal pressed"
    WAITING_FOR_REPRESS = "Waiting for repress"
    SIFA_ACKNOWLEDGED = "Sifa acknowledged"
    EMERGENCY_BRAKE = "Emergency brake applied"
    PAUSED = "Paused (Station Mode)"


class SifaPedalCore:
    def __init__(self):
        self.utils = Utils()

        pygame.init()
        pygame.joystick.init()

        self.keyboard = Controller()

        self.joystick = None
        self.joystick_index = -1
        self.config_file = self.utils.config_path

        self.axis_index = 0
        self.threshold = 0.5
        self.deadzone = 0.05
        self.invert = False

        self.sifa_base_key = 'space'
        self.sifa_modifiers = {'ctrl': False, 'alt': False, 'shift': False}

        self.emergency_brake_enabled = False
        self.emergency_brake_timeout = 3.0
        self.emergency_brake_key = 'backspace'
        self.emergency_brake_modifiers = {'ctrl': False, 'alt': False, 'shift': False}

        self.target_joystick_name = ''
        self.station_mode_key = '\\'
        self.station_mode_modifiers = {'ctrl': False, 'alt': False, 'shift': False}
        self.load_config()

        self.is_pressed = False
        self.running = False
        self.has_moved = False
        self.is_paused = False

        self.state = PedalState.NO_JOYSTICK
        self.last_action_time = 0.0

        self.current_modifiers = set()
        self.listener = Listener(on_press=self.on_key_press, on_release=self.on_key_release)
        self.listener.start()

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                self.axis_index = config.get('axis_index', 0)
                self.threshold = config.get('threshold', 0.5)
                self.deadzone = config.get('deadzone', 0.05)
                self.invert = config.get('invert', False)
                self.sifa_base_key = config.get('sifa_base_key', config.get('base_key', 'space'))
                self.sifa_modifiers = config.get('sifa_modifiers',
                                                 config.get('modifiers', {'ctrl': False, 'alt': False, 'shift': False}))
                self.emergency_brake_enabled = config.get('emergency_brake_enabled', False)
                self.emergency_brake_timeout = config.get('emergency_brake_timeout', 3.0)
                self.emergency_brake_key = config.get('emergency_brake_key', 'backspace')
                self.emergency_brake_modifiers = config.get('emergency_brake_modifiers',
                                                            {'ctrl': False, 'alt': False, 'shift': False})
                self.station_mode_key = config.get('station_mode_key', '\\')
                self.station_mode_modifiers = config.get('station_mode_modifiers',
                                                         {'ctrl': False, 'alt': False, 'shift': False})
                self.target_joystick_name = config.get('joystick_name', '')
            except Exception as e:
                print(f"Failed to load config: {e}")

    def save_config(self):
        joystick_name = ''
        if self.joystick is not None:
            joystick_name = self.joystick.get_name()

        config = {
            'joystick_name': joystick_name,
            'axis_index': self.axis_index,
            'threshold': self.threshold,
            'deadzone': self.deadzone,
            'invert': self.invert,
            'sifa_base_key': self.sifa_base_key,
            'sifa_modifiers': self.sifa_modifiers,
            'emergency_brake_enabled': self.emergency_brake_enabled,
            'emergency_brake_timeout': self.emergency_brake_timeout,
            'emergency_brake_key': self.emergency_brake_key,
            'emergency_brake_modifiers': self.emergency_brake_modifiers,
            'station_mode_key': self.station_mode_key,
            'station_mode_modifiers': self.station_mode_modifiers
        }
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")

    def refresh_joysticks(self):
        """Returns a list of tuples (index, name) for all connected joysticks."""
        pygame.joystick.quit()
        pygame.joystick.init()
        joysticks = []
        for x in range(pygame.joystick.get_count()):
            j = pygame.joystick.Joystick(x)
            joysticks.append((x, j.get_name()))
        return joysticks

    def select_joystick(self, index):
        """Initializes the selected joystick."""
        if self.joystick is not None:
            self.joystick.quit()

        self.has_moved = False

        if 0 <= index < pygame.joystick.get_count():
            self.joystick = pygame.joystick.Joystick(index)
            self.joystick.init()
            self.joystick_index = index
            return True
        self.joystick = None
        self.joystick_index = -1
        return False

    def get_num_axes(self):
        if self.joystick is not None:
            return self.joystick.get_numaxes()
        return 0

    def parse_key(self, key_str):
        key_str = key_str.lower().strip()
        if hasattr(Key, key_str):
            return getattr(Key, key_str)
        elif len(key_str) == 1:
            return KeyCode.from_char(key_str)
        return Key.space

    def _press_sifa_keys(self):
        if self.sifa_modifiers['ctrl']: self.keyboard.press(Key.ctrl)
        if self.sifa_modifiers['alt']: self.keyboard.press(Key.alt)
        if self.sifa_modifiers['shift']: self.keyboard.press(Key.shift)

        key = self.parse_key(self.sifa_base_key)
        self.keyboard.press(key)

    def _release_sifa_keys(self):
        key = self.parse_key(self.sifa_base_key)
        self.keyboard.release(key)

        if self.sifa_modifiers['shift']: self.keyboard.release(Key.shift)
        if self.sifa_modifiers['alt']: self.keyboard.release(Key.alt)
        if self.sifa_modifiers['ctrl']: self.keyboard.release(Key.ctrl)

    def tap_keys(self):
        """Briefly press and release keys."""
        self._press_sifa_keys()
        time.sleep(0.05)
        self._release_sifa_keys()

    def _press_emergency_brake_keys(self):
        if self.emergency_brake_modifiers['ctrl']: self.keyboard.press(Key.ctrl)
        if self.emergency_brake_modifiers['alt']: self.keyboard.press(Key.alt)
        if self.emergency_brake_modifiers['shift']: self.keyboard.press(Key.shift)

        key = self.parse_key(self.emergency_brake_key)
        self.keyboard.press(key)

    def _release_emergency_brake_keys(self):
        key = self.parse_key(self.emergency_brake_key)
        self.keyboard.release(key)

        if self.emergency_brake_modifiers['shift']: self.keyboard.release(Key.shift)
        if self.emergency_brake_modifiers['alt']: self.keyboard.release(Key.alt)
        if self.emergency_brake_modifiers['ctrl']: self.keyboard.release(Key.ctrl)

    def tap_emergency_brake_keys(self):
        """Briefly press and release emergency brake keys."""
        self._press_emergency_brake_keys()
        time.sleep(0.05)
        self._release_emergency_brake_keys()

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.set_state(PedalState.PAUSED)
        else:
            self.set_state(PedalState.READY if self.joystick else PedalState.NO_JOYSTICK)
            self.has_moved = False
            self.is_pressed = False

    def on_key_press(self, key):
        if hasattr(key, 'name'):
            if key.name in ('ctrl', 'ctrl_l', 'ctrl_r'): self.current_modifiers.add('ctrl')
            if key.name in ('alt', 'alt_l', 'alt_r', 'alt_gr'): self.current_modifiers.add('alt')
            if key.name in ('shift', 'shift_l', 'shift_r'): self.current_modifiers.add('shift')

        target_key = self.parse_key(self.station_mode_key)

        match = False
        if hasattr(key, 'char') and hasattr(target_key, 'char'):
            if key.char and target_key.char and key.char.lower() == target_key.char.lower():
                match = True
        elif key == target_key:
            match = True

        if match:
            if (self.station_mode_modifiers['ctrl'] == ('ctrl' in self.current_modifiers) and
                    self.station_mode_modifiers['alt'] == ('alt' in self.current_modifiers) and
                    self.station_mode_modifiers['shift'] == ('shift' in self.current_modifiers)):
                self.toggle_pause()

    def on_key_release(self, key):
        if hasattr(key, 'name'):
            if key.name in ('ctrl', 'ctrl_l', 'ctrl_r'): self.current_modifiers.discard('ctrl')
            if key.name in ('alt', 'alt_l', 'alt_r', 'alt_gr'): self.current_modifiers.discard('alt')
            if key.name in ('shift', 'shift_l', 'shift_r'): self.current_modifiers.discard('shift')

    def tick(self):
        """
        To be called periodically (e.g. from UI main loop or a thread).
        Pumps pygame events and processes the selected axis.
        Returns the current axis value, or 0.0 if not available.
        """
        pygame.event.pump()

        if self.joystick is None:
            if not self.is_paused:
                self.set_state(PedalState.NO_JOYSTICK)
            return 0.0

        try:
            raw_value = self.joystick.get_axis(self.axis_index)
        except pygame.error:
            if not self.is_paused:
                self.set_state(PedalState.NO_JOYSTICK)
            return 0.0

        if self.is_paused:
            val = (raw_value + 1.0) / 2.0
            if self.invert: val = 1.0 - val
            if val < self.deadzone: val = 0.0
            return val

        if self.state == PedalState.NO_JOYSTICK:
            self.set_state(PedalState.READY)

        if not self.has_moved:
            if abs(raw_value) < 0.05:
                raw_value = 1.0 if self.invert else -1.0
            else:
                self.has_moved = True

        return self.process_axis_value(raw_value)

    def set_state(self, new_state):
        self.state = new_state
        self.last_action_time = time.time()

    def process_axis_value(self, value):
        """Processes the raw axis value and triggers key events if necessary."""
        val = (value + 1.0) / 2.0

        if self.invert:
            val = 1.0 - val

        if val < self.deadzone:
            val = 0.0

        currently_pressed = (val >= self.threshold)

        if currently_pressed and not self.is_pressed:
            self.is_pressed = True
            if self.state in (PedalState.WAITING_FOR_REPRESS, PedalState.EMERGENCY_BRAKE):
                self.set_state(PedalState.SIFA_ACKNOWLEDGED)
                threading.Thread(target=self.tap_keys, daemon=True).start()
            else:
                self.set_state(PedalState.PEDAL_PRESSED)

        elif not currently_pressed and self.is_pressed:
            self.is_pressed = False
            self.set_state(PedalState.WAITING_FOR_REPRESS)

        time_since_action = time.time() - self.last_action_time

        if self.state == PedalState.SIFA_ACKNOWLEDGED:
            if time_since_action > 5.0:
                self.state = PedalState.PEDAL_PRESSED
        elif self.state == PedalState.WAITING_FOR_REPRESS:
            if self.emergency_brake_enabled and time_since_action > self.emergency_brake_timeout:
                self.set_state(PedalState.EMERGENCY_BRAKE)
                threading.Thread(target=self.tap_emergency_brake_keys, daemon=True).start()
            elif time_since_action > 30.0:
                self.set_state(PedalState.READY)
        elif self.state == PedalState.EMERGENCY_BRAKE:
            if time_since_action > 30.0:
                self.set_state(PedalState.READY)

        return val

    def cleanup(self):
        if hasattr(self, 'listener'):
            self.listener.stop()
        pygame.quit()
