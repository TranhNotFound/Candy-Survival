import pygame, json

class InputManager:
    def __init__(self, settings_path):
        with open(settings_path,"r",encoding="utf-8") as f:
            self.settings = json.load(f)
        self.keymap = self._build_keymap(self.settings.get("keybinds", {}))

    def _build_keymap(self, keybinds):
        mapping={}
        for action, keyname in keybinds.items():
            key = getattr(pygame, f"K_{keyname.lower()}", None)
            if key is None:
                key = getattr(pygame, "K_" + keyname.lower(), pygame.K_UNKNOWN)
            mapping[action]=key
        return mapping

    def is_pressed(self, action, keys):
        key = self.keymap.get(action, None)
        if key is None or key == pygame.K_UNKNOWN:
            return False
        return keys[key]
