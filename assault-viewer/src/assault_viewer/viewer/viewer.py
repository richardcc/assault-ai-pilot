import pygame
from .drawing import draw_frame
from .input import handle_input


class ReplayViewer:
    def __init__(self, replay, width=1280, height=900):
        self.replay = replay
        self.step = 0
        self.auto_play = False

        self.width = width
        self.height = height

        pygame.init()
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Assault Replay Viewer")

        self.clock = pygame.time.Clock()

    def run(self):
        running = True

        while running:
            running = handle_input(self)
            draw_frame(self.screen, self.replay.states[self.step])

            pygame.display.flip()
            self.clock.tick(30)
