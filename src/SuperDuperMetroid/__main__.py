import json
from SuperDuperMetroid.ROM_Patcher import patch_rom_json
from io import BytesIO
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-rom-path", type=Path, required=True)
    parser.add_argument("--output-rom-path", type=Path, required=True)
    parser.add_argument("--json-path", type=Path, required=True)
    args = parser.parse_args()

    rom_file = BytesIO(args.input_rom_path.read_bytes())

    with args.json_path.open() as json_contents:
        patch_data = json.load(json_contents)

    patch_rom_json(rom_file, args.output_rom_path, patch_data)


if __name__ == "__main__":
    main()
