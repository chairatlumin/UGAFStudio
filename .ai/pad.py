"""Gamepad controller for Agent Veil via vgamepad (ViGEmBus)."""
import time
import vgamepad as vg


class Pad:
    def __init__(self):
        self.pad = vg.VX360Gamepad()

    def press(self, button, t=0.15):
        self.pad.press_button(button=button)
        self.pad.update()
        time.sleep(t)
        self.pad.release_button(button=button)
        self.pad.update()

    def a(self, t=0.2):          # confirm / interact
        self.press(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, t)

    def b(self, t=0.15):         # back / cancel
        self.press(vg.XUSB_BUTTON.XUSB_GAMEPAD_B, t)

    def x(self, t=0.15):
        self.press(vg.XUSB_BUTTON.XUSB_GAMEPAD_X, t)

    def y(self, t=0.15):
        self.press(vg.XUSB_BUTTON.XUSB_GAMEPAD_Y, t)

    def dpad(self, direction, t=0.25):
        m = {
            "up": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
            "down": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
            "left": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
            "right": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
        }
        self.press(m[direction], t)

    def stick(self, lx=0.0, ly=0.0, rx=0.0, ry=0.0, t=0.5):
        """lx/ly left stick, rx/ry right stick; range -1..1."""
        self.pad.left_joystick_float(lx, ly)
        self.pad.right_joystick_float(rx, ry)
        self.pad.update()
        time.sleep(t)
        self.pad.left_joystick_float(0, 0)
        self.pad.right_joystick_float(0, 0)
        self.pad.update()

    def walk(self, lx, ly, seconds):
        """Hold left stick for movement."""
        end = time.time() + seconds
        while time.time() < end:
            self.pad.left_joystick_float(lx, ly)
            self.pad.update()
            time.sleep(0.05)
        self.pad.left_joystick_float(0, 0)
        self.pad.update()


if __name__ == "__main__":
    pad = Pad()
    print("pad ready")
