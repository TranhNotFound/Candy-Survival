import pygame
class PauseState:
    def __init__(self, game):
        self.game=game; self.font=pygame.font.SysFont(None,42)
        self.options=[("Continue", self.resume), ("Intructions", self.intructions), ("Back to menu", self.to_menu), ("Quit", self.quit)]; self.selected=0
    def resume(self): self.game.pop_state()
    def intructions(self):
        self.game.push_state("instructions")
    def to_menu(self): self.game.change_state("menu")
    def quit(self): self.game.running=False
    def handle_event(self, e):
        if e.type==pygame.KEYDOWN:
            if e.key in (pygame.K_UP, pygame.K_w): self.selected=(self.selected-1)%len(self.options)
            elif e.key in (pygame.K_DOWN, pygame.K_s): self.selected=(self.selected+1)%len(self.options)
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE): self.options[self.selected][1]()
    def update(self, dt): pass
    def draw(self, surf):
        overlay=pygame.Surface(surf.get_size(), pygame.SRCALPHA); overlay.fill((0,0,0,180)); surf.blit(overlay,(0,0))
        y=surf.get_height()//2 - 60
        for i,(name,_) in enumerate(self.options):
            color=(255,255,255) if i==self.selected else (180,180,180)
            txt=self.font.render(name,True,color); surf.blit(txt,(surf.get_width()//2 - txt.get_width()//2, y)); y+=60
