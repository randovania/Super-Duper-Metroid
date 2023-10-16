# Super Duper Metroid - A Super Metroid Randomizer Placement Patcher
# Written by Samuel D. Roy
#
# Thanks to Metroid Construction for its detailed RAM and ROM maps.
# https://wiki.metroidconstruction.com/doku.php?id=super_metroid
#
# Thanks to Jathys for a plethora of miscellaneous additional documentation.
# Their work helped me decode a lot of the more in-depth game functionality.
# https://jathys.zophar.net/supermetroid/
#
# Thanks to Kazuto for their More Efficient Item PLMs Hacks.
# This is what allows custom items to work.
# https://www.metroidconstruction.com/resource.php?id=349
#
# Thanks to PHOSPHOTiDYL for their Skip Intro Saves hack, which enables custom save start,
# As well as custom starting items.
# https://metroidconstruction.com/resource.php?id=265
#
# Designed for HEADERLESS ROMS ONLY!
#
# It is recommended to use a monospace font when reading this code.
# Many tables are formatted to take advantage of monospace fonts.
# I personally use OCRA.
#
# FOR DEVELOPERS:
#
# Breakdown of memory changes:
#
# Message Box code edits are made to 4 minor functions in bank 85.
# Bank 85 also has 4 more routines appended to the start of free space,
# Along with routines to replace pickup effects for game items.
# In bank 85, starting at $85:9A00, we write 5 tables to ROM, each 2 pages long.
# TODO: Shift tables forward to make room for more routines.
# Each entry in each table is 2 bytes long.
# For each item in the game, these point to, in order:
# * Pointer to Messagebox Header/Footer tilemap
# * Pointer to Messagebox Content tilemap
# * The size of the Messagebox content in memory
# * The messagebox ID, functionally equivalent to the value stored in RAM at $7E:1C1F
#   when the Messagebox code is being executed.
# * Pointer to the collection code to run for this item
#
# Item PLM References are overwritten with the appropriate new type in bank $8F
#
# RAM address $7FFF72-$7FFF73 is the routine in bank 83 to jump to.
# RAM address $7FFF74-$7FFF75 is nonzero when we haven't been sent an item.
# RAM address $7FFF76-$7FFF7F are occupied by values for a multiworld item we've been
# Given. Same as the 5 values we have tables for.
#
# RAM addresses $7FFF8E-$7FFFFF are occupied by a copy of the game's item bitflags,
# Which are used to determine which item a player has picked up.
#
# Kazuto's More Efficient PLMs patch is applied, and changes are present
# in banks $84 and $89.

import json
import os
import random
from pathlib import Path

from SuperDuperMetroid.IPS_Patcher import IPSPatcher
from SuperDuperMetroid.SM_Constants import SuperMetroidConstants
from SuperDuperMetroid.SM_Room_Header_Data import DoorData, SMRooms
from enum import Enum
from io import BytesIO

VRAM_ITEMS_PATH = Path(__file__).with_name(name="VramItems.bin")


class MessageBoxGenerator:
    # List of characters that messages are allowed to have.
    # Note that messages will be converted to uppercase
    # Before removing invalid characters.
    allowedCharacterList = [
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "J",
        "K",
        "L",
        "M",
        "N",
        "O",
        "P",
        "Q",
        "R",
        "S",
        "T",
        "U",
        "V",
        "W",
        "X",
        "Y",
        "Z",
        "%",
        " ",
        "&",
        "-",
        ".",
        ",",
        "'",
        "?",
        "!",
    ]

    # First digit of tuple is row in tilemap, second is column.
    # The messagebox character tilemap is 16x16.
    characterToTilemapPosDict = {
        "1": (0, 0),
        "2": (0, 1),
        "3": (0, 2),
        "4": (0, 3),
        "5": (0, 4),
        "6": (0, 5),
        "7": (0, 6),
        "8": (0, 7),
        "9": (0, 8),
        "0": (0, 9),
        "%": (0, 10),
        " ": (4, 14),
        "&": (12, 8),
        "-": (12, 15),
        "A": (14, 0),
        "B": (14, 1),
        "C": (14, 2),
        "D": (14, 3),
        "E": (14, 4),
        "F": (14, 5),
        "G": (14, 6),
        "H": (14, 7),
        "I": (14, 8),
        "J": (14, 9),
        "K": (14, 10),
        "L": (14, 11),
        "M": (14, 12),
        "N": (14, 13),
        "O": (14, 14),
        "P": (14, 15),
        "Q": (15, 0),
        "R": (15, 1),
        "S": (15, 2),
        "T": (15, 3),
        "U": (15, 4),
        "V": (15, 5),
        "W": (15, 6),
        "X": (15, 7),
        "Y": (15, 8),
        "Z": (15, 9),
        ".": (15, 10),
        ",": (15, 11),
        "'": (15, 12),
        "?": (15, 14),
        "!": (15, 15),
    }

    maxMessageLengths = {"Small": 19, "Large": 26}

    # Maximum length in characters of a standard message box.
    # Technically some, like the missile pickup, are bigger, but we're ignoring those.
    messageBoxMaxLength = 19

    # Create the message box generator.
    # TODO: Place initial method *after* appended messagebox routines.
    def __init__(self, rom_file, initial_address="029643"):
        self.currentAddress = initial_address
        self.messageBoxList = {}
        self.file = rom_file
        self.smallMessagePointerTable = {}
        self.largeMessagePointerTable = {}

    # Change this message to be usable.
    def conform_message_to_format(self, message_text, message_box_size):
        # First we convert the message to uppercase only.
        message_text = message_text.upper()

        # Now we strip out any characters that we can't have in our message.
        stripped_message = ""
        for message_char in message_text:
            if message_char in self.allowedCharacterList:
                stripped_message += message_char
        # Tell the user if their message contains unsupported characters
        if len(message_text) > len(stripped_message):
            print(
                "WARNING: Message box text "
                + message_text
                + " contains unsupported characters. These will be stripped from the message.\nMessage boxes support the latin alphabet (will be converted to uppercase only), the arabic numerals 0-9, spaces, and a limited set of miscellaneous characters: ?!,.'&-%"
            )
        message_text = stripped_message

        # If the message is too long, cut it off.
        # We'll also include a warning if this happens.
        if len(message_text) > maxMessageLengths(message_box_size):
            print(
                f"WARNING: Message box text {message_text} exceeds maximum length of message box. Message will be cut to first 19 characters."
            )
            message_text = message_text[: maxMessageLengths(message_box_size)]
        return message_text

    # Generate and write the hex of a line of message to the file.
    def generate_messagebox(self, message_text, message_box_size):
        message_text = self.conform_message_to_format(message_text, message_box_size)

        # Get the raw text of the message.
        # Pad the message with spaces if it doesn't take up the whole line.
        num_spaces = maxMessageLengths(message_box_size) - len(message_text)
        actual_message_string = floor(num_spaces / 2) * " " + message_text
        num_spaces -= floor(num_spaces / 2)
        actual_message_string += " " * num_spaces

        # Convert our stuff to a hex string
        message_hex = ""
        for c in actual_message_string:
            indices = characterToTilemapPosDict[c]
            # Add the tile index byte
            message_hex += (hex(int(indices[0], 16))[2:]).upper()
            message_hex += (hex(int(indices[1], 16))[2:]).upper()
            # Add the metadata byte
            # We assume this character is unflipped and
            message_hex += "28"

        # Add padding for memory.
        # These tiles aren't drawn by the game but are part of the message
        # Each line of a messages is exactly 64 bytes long.
        # The bank where the game stores messages has room for exactly 270 lines of messages,
        # So it is impossible to run out of space even if every item belongs to a different,
        # Non-host player and each is a unique item not present in the vanilla game,
        # Assuming only one-line messages were used.
        padding_hex = "0E00"
        if message_box_size == "Small":
            messag_hex = (padding_hex * 6) + message_hex + (padding_hex * 7)
        elif message_box_size == "Large":
            messag_hex = (padding_hex * 3) + message_hex + (padding_hex * 3)
        else:
            print(
                f"WARNING: You are attempting to create a message with size paramater {message_box_size}, which is not a supported size.\nSupported sizes are Small and Large"
            )
            return

        # Record our addition of this message.
        if message_box_size == "Small":
            if message_text in smallMessagePointerTable.keys():
                print(
                    f"WARNING: The message {message_text} has already been added to this ROM.\nPlease consult the current maintainer of this patcher."
                )
            else:
                self.smallMessagePointerTable[message_text] = message_text
        elif message_box_size == "Large":
            if message_text in largeMessagePointerTable.keys():
                print(
                    f"WARNING: The message {message_text} has already been added to this ROM.\nPlease consult the current maintainer of this patcher."
                )
            else:
                self.largeMessagePointerTable[message_text] = message_text

        # Write hex to ROM
        self.file.seek(int(self.currentAddress, 16))
        self.file.write(bytes.fromhex(format(message_hex, "x")))

        # Update address for next message box write.
        self.currentAddress = (hex(int(self.currentAddress, 16) + 64)[2:]).upper()
        # Prepend a 0 to make it look more presentable.
        # Not important, I'm just a perfectionist.
        if len(self.currentAddress) == 5:
            self.currentAddress = "0" + self.currentAddress


class ItemType:
    itemName = None
    GFXOffset = None
    # Most items use this all 00's palette, so just have it as the defaultl.
    paletteBytes = bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

    def __init__(self, item_name, gfx_offset, palette_bytes=None):
        self.itemName = item_name
        self.GFXOffset = gfx_offset
        if palette_bytes is not None:
            self.paletteBytes = palette_bytes


# Class which represents items being passed to the game from the generator
# TODO: Implement this more fully
class PickupPlacementData:
    def __init__(
        self,
        quantity_given=0,
        pickup_index=-1,
        item_name="No Item",
        pickup_effect="No Effect",
        native_graphics=True,
        owner_name=None,
        graphics_filename=None,
        native_sprite_name=None,
    ):
        self.quantity_given = quantity_given
        self.pickup_index = pickup_index
        self.item_name = item_name
        self.pickup_effect = pickup_effect
        self.native_graphics = native_graphics
        self.owner_name = owner_name
        self.graphics_file_name = graphics_filename
        self.native_sprite_name = native_sprite_name


# class PickupEffect(Enum):


# Converts a hexadecimal string to a base 10 integer.
def hex_to_int(hex_to_convert):
    return int(hex_to_convert, 16)


# Converts an integer to a hexadecimal string.
def int_to_hex(int_to_convert):
    return (hex(int_to_convert)[2:]).upper()


# Converts a hexadecimal string to binary data.
def hex_to_data(hex_to_convert):
    return bytes.fromhex(hex_to_convert)


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


# Substitutes every incidence of a keyword in a string with a hex version of the passed number.
def replace_with_hex(original_string, keyword, number, num_hex_digits=4):
    num_hex_string = reverse_endianness(pad_hex(int_to_hex(number), num_hex_digits))
    return original_string.replace(keyword, num_hex_string)


def raw_randomized_example_item_pickup_data():
    return [
        PickupPlacementData(1, 0, "Grapple Beam"),
        PickupPlacementData(100, 1, "Reserve Tank"),
        PickupPlacementData(5, 2, "Missile Expansion"),
        PickupPlacementData(100, 3, "Energy Tank"),
        PickupPlacementData(5, 4, "Missile Expansion"),
        PickupPlacementData(5, 5, "Missile Expansion"),
        PickupPlacementData(5, 6, "Power Bomb Expansion"),
        PickupPlacementData(5, 7, "Missile Expansion"),
        PickupPlacementData(100, 8, "Energy Tank"),
        PickupPlacementData(5, 9, "Missile Expansion"),
        PickupPlacementData(5, 10, "Missile Expansion"),
        PickupPlacementData(5, 11, "Missile Expansion"),
        PickupPlacementData(5, 12, "Missile Expansion"),
        PickupPlacementData(100, 13, "Energy Tank"),
        PickupPlacementData(5, 14, "Super Missile Expansion"),
        PickupPlacementData(100, 15, "Energy Tank"),
        PickupPlacementData(100, 16, "Energy Tank"),
        PickupPlacementData(6, 17, "Missile Expansion"),
        PickupPlacementData(5, 18, "Super Missile Expansion"),
        PickupPlacementData(1, 19, "Spazer Beam"),
        PickupPlacementData(6, 21, "Missile Expansion"),
        PickupPlacementData(1, 22, "Speed Booster"),
        PickupPlacementData(100, 23, "Energy Tank"),
        PickupPlacementData(6, 24, "Missile Expansion"),
        PickupPlacementData(5, 25, "Super Missile Expansion"),
        PickupPlacementData(1, 26, "Morph Ball"),
        PickupPlacementData(6, 27, "Missile Expansion"),
        PickupPlacementData(1, 28, "Hi-Jump Boots"),
        PickupPlacementData(6, 29, "Missile Expansion"),
        PickupPlacementData(6, 30, "Missile Expansion"),
        PickupPlacementData(5, 31, "Power Bomb Expansion"),
        PickupPlacementData(100, 33, "Reserve Tank"),
        PickupPlacementData(1, 34, "Morph Ball Bombs"),
        PickupPlacementData(6, 35, "Missile Expansion"),
        PickupPlacementData(100, 36, "Energy Tank"),
        PickupPlacementData(5, 37, "Power Bomb Expansion"),
        PickupPlacementData(1, 38, "Plasma Beam"),
        PickupPlacementData(5, 39, "Super Missile Expansion"),
        PickupPlacementData(5, 40, "Super Missile Expansion"),
        PickupPlacementData(6, 41, "Missile Expansion"),
        PickupPlacementData(6, 42, "Missile Expansion"),
        PickupPlacementData(6, 43, "Missile Expansion"),
        PickupPlacementData(5, 44, "Power Bomb Expansion"),
        PickupPlacementData(100, 48, "Energy Tank"),
        PickupPlacementData(6, 49, "Missile Expansion"),
        PickupPlacementData(5, 50, "Power Bomb Expansion"),
        PickupPlacementData(6, 51, "Missile Expansion"),
        PickupPlacementData(1, 52, "X-Ray Scope"),
        PickupPlacementData(1, 53, "Space Jump"),
        PickupPlacementData(6, 54, "Missile Expansion"),
        PickupPlacementData(1, 55, "Varia Suit"),
        PickupPlacementData(5, 56, "Missile Expansion"),
        PickupPlacementData(5, 57, "Missile Expansion"),
        PickupPlacementData(5, 58, "Super Missile Expansion"),
        PickupPlacementData(5, 59, "Missile Expansion"),
        PickupPlacementData(1, 60, "Screw Attack"),
        PickupPlacementData(100, 61, "Energy Tank"),
        PickupPlacementData(5, 62, "Power Bomb Expansion"),
        PickupPlacementData(6, 63, "Missile Expansion"),
        PickupPlacementData(100, 64, "Reserve Tank"),
        PickupPlacementData(1, 65, "Gravity Suit"),
        PickupPlacementData(5, 66, "Missile Expansion"),
        PickupPlacementData(5, 67, "Super Missile Expansion"),
        PickupPlacementData(1, 68, "Ice Beam"),
        PickupPlacementData(100, 70, "Energy Tank"),
        PickupPlacementData(5, 71, "Missile Expansion"),
        PickupPlacementData(6, 73, "Missile Expansion"),
        PickupPlacementData(5, 74, "Missile Expansion"),
        PickupPlacementData(5, 75, "Power Bomb Expansion"),
        PickupPlacementData(100, 76, "Energy Tank"),
        PickupPlacementData(5, 77, "Power Bomb Expansion"),
        PickupPlacementData(5, 78, "Missile Expansion"),
        PickupPlacementData(5, 79, "Missile Expansion"),
        PickupPlacementData(5, 80, "Missile Expansion"),
        PickupPlacementData(5, 128, "Super Missile Expansion"),
        PickupPlacementData(5, 129, "Missile Expansion"),
        PickupPlacementData(1, 130, "Charge Beam"),
        PickupPlacementData(5, 131, "Missile Expansion"),
        PickupPlacementData(5, 132, "Power Bomb Expansion"),
        PickupPlacementData(5, 133, "Missile Expansion"),
        PickupPlacementData(5, 134, "Missile Expansion"),
        PickupPlacementData(1, 135, "Spring Ball"),
        PickupPlacementData(6, 136, "Missile Expansion"),
        PickupPlacementData(6, 137, "Missile Expansion"),
        PickupPlacementData(100, 138, "Reserve Tank"),
        PickupPlacementData(100, 139, "Energy Tank"),
        PickupPlacementData(5, 140, "Super Missile Expansion"),
        PickupPlacementData(1, 141, "Wave Beam"),
        PickupPlacementData(6, 142, "Missile Expansion"),
        PickupPlacementData(100, 143, "Energy Tank"),
        PickupPlacementData(5, 144, "Power Bomb Expansion"),
        PickupPlacementData(5, 145, "Super Missile Expansion"),
        PickupPlacementData(6, 146, "Missile Expansion"),
        PickupPlacementData(6, 147, "Missile Expansion"),
        PickupPlacementData(6, 148, "Missile Expansion"),
        PickupPlacementData(100, 149, "Energy Tank"),
        PickupPlacementData(6, 150, "Missile Expansion"),
        PickupPlacementData(6, 151, "Missile Expansion"),
        PickupPlacementData(6, 152, "Missile Expansion"),
        PickupPlacementData(6, 154, "Missile Expansion"),
    ]


def create_item_types(pickup_data_list):
    item_types = {}
    # TODO: Add a placeholder-type sprite to available native graphics sprites
    # REMINDER: After doing so increment the initial GFXDataLocation address
    next_pickup_gfx_data_location = "0095"
    item_gfx_added = {}
    for pickup in pickup_data_list:
        if pickup.item_name == "No Item":
            continue
        if not pickup.item_name in item_types:
            if pickup.native_graphics:
                item_types[pickup.item_name] = ItemType(
                    pickup.item_name,
                    SuperMetroidConstants.nativeItemSpriteLocations[pickup.native_sprite_name],
                    SuperMetroidConstants.nativeItemPalettes[pickup.native_sprite_name],
                )
            else:
                # TODO: Patch pickup graphics into ROM from file
                # TODO: Add message box generation
                item_gfx_added[pickup.item_name] = pickup.graphics_file_name
                next_pickup_gfx_data_location = pad_hex(int_to_hex(hex_to_int(next_pickup_gfx_data_location) + 1), 4)
    return item_types


def get_patch_dict():
    static_patch_dict = {
        "instant_g4": "QoL/g4_skip.ips",
        "max_ammo_display": "QoL/max_ammo_display.ips",
        "aim_with_any_button": "QoL/aim_any_button.ips",
        "better_decompression": "QoL/better_decompress.ips",
        "fast_doors_and_elevators": "QoL/fast_elevators_doors.ips",
        "backup_saves": "QoL/enable_backup_saves.ips",
        "enable_moonwalk_by_default": "QoL/enable_moonwalk_by_default.ips",
        "random_music": "Music/random_music.ips",
        "no_music": "Music/no_music.ips",
        "door_transitions": "Mandatory Patches/door_transition.ips",
        "varia_rng": "Mandatory Patches/varia_rng.ips",
        "varia_timer_fix": "Mandatory Patches/varia_timer_fix.ips",
        "seed_display": "Mandatory Patches/seed_display.ips",
        "eye_fix": "Mandatory Patches/eye_fix.ips",
        "respin": "Tweaks/respin.ips",
        "no_demo": "Tweaks/no_demo.ips",
        "refill_before_save": "Tweaks/refill_before_save.ips",
        "cant_use_supers_on_red_doors": "Tweaks/no_supers_on_red_doors.ips",
        "cheap_charge": "Tweaks/cheap_charge.ips",
        "nerfed_rainbow_beam": "Tweaks/nerfed_rainbow_beam.ips",
        "mother_brain_cutscene_edits": "Tweaks/mother_brain_cutscene_edits.ips",
        "infinite_space_jump": "Tweaks/infinite_space_jump.ips",
        "speedkeep": "Tweaks/speed_keep.ips",
        "no_ln_chozo_inventory_check": "Tweaks/no_ln_chozo_inventory_check.ips",
        "no_gt_code": "Fixes/disable_gt_code.ips",
        "fix_heat_echoes": "Fixes/fix_heat_echoes.ips",
        "fix_screw_attack_menu": "Fixes/fix_screw_attack_menu.ips",
        "fix_spacetime": "Fixes/fix_spacetime_beam.ips",
        "dachora_pit": "Map Changes/dachora_pit.ips",
        "early_supers_bridge": "Map Changes/early_super_bridge.ips",
        "pre_hi_jump": "Map Changes/pre_high_jump.ips",
        "moat": "Map Changes/moat.ips",
        "pre_spazer": "Map Changes/pre_spazer.ips",
        "red_tower": "Map Changes/red_tower.ips",
        "nova_boost_platform": "Map Changes/nova_boost_platform.ips",
        "colorblind_mode": "Accessibility/colorblind.ips",
    }
    return static_patch_dict


def get_equipment_routines():
    # Generates a list of all effects for picking up "Equipment" (i.e. items which have no ammo count associated, permanent)
    # Not all routines here are written to ROM, only those which we determine are used in-game.
    # This is why passing items from the multiworld session that this player receives is necessary.

    # Make all the get routines and templates.
    grapple_get = "ADA2090900408DA209ADA4090900408DA409222E9A8060"
    x_ray_get = "ADA2090900808DA209ADA4090900808DA409223E9A8060"
    equipment_get_template = "ADA20909-eqp8DA209ADA40909-eqp8DA40960"
    beam_get_template = (
        "A9-eqp0DA6098DA609A9-eqp0DA8098DA809A9-eqp0A2908001CA609A9-eqp4A2904001CA609ADDA09F004228DAC9060"
    )

    # Note that if items appear more than once with different implementations, things will break horribly.
    # If you want major items with different effects, give them a new name -
    # Ex. Instead of "Spazer" and "Plasma" for a progressive spazer hack, call it
    # "Progressive Spazer"
    # Will still try its damnedest if you give it conflicting info, but can't give multiple effects to an item that it thinks is the same.
    # This is why ammo item names have the quantity appended to them - since having differing quantities makes them effectively different items.
    equipment_gets = {}
    equipment_gets["Get X-Ray Scope"] = bytes.fromhex(x_ray_get)
    equipment_gets["Get Grapple Beam"] = bytes.fromhex(grapple_get)
    for item_name, bit_flags in SuperMetroidConstants.equipmentBitflagsDict.items():
        equipmentHex = replace_with_hex(equipment_get_template, "-eqp", bit_flags)
        equipment_gets["Get " + item_name] = bytes.fromhex(equipmentHex)
    for item_name, bit_flags in SuperMetroidConstants.beamBitflagsDict.items():
        equipmentHex = replace_with_hex(beam_get_template, "-eqp", bit_flags)
        equipment_gets["Get " + item_name] = bytes.fromhex(equipmentHex)
    return equipment_gets


def get_all_necessary_pickup_routines(item_list, item_get_routines_dict, starting_items, player_name):
    ammo_get_templates = {
        "Get Energy Tank": "ADC4091869-qty8DC4098DC20960",
        "Get Reserve Tank": "ADD4091869-qty8DD409ADC009D003EEC00960",
        "Get Missile Expansion": "ADC8091869-qty8DC809ADC6091869-qty8DC60922CF998060",
        "Get Super Missile Expansion": "ADCC091869-qty8DCC09ADCA091869-qty8DCA09220E9A8060",
        "Get Power Bomb Expansion": "ADD0091869-qty8DD009ADCE091869-qty8DCE09221E9A8060",
    }

    equipment_gets = get_equipment_routines()

    # For non-vanilla ammo get routines.
    custom_ammo_get_templates = {}

    # This is a command that will do nothing, used for items that are meant to go to other players.
    # 60 is hex for the RTS instruction. In other words when called it will immediately return.
    item_get_routines_dict["No Effect"] = (0x60).to_bytes(1, "little")

    # Create individual routines from ASM templates.
    # Note that the exact effect is hardcoded in, so ex. wave beam and ice beam are two different routines.
    # This is because I'm lazy and we absolutely have room for it.
    all_items_list = item_list.copy()
    all_items_list += starting_items
    for pickup in all_items_list:
        if pickup.owner_name is None or pickup.owner_name == player_name:
            if pickup.item_name == "No Item":
                continue
            if pickup.item_name in SuperMetroidConstants.ammoItemList:
                item_effect_name = f"Get {pickup.item_name} {pickup.quantity_given}"
                if not item_effect_name in item_get_routines_dict:
                    pickup_hex = replace_with_hex(
                        ammo_get_templates[pickup.pickup_effect], "-qty", pickup.quantity_given
                    )
                    item_get_routines_dict[item_effect_name] = bytes.fromhex(pickup_hex)
            elif pickup.item_name in SuperMetroidConstants.toggleItemList:
                # Overwrite vanilla behavior for this item if vanilla.
                # Otherwise add new item effect for the item type.
                if not "Get " + pickup.item_name in item_get_routines_dict:
                    if pickup.pickup_effect in equipment_gets:
                        item_get_routines_dict[pickup.item_name] = equipment_gets[pickup.pickup_effect]
                # Otherwise add new effect
            else:
                raise NotImplementedError("ERROR: Custom item pickup behaviors are not yet implemented.")

    return item_get_routines_dict


def get_door_data():
    door_data_dict = {}
    for room_address, door_hex_list in SMRooms.addr_to_door_data_dict.items():
        door_data_dict[room_address] = [DoorData(door_hex) for door_hex in door_hex_list]
    return door_data_dict


def write_door_asm_routines(rom_file, door_data_list):
    base_address = 0xF800
    current_address = base_address
    file_offset = 0x070000
    rom_file.seek(base_address + file_offset)
    # As an efficiency measure,
    # We hardcode in the door ASM which I believe is likely to be most common.
    most_basic_door_asm = hex_to_data("60")
    most_basic_door_asm_address = base_address
    rom_file.write(most_basic_door_asm)
    current_address += len(most_basic_door_asm)
    for door_data in door_data_list:
        door_routine = bytearray()
        # Call original asm if this door is associated with any
        if door_data.door_asm_pointer != 0x0000 and door_data.door_asm_pointer != most_basic_door_asm_address:
            door_routine.append(0x20)
            door_routine += door_data.door_asm_pointer.to_bytes(2, "little")
        # Extra ASM for special, room-specific patches
        if door_data.extra_asm_pointer != 0x0000:
            door_routine.append(0x20)
            door_routine += door_data.extra_asm_pointer.to_bytes(2, "little")
        if door_data.door_redirect:
            # Rectify door directional mismatches
            # Relies on door_transition.ips
            if door_data.door_mismatch:
                door_routine += bytearray([0x20, 0x00, 0xF6, 0xA9])
                door_routine += door_data.override_x.to_bytes(2, "little")
                door_routine += bytearray([0x8D, 0xF6, 0x0A, 0xA9])
                door_routine += door_data.override_y.to_bytes(2, "little")
                door_routine += bytearray([0x8D, 0xFA, 0x0A])
            # Apply iframes after going through a door
            else:
                door_routine += bytearray([0x20, 0x40, 0xF6])
        door_routine.append(0x60)

        if door_routine == most_basic_door_asm:
            door_data.door_asm_pointer = most_basic_door_asm_address
        else:
            door_data.door_asm_pointer = current_address
            rom_file.seek(current_address + file_offset)
            rom_file.write(door_routine)
            current_address += len(door_routine)


def write_doors(rom_file, door_data_list):
    for door_data in door_data_list:
        door_data.write_ddb_entry_to_file(rom_file)


def write_item_get_routines(rom_file, item_get_routines_dict, in_game_address):
    # Write them to memory and store their addresses in a dict.
    # This is critical, as we will use these addresses to store to a table that dictates
    # What an item will do when picked up.
    # We'll be appending them to the same place as messagebox code, so we'll keep the
    # Address and file pointer we had from before.
    # We may want to move these somewhere else later.
    item_get_routine_addresses_dict = {}

    # Use this to make sure the item data tables, which contain data about pickups, isn't overwritten.
    passed_tables = False
    for item_name, routine in item_get_routines_dict.items():
        # Don't overwrite the tables
        if in_game_address + len(routine) >= 0x9A00 and not passed_tables:
            rom_file.seek(0x2A400)
            in_game_address = 0xA400
            passed_tables = True
        # KEY CHANGE HERE - BIG NOT LITTLE ENDIAN STORED HERE!
        item_get_routine_addresses_dict[item_name] = in_game_address
        rom_file.write(routine)
        in_game_address += len(routine)

    return item_get_routine_addresses_dict


def write_messagebox_routines(rom_file, base_in_game_address):
    # Now write our new routines to memory.
    # First we append new routines to free space
    # At the end of bank 85.

    # Routines stored as hexadecimal.
    #
    # We handle writing these in the program itself instead of as static patches,
    # Because I write them myself and don't want to manually recalculate addresses
    # Each time I test changes.
    #
    # Keyphrases starting in - will be substituted with addresses.
    # These must be of appropriate length or size calculations might fail.
    # on_pickup_found_routine = -alp
    # get_message_header_data_routine  = -bta
    # get_message_header_routine = -gma
    # get_message_content_routine = -dlt

    on_pickup_found_routine = "8D1F1CC91C00F00AC914009006C91900B00160AF74FF7FC90100D01CAF7CFF7F8D1F1CA500DA48AF7EFF7F850068A20000FC0000FA8500605ADAA22000BF6ED87E9FCEFF7FCACAE00000D0F1A22000A00000BFCEFF7F385FAEFF7FC90000F0028004EAEA801C8F8EFF7FA90100CF8EFF7FF008C90080080A288003C88004D0EDC8C8CACAE00000D0C9C00100F043AF52097EAAA9DE00E00000F00A18695C06CAE00000D0F6AAA02000BF000070DA5AFA7A9FAEFF7FDA5AFA7ACACA8888C00000D0E7A22000A900009F8EFF7FCACAE00000D0F5A22000BFCEFF7F38FFAEFF7F9F8EFF7FCACAE00000D0ECA0F000A22000BF8EFF7FC90000D00A9838E91000A8CACA80EDBFCEFF7F9FAEFF7FBF8EFF7FC90100F004C84A80F7A900009F8EFF7F980A8F8EFF7FAABD00A08D1F1CFC00A2FA7A60"
    get_message_header_data_routine = "20-gmaA920008516B900009F00327EC8C8E8E8C616D0F160"
    get_message_header_routine = (
        "AD1F1CC91C00F00AC914009009C91900B004A0408060AF74FF7FC90100D006AF76FF7FA860DAAF8EFF7FAABF009A85A8FA60"
    )
    get_message_content_routine = "AD1F1CC91C00F00AC91400902AC91900B025AD1F1C3A0A85340A186534AABD9F868500BDA58638E50085094A8516A50918698000850960AF74FF7FC90100D016AF78FF7FA88400AF7AFF7F4A85160A18698000850960DAAF8EFF7FAABF009C85A88400BF009E854A85160A186980008509FA60"
    # KEY NOTE: WRITE ROUTINE ADDRESSES LITTLE ENDIAN!!!
    routines = [
        on_pickup_found_routine,
        get_message_header_data_routine,
        get_message_header_routine,
        get_message_content_routine,
    ]
    routine_addresses = []
    routine_address_refs = ["-alp", "-bta", "-gma", "-dlt"]
    in_game_address = base_in_game_address
    rom_file.seek(0x020000 + in_game_address)
    # Calculate routine addresses
    for i in range(len(routines)):
        routine_addresses.append(in_game_address)
        in_game_address += len(routines[i]) // 2

    # Replace subroutine references with their addresses and write them to the ROM file.
    for i in range(len(routines)):
        for j in range(len(routines)):
            routines[i] = replace_with_hex(routines[i], routine_address_refs[j], routine_addresses[j])
        rom_file.write(hex_to_data(routines[i]))

    # Modify/overwrite existing routines.
    overwrite_routines = []
    overwrite_routine_addresses = []

    # Modify Message Box Routines To Allow Customizable Behavior
    overwrite_jsr_to_pickup_routine = "20-alp"
    overwrite_get_message_header_routine = "20-gmaA20000B900009F00327EE8E8C8C8E04000D0F0A0000020B88220-bta60"
    overwrite_jsr_to_get_message_routine = "20-dltEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEA"
    overwrite_jsr_to_get_header_routine = "205A82"

    # Addresses to write routines to in Headerless ROM file.
    overwrite_jsr_to_pickup_routine_address = "028086"
    overwrite_get_message_header_routine_address = "02825A"
    overwrite_jsr_to_get_message_routine_address = "0282E5"
    overwrite_jsr_to_get_header_routine_address = "028250"

    overwrite_routines = []
    overwrite_routine_addresses = []

    overwrite_routines.extend(
        [
            overwrite_jsr_to_pickup_routine,
            overwrite_get_message_header_routine,
            overwrite_jsr_to_get_message_routine,
            overwrite_jsr_to_get_header_routine,
        ]
    )

    overwrite_routine_addresses.extend(
        [
            overwrite_jsr_to_pickup_routine_address,
            overwrite_get_message_header_routine_address,
            overwrite_jsr_to_get_message_routine_address,
            overwrite_jsr_to_get_header_routine_address,
        ]
    )

    # Replace references with actual addresses.
    for i in range(len(overwrite_routines)):
        for j in range(len(routines)):
            overwrite_routines[i] = replace_with_hex(
                overwrite_routines[i], routine_address_refs[j], routine_addresses[j]
            )

    # Write to file
    for i, routine in enumerate(overwrite_routines):
        rom_file.seek(hex_to_int(overwrite_routine_addresses[i]))
        rom_file.write(hex_to_data(routine))

    # Seek back to where we expect to be.
    rom_file.seek(0x020000 + in_game_address)

    return in_game_address


def write_save_initialization_routines(rom_file, skip_intro, custom_save_start=None):
    if skip_intro:
        # Skips the intro cutscene
        intro_routine = "9CE20DADDA09D01E223AF690A9-rgn8D9F07A9-sav8D8B07ADEA098F08D87EAD520922008081AD520922858081AF08D87E8DEA09228C8580A905008D9809AF18D97E8D500960"
        intro_routine_address = 0x016EB4
    else:
        # Play the intro cutscene before figuring out where to spawn the player/what to give them.
        # -sta - State to load with (06 - load like a save station, 1F - load like ceres, 22 - load like zebes landing)
        # -rgn - Region to start in
        # -sav - Save station index
        intro_routine = "A9-sta8F14D97E8D9809223AF690A9-rgn8D9F07A9-sav8D8B07AD5209220080816B"
        redirection_routine = "22F4ED9260"
        intro_routine_address = 0x096DF4
        redirection_routine_address = 0x05C100
        # Write the redirection routine to ROM
        rom_file.seek(redirection_routine_address)
        rom_file.write(hex_to_data(redirection_routine))
    if custom_save_start is not None:
        # Custom save start should be a list/tuple with two values:
        # Region name and save station index
        region_hex = SuperMetroidConstants.regionToHexDict[custom_save_start[0]]
        save_hex = reverse_endianness(pad_hex(int_to_hex(custom_save_start[1]), 4))
        intro_routine = intro_routine.replace("-rgn", region_hex)
        intro_routine = intro_routine.replace("-sav", save_hex)

        if region_hex == "0600":
            intro_routine = intro_routine.replace("-sta", "1F00")
        else:
            intro_routine = intro_routine.replace("-sta", "0600")
    else:
        # Default start is ship save
        intro_routine = intro_routine.replace("-rgn", "0000")
        intro_routine = intro_routine.replace("-sav", "0000")
        intro_routine = intro_routine.replace("-sta", "0600")

    rom_file.seek(intro_routine_address)
    rom_file.write(hex_to_data(intro_routine))


def write_multiworld_routines(rom_file):
    # MULTIWORLD ROUTINES:
    # Appended to bank 90. Used to work the game's events in our favor.
    # TODO: Convert this to an ips patch?
    multiworld_execute_arbitrary_function_routine = "E220A98348C220AF72FF7F486B"

    rom_file.seek(0x087FF0)
    rom_file.write(hex_to_data(multiworld_execute_arbitrary_function_routine))

    # Routines to append to bank $83.
    # More than one are planned, for things like sending messages &c.

    multiworld_item_get_routine = "AD1F1C22808085A900008F74FF7FAF80FF7F8D420A6B"
    multiworld_routine_address_start = 0x01AD66

    multiworld_routines = [multiworld_item_get_routine]

    rom_file.seek(multiworld_routine_address_start)
    for routine in multiworld_routines:
        rom_file.write(hex_to_data(routine))


def write_crateria_wakeup_routine(rom_file):
    # TODO: Convert this to an ips patch?
    overwrite_crateria_wakeup_routine = "AF73D87E290400F007BD0000AA4CE6E5E8E860"
    overwrite_crateria_wakeup_routine_address = 0x07E652
    rom_file.seek(overwrite_crateria_wakeup_routine_address)
    rom_file.write(hex_to_data(overwrite_crateria_wakeup_routine))


# Generate a game with vanilla item placements
def gen_vanilla_game():
    pickups_list = []
    for item_index, item_name in zip(SuperMetroidConstants.itemIndexList, SuperMetroidConstants.vanillaPickupList):
        if item_name in SuperMetroidConstants.ammoItemList:
            pickups_list.append(
                PickupPlacementData(SuperMetroidConstants.defaultAmmoItemToQuantity[item_name], item_index, item_name)
            )
        else:
            pickups_list.append(PickupPlacementData(1, item_index, item_name))
    return pickups_list


# Adds the ability to start the game with items
# Takes a list of PickupPlacementData
# Irrelevent fields need not be specified.
def add_starting_inventory(rom_file, pickups, item_get_routine_addresses_dict):
    # Safeguard so that we don't overlap routine associations,
    # Which start 0x100 after the starting inventory.
    if len(pickups) > 127:
        raise ValueError(
            "ERROR: Unreasonable amount of starting items detected. Starting items will not be placed. Did you send correct information to the patcher?"
        )
    print(f"Placing {len(pickups)} starting items")
    rom_file.seek(0x1C0000)
    rom_file.write(len(pickups).to_bytes(2, "little"))
    for starting_item in pickups:
        effect_name = starting_item.pickup_effect
        if starting_item.item_name in SuperMetroidConstants.ammoItemList:
            effect_name += " " + str(starting_item.quantity_given)
        routine_address = item_get_routine_addresses_dict[effect_name] - 1
        rom_file.write(routine_address.to_bytes(2, "little"))

    award_starting_inventory_routine = (
        "AF0080B8AAE00000F019DA4BF4FAFFE220A98548C2208A0AAABF0080B8486BFACA80E2A90000A20800A00300E202186B"
    )
    function_to_return_properly = "F458F66B"
    award_starting_inventory_routine_address = 0x08763A
    function_to_return_properly_address = 0x02FFFB

    rom_file.seek(award_starting_inventory_routine_address)
    rom_file.write(hex_to_data(award_starting_inventory_routine))
    rom_file.seek(function_to_return_properly_address)
    rom_file.write(hex_to_data(function_to_return_properly))


# This is just a python function that applies a modified version of
# Kazuto's More_Efficient_PLM_Items.asm patch without an assembler.
# Please, send lots of thanks to Kazuto for this, I could not have done
# Any of this without their hard work.
def write_kazuto_more_efficient_items_hack(rom_file, item_types_list):
    # Where we start writing our data in the actual file.
    # Inclusive - first byte written here.
    in_file_initial_offset = 0x026099

    # Where the game believes data to be at runtime.
    # Equivalent to InFileInitialOffset in placement.
    # Influences addressing.
    # Excludes the bank address, which is implicitly 84
    in_memory_initial_offset = 0xE099

    # Where we start writing PLM Headers for items.
    in_memory_plm_header_offset = 0xEED7
    in_file_plm_header_offset = 0x026ED7

    # Each item represents two bytes in each table
    item_get_table_size = len(item_types_list) * 2
    item_gfx_table_size = item_get_table_size

    # Calculate addresses of some important things.
    vram_item_normal_addr = in_memory_initial_offset + 0x04
    vram_item_ball_addr = vram_item_normal_addr + 0x0C
    start_addr = vram_item_ball_addr + 0x10
    gfx_addr = start_addr + 0x0B
    goto_addr = gfx_addr + 0x08
    vram_item_block_addr = goto_addr + 0x08
    respawn_addr = vram_item_block_addr + 0x08
    block_loop_addr = respawn_addr + 0x04
    gfx_addr_b = block_loop_addr + 0x13
    block_goto_addr = gfx_addr_b + 0x10
    get_item_addr = block_goto_addr + 0x04
    table_ptr_addr = get_item_addr + 0x05

    # ASM Functions
    table_load_func_addr = table_ptr_addr + 0x04
    lava_rise_func_addr = table_load_func_addr + 0x1D

    # Tables
    item_get_table_addr = lava_rise_func_addr + 0x07
    item_gfx_table_addr = item_get_table_addr + item_get_table_size

    # Item Data
    item_plm_data_addr = item_gfx_table_addr + item_gfx_table_size

    # Write Data
    # Setup
    # Don't bother reading this, it's a 1 for 1 recreation of the Setup portion of Kazuto's asm file.
    # Or at least it should be.
    rom_file.seek(in_file_initial_offset)
    rom_file.write(table_load_func_addr.to_bytes(2, "little") + item_gfx_table_addr.to_bytes(2, "little"))
    # VRAMItem_Normal
    rom_file.write(
        bytearray([0x7C, 0x88, 0xA9, 0xDF, 0x2E, 0x8A])
        + in_memory_initial_offset.to_bytes(2, "little")
        + bytearray([0x24, 0x87])
        + start_addr.to_bytes(2, "little")
    )
    # VRAMItem_Ball
    rom_file.write(
        bytearray([0x7C, 0x88, 0xA9, 0xDF, 0x2E, 0x8A])
        + in_memory_initial_offset.to_bytes(2, "little")
        + bytearray([0x2E, 0x8A, 0xAF, 0xDF, 0x2E, 0x8A, 0xC7, 0xDF])
    )
    # Start
    rom_file.write(
        bytearray([0x24, 0x8A])
        + goto_addr.to_bytes(2, "little")
        + bytearray([0xC1, 0x86, 0x89, 0xDF, 0x4E, 0x87, 0x16])
    )
    # .Gfx (1)
    rom_file.write(bytearray([0x4F, 0xE0, 0x67, 0xE0, 0x24, 0x87]) + gfx_addr.to_bytes(2, "little"))
    # Goto
    rom_file.write(bytearray([0x24, 0x8A, 0xA9, 0xDF, 0x24, 0x87]) + get_item_addr.to_bytes(2, "little"))
    # VRAMItem_Block
    rom_file.write(
        bytearray([0x2E, 0x8A])
        + in_memory_initial_offset.to_bytes(2, "little")
        + bytearray([0x24, 0x87])
        + block_loop_addr.to_bytes(2, "little")
    )
    # Respawn
    rom_file.write(bytearray([0x2E, 0x8A, 0x32, 0xE0]))
    # BlockLoop
    rom_file.write(
        bytearray([0x2E, 0x8A, 0x07, 0xE0, 0x7C, 0x88])
        + respawn_addr.to_bytes(2, "little")
        + bytearray([0x24, 0x8A])
        + block_goto_addr.to_bytes(2, "little")
        + bytearray([0xC1, 0x86, 0x89, 0xDF, 0x4E, 0x87, 0x16])
    )
    # .Gfx (2)
    rom_file.write(
        bytearray([0x4F, 0xE0, 0x67, 0xE0, 0x3F, 0x87])
        + gfx_addr_b.to_bytes(2, "little")
        + bytearray([0x2E, 0x8A, 0x20, 0xE0, 0x24, 0x87])
        + block_loop_addr.to_bytes(2, "little")
    )
    # BlockGoto
    rom_file.write(bytearray([0x24, 0x8A]) + respawn_addr.to_bytes(2, "little"))
    # GetItem
    rom_file.write(bytearray([0x99, 0x88, 0xDD, 0x8B, 0x02]))
    rom_file.write(table_load_func_addr.to_bytes(2, "little") + item_get_table_addr.to_bytes(2, "little"))

    # ASM Functions
    # LoadItemTable
    rom_file.write(hex_to_data("B900008512BF371C7EC92BEF9005E9540080F638E9D7EE4AA8B112A860"))
    # LavaRise
    rom_file.write(bytearray([0xA9, 0xE0, 0xFF, 0x8D, 0x7C, 0x19, 0x60]))

    # Item Tables
    # Initial item table hexstrings.
    item_table_bytes = []
    gfx_table_bytes = []

    # Size of the data pointed to for each entry.
    item_get_length = 0x07
    item_gfx_length = 0x0E
    item_total_length = item_get_length + item_gfx_length

    # Pointers to next item PLM data
    item_next_get_data = item_plm_data_addr
    item_next_gfx_data = item_plm_data_addr + item_get_length

    # Get table bytes one item at a time.
    for item_type in item_types_list:
        # Add bytes to tables
        item_table_bytes.append(item_next_get_data.to_bytes(2, "little"))
        gfx_table_bytes.append(item_next_gfx_data.to_bytes(2, "little"))
        # Increment Data Pointers
        item_next_get_data = item_next_get_data + item_total_length
        item_next_gfx_data = item_next_gfx_data + item_total_length

    # Write tables to file
    for item_table_byte_pair in item_table_bytes:
        rom_file.write(item_table_byte_pair)
    for gfx_table_byte_pair in gfx_table_bytes:
        rom_file.write(gfx_table_byte_pair)

    # Item PLM Data
    # This acquire data should do nothing but display a message box.
    # The actual "effects" of picking up the item are determined in
    # Messagebox display routines instead, as items for this player
    # Are the same PLM as an item that is for another player in the
    # Session. We already check which player it's for there and I
    # Honestly can't for the life of me decode how PLMs actually work,
    # So that's just where it happens. It is quite nice since this also
    # Works for the player receiving items from others, as the only thing
    # That actually happens is that a Messagebox appears for the player (i.e.
    # There is no actual item entity in the game world being picked up).
    generic_acquire_data = bytearray([0xF3, 0x88, 0x00, 0x00, 0x13, 0x3A, 0x8A])
    for item_type in item_types_list:
        # Construct the item's graphics data.
        current_item_gfx_data = [0x64, 0x87]
        current_item_gfx_data += item_type.GFXOffset.to_bytes(2, "big")
        for paletteByte in item_type.paletteBytes:
            current_item_gfx_data.append(paletteByte)
        current_item_gfx_data += [0x3A, 0x8A]
        try:
            assert len(current_item_gfx_data) == item_gfx_length
        except:
            raise ValueError(
                f"ERROR: Invalid-size graphics data supplied for item type {item_type.item_name}:\n {current_item_gfx_data} should be only 14(0x0E) bytes, is instead {str(len(current_item_gfx_data))}."
            )
            return
        # Write to file
        rom_file.write(generic_acquire_data)
        rom_file.write(bytearray(current_item_gfx_data))

    # Now we write out the PLM Header Data
    rom_file.seek(in_file_plm_header_offset)
    normal_item_hex = bytearray([0x64, 0xEE]) + vram_item_normal_addr.to_bytes(2, "little")
    ball_item_hex = bytearray([0x64, 0xEE]) + vram_item_ball_addr.to_bytes(2, "little")
    block_item_hex = bytearray([0x8E, 0xEE]) + vram_item_block_addr.to_bytes(2, "little")
    for item_type in item_types_list:
        rom_file.write(normal_item_hex)
    for item_type in item_types_list:
        rom_file.write(ball_item_hex)
    for item_type in item_types_list:
        rom_file.write(block_item_hex)
    # Write native item graphics that aren't already in the ROM
    # This is primarily for what were originally CRE items like Missile Expansions.
    rom_file.seek(0x049100)
    # FIXME - REMOVE DEPENDENCE ON CURRENT WORKING DIRECTORY!

    with VRAM_ITEMS_PATH.open("rb") as f2:
        rom_file.write(f2.read())
    return in_memory_plm_header_offset


# Perform actions based on altering door database
def do_doors(rom_file):
    door_data_dict = get_door_data()

    # Test Modification
    # door_to_modify = ((door_data_dict[0x91F8])[0])
    # door_to_modify.to_string()
    # door_to_modify.change_destination(0x96BA, 0)
    # door_to_modify.to_string()

    door_data_list = []
    for data_list in door_data_dict.values():
        door_data_list += data_list
    write_door_asm_routines(rom_file, door_data_list)
    write_doors(rom_file, door_data_list)


def write_seed_to_display(rom_file, seed):
    random.seed(seed)
    seedDisplayWordA = random.randint(0, 0xFFFF)
    seedDisplayWordB = random.randint(0, 0xFFFF)
    rom_file.seek(0x2FFF00)
    rom_file.write(seedDisplayWordA.to_bytes(2, byteorder="little"))
    rom_file.write(seedDisplayWordB.to_bytes(2, byteorder="little"))


# Sets default control scheme when starting a new game
def write_controls(controls_dict, rom_file):
    buttons = {
        "Select": [0x00, 0x20],
        "A": [0x80, 0x00],
        "B": [0x00, 0x80],
        "X": [0x40, 0x00],
        "Y": [0x00, 0x40],
        "L": [0x20, 0x00],
        "R": [0x10, 0x00],
        "None": [0x00, 0x00],
    }

    controls = {
        "Shot": [0xB331, 0x1722D],
        "Jump": [0xB325, 0x17233],
        "Dash": [0xB32B, 0x17239],
        "ItemSelect": [0xB33D, 0x17245],
        "ItemCancel": [0xB337, 0x1723F],
        "AngleUp": [0xB343, 0x1724B],
        "AngleDown": [0xB349, 0x17251],
    }

    for ctrl, button in controls_dict.items():
        assert ctrl in controls
        assert button in buttons
        for addr in controls[ctrl]:
            rom_file.seek(addr)
            rom_file.write(buttons[button][0].to_bytes(1, byteorder="little"))
            rom_file.write(buttons[button][1].to_bytes(1, byteorder="little"))


# Places the items into the game.
def place_items(rom_file, item_get_routine_addresses_dict, pickup_data_list, player_name=None):
    # Initialize MessageBoxGenerator
    message_box_generator = MessageBoxGenerator(rom_file)

    # Necessary for applying the Kazuto More Efficient Items Patch
    item_types = create_item_types(pickup_data_list)

    item_type_list = item_types.values()
    plm_header_offset = write_kazuto_more_efficient_items_hack(rom_file, item_type_list)
    # Generate dict of item PLMIDs. Since there's no more guarantee of ordering here, we create this
    # at patch time.
    item_plm_ids = {}

    for itemType in item_type_list:
        item_plm_ids[itemType.itemName] = plm_header_offset
        plm_header_offset += 4
    item_plm_ids["No Item"] = 0xB62F

    # How much an increment for each slot above increases the value of the PLM ID.
    # We will calculate this on the fly depending on how many new items are added to this ROM.
    # TODO: Rewrite this based on len(item_types)
    item_plm_block_type_multiplier = 0x54

    # Patch ROM.
    # This part of the code is ugly as sin, I apologize.
    for i, item in enumerate(pickup_data_list):
        patcher_index = SuperMetroidConstants.itemIndexList.index(item.pickup_index)
        # Write PLM Data.
        rom_file.seek(SuperMetroidConstants.itemPLMLocationList[patcher_index])
        # If there is no item in this location, we should NOT try to calculate a PLM-type offset,
        # As this could give us an incorrect PLM ID.
        if item.item_name == "No Item":
            rom_file.write(item_plm_ids[item.item_name].to_bytes(2, "little"))
            continue
        rom_file.write(
            (
                item_plm_ids[item.item_name]
                + item_plm_block_type_multiplier * SuperMetroidConstants.itemPLMBlockTypeList[patcher_index]
            ).to_bytes(2, "little")
        )
        # Write Message Box Data.
        # ITEM TABLE FORMAT
        # 2 PAGES PER TABLE
        # TABLE 1: MESSAGEBOX HEADER LOCATION
        # TABLE 2: MESSAGEBOX CONTENT LOCATION
        # TABLE 3: MESSAGEBOX SIZE
        # TABLE 4: MESSAGEBOX ID. USED TO CALCULATE IMPORTANT VALUES.
        # TABLE 5: ITEM COLLECTION ROUTINE. REWARDS ITEMS TO PLAYER ON PICKUP.
        # This table is not present in the vanilla ROM, and is used with the custom routines.
        # See documentation on memory alterations at the top of this document.

        # Each table entry is two bytes wide, hence the doubling.
        memory_base_location = 0x029A00 + SuperMetroidConstants.itemLocationList[patcher_index] * 2

        rom_file.seek(memory_base_location)
        # TODO: Handle width and height separately.
        if item.item_name in SuperMetroidConstants.itemMessageNonstandardSizes:
            rom_file.write((0x0080).to_bytes(2, "big"))
            rom_file.seek(memory_base_location + 0x400)
            rom_file.write(SuperMetroidConstants.itemMessageNonstandardSizes[item.item_name].to_bytes(2, "little"))
        else:
            rom_file.write((0x4080).to_bytes(2, "big"))
            rom_file.seek(memory_base_location + 0x400)
            rom_file.write((0x4000).to_bytes(2, "big"))

        rom_file.seek(memory_base_location + 0x200)
        rom_file.write(SuperMetroidConstants.itemMessageAddresses[item.item_name].to_bytes(2, "little"))

        rom_file.seek(memory_base_location + 0x600)
        rom_file.write(SuperMetroidConstants.itemMessageIDs[item.item_name].to_bytes(2, "little"))

        rom_file.seek(memory_base_location + 0x800)
        # If item is meant for a different player, it will do nothing at all.
        # This is not the same as there not being an item in this position -
        # The item will be there, it will just have no effect for the SM player.
        if player_name is not None and not item.owner_name == player_name:
            rom_file.write(item_get_routine_addresses_dict["No Item"].to_bytes(2, "little"))
        else:
            item_effect_name = "Get " + item.item_name
            if item.item_name in SuperMetroidConstants.ammoItemList:
                item_effect_name = f"Get {item.item_name} {item.quantity_given}"
            rom_file.write(item_get_routine_addresses_dict[item_effect_name].to_bytes(2, "little"))


def patch_rom_json(rom_file, output_path, patch_data):
    if "seed" in patch_data:
        seed = patch_data["seed"]
    else:
        seed = 0

    item_list = []
    for pickup in patch_data["pickups"]:
        pickup_data = PickupPlacementData()
        for field_name, value in pickup.items():
            setattr(pickup_data, field_name, value)
        pickup_data.native_graphics = pickup_data.native_sprite_name != None
        item_list.append(pickup_data)

    keyword_arguments = {}

    patch_list = []
    for field_name, value in patch_data["specific_patches"].items():
        if value == True:
            patch_list.append(field_name)

    keyword_arguments["skip_intro"] = False
    if "skip_intro" in patch_list:
        patch_list.remove("skip_intro")
        keyword_arguments["skip_intro"] = True

    keyword_arguments["static_patches"] = patch_list

    starting_items = []
    for starting_item in patch_data["starting_items"]:
        pickup_data = PickupPlacementData()
        for field_name, value in starting_item.items():
            setattr(pickup_data, field_name, value)
        pickup_data.native_graphics = pickup_data.native_sprite_name != None
        starting_items.append(pickup_data)

    keyword_arguments["starting_items"] = starting_items

    custom_save_start = patch_data["starting_conditions"]
    keyword_arguments["custom_save_start"] = [
        custom_save_start["starting_region"],
        custom_save_start["starting_save_station_index"],
    ]

    if "controls" in patch_data:
        keyword_arguments["controls"] = patch_data["controls"]

    patch_rom(rom_file, output_path, item_list, None, None, seed, **keyword_arguments)


def patch_rom(rom_file, output_path, item_list=None, player_name=None, recipient_list=None, seed=0, **kwargs):
    starting_items = []
    if "starting_items" in kwargs:
        starting_items = kwargs["starting_items"]

    # Generate item placement if none has been provided.
    # This will give a warning message, as this is only appropriate for debugging patcher features.
    if item_list is None:
        item_list = gen_vanilla_game()
        starting_items = None
        print(
            "WARNING: Item list was not supplied to ROM patcher. Generating Vanilla placement with no starting items."
        )
    else:
        try:
            assert len(item_list) >= 100
        except:
            raise ValueError("ERROR: Non-Empty item list didn't meet length requirement. Aborting ROM Patch.")

    # Now write our new routines to memory.
    # First we append new routines to free space
    # At the end of bank 85.
    in_game_address = 0x9643
    in_game_address = write_messagebox_routines(rom_file, in_game_address)

    # Create and write the routines which handle pickup effects.
    equipment_gets = get_equipment_routines()
    item_get_routines_dict = get_all_necessary_pickup_routines(item_list, equipment_gets, starting_items, player_name)
    item_get_routine_addresses_dict = write_item_get_routines(rom_file, item_get_routines_dict, in_game_address)

    # Patch Item Placements into the ROM.
    place_items(rom_file, item_get_routine_addresses_dict, item_list)

    # Add starting items patch
    add_starting_inventory(rom_file, starting_items, item_get_routine_addresses_dict)

    # Skip intro cutscene and/or Space Station Ceres depending on parameters passed to function.
    # Default behavior is to skip straight to landing site.

    skip_intro = True
    if "skip_intro" in kwargs:
        skip_intro = kwargs["skip_intro"]
    # Check to make sure intro option choice doesn't conflict with custom start point.
    custom_save_start = None
    if "custom_save_start" in kwargs:
        custom_save_start = kwargs["custom_save_start"]
    write_save_initialization_routines(rom_file, skip_intro, custom_save_start)

    # Write the routine used to cause Crateria to wake up
    write_crateria_wakeup_routine(rom_file)

    # Write routines used for multiworld
    write_multiworld_routines(rom_file)

    # Apply static patches.
    # Many of these patches are provided by community members -
    # See top of document for details.
    # Dictionary of files associated with static patch names:
    static_patch_dict = get_patch_dict()
    patches_dir = Path(__file__).parent.joinpath("Patches")

    static_patches = ["door_transitions", "varia_rng", "varia_timer_fix", "eye_fix"]
    if seed != 0:
        write_seed_to_display(rom_file, seed)
        static_patches.append("seed_display")
    if "static_patches" in kwargs:
        static_patches += kwargs["static_patches"]
        for patch in static_patches:
            if patch in static_patch_dict:
                IPSPatcher.apply_ips_patch(patches_dir.joinpath(static_patch_dict[patch]), rom_file)
            else:
                print(f"Provided patch {patch} does not exist!")

    # Write default controls to ROM
    if "controls" in kwargs:
        write_controls(kwargs["controls"], rom_file)

    do_doors(rom_file)

    with open(output_path, "wb") as output_file:
        output_file.write(rom_file.getbuffer())

    rom_file.close()
    print("ROM modified successfully.")


if __name__ == "__main__":
    # Build in this to make it faster to test.
    # Saves me some time.
    if os.path.isfile(os.getcwd() + "/romfilepath.txt"):
        rom_path_file = open(os.getcwd() + "/romfilepath.txt", "r")
        file_path = rom_path_file.readline().rstrip()
        print("Patching will be applied to ROM at:", file_path)
        rom_path_file.close()
    else:
        print(
            "Enter full file path for your headerless Super Metroid ROM file.\nNote that the patcher DOES NOT COPY the game files - it will DIRECTLY OVERWRITE them. Make sure to create a backup before using this program.\nWARNING: Video game piracy is a crime - only use legally obtained copies of the game Super Metroid with this program."
        )
        file_path = input()
    if os.path.isfile(os.getcwd() + "\\test_data.json"):
        json_file = open("test_data.json", "r")
    else:
        print("Enter full file path for your JSON patch data file.")
        json_path = input()
        try:
            assert os.path.isfile(json_path)
        except:
            raise ValueError("ERROR: JSON file does not exist.")
        json_file = open(json_path)
    json = json.load(json_file)
    json_file.close()

    with open(file_path, "rb+") as fh:
        bytes_io = BytesIO(fh.read())

    # Patch ROM
    patch_rom_json(bytes_io, file_path, json)
