import json
from SuperDuperMetroid.ROM_Patcher import patch_rom_json
from io import BytesIO
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-rom-path", type=str, required=True)
    parser.add_argument("--output-rom-path", type=str, required=True)
    parser.add_argument("--json-path", type=str, required=True)
    args = parser.parse_args()

    with open(args.input_rom_path, "rb+") as fh:
        rom_file = BytesIO(fh.read())

    with open(args.json_path) as json_contents:
        patch_data = json.load(json_contents)

    patch_rom_json(rom_file, args.output_rom_path, patch_data)


if __name__ == "__main__":
    main()
