import sys
from assault.replay.loader import load_replay_from_json
from .viewer import ReplayViewer


def main():
    if len(sys.argv) < 2:
        print("Usage: play_replay.py <replay.json>")
        sys.exit(1)

    replay_path = sys.argv[1]
    replay = load_replay_from_json(replay_path)

    viewer = ReplayViewer(replay)
    viewer.run()


if __name__ == "__main__":
    main()