import pygame


def handle_input(viewer):
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False

            # Step backward
            if event.key == pygame.K_a:
                viewer.step = max(0, viewer.step - 1)

            # Step forward
            if event.key == pygame.K_d:
                viewer.step = min(
                    len(viewer.replay.states) - 1,
                    viewer.step + 1
                )

            # Toggle autoplay
            if event.key == pygame.K_SPACE:
                viewer.auto_play = not viewer.auto_play

    # Autoplay
    if viewer.auto_play:
        viewer.step += 1
        if viewer.step >= len(viewer.replay.states):
            viewer.step = len(viewer.replay.states) - 1
            viewer.auto_play = False

    return True