from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_line import hex_line

def main():
    print("START TEST")  # 👈 AÑADE ESTO

    a = HexCoord(0, 0)
    b = HexCoord(5, 4)

    line = hex_line(a, b)

    print("Line from A to B:")
    for h in line:
        print(f"({h.q},{h.r})")

if __name__ == "__main__":
    main()