import pygame
class MenuState:
    def __init__(self, game):
        self.game=game
        self.font=pygame.font.SysFont(None,48)
        self.small=pygame.font.SysFont(None,28)
        self.options=[("New game", self.start), ("Intructions", self.instructions), ("Quit", self.quit)]
        self.selected=0
    def start(self): self.game.change_state("playing")
    def instructions(self): self.game.push_state("instructions")
    def quit(self): self.game.running=False
    def handle_event(self, e):
        if e.type==pygame.KEYDOWN:
            if e.key in (pygame.K_UP, pygame.K_w): self.selected=(self.selected-1)%len(self.options)
            elif e.key in (pygame.K_DOWN, pygame.K_s): self.selected=(self.selected+1)%len(self.options)
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE): self.options[self.selected][1]()
    def update(self, dt): pass
    def draw(self, surf):
        surf.fill((15,20,25))
        title=self.font.render("Candy Survival",True,(255,255,0))
        surf.blit(title,(surf.get_width()//2 - title.get_width()//2, 120))
        y=240
        for i,(name,_) in enumerate(self.options):
            color=(255,255,255) if i==self.selected else (180,180,180)
            txt=self.font.render(name,True,color)
            surf.blit(txt,(surf.get_width()//2 - txt.get_width()//2, y)); y+=60
        #hint=self.small.render("W/S to choose, Enter to commit. (Esc to pause)",True,(200,200,200))
        #surf.blit(hint,(surf.get_width()//2 - hint.get_width()//2, y+40))
