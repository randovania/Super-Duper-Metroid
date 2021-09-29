# Super Metroid Interface
# By Samuel D. Roy
#
# This script is used for interfacing with SNI for the Super Metroid randomizer.
# This script also exposes some functionality which trackers and other programs can use.
#
# Data about the SM game which can be probed:
# -Current game state (ex. title screen, in game, paused, etc.)
# -Current game region (ex. Crateria, Maridia, Ceres, etc.)
# -Current player map coordinates
# -Current game room
# -Map progress (e.g. which map squares have been visited)
# -Map stations visited
# -Current inventory
# -Item locations obtained
# -Console type (Emulator, SD2SNES, SNES Classic)

# In theory, a player might be able to break this if they somehow switched states in between the steps of a key operation.
# If a player, for example, unloaded their game after we checked to see that their game was loaded but before we check their status,
# That could possibly cause us to get a garbage value.
# There's not really anything we can do about that, since there's no way to lock this data (to my knowledge).
# This is incredibly unlikely, however, as the speed of this program and its interface
# Is significantly faster than the framerate of an SNES (and obviously blows the speed of a human's actions out of the water).
# If interfacing is slower with physical devices there may be a need for further investigation.

# TODO: Implement data sharing with this.
# Some data from the launcher needs to be sent to the interface for it to function fully.
# This includes:
#   -Message Box Address Dict
#   -Item Routine Address Dict
#   -List of non-vanilla items in game

import json
import os
import sys
import threading
import time

from SuperDuperMetroid.SM_Constants import SuperMetroidConstants
from websocket import create_connection

# Converts a hexadecimal string to a base 10 integer.
def hex_to_int(hex_to_convert):
    return int(hex_to_convert, 16)


# Converts an integer to a hexadecimal string.
def int_to_hex(int_to_convert):
    return (hex(int_to_convert)[2:]).upper()


# Converts a hexadecimal string to binary data.
def hex_to_data(hex_to_convert):
    return bytes.fromhex(hex_to_convert)


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


class SuperMetroidInterface:

    # These get imported dynamically from a JSON file created by the patcher.
    # This is necessary because these may not always be in the same place every game.
    itemRoutineDict = {
        "Energy Tank": None,
        "Missile Expansion": None,
        "Super Missile Expansion": None,
        "Power Bomb Expansion": None,
        "Grapple Beam": None,
        "X-Ray Scope": None,
        "Varia Suit": None,
        "Spring Ball": None,
        "Morph Ball": None,
        "Screw Attack": None,
        "Hi-Jump Boots": None,
        "Space Jump": None,
        "Speed Booster": None,
        "Charge Beam": None,
        "Ice Beam": None,
        "Wave Beam": None,
        "Spazer Beam": None,
        "Plasma Beam": None,
        "Morph Ball Bombs": None,
        "Reserve Tank": None,
        "Gravity Suit": None,
        "No Item": None,
    }

    # TODO: Find a clean way to send dynamically generated item list to interface from patcher, as multiworld will later involve dynamically adding items to the game, and these may be ordered differently for different players.
    # TODO: Import ammo per item from the patcher

    obtainedToggleItems = []
    equippedToggleItems = []

    ammoItemsHeldList = []
    ammoItemCurrentCount = []
    ammoItemMaximumCount = []

    webSocket = None
    # If true, player has booted game and connection has been initialized.
    connectionInitialized = False
    # True if SNI has successfully connected to an SNES-Like device.
    connectedToDevice = False
    # True if player's device has the game Super Metroid loaded,
    # Or if we can't verify for sure that this is the case.
    # Note that the SNES Classic can't tell us what game it's playing.
    inSuperMetroid = False
    # True if player has started a save file. If this is false we can't expect to reliably read RAM.
    gameLoaded = False
    # True if player is playing Super Metroid and is in the standard gamestate.
    # Player cannot be in a transition, the pause menu, a cutscene, the title screen, a demo, or anything else.
    playingGame = False
    # List of things about the device, such as device type, last known game, and system capabilities.
    deviceInfo = None

    lastLocationsCheckedBitflags = None

    lock = threading.Lock()
    inGameInvokeEventThread = None
    pollLocationChecksThread = None
    # Format of a queued event:
    # Will check to see if args or kwargs are not present, will omit them if this is the case.
    # Note that you should still have three elements in the base list, as it will naiively index it.
    # Just set unused things to be either empty or None
    # [function, [arg1, arg2, ...], {kw1 : kwarg1, kw2 : kwarg2, ...}]
    queued_events = []

    # Small routines used to wrap simple operations for readability.

    # These methods are used to directly interface with the game.
    # They will be called by higher-level code.
    def initialize_connection(self):
        try:
            self.webSocket = create_connection("ws://localhost:8080")
            print("Connection made with SNI successfully.")
            self.connectionInitialized = True
        except Exception:
            print("ERROR: Could not connect to SNI.")

    # After connecting to SNI, get list of devices and connect to the first.
    def connect_to_device(self):
        if self.connectionInitialized:
            # Get devices.
            json_get_devices_command = {"Opcode": "DeviceList", "Space": "SNES"}

            self.webSocket.send(json.dumps(json_get_devices_command))
            result = self.webSocket.recv()
            result = (json.loads(result))["Results"]
            if len(result) == 0:
                print("ERROR: No devices were found by SNI. Could not link to any device.")
                return
            if len(result) > 1:
                print("WARNING: More than one devices have been listed by SNI. Device list is as follows:")
                for i, device in enumerate(result):
                    print(f"\tDevice {str(i)}: {device}")
                print("The Super Metroid interface will default to connecting to the first device listed.\n")

            # Connect to first device.
            device_to_connect_to = [result[0]]
            json_attach_to_device_command = {"Opcode": "Attach", "Space": "SNES", "Operands": device_to_connect_to}
            self.webSocket.send(json.dumps(json_attach_to_device_command))
            self.verify_connected_to_device()
            self.print_device_info()
            if self.connectedToDevice:
                print("Successfully connected to device.")
        else:
            print("ERROR: An attempt was made to connect to a device, but no connection has been made with SNI.")

    def print_device_info(self):
        print("Device Info:")
        for info in self.deviceInfo:
            print("\t" + info)

    # Get data at the specified address.
    # If checkRomRead = True, check whether the read being requested would read from ROM.
    # If it would, check to see whether the system being used allows it.
    # If it doesn't, refuse to read it, throw error.
    def get_data(self, address, num_bytes, check_rom_read=True):
        self.verify_connected_to_device()
        if self.connectedToDevice:
            if hex_to_int(address) < hex_to_int("F50000") and check_rom_read:
                if "NO_ROM_READ" in self.deviceInfo:
                    print(
                        f"ERROR: An attempt was made to read from ROM, but this operation is not supported for device of type '{self.deviceInfo[0]}'."
                    )
                    return None
            json_read_data_from_address_command = {
                "Opcode": "GetAddress",
                "Space": "SNES",
                "Operands": [address, int_to_hex(num_bytes)],
            }
            self.webSocket.send(json.dumps(json_read_data_from_address_command))
            result = self.webSocket.recv()
            result = data_to_hex(result)
            # print(f"Read from address {address} was successful.")
            return result
        else:
            print("ERROR: Connection was not initialized properly before attempting to get data. Ignoring request...")
            return None

    # Write data to the specified address.
    # If checkRomWrite = True, check whether the write being requested would write to ROM.
    # If it would, check to see whether the system being used allows it.
    # If it doesn't, refuse to write it, throw error.
    def set_data(self, address, hex_data, check_rom_write=True):
        self.verify_connected_to_device()
        if self.connectedToDevice:
            if hex_to_int(address) < hex_to_int("F50000") and check_rom_write:
                if "NO_ROM_WRITE" in self.deviceInfo:
                    print(
                        f"ERROR: An attempt was made to write to ROM, but this operation is not supported for device of type '{self.deviceInfo[0]}'."
                    )
                    return None
            # Send Put Data Opcode
            num_bytes = len(hex_data) // 2
            json_read_data_from_address_command = {
                "Opcode": "PutAddress",
                "Space": "SNES",
                "Operands": [address, int_to_hex(num_bytes)],
            }
            self.webSocket.send(json.dumps(json_read_data_from_address_command))
            # Send Data
            self.webSocket.send(hex_to_data(hex_data))
            # print(f"Write to address {address} was successful.")
        else:
            print("ERROR: Connection was not initialized properly before attempting to set data. Ignoring request...")

    # Checks for an overflow, and corrects it if one has occurred.
    # Used to check values before we alter them.
    @staticmethod
    def check_value_overflow(current_value, amount_to_add, num_bytes=2):
        corrected_amount_to_add = amount_to_add
        if current_value + amount_to_add < 0:
            corrected_amount_to_add += current_value + amount_to_add
        elif current_value + amount_to_add > ((2 ^ (num_bytes * 8)) - 1):
            corrected_amount_to_add = ((2 ^ (num_bytes * 8)) - 1) - current_value
        return corrected_amount_to_add

    # Checks memory at a specific address to see if item value has overflown, corrects it if it has.
    # Used to check values after we rely on a game routine to change them.
    # This is really more of a failsafe in case people set absurd values for expansion amounts, but it won't work in singleplayer.
    # if bigToSmall is true, we're looking to see if a value has ended up smaller than it was initially. Otherwise, we're looking for the opposite.
    # Run after a small delay to allow the SNES to perform the operation.
    def __check_value_at_address_overflow(self, address, last_value, item_name, big_to_small=True, num_bytes=2):
        current_value = HexToInt(self.get_data(address))
        if current_value == last_value:
            print(
                f"CAUTION: Value of '{item_name}' has not updated by the time it could be checked - it is possible the CPU hasn't had time to change it, or the game state may have changed."
            )
            return
        if big_to_small and current_value < last_value:
            print(
                f"WARNING: Value of '{item_name}' has overflowed because it became too big. This may be due to very large values being used for this item's reward amount. Setting its value to the maximum possible..."
            )
            self.set_data("FF" * num_bytes, address)
        elif not big_to_small and current_value > last_value:
            print(
                f"WARNING: Value of '{item_name}' has overflowed because it became too small. This may be due to negative values being used for this item's reward amount. Setting its value to 0..."
            )
            self.set_data("00" * num_bytes, address)

    # Receive an item and display a message.
    # Works for all item types.
    # For ammo-type items, energy tanks, and reserve tanks, they will award whatever amount has been set in the player's patcher.
    # If this results in an overflow, their item amount will be set to its max possible value.
    # If showMessage is false, this will be done without displaying a message for player.
    # Note that this will automatically equip equipment items (will not equip Spazer and Plasma simultaneously)
    # Also note that this does not error out if player is not in game. We record entries to our queue even in menus.
    # It is the job of the inGameInvokeEventThread to check whether the state is correct before giving out the items.
    def receive_item(self, item_name, sender, show_message=True):
        if item_name in SuperMetroidConstants.itemList:
            # Lock this part to prevent overlapping with the event handling thread.
            print("Trying to queue Receive Item Event...")
            self.lock.acquire()
            try:
                self.queued_events.append((self.__receive_item_internal, [item_name, sender, show_message], {}))
                if self.inGameInvokeEventThread is None or not self.inGameInvokeEventThread.is_alive():
                    self.inGameInvokeEventThread = threading.Thread(target=self.__invoke_in_game_events)
                    self.inGameInvokeEventThread.daemon = True
                    self.inGameInvokeEventThread.start()
                print("Receive Item Event queued successfully!")
            finally:
                self.lock.release()
        else:
            print(
                f"ERROR: Super Metroid player was sent item '{item_name}', which is not known to be a valid Super Metroid item."
            )

    def start_polling_game_for_checks(self):
        if self.pollLocationChecksThread is None or not self.pollLocationChecksThread.is_alive():
            # This data can be junk so we take care to set this before we start polling.
            # That way we only update once everything is actually cleared.
            # TODO: Modify code so a flag is set once we know this memory is good.
            self.lastLocationsCheckedBitflags = bin(hex_to_int(self.get_data("F6FFD0", 32)))[2:].zfill(256)
            self.pollLocationChecksThread = threading.Thread(target=self.__poll_game_for_checks)
            self.pollLocationChecksThread.daemon = True
            self.pollLocationChecksThread.start()
            print("Started polling for location checks...")

    # Poll the game to see
    def __poll_game_for_checks(self):
        # TODO: I'm sure there's better syntax for doing this sort of thing.
        timeout = 1.4
        while True:
            bitflags = bin(hex_to_int(self.get_data("F6FFD0", 32)))[2:].zfill(256)
            time.sleep(timeout)
            if bitflags != self.lastLocationsCheckedBitflags:
                # Convert to a binary string so we can easily check flags
                for index, location_bit in enumerate(bitflags):
                    if location_bit == "1":
                        if self.lastLocationsCheckedBitflags is None or self.lastLocationsCheckedBitflags[index] == "0":
                            # It is necessary to reverse the bit order per byte for calculating our index,
                            # As the most significant bit comes first in the string and would,
                            # Without this treatment,
                            # Act as though it were the least significant bit.
                            true_index = (index // 8) * 8 + -((index % 8) - 7)
                            print(
                                f"Samus Checked Location {SuperMetroidConstants.bitflagIndexToLocationNameDict[true_index]}"
                            )
                self.lastLocationsCheckedBitflags = bitflags

    # Run on its own thread.
    # Polls the game to see when it's ready,
    # Then executes events in-game.
    def __invoke_in_game_events(self):
        self.lock.acquire()
        try:
            timeout = 0.3
            while len(self.queued_events) > 0:
                if self.is_player_ready_for_event():
                    print("Player is ready for event, sending now...")
                    current_event = self.queued_events.pop(0)
                    (current_event[0])(*current_event[1])
                    timeout = 0.8
                else:
                    print(f"Player is not ready for event, waiting {timeout} seconds...")
                    self.lock.release()
                    time.sleep(timeout)
                    self.lock.acquire()
                    timeout *= 1.3
        finally:
            self.lock.release()

    # The part that actually does the thing.
    # Only called from event manager, will assume that state is permissible when run.
    # Always called from within a lock.
    def __receive_item_internal(self, item_name, sender, show_message=True):
        # Use the in-game event system to send a player their item.
        if show_message:
            # Set message ID appropriately.
            # Needs to be a valid item ID (though not necessarily the message ID of the item the player received.)
            self.set_data("F51C1F", "1000")

            # Set the function to be called.
            # TODO: Verify this is correct
            self.set_data("F6FF72", "65AD")

            # Set the "Item Picked Up" word to 1.
            # Tells the game that the next item it gets will be from multi.
            self.set_data("F6FF74", "0100")
            # Give item data needed to complete pickup.

            # Header/footer.
            # This is a standard item, so give the pointer to
            # An empty header/footer of correct width.
            # TODO: Import these dynamically from patcher.
            width = "Small"
            if item_name in SuperMetroidConstants.itemMessageWidths:
                width = SuperMetroidConstants.itemMessageWidths[item_name]
            if width == "Small":
                self.set_data("F6FF76", "4080")
            elif width == "Large":
                self.set_data("F6FF76", "0080")

            # Content.
            # Different for each item - main message for an item pickup.
            # TODO: Import these dynamically from patcher.
            self.set_data("F6FF78", reverse_endianness(SuperMetroidConstants.itemMessageAddresses[item_name]))

            # Message box size, in bytes.
            # Dictates height.
            size = "4000"
            if item_name in SuperMetroidConstants.itemMessageNonstandardSizes:
                size = reverse_endianness(SuperMetroidConstants.itemMessageNonstandardSizes[item_name])
            self.set_data("F6FF7A", size)

            # Message ID. Should be accurate if it can be helped.
            # Also set to Wave Beam.
            self.set_data("F6FF7C", reverse_endianness(SuperMetroidConstants.itemMessageIDs[item_name]))

            # Get the original routine address and save it to jump to later.
            original_jump_destination = self.get_data("F50A42", 2)

            self.set_data("F6FF80", original_jump_destination)

            # Item Collection Routine.
            # What we actually call on pickup.
            self.set_data("F6FF7E", self.itemRoutineDict[item_name])

            # Overwrite an instruction pointer in the game's RAM.
            # This is what actually causes our code to execute.
            self.set_data("F50A42", "F0FF")

        # Otherwise, directly add the item to their inventory.
        else:
            if item_name in SuperMetroidConstants.toggleItemList:
                self.give_toggle_item(item_name)
            elif item_name in SuperMetroidConstants.ammoItemList:
                # TODO: Change this part so that this is passed as an argument actually
                self.increment_item(item_name, self.ammoItemToQuantity[item_name])

    # For displaying an arbitrary message
    # TODO: Figure out how to do this.
    def receive_message(message, width="Variable", size=None):
        pass

    # The part that actually does the thing.
    # Only called from event manager, will assume that state is permissible when run.
    # Always called from within a lock.
    def __receive_message_internal(message, width="Variable", size=None):
        pass

    # Increment (or decrement) the amount of an item that a player has.
    # NOTE: This will not work with unique items (ex. Charge Beam, Gravity Suit)
    # These types of items are stored as bitflags, not integers.
    # This will work with Missiles, Supers, Power Bombs, E-Tanks, and Reserve Tanks
    # If maxAmountOnly is true, this will not increment the player's current number of this item, only the capacity for this item.
    # 7E:0A12 - 7E:0A13 Mirror's Samus's health. Used to check to make hurt sound and flash.
    # TODO: Test to see if this introduces errors in HUD graphics.
    def increment_item(self, item_name, increment_amount, max_amount_only=False):
        self.verify_game_loaded()
        if self.gameLoaded:
            if item_name in SuperMetroidConstants.ammoItemList:
                current_ammo_address = SuperMetroidConstants.ammoItemAddresses[item_name]
                max_ammo_address = int_to_hex(hex_to_int(current_ammo_address) + 2)
                current_ammo = reverse_endianness(self.get_data(current_ammo_address, 2))
                max_ammo = reverse_endianness(self.get_data(max_ammo_address, 2))
                if max_amount_only:
                    new_current_ammo = reverse_endianness(current_ammo)
                else:
                    new_current_ammo = reverse_endianness(
                        pad_hex(int_to_hex(hex_to_int(current_ammo) + increment_amount), 4)
                    )
                new_max_ammo = reverse_endianness(pad_hex(int_to_hex(hex_to_int(max_ammo) + increment_amount), 4))
                self.set_data(current_ammo_address, new_current_ammo)
                self.set_data(max_ammo_address, new_max_ammo)
            else:
                if item_name in SuperMetroidConstants.toggleItemList:
                    print(
                        f"ERROR: IncrementItem cannot be called with item '{item_name}', as this item is not represented by an integer."
                    )
                else:
                    print(
                        f"ERROR: Super Metroid player had item '{item_name}' incremented, but this item is not a valid Super Metroid item."
                    )
        else:
            print(
                "ERROR: An attempt was made to increment player's {itemName} by {incrementAmount}, but their game is not loaded."
            )

    # Give a player a bitflag-type item.
    # This will also equip it.
    # TODO: Make sure Plasma and Spazer can't both be equipped simultaneously
    def give_toggle_item(self, item_name):
        self.verify_game_loaded()
        if self.gameLoaded:
            if item_name in SuperMetroidConstants.toggleItemList:
                item_offset = SuperMetroidConstants.toggleItemBitflagOffsets[item_name]
                equipped_byte_address = int_to_hex(
                    hex_to_int(SuperMetroidConstants.toggleItemBaseAddress) + item_offset[0]
                )
                obtained_byte_address = int_to_hex(hex_to_int(equipped_byte_address) + 2)
                equipped_byte = self.get_data(equipped_byte_address, 1)
                obtained_byte = self.get_data(obtained_byte_address, 1)
                bitflag = 1 << item_offset[1]
                new_equipped_byte = pad_hex(int_to_hex(hex_to_int(equipped_byte) | bitflag), 2)
                new_obtained_byte = pad_hex(int_to_hex(hex_to_int(obtained_byte) | bitflag), 2)
                self.set_data(equipped_byte_address, new_equipped_byte)
                self.set_data(obtained_byte_address, new_obtained_byte)
            else:
                if item_name in SuperMetroidConstants.ammoItemList:
                    print(
                        f"ERROR: TakeAwayItem cannot be called with item '{item_name}', as this item is represented by an integer and not a bitflag."
                    )
                else:
                    print(
                        f"ERROR: Super Metroid player had item '{item_name}' taken away, but this item is not a valid Super Metroid item."
                    )
        else:
            print(f"ERROR: An attempt was made to send player {item_name}, but their game is not loaded.")

    # Take away a player's bitflag-type item if they have it.
    # This will also unequip it.
    def take_away_toggle_item(self, item_name):
        self.verify_game_loaded()
        if self.gameLoaded:
            if item_name in SuperMetroidConstants.toggleItemList:
                item_offset = SuperMetroidConstants.toggleItemBitflagOffsets[item_name]
                equipped_byte_address = pad_hex(
                    int_to_hex(hex_to_int(SuperMetroidConstants.toggleItemBaseAddress) + item_offset[0]),
                    2,
                )
                obtained_byte_address = pad_hex(int_to_hex(hex_to_int(equipped_byte_address) + 2), 2)
                equipped_byte = self.get_data(equipped_byte_address, 1)
                obtained_byte = self.get_data(obtained_byte_address, 1)
                bitflag = 1 << item_offset[1]
                # Do bitwise and with all ones (except the bitflag we want to turn off)
                new_equipped_byte = pad_hex(int_to_hex(hex_to_int(equipped_byte) & (255 - bitflag)), 4)
                new_obtained_byte = pad_hex(int_to_hex(hex_to_int(obtained_byte) & (255 - bitflag)), 4)
                self.set_data(equipped_byte_address, new_equipped_byte)
                self.set_data(obtained_byte_address, new_obtained_byte)
            else:
                if item_name in SuperMetroidConstants.ammoItemList:
                    print(
                        f"ERROR: TakeAwayItem cannot be called with item '{item_name}', as this item is represented by an integer and not a bitflag."
                    )
                else:
                    print(
                        f"ERROR: Super Metroid player had item '{item_name}' taken away, but this item is not a valid Super Metroid item."
                    )
        else:
            print(f"ERROR: An attempt was made to take away player's {item_name}, but their game is not loaded.")

    # Sends an info request.
    # Returns true if it receives a result.
    # Returns false if the request fails.
    def verify_connected_to_device(self):
        if self.connectionInitialized:
            try:
                json_get_device_info_command = {"Opcode": "Info", "Space": "SNES"}
                self.webSocket.send(json.dumps(json_get_device_info_command))
                result = self.webSocket.recv()
                result = (json.loads(result))["Results"]
                if len(result) < 1:
                    print("ERROR: No device info could be found. Device has not successfully attached.")
                    return False
                else:
                    self.deviceInfo = result
                    self.connectedToDevice = True
                    return True
            except Exception:
                print("ERROR: Failed to send verification message to SNI. Marking connection as closed...")
                self.connectionInitialized = False
                self.connectedToDevice = False
                self.deviceInfo = None
                return False
        else:
            print(
                "ERROR: Cannot verify that device has been connected, as the connection to SNI has not been initialized. Attempting to reestablish connection..."
            )
            self.connect_to_device()
            # self.deviceInfo = None
            # self.connectedToDevice = False
            return False

    # Check game to make sure it's Super Metroid.
    def verify_correct_game(self):
        self.verify_connected_to_device()
        if self.connectedToDevice:
            game_type = self.deviceInfo[2].strip()
            if game_type == "No Info":
                # print("CAUTION: Could not determine current game. This could be because the device connected is an SNES Classic, or because the interface hasn't exposed this information.")
                self.inSuperMetroid = True
                return True
            if game_type == "Super Metroid":
                self.inSuperMetroid = True
                return True
            else:
                print(
                    f"ERROR: Could not verify game being played as Super Metroid. According to SNI, this device is currently running {game_type}."
                )
                self.inSuperMetroid = False
                return False
        else:
            self.inSuperMetroid = False
            return False

    # Check game version.
    # Either NTSC or PAL
    # Note that NTSC-U and NTSC-J are identical.
    def get_game_version(self):
        pass

    # Check to see if player is ready to have an event inserted.
    def is_player_ready_for_event(self):
        self.verify_in_gameplay()
        if self.playingGame:
            # Query function slot to make sure it isn't currently occupied.
            functionSlot = self.get_data("F50A42", 2)
            # F0FF is the value used to redirect control flow to arbitrary functions.
            # If this is the function slot's current value, we'd be writing over our own request.
            if functionSlot != "F0FF":
                return True
            else:
                return False
        else:
            return False

    # Query if the player is currently in a fully loaded save.
    # This ensures that we can read important values from RAM, such as item counts, without fearing garbage data.
    def verify_game_loaded(self):
        self.verify_correct_game()
        if self.inSuperMetroid:
            game_state = self.get_game_state()
            # We could technically give players items while pausing,
            # But this causes the pickup box to show up on a pitch black screen once
            # The player unpauses.
            # This may be confusing as players will not be able to see it.
            valid_game_states = ["In Game", "In Room Transition"]
            if game_state in valid_game_states:
                self.gameLoaded = True
                return True
            else:
                self.gameLoaded = False
                return False
        else:
            self.gameLoaded = False
            return False

    # Query if the player is currently in normal gameplay.
    # Will not return true if player is in a cutscene, in a transition, loading, paused, in a menu, etc.
    def verify_in_gameplay(self):
        self.verify_game_loaded()
        if self.gameLoaded:
            game_state = self.get_game_state()
            if game_state == "In Game":
                self.playingGame = True
                return True
            else:
                self.playingGame = False
                return False
        else:
            self.playingGame = False
            return False

    # Get what state the player is in.
    # Returns a string.
    # TODO: Convert to a dict
    def get_game_state(self):
        self.verify_correct_game()
        if self.inSuperMetroid:
            status = hex_to_int(self.get_data("F50998", 1))
            if status == 1:
                return "Title Screen"
            elif status == 4:
                return "In Menu"
            elif status == 5:
                return "Loading a Area"
            elif status == 6:
                return "Loading a Save Game"
            elif status == 7:
                return "Initializing from a Save Game"
            elif status == 8:
                return "In Game"
            elif status == 9:
                return "In Room Transition"
            elif status == 10 or status == 11:
                return "On Elevator"
            elif 12 <= status <= 14:
                return "Pausing"
            elif status == 15:
                return "Paused"
            elif 16 <= status <= 20:
                return "Unpausing"
            elif 21 <= status <= 26:
                return "Dead"
            elif 30 <= status <= 36:
                return "In Cutscene"
            elif status == 42:
                return "Watching Demo"
            else:
                return "Status Not Known"
        else:
            print(
                "ERROR: An attempt was made to query game state, but something other than the game Super Metroid seems to be loaded."
            )

    # Returns a pretty string saying where player is.
    # Room and region name.
    # 7E:07BD - 7E:07BF : 3 byte pointer to room tilemap.
    def get_player_location(self):
        pass

    def get_player_inventory(self):
        self.verify_game_loaded()
        if self.gameLoaded:
            self.get_player_ammo_counts()
            self.get_player_toggle_items()
        else:
            print("ERROR: An attempt was made to query the player's inventory, but they aren't in the game yet.")

    def get_player_ammo_counts(self):
        self.verify_game_loaded()
        if self.gameLoaded:
            ammo_item_list = []
            ammo_item_current_count = []
            ammo_item_maximum_count = []
            # Get player's ammo counts.
            for item_name, address in SuperMetroidConstants.ammoItemAddresses.items():
                ammo_item_list.append(item_name)
                current_ammo = self.get_data(address, 2)
                ammo_item_current_count.append(hex_to_int(reverse_endianness(current_ammo)))
                max_ammo_address = pad_hex(int_to_hex(hex_to_int(address) + 2), 6)
                maximum_ammo = self.get_data(max_ammo_address, 2)
                ammo_item_maximum_count.append(hex_to_int(reverse_endianness(maximum_ammo)))
                # Reserve energy is backwards, for some reason.
                if item_name == "Reserve Tank":
                    index = len(ammo_item_current_count) - 1
                    ammo_item_current_count[index], ammo_item_maximum_count[index] = (
                        ammo_item_maximum_count[index],
                        ammo_item_current_count[index],
                    )
            for i in range(len(ammo_item_list)):
                print(
                    f"Samus has {str(ammo_item_current_count[i])} {SuperMetroidConstants.itemNameToQuantityName[(ammo_item_list[i])]} out of {str(ammo_item_maximum_count[i])}."
                )
            self.ammoItemsHeldList = ammo_item_list
            self.ammoItemCurrentCount = ammo_item_current_count
            self.ammoItemMaximumCount = ammo_item_maximum_count
        else:
            print("ERROR: An attempt was made to query the player's ammo counts, but they aren't in the game yet.")

    def get_player_toggle_items(self):
        self.verify_game_loaded()
        if self.gameLoaded:
            toggle_item_hex = self.get_data(SuperMetroidConstants.toggleItemBaseAddress, 8)
            obtained_items = []
            equipped_items = []
            for item_name, byte_bit_offset_pair in SuperMetroidConstants.toggleItemBitflagOffsets.items():
                obtained_byte = toggle_item_hex[
                    ((byte_bit_offset_pair[0] * 2) + 4) : ((byte_bit_offset_pair[0] * 2) + 6)
                ]
                equipped_byte = toggle_item_hex[(byte_bit_offset_pair[0] * 2) : ((byte_bit_offset_pair[0] * 2) + 2)]
                obtained_val = hex_to_int(obtained_byte)
                equipped_val = hex_to_int(equipped_byte)
                bit_to_check = 1 << byte_bit_offset_pair[1]
                if (obtained_val & bit_to_check) != 0:
                    obtained_items.append(item_name)
                if (equipped_val & bit_to_check) != 0:
                    equipped_items.append(item_name)
                    if item_name not in obtained_items:
                        print(f"WARNING: Player has equipped item '{item_name}', but they haven't obtained it yet.")
            self.obtainedToggleItems = obtained_items
            self.equippedToggleItems = equipped_items
            for item_name in obtained_items:
                display_string = f"Samus has obtained {item_name}"
                if item_name in equipped_items:
                    display_string += ", and has it equipped."
                else:
                    display_string += ", but does not have it equipped."
                print(display_string)
        else:
            print("ERROR: An attempt was made to query the player's toggle items, but they aren't in the game yet.")

    # Check if player has debug mode on.
    def get_player_debug_state(self):
        pass

    # Check if player has sounds enabled.
    def get_sounds_enabled(self):
        pass

    # Get what region player is in right now.
    def get_region_number(self):
        pass

    # Get what map coordinates player is in right now.
    def get_map_coordinates(self):
        pass

    # Get what tiles in current region player has visited.
    # 7E:07F7 - 7E:08F6 : Map tiles explored for current area (1 tile = 1 bit)
    # TODO: Make more observations about data format
    def get_map_completion(self):
        pass

    # Check if player has automap enabled.
    def get_automap_enabled(self):
        pass

    # Used to take away X-Ray Scope and Grapple Beam.
    # 7E:09D2 - 7E:09D3 : Currently selected status bar item
    # TODO: Check whether this is necessary.
    # def __SetStatusBarSelection(self):
    #     pass

    # Close interface, shut down any threads
    def close(self):
        self.close_connection()
        sys.exit()

    # I don't know if this is strictly necessary, but it can't possibly hurt.
    def close_connection(self):
        if self.connectionInitialized:
            self.webSocket.close()
        else:
            print("WARNING: Connection cannot be closed, as no connection was initialized. Ignoring request...")

    # This method handles making sure requests don't overlap, and that requests wait for one another to finish.
    # Not all requests need to be handled this way, such as those which only read from memory.
    def handle_request_queue(self):
        pass


def temp(interface):
    interface.receive_item("Wave Beam", "Galactic Federation HQ")
    interface.receive_item("Ice Beam", "Galactic Federation HQ")
    interface.receive_item("Plasma Beam", "Galactic Federation HQ")
    interface.receive_item("Charge Beam", "Galactic Federation HQ")
    interface.receive_item("Grapple Beam", "Galactic Federation HQ")
    interface.receive_item("X-Ray Scope", "Galactic Federation HQ")
    interface.receive_item("Varia Suit", "Galactic Federation HQ")
    interface.receive_item("Gravity Suit", "Galactic Federation HQ")
    interface.receive_item("Morph Ball", "Galactic Federation HQ")
    interface.receive_item("Spring Ball", "Galactic Federation HQ")
    interface.receive_item("Morph Ball Bombs", "Galactic Federation HQ")
    interface.receive_item("Speed Booster", "Galactic Federation HQ")
    interface.receive_item("Hi-Jump Boots", "Galactic Federation HQ")
    interface.receive_item("Space Jump", "Galactic Federation HQ")
    interface.receive_item("Screw Attack", "Galactic Federation HQ")
    interface.receive_item("Energy Tank", "Galactic Federation HQ")
    interface.receive_item("Energy Tank", "Galactic Federation HQ")
    interface.receive_item("Energy Tank", "Galactic Federation HQ")
    interface.receive_item("Energy Tank", "Galactic Federation HQ")
    interface.receive_item("Energy Tank", "Galactic Federation HQ")
    interface.receive_item("Energy Tank", "Galactic Federation HQ")
    interface.receive_item("Reserve Tank", "Galactic Federation HQ")
    interface.receive_item("Reserve Tank", "Galactic Federation HQ")
    interface.receive_item("Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Super Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Super Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Super Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Super Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Super Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Super Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Super Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Super Missile Expansion", "Galactic Federation HQ")
    interface.receive_item("Power Bomb Expansion", "Galactic Federation HQ")
    interface.receive_item("Power Bomb Expansion", "Galactic Federation HQ")
    interface.receive_item("Power Bomb Expansion", "Galactic Federation HQ")
    interface.receive_item("Power Bomb Expansion", "Galactic Federation HQ")
    interface.receive_item("Power Bomb Expansion", "Galactic Federation HQ")
    interface.receive_item("Power Bomb Expansion", "Galactic Federation HQ")


if __name__ == "__main__":
    menu = "C: Initialize Connection\n"
    menu += "D: Attach to a Device\n"
    menu += "I: Query Inventory\n"
    menu += "S: Query Gamestate\n"
    menu += "R: Query If Player is Ready for an Item\n"
    menu += "W: Send Wave Beam\n"
    menu += "G: Force Give Screw Attack\n"
    menu += "T: Force Take Screw Attack\n"
    menu += "M: Force Give 5 Missiles\n"
    menu += "P: Start Polling for Location Checks\n"
    menu += "Q: Quit"
    last_input = None
    while last_input != "Q":
        print(menu)
        last_input = input()[0]
        if last_input == "C":
            print("\nAttempting to connect...")
            interface.initialize_connection()
        elif last_input == "D":
            print("\nAttempting to attach to a device...")
            interface.connect_to_device()
        elif last_input == "I":
            print("\nAttempting to query inventory...")
            interface.get_player_inventory()
        elif last_input == "S":
            print("\nAttemtping to query game state...")
            state = interface.get_game_state()
            if state is not None:
                print(f"Current State: {state}")
        elif last_input == "R":
            if interface.is_player_ready_for_event():
                print("Samus is ready to receive an item.")
            else:
                print("Samus isn't ready to receive an item.")
        elif last_input == "W":
            print("\nTrying to send Wave Beam...")
            interface.receive_item("Wave Beam", "Galactic Federation HQ")
        elif last_input == "G":
            print("\nManually Giving Screw Attack...")
            interface.give_toggle_item("Screw Attack")
        elif last_input == "T":
            print("\nManually Taking Screw Attack...")
            interface.take_away_toggle_item("Screw Attack")
        elif last_input == "M":
            print("\nManually Giving 5 Missiles...")
            interface.increment_item("Missile Expansion", 5)
        elif last_input == "P":
            print("\nManually starting polling thread...")
            interface.start_polling_game_for_checks()
        elif last_input == "F":
            print("\nChecking and printing location bitflags...")
            print(interface.get_data("F6FFD0", 96))
        elif last_input == "H":
            print("\nTEMP COMMAND")
            temp(interface)
        elif last_input == "Q":
            print("\nQuitting...")
            interface.close()
        else:
            print(f"\nERROR: Input '{str(last_input)}' not recognized")
