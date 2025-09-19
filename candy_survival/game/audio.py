import pygame

class Audio:
    def __init__(self):
        self.sounds={}; self.music_loaded=False
    def load(self):
        self.sounds["pickup"]=pygame.mixer.Sound("assets/audio/pickup.wav")
        self.sounds["radio"]=pygame.mixer.Sound("assets/audio/radio_beep.wav")
        self.sounds["success"]=pygame.mixer.Sound("assets/audio/success.wav")
        self.sounds["fail"]=pygame.mixer.Sound("assets/audio/fail.wav")
        try:
            pygame.mixer.music.load("assets/audio/bg_loop.wav")
            pygame.mixer.music.set_volume(0.2); self.music_loaded=True
        except pygame.error:
            self.music_loaded=False
    def play_music(self):
        if self.music_loaded: pygame.mixer.music.play(-1)
    def stop_music(self):
        if self.music_loaded: pygame.mixer.music.stop()
    def sfx(self, name):
        s=self.sounds.get(name); 
        if s: s.play()
