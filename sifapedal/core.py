import os

os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame
from pynput.keyboard import Controller, Key, KeyCode
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

        self.base_key = 'space'
        self.modifiers = {'ctrl': False, 'alt': False, 'shift': False}

        self.target_joystick_name = ''
        self.load_config()

        self.is_pressed = False
        self.running = False
        self.has_moved = False

        self.state = PedalState.NO_JOYSTICK
        self.last_action_time = 0.0

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                self.axis_index = config.get('axis_index', 0)
                self.threshold = config.get('threshold', 0.5)
                self.deadzone = config.get('deadzone', 0.05)
                self.invert = config.get('invert', False)
                self.base_key = config.get('base_key', 'space')
                self.modifiers = config.get('modifiers', {'ctrl': False, 'alt': False, 'shift': False})
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
            'base_key': self.base_key,
            'modifiers': self.modifiers
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

    def _press_keys(self):
        if self.modifiers['ctrl']: self.keyboard.press(Key.ctrl)
        if self.modifiers['alt']: self.keyboard.press(Key.alt)
        if self.modifiers['shift']: self.keyboard.press(Key.shift)

        key = self.parse_key(self.base_key)
        self.keyboard.press(key)

    def _release_keys(self):
        key = self.parse_key(self.base_key)
        self.keyboard.release(key)

        if self.modifiers['shift']: self.keyboard.release(Key.shift)
        if self.modifiers['alt']: self.keyboard.release(Key.alt)
        if self.modifiers['ctrl']: self.keyboard.release(Key.ctrl)

    def tap_keys(self):
        """Briefly press and release keys."""
        self._press_keys()
        time.sleep(0.05)
        self._release_keys()

    def tick(self):
        """
        To be called periodically (e.g. from UI main loop or a thread).
        Pumps pygame events and processes the selected axis.
        Returns the current axis value, or 0.0 if not available.
        """
        pygame.event.pump()

        if self.joystick is None:
            self.set_state(PedalState.NO_JOYSTICK)
            return 0.0

        try:
            raw_value = self.joystick.get_axis(self.axis_index)
        except pygame.error:
            self.set_state(PedalState.NO_JOYSTICK)
            return 0.0

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
            if self.state == PedalState.WAITING_FOR_REPRESS:
                self.set_state(PedalState.SIFA_ACKNOWLEDGED)
                threading.Thread(target=self.tap_keys, daemon=True).start()
            else:
                self.set_state(PedalState.PEDAL_PRESSED)

        elif not currently_pressed and self.is_pressed:
            self.is_pressed = False
            self.set_state(PedalState.WAITING_FOR_REPRESS)

        time_since_action = time.time() - self.last_action_time

        if self.state == PedalState.SIFA_ACKNOWLEDGED:
            if time_since_action > 30.0:
                self.set_state(PedalState.READY)
            elif time_since_action > 5.0:
                self.state = PedalState.PEDAL_PRESSED
        elif self.state == PedalState.PEDAL_PRESSED:
            if time_since_action > 30.0:
                self.set_state(PedalState.READY)
        elif self.state == PedalState.WAITING_FOR_REPRESS:
            if time_since_action > 30.0:
                self.set_state(PedalState.READY)

        return val

    def cleanup(self):
        pygame.quit()
