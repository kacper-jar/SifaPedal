import os

os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame
from pynput.keyboard import Controller, Key, KeyCode
import threading
import time


class SifaPedalCore:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()

        self.keyboard = Controller()

        self.joystick = None
        self.joystick_index = -1
        self.axis_index = 0
        self.threshold = 0.5
        self.deadzone = 0.05
        self.invert = False

        self.base_key = 'space'
        self.modifiers = {'ctrl': False, 'alt': False, 'shift': False}

        self.is_pressed = False
        self.running = False

        self.state = "Ready"
        self.last_released_time = 0.0

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
        """Briefly press and release keys for 'tap' mode."""
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
            return 0.0

        try:
            raw_value = self.joystick.get_axis(self.axis_index)
        except pygame.error:
            return 0.0

        return self.process_axis_value(raw_value)

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
            self.state = "Pedal pressed"

        elif not currently_pressed and self.is_pressed:
            self.is_pressed = False
            self.state = "Pedal released (Sifa Acknowledge keybind pressed)"
            self.last_released_time = time.time()
            threading.Thread(target=self.tap_keys, daemon=True).start()

        if not self.is_pressed and self.state != "Ready":
            if time.time() - self.last_released_time > 30.0:
                self.state = "Ready"

        return val

    def cleanup(self):
        pygame.quit()
