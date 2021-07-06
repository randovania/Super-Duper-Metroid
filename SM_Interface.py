# Super Metroid Interface
# By Samuel D. Roy
#
# This script is used for interfacing with QUSB2SNES for the Super Metroid randomizer.
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

import threading
import json
import pprint
import websocket
from websocket import create_connection

class SuperMetroidInterface:
    # List of ammo items, ordered by ascending Message ID
    ammoItemList = [
        "Energy Tank",
        "Missile Expansion",
        "Super Missile Expansion",
        "Power Bomb Expansion",
        "Reserve Tank"
    ]
    
    # List of toggle items, ordered by ascending Message ID
    toggleItemList = [
        "Grapple Beam",
        "X-Ray Scope",
        "Varia Suit",
        "Spring Ball",
        "Morph Ball",
        "Screw Attack",
        "Hi-Jump Boots",
        "Space Jump",
        "Speed Booster",
        "Charge Beam",
        "Ice Beam",
        "Wave Beam",
        "Spazer Beam",
        "Plasma Beam",
        "Morph Ball Bombs",
        "Gravity Suit"
    ]
    
    # TODO: Import this dynamically.
    itemRoutineDict = {
        "Energy Tank"             : "D797",
        "Missile Expansion"       : "E597",
        "Super Missile Expansion" : "FE97",
        "Power Bomb Expansion"    : "1798",
        "Grapple Beam"            : "3098",
        "X-Ray Scope"             : "4798",
        "Varia Suit"              : "5E98",
        "Spring Ball"             : "7198",
        "Morph Ball"              : "8498",
        "Screw Attack"            : "9798",
        "Hi-Jump Boots"           : "AA98",
        "Space Jump"              : "BD98",
        "Speed Booster"           : "D098",
        "Charge Beam"             : "E398",
        "Ice Beam"                : "0E99",
        "Wave Beam"               : "3999",
        "Spazer Beam"             : "6499",
        "Plasma Beam"             : "8F99",
        "Morph Ball Bombs"        : "BA99",
        "Reserve Tank"            : "CD99",
        "Gravity Suit"            : "E099",
        "No Item"                 : "F399"
    }
    
    # Dictionary of nonstandard message box sizes
    # TODO: Replace this with something more elegant? Possibly.
    itemMessageNonstandardSizes = {
        "Missile Expansion"       : "0100",
        "Super Missile Expansion" : "0100",
        "Power Bomb Expansion"    : "0100",
        "Morph Ball Bombs"        : "0100",
        "Speed Booster"           : "0100",
        "Grapple Beam"            : "0100",
        "X-Ray Scope"             : "0100"}
    
    # Dictionary of item message locations
    itemMessageAddresses = {
        "Energy Tank"             : "877F",
        "Missile Expansion"       : "87BF",
        "Super Missile Expansion" : "88BF",
        "Power Bomb Expansion"    : "89BF",
        "Grapple Beam"            : "8ABF",
        "X-Ray Scope"             : "8BBF",
        "Varia Suit"              : "8CBF",
        "Spring Ball"             : "8CFF",
        "Morph Ball"              : "8D3F",
        "Screw Attack"            : "8D7F",
        "Hi-Jump Boots"           : "8DBF",
        "Space Jump"              : "8DFF",
        "Speed Booster"           : "8E3F",
        "Charge Beam"             : "8F3F",
        "Ice Beam"                : "8F7F",
        "Wave Beam"               : "8FBF",
        "Spazer Beam"             : "8FFF",
        "Plasma Beam"             : "903F",
        "Morph Ball Bombs"        : "907F",
        "Reserve Tank"            : "94FF",
        "Gravity Suit"            : "953F"}
    
    itemMessageIDs = {
        "Energy Tank"             : "0001",
        "Missile Expansion"       : "0002",
        "Super Missile Expansion" : "0003",
        "Power Bomb Expansion"    : "0004",
        "Grapple Beam"            : "0005",
        "X-Ray Scope"             : "0006",
        "Varia Suit"              : "0007",
        "Spring Ball"             : "0008",
        "Morph Ball"              : "0009",
        "Screw Attack"            : "000A",
        "Hi-Jump Boots"           : "000B",
        "Space Jump"              : "000C",
        "Speed Booster"           : "000D",
        "Charge Beam"             : "000E",
        "Ice Beam"                : "000F",
        "Wave Beam"               : "0010",
        "Spazer Beam"             : "0011",
        "Plasma Beam"             : "0012",
        "Morph Ball Bombs"        : "0013",
        "Reserve Tank"            : "0019",
        "Gravity Suit"            : "001A"}
    
    # Widths for all messages, either "Small" or "Large".
    # Small boxes have a width of 19 tiles,
    # Large boxes have a width of 26 tiles.
    # This dictates how messages are generated.
    # If a message type is not in this dict,
    # It is "Small".
    # All non-item messages, such as save station menus, recharge stations, etc. are also always small.
    # This includes unused messages.
    # Note that messageboxes may have varying heights.
    itemMessageWidths = {
        "Energy Tank"             : "Small",
        "Missile Expansion"       : "Large",
        "Super Missile Expansion" : "Large",
        "Power Bomb Expansion"    : "Large",
        "Grapple Beam"            : "Large",
        "X-Ray Scope"             : "Large",
        "Varia Suit"              : "Small",
        "Spring Ball"             : "Small",
        "Morph Ball"              : "Small",
        "Screw Attack"            : "Small",
        "Hi-Jump Boots"           : "Small",
        "Space Jump"              : "Small",
        "Speed Booster"           : "Large",
        "Charge Beam"             : "Small",
        "Ice Beam"                : "Small",
        "Wave Beam"               : "Small",
        "Spazer Beam"             : "Small",
        "Plasma Beam"             : "Small",
        "Morph Ball Bombs"        : "Large",
        "Reserve Tank"            : "Small",
        "Gravity Suit"            : "Small"}
    
    
    # Combined list, in order of ascending Message ID
    itemList = ammoItemList[0:4] + toggleItemList[0:15] + [ammoItemList[4]] + [toggleItemList[15]]
    
    # TODO: Find a clean way to send dynamically generated item list to interface from patcher, as multiworld will later involve dynamically adding items to the game, and these may be ordered differently for different players.
    
    # What address we should look at to find equipment (from QUSB2SNES's perspective, it's complicated)
    toggleItemBaseAddress = "F509A2"
    
    # Formatted offsets for where to read/write toggleable items.
    # Stored as a tuple.
    # First  value: Byte offset.
    # Second value: Bit offset.
    # NOTE: Equipped and collected items are stored adjacently in memory.
    # The item collected flag is always exactly two bytes after the corresponding item equipped flag.
    # Bit offset is the offset from lsb.
    # Ex. the 1 in 00000001 has offset 0.
    toggleItemBitflagOffsets = {
        "Grapple Beam"     : (1, 6),
        "X-Ray Scope"      : (1, 7),
        "Varia Suit"       : (0, 0),
        "Spring Ball"      : (0, 1),
        "Morph Ball"       : (0, 2),
        "Screw Attack"     : (0, 3),
        "Hi-Jump Boots"    : (1, 0),
        "Space Jump"       : (1, 1),
        "Speed Booster"    : (1, 5),
        "Charge Beam"      : (5, 4),
        "Ice Beam"         : (4, 1),
        "Wave Beam"        : (4, 0),
        "Spazer Beam"      : (4, 2),
        "Plasma Beam"      : (4, 3),
        "Morph Ball Bombs" : (1, 4),
        "Gravity Suit"     : (0, 5)
    }
    
    # Address to current quantity of indicated type.
    # Max quantity is stored 2 bytes after current quantity in all cases.
    ammoItemAddresses = {
        "Energy Tank"             : "F509C2",
        "Missile Expansion"       : "F509C6",
        "Super Missile Expansion" : "F509CA",
        "Power Bomb Expansion"    : "F509CE",
        "Reserve Tank"            : "F509D4"
    }
    
    itemNameToQuantityName = {
        "Energy Tank"             : "Energy",
        "Missile Expansion"       : "Missiles",
        "Super Missile Expansion" : "Super Missiles",
        "Power Bomb Expansion"    : "Power Bombs",
        "Reserve Tank"            : "Reserve Energy"
    }
    
    obtainedToggleItems  = []
    equippedToggleItems  = []
    
    ammoItemList         = []
    ammoItemCurrentCount = []
    ammoItemMaximumCount = []
    
    ws = None
    # If true, player has booted game and connection has been initialized.
    connectionInitialized = False
    # True if QUSB2SNES has successfully connected to an SNES-Like device.
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
    
    
    lock = threading.Lock()
    inGameInvokeEventThread = None
    # Format of a queued event:
    # Will check to see if args or kwargs are not present, will omit them if this is the case.
    # Note that you should still have three elements in the base list, as it will naiively index it.
    # Just set unused things to be either empty or None
    # [function, [arg1, arg2, ...], {kw1 : kwarg1, kw2 : kwarg2, ...}]
    queuedEvents = []
    
    # Small routines used to wrap simple operations for readability.
    
    # Convert a hex string to an integer.
    @staticmethod
    def HexToInt(hexToConvert):
        return int(hexToConvert, 16)

    # Convert an integer to a hex string.
    @staticmethod
    def IntToHex(intToConvert):
        return (hex(intToConvert)[2:]).upper()

    @staticmethod
    def HexToData(hexToConvert):
        return bytes.fromhex(hexToConvert)
    
    @staticmethod
    def DataToHex(dataToConvert):
        return ''.join('{:02x}'.format(x) for x in dataToConvert).upper()
    
    # Reverse the endianness of a hex string.
    # The Super Nintendo is a little-endian architecture, so this is often necessary.
    @staticmethod
    def ReverseEndianness(hexToReverse):
        assert (len(hexToReverse) % 2) == 0
        hexPairs = []
        for i in range(len(hexToReverse) // 2):
            hexPairs.append(hexToReverse[2 * i] + hexToReverse[2 * i + 1])
        reversedHexPairs = hexPairs[::-1]
        outputString = ""
        for pair in reversedHexPairs:
            outputString += pair
        return outputString

    # Pad hex with zeroes to the left until it reaches the specified length.
    @staticmethod
    def PadHex(hexToPad, numHexCharacters):
        returnHex = hexToPad
        while len(returnHex) < numHexCharacters:   
            returnHex = "0" + returnHex
        return returnHex

    # These methods are used to directly interface with the game.
    # They will be called by higher-level code.
    def InitializeConnection(self):
        try:
            self.ws = create_connection('ws://localhost:8080')
            print("Connection made with QUSB2SNES successfully.")
            self.connectionInitialized = True
        except Exception:
            print("ERROR: Could not connect to QUSB2SNES.")
    
    # After connecting to QUSB2SNES, get list of devices and connect to the first.
    def ConnectToDevice(self):
        if self.connectionInitialized:
            # Get devices.
            jsonGetDevicesCommand = {
                "Opcode" : "DeviceList",
                "Space"  : "SNES"
            }
            
            self.ws.send(json.dumps(jsonGetDevicesCommand))
            result = self.ws.recv()
            result = (json.loads(result))["Results"]
            if len(result) == 0:
                print("ERROR: No devices were found by QUSB2SNES. Could not link to any device.")
                return
            if len(result) > 1:
                print("WARNING: More than one devices have been listed by QUSB2SNES. Device list is as follows:")
                for i, device in enumerate(result):
                    print("\tDevice " + str(i) + ": " + device)
                print("The Super Metroid interface will default to connecting to the first device listed.\n")
            
            # Connect to first device.
            deviceToConnectTo = [result[0]]
            jsonAttachToDeviceCommand = {
                "Opcode"   : "Attach",
                "Space"    : "SNES",
                "Operands" : deviceToConnectTo
            }
            self.ws.send(json.dumps(jsonAttachToDeviceCommand))
            self.VerifyConnectedToDevice()
            self.PrintDeviceInfo()
            if(self.connectedToDevice):
                print("Successfully connected to device.")
        else:
            print("ERROR: An attempt was made to connect to a device, but no connection has been made with QUSB2SNES.")
    
    def PrintDeviceInfo(self):
        print("Device Info:")
        for info in self.deviceInfo:
            print("\t" + info)
    
    # Get data at the specified address.
    # If checkRomRead = True, check whether the read being requested would read from ROM.
    # If it would, check to see whether the system being used allows it.
    # If it doesn't, refuse to read it, throw error.
    def GetData(self, address, numBytes, checkRomRead = True):
        self.VerifyConnectedToDevice()
        if self.connectedToDevice:
            if self.HexToInt(address) < self.HexToInt("F50000") and checkRomRead:
                if "NO_ROM_READ" in self.deviceInfo:
                    print("ERROR: An attempt was made to read from ROM, but this operation is not supported for device of type '" + self.deviceInfo[0] + "'.")
                    return None
            jsonReadDataFromAddressCommand = {
                "Opcode" : "GetAddress",
                "Space"  : "SNES",
                "Operands" : [address, self.IntToHex(numBytes)]
            }
            self.ws.send(json.dumps(jsonReadDataFromAddressCommand))
            result = self.ws.recv()
            result = self.DataToHex(result)
            print("Read from address " + address + " was successful.")
            return result
        else:
            print("ERROR: Connection was not initialized properly before attempting to get data. Ignoring request...")
            return None
    
    # Write data to the specified address.
    # If checkRomWrite = True, check whether the write being requested would write to ROM.
    # If it would, check to see whether the system being used allows it.
    # If it doesn't, refuse to write it, throw error.
    def SetData(self, address, hexData, checkRomWrite = True):
        self.VerifyConnectedToDevice()
        if self.connectedToDevice:
            if self.HexToInt(address) < self.HexToInt("F50000") and checkRomWrite:
                if "NO_ROM_WRITE" in self.deviceInfo:
                    print("ERROR: An attempt was made to write to ROM, but this operation is not supported for device of type '" + self.deviceInfo[0] + "'.")
                    return None
            # Send Put Data Opcode
            numBytes = len(hexData) // 2
            jsonReadDataFromAddressCommand = {
                "Opcode" : "PutAddress",
                "Space"  : "SNES",
                "Operands" : [address, self.IntToHex(numBytes)]
            }
            self.ws.send(json.dumps(jsonReadDataFromAddressCommand))
            # Send Data
            self.ws.send(bytearray.fromhex(hexData))
            print("Write to address " + address + " was successful.")
        else:
            print("ERROR: Connection was not initialized properly before attempting to set data. Ignoring request...")
    
    # Checks for an overflow, and corrects it if one has occurred.
    # Used to check values before we alter them.
    @staticmethod
    def CheckValueOverflow(currentValue, amountToAdd, numBytes = 2):
        correctedAmountToAdd = amountToAdd
        if currentValue + amountToAdd < 0:
            correctedAmountToAdd += (currentValue + amountToAdd)
        elif currentValue + amountToAdd > ((2 ^ (numBytes * 8)) - 1):
            correctedAmountToAdd = ((2 ^ (numBytes * 8)) - 1) - currentValue
        return correctedAmountToAdd
    
    # Checks memory at a specific address to see if item value has overflown, corrects it if it has.
    # Used to check values after we rely on a game routine to change them.
    # This is really more of a failsafe in case people set absurd values for expansion amounts, but it won't work in singleplayer.
    # if bigToSmall is true, we're looking to see if a value has ended up smaller than it was initially. Otherwise, we're looking for the opposite.
    # Run after a small delay to allow the SNES to perform the operation.
    def __CheckValueAtAddressOverflow(self, address, lastValue, itemName, bigToSmall = True, numBytes = 2):
        currentValue = HexToInt(self.GetData(address))
        if currentValue == lastValue:
            print("CAUTION: Value of '" + itemName + "' has not updated by the time it could be checked - it is possible the CPU hasn't had time to change it, or the game state may have changed.")
            return
        if bigToSmall and currentValue < lastValue:
            print("WARNING: Value of '" + itemName + "' has overflowed because it became too big. This may be due to very large values being used for this item's reward amount. Setting its value to the maximum possible...")
            self.SetData("FF" * numBytes, address)
        elif not bigToSmall and currentValue > lastValue:
            print("WARNING: Value of '" + itemName + "' has overflowed because it became too small. This may be due to negative values being used for this item's reward amount. Setting its value to 0...")
            self.SetData("00" * numBytes, address)
    
    # Receive an item and display a message.
    # Works for all item types.
    # For ammo-type items, energy tanks, and reserve tanks, they will award whatever amount has been set in the player's patcher.
    # If this results in an overflow, their item amount will be set to its max possible value.
    # If showMessage is false, this will be done without displaying a message for player.
    # Note that this will automatically equip equipment items (will not equip Spazer and Plasma simultaneously)
    # Also note that this does not error out if player is not in game. We record entries to our queue even in menus.
    # It is the job of the inGameInvokeEventThread to check whether the state is correct before giving out the items.
    def ReceiveItem(self, itemName, sender, showMessage = True):        
        if itemName in self.itemList:
            # Lock this part to prevent overlapping with the event handling thread.
            self.lock.acquire()
            self.queuedEvents.append(self.__ReceiveItemInternal, [itemName, sender, showMessage], {})
            if self.inGameInvokeEventThread is None or not self.inGameInvokeEventThread.is_alive():
                self.inGameInvokeEventThread = threading.Thread(target = self.__ReceiveItemInternal)
                self.inGameInvokeEventThread.start()
            self.lock.release()
        else:
            print("ERROR: Super Metroid player was sent item '" + itemName + "', which is not known to be a valid Super Metroid item.")
    
    def TestMyLuck(self, itemName, sender, showMessage = True):
        self.__ReceiveItemInternal(itemName, sender, showMessage)
    
    # The part that actually does the thing.
    # Only called from event manager, will assume that state is permissible when run.
    # Always called from within a lock.
    def __ReceiveItemInternal(self, itemName, sender, showMessage = True):
        # Use the in-game event system to send a player their item.
        if showMessage:
            # 1C1F : 1000
            # 0A42 : F0FF
            
            # 65 AD
            # 01 00
            # 40 80
            # BF 8F
            # 40 00
            # 10 00
            # 39 99
            
            # Set message appropriately.
            # This doesn't need to be any particular value,
            # Any messagebox ID which maps to an item pickup will do.
            # In our case, the ID corresponds to Wave Beam.
            self.SetData("F51C1F", "1000")
            
            # Set the function to be called.
            self.SetData("F6FF72", "65AD")
            
            # Set the "Item Picked Up" word.
            # Any nonzero value will do.
            self.SetData("F6FF74", "0100")
            # Give item data needed to complete pickup.
            
            # Header/footer.
            # This is a standard item, so give the pointer to
            # An empty header/footer of correct width.
            width = "Small"
            if itemName in self.itemMessageWidths:
                width = self.itemMessageWidths[itemName]
            if width == "Small":
                self.SetData("F6FF76", "4080")
            elif width == "Large":
                self.SetData("F6FF76", "0080")
            
            # Content.
            # Different for each item - main message for an item pickup.
            self.SetData("F6FF78", self.ReverseEndianness(self.itemMessageAddresses[itemName]))
            
            # Message box size, in bytes.
            # Dictates height.
            size = "4000"
            if itemName in self.itemMessageNonstandardSizes:
                size = self.ReverseEndianness(self.itemMessageNonstandardSizes[itemName])
            self.SetData("F6FF7A", size)
            
            # Message ID. Should be accurate if it can be helped.
            # Also set to Wave Beam.
            self.SetData("F6FF7C", self.ReverseEndianness(self.itemMessageIDs[itemName]))
            
            # Get the original routine address and save it to jump to later.
            originalJumpDestination = self.GetData("F50A42", 2)
            
            self.SetData("F6FF80", originalJumpDestination)
            
            # Item Collection Routine.
            # What we actually call on pickup.
            self.SetData("F6FF7E", self.itemRoutineDict[itemName])
            
            
            
            
            # ACTUAL INSTRUCTION
            self.SetData("F50A42", "F0FF")
            
            
            
        # Otherwise, directly add the item to their inventory.
        else:
            pass
    # For displaying an arbitrary message
    # Will do its damnedest to display a string it has been given.
    # Note that SM messages have a maximum size, both total and for individual lines.
    # A line cannot exceed 26 characters, and there are at most 4 lines available
    # For standard text. This may be alterable, but treat this as a hard limit for now.
    # If you want it to include linebreaks at specific places, include linebreak characters.
    # Otherwise it will try to find good breaks in the string by itself.
    def ReceiveMessage(message, width = "Variable", size = None):
        pass
    
    # The part that actually does the thing.
    # Only called from event manager, will assume that state is permissible when run.
    # Always called from within a lock.
    def __ReceiveMessageInternal(message, width = "Variable", size = None):
        pass
    # Increment (or decrement) the amount of an item that a player has.
    # NOTE: This will not work with unique items (ex. Charge Beam, Gravity Suit)
    # These types of items are stored as bitflags, not integers.
    # This will work with Missiles, Supers, Power Bombs, E-Tanks, and Reserve Tanks
    # If maxAmountOnly is true, this will not increment the player's current number of this item, only the capacity for this item.
    # 7E:0A12 - 7E:0A13 Mirror's Samus's health. Used to check to make hurt sound and flash.
    def IncrementItem(self, itemName, incrementAmount, maxAmountOnly = False):
        if itemName in ammoItemList:
            pass
        else:
            if itemName in toggleItemList:
                print("ERROR: IncrementItem cannot be called with item '" + itemName + "', as this item is not represented by an integer.")
            else:
                print("ERROR: Super Metroid player had item '" + itemName + "' incremented, but this item is not a valid Super Metroid item.")
    
    # Take away a player's bitflag-type item if they have it.
    # This will also unequip it.
    def TakeAwayItem(self, itemName):
        if itemName in toggleItemList:
            pass
        else:
            if itemName in ammoItemList:
                print("ERROR: TakeAwayItem cannot be called with item '" + itemName + "', as this item is represented by an integer and not a bitflag.")
            else:
                print("ERROR: Super Metroid player had item '" + itemName + "' taken away, but this item is not a valid Super Metroid item.")
    
    # Sends an info request.
    # Returns true if it receives a result.
    # Returns false if the request fails.
    def VerifyConnectedToDevice(self):
        if self.connectionInitialized:
            try:
                jsonGetDeviceInfoCommand = {
                    "Opcode" : "Info",
                    "Space"  : "SNES"
                }
                self.ws.send(json.dumps(jsonGetDeviceInfoCommand))
                result = self.ws.recv()
                result = (json.loads(result))["Results"]
                if len(result) < 1:
                    print("ERROR: No device info could be found. Device has not successfully attached.")
                    return False
                else:
                    self.deviceInfo = result
                    self.connectedToDevice = True
                    return True
            except Exception:
                print("ERROR: Failed to send verification message to QUSB2SNES. Marking connection as closed...")
                self.connectionInitialized = False
                self.connectedToDevice = False
                self.deviceInfo = None
                return False
        else:
            print("ERROR: Cannot verify that device has been connected, as the connection to QUSB2SNES has not been initialized. Attempting to reestablish connection...")
            self.ConnectToDevice()
            #self.deviceInfo = None
            #self.connectedToDevice = False
            return False
        
    # Check game to make sure it's Super Metroid.
    def VerifyCorrectGame(self):
        self.VerifyConnectedToDevice()
        if self.connectedToDevice:
            gameType = self.deviceInfo[2].strip()
            if gameType == "No Info":
                print("CAUTION: Could not determine current game. This could be because the device connected is an SNES Classic, or because of a reason I haven't thought of.")
                self.inSuperMetroid = True
                return True
            if gameType == "Super Metroid":
                self.inSuperMetroid = True
                return True
            else:
                print("ERROR: Could not verify game being played as Super Metroid. According to QUSB2SNES, this device is currently running " + gameType + ".")
                self.inSuperMetroid = False
                return False
        else:
            self.inSuperMetroid = False
            return False
    
    # Check game version.
    # Either NTSC or PAL
    # Note that NTSC-U and NTSC-J are identical.
    def GetGameVersion(self):
        pass
    
    # Check to see if player is ready to have an event inserted.
    def IsPlayerReadyForEvent(self):
        self.VerifyInGameplay()
        if self.playingGame:
            # Query function slot to make sure it isn't currently occupied.
            functionSlot = self.GetData("F51E7D", 2)
            if functionSlot == "0000":
                return True
            else:
                return False
        else:
            return False
    
    # Query if the player is currently in a fully loaded save.
    # This ensures that we can read important values from RAM, such as item counts, without fearing garbage data.
    def VerifyGameLoaded(self):
        self.VerifyCorrectGame()
        if self.inSuperMetroid:
            gameState = self.GetGameState()
            validGameStates = ["In Game", "In Room Transition", "On Elevator", "Pausing", "Paused", "Unpausing"]
            if gameState in validGameStates:
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
    def VerifyInGameplay(self):
        self.VerifyGameLoaded()
        if self.gameLoaded:
            gameState = self.GetGameState()
            if gameState == "In Game":
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
    def GetGameState(self):
        self.VerifyCorrectGame()
        if self.inSuperMetroid:
            status = self.HexToInt(self.GetData("F50998", 1))
            if   status == 1:
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
            elif status == 10 or  status == 11:
                return "On Elevator"
            elif status >= 12 and status <= 14:
                return "Pausing"
            elif status == 15:
                return "Paused"
            elif status >= 16 and status <= 20:
                return "Unpausing"
            elif status >= 21 and status <= 26:
                return "Dead"
            elif status >= 30 and status <= 36:
                return "In Cutscene"
            elif status == 42:
                return "Watching Demo"
            else:
                return "Status Not Known"
        else:
            print("ERROR: An attempt was made to query game state, but something other than the game Super Metroid seems to be loaded.")
    
    # Returns a pretty string saying where player is.
    # Room and region name.
    # 7E:07BD - 7E:07BF : 3 byte pointer to room tilemap.
    def GetPlayerLocation(self):
        pass

    def GetPlayerInventory(self):
        self.VerifyGameLoaded()
        if self.gameLoaded:
            self.GetPlayerAmmoCounts()
            self.GetPlayerToggleItems()
        else:
            print("ERROR: An attempt was made to query the player's inventory, but they aren't in the game yet.")
    
    def GetPlayerAmmoCounts(self):
        self.VerifyGameLoaded()
        if self.gameLoaded:
            ammoItemList         = []
            ammoItemCurrentCount = []
            ammoItemMaximumCount = []
            # Get player's ammo counts.
            for itemName, address in self.ammoItemAddresses.items():
                ammoItemList.append(itemName)
                currentAmmo = self.GetData(address, 2)
                ammoItemCurrentCount.append(self.HexToInt(self.ReverseEndianness(currentAmmo)))
                maxAmmoAddress = self.PadHex(self.IntToHex(self.HexToInt(address) + 2), 6)
                maximumAmmo = self.GetData(maxAmmoAddress, 2)
                ammoItemMaximumCount.append(self.HexToInt(self.ReverseEndianness(maximumAmmo)))
                # Reserve energy is backwards, for some reason.
                if itemName == "Reserve Tank":
                    index = len(ammoItemCurrentCount) - 1
                    ammoItemCurrentCount[index], ammoItemMaximumCount[index] = ammoItemMaximumCount[index], ammoItemCurrentCount[index]
            for i in range(len(ammoItemList)):
                print("Samus has " + str(ammoItemCurrentCount[i]) + " " + self.itemNameToQuantityName[(ammoItemList[i])] + " out of " + str(ammoItemMaximumCount[i]) + ".")
            self.ammoItemList         = ammoItemList
            self.ammoItemCurrentCount = ammoItemCurrentCount
            self.ammoItemMaximumCount = ammoItemMaximumCount
        else:
            print("ERROR: An attempt was made to query the player's ammo counts, but they aren't in the game yet.")
    
    def GetPlayerToggleItems(self):
        self.VerifyGameLoaded()
        if self.gameLoaded:
            toggleItemHex = self.GetData(self.toggleItemBaseAddress, 8)
            obtainedItems = []
            equippedItems = []
            for itemName, byteBitOffsetPair in self.toggleItemBitflagOffsets.items():
                obtainedByte = toggleItemHex[((byteBitOffsetPair[0] * 2) + 4) : ((byteBitOffsetPair[0] * 2) + 6)]
                equippedByte = toggleItemHex[(byteBitOffsetPair[0] * 2) : ((byteBitOffsetPair[0] * 2) + 2)]
                obtainedVal = self.HexToInt(obtainedByte)
                equippedVal = self.HexToInt(equippedByte)
                bitToCheck = 1 << byteBitOffsetPair[1]
                if (obtainedVal & bitToCheck) != 0:
                    obtainedItems.append(itemName)
                if (equippedVal & bitToCheck) != 0:
                    equippedItems.append(itemName)
                    if itemName not in obtainedItems:
                        print("WARNING: Player has equipped item '" + itemName + "', but they haven't obtained it yet.")
            self.obtainedToggleItems = obtainedItems
            self.equippedToggleItems = equippedItems
            for itemName in obtainedItems:
                displayString = "Samus has obtained " + itemName
                if itemName in equippedItems:
                    displayString += ", and has it equipped."
                else:
                    displayString += ", but does not have it equipped."
                print(displayString)
        else:
            print("ERROR: An attempt was made to query the player's toggle items, but they aren't in the game yet.")

    # Check if player has debug mode on.
    def GetPlayerDebugState(self):
        pass

    # Check if player has sounds enabled.
    def GetSoundsEnabled(self):
        pass

    # Get what region player is in right now.
    def GetRegionNumber(self):
        pass

    # Get what map coordinates player is in right now.
    def GetMapCoordinates(self):
        pass

    # Get what tiles in current region player has visited.
    # 7E:07F7 - 7E:08F6 : Map tiles explored for current area (1 tile = 1 bit)
    def GetMapCompletion(self):
        pass
    
    # Check if player has automap enabled.
    def GetAutomapEnabled(self):
        pass
    
    # Used to take away X-Ray Scope and Grapple Beam.
    # 7E:09D2 - 7E:09D3 : Currently selected status bar item	
    def __SetStatusBarSelection(self):
        pass
    
    # I don't know if this is strictly necessary, but it can't possibly hurt.
    def CloseConnection(self):
        if self.connectionInitialized:
            self.ws.close()
        else:
            print("WARNING: Connection cannot be closed, as no connection was initialized. Ignoring request...")
    
    # This method handles making sure requests don't overlap, and that requests wait for one another to finish.
    # Not all requests need to be handled this way, such as those which only read from memory.
    def HandleRequestQueue(self):
        pass

if __name__ == "__main__":
    interface = SuperMetroidInterface()
    menu  = "C: Initialize Connection\n"
    menu += "D: Attach to a Device\n"
    menu += "I: Query Inventory\n"
    menu += "S: Query Gamestate\n"
    menu += "R: Query If Player is Ready for an Item\n"
    menu += "T: Test My Luck\n"
    menu += "Q: Quit"
    lastInput = None
    while lastInput != "Q":
        print(menu)
        lastInput = input()[0]
        if   lastInput == "C":
            print("\nAttempting to connect...")
            interface.InitializeConnection()
        elif lastInput == "D":
            print("\nAttempting to attach to a device...")
            interface.ConnectToDevice()
        elif lastInput == "I":
            print("\nAttempting to query inventory...")
            interface.GetPlayerInventory()
        elif lastInput == "S":
            print("\nAttemtping to query game state...")
            state = interface.GetGameState()
            if state is not None:
                print("Current State: " + state)
        elif lastInput == "R":
            print("\nQuerying whether Samus is ready for an item...")
            readiness = interface.IsPlayerReadyForItem()
            if   readiness == True:
                print("Samus is ready to receive an item.")
            elif readiness == False:
                print("Samus isn't ready to receive an item.")
        elif lastInput == "T":
            print("Testing luck...")
            interface.TestMyLuck("Morph Ball", "Galactic Federation HQ")
        elif lastInput == "Q":
            print("\nQuitting...")
            interface.CloseConnection()
        else:
            print("\nERROR: Input '" + str(lastInput) + "' not recognized")
        
        
    
    
    