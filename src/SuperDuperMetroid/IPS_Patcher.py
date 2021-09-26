# Converts a hexadecimal string to a base 10 integer.
def hex_to_int(hex_to_convert):
    return int(hex_to_convert, 16)


# Converts binary data to a hexadecimal string.
def data_to_hex(data_to_convert):
    return "".join("{:02x}".format(x) for x in data_to_convert).upper()


# Reverses the endianness of a hexadecimal string.
def reverse_endianness(hex_to_reverse):
    assert (len(hex_to_reverse) % 2) == 0
    hex_pairs = []
    for i in range(len(hex_to_reverse) // 2):
        hex_pairs.append(hex_to_reverse[2 * i] + hex_to_reverse[2 * i + 1])
    reversed_hex_pairs = hex_pairs[::-1]
    output_string = ""
    for pair in reversed_hex_pairs:
        output_string += pair
    return output_string


# Pads a hexadecimal string with 0's until it meets the provided length.
def pad_hex(hex_to_pad, num_hex_characters):
    return_hex = hex_to_pad
    while len(return_hex) < num_hex_characters:
        return_hex = "0" + return_hex
    return return_hex


class IPSPatcher:
    # Read the next hunk's data and apply it to the ROM file.
    @staticmethod
    def read_and_apply_hunk(ips_file, rom_file):
        # Get the offset field
        offset_field = data_to_hex(ips_file.read(3))
        # print(offset_field)
        # If EOF, return False
        if offset_field == "454F46":  # Spells out "EOF"
            print("Reached EOF successfully, finishing IPS patch...")
            return False
        # Get the length field
        length_field = data_to_hex(ips_file.read(2))
        # Convert fields to integer
        patch_offset = hex_to_int(offset_field)
        patch_length = hex_to_int(length_field)
        # Apply hunk.
        rom_file.seek(patch_offset)
        if patch_length == 0:
            num_repeats = hex_to_int(data_to_hex(ips_file.read(2)))
            byte = ips_file.read(1)
            for i in range(num_repeats):
                rom_file.write(byte)
        else:
            # Patches tend to be short - format enforced - so this shouldn't(?) raise any errors.
            bytes = ips_file.read(patch_length)
            rom_file.write(bytes)
        return True

    # Read the first 5 bytes to verify that this is an IPS file.
    @staticmethod
    def verify_format(ips_file):
        verification_bytes = data_to_hex(ips_file.read(5))
        if verification_bytes == "5041544348":  # Spells out "PATCH"
            return True
        else:
            return False

    # Apply an IPS patch to a ROM, given the paths of an IPS file and a ROM file.
    @staticmethod
    def apply_ips_patch(ips_path, rom_path):
        print(f"Applying patch from file {ips_path}...")
        ips_file = open(ips_path, "rb")
        rom_file = open(rom_path, "r+b", buffering=0)
        if IPSPatcher.verify_format(ips_file):
            while IPSPatcher.read_and_apply_hunk(ips_file, rom_file):
                pass
            print(f"Finished applying patch {ips_path} successfully.")
        else:
            print(f"CRITICAL ERROR: Provided IPS file {ips_path} does not match the format specification!")
        ips_file.close()
        rom_file.close()


if __name__ == "__main__":
    print("Enter path to IPS file.")
    ips_path = input()
    print("Enter path to ROM file.")
    rom_path = input()
    IPSPatcher.apply_ips_patch(ips_path, rom_path)
