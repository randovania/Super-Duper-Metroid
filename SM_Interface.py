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

import threading
import json
import pprint
import websocket
import time
import os
from websocket import create_connection
from hexhelper import HexHelper

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
    
    # These get imported dynamically from a JSON file created by the patcher.
    # This is necessary because these may not always be in the same place every game.
    itemRoutineDict = {
        "Energy Tank"             : None,
        "Missile Expansion"       : None,
        "Super Missile Expansion" : None,
        "Power Bomb Expansion"    : None,
        "Grapple Beam"            : None,
        "X-Ray Scope"             : None,
        "Varia Suit"              : None,
        "Spring Ball"             : None,
        "Morph Ball"              : None,
        "Screw Attack"            : None,
        "Hi-Jump Boots"           : None,
        "Space Jump"              : None,
        "Speed Booster"           : None,
        "Charge Beam"             : None,
        "Ice Beam"                : None,
        "Wave Beam"               : None,
        "Spazer Beam"             : None,
        "Plasma Beam"             : None,
        "Morph Ball Bombs"        : None,
        "Reserve Tank"            : None,
        "Gravity Suit"            : None,
        "No Item"                 : None
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
    
    # What address we should look at to find equipment (from SNI's perspective, it's complicated)
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
    
    # TODO: Import this dynamically from the patcher
    ammoItemToQuantity = {
        "Energy Tank"             : 100,
        "Missile Expansion"       : 5,
        "Super Missile Expansion" : 5,
        "Power Bomb Expansion"    : 5,
        "Reserve Tank"            : 100
    }
    
    obtainedToggleItems  = []
    equippedToggleItems  = []
    
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
    
    
    lock = threading.Lock()
    inGameInvokeEventThread = None
    # Format of a queued event:
    # Will check to see if args or kwargs are not present, will omit them if this is the case.
    # Note that you should still have three elements in the base list, as it will naiively index it.
    # Just set unused things to be either empty or None
    # [function, [arg1, arg2, ...], {kw1 : kwarg1, kw2 : kwarg2, ...}]
    queuedEvents = []
    
    # Small routines used to wrap simple operations for readability.
    
    # Load necessary data from patcher output JSON file.
    def __init__(self, patcherOutputFilePath):
        jsonFile = open(patcherOutputFilePath)
        jsonData = json.load(jsonFile)
        itemRoutines = ((jsonData["patcherData"])[0])["itemRoutines"]
        for routine in itemRoutines:
            itemName = routine["itemName"]
            itemRoutineAddress = routine["routineAddress"]
            self.itemRoutineDict[itemName] = itemRoutineAddress
        jsonFile.close()
            
    
    # These methods are used to directly interface with the game.
    # They will be called by higher-level code.
    def InitializeConnection(self):
        try:
            self.webSocket = create_connection('ws://localhost:8080')
            print("Connection made with SNI successfully.")
            self.connectionInitialized = True
        except Exception:
            print("ERROR: Could not connect to SNI.")
    
    # After connecting to SNI, get list of devices and connect to the first.
    def ConnectToDevice(self):
        if self.connectionInitialized:
            # Get devices.
            jsonGetDevicesCommand = {
                "Opcode" : "DeviceList",
                "Space"  : "SNES"
            }
            
            self.webSocket.send(json.dumps(jsonGetDevicesCommand))
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
            deviceToConnectTo = [result[0]]
            jsonAttachToDeviceCommand = {
                "Opcode"   : "Attach",
                "Space"    : "SNES",
                "Operands" : deviceToConnectTo
            }
            self.webSocket.send(json.dumps(jsonAttachToDeviceCommand))
            self.VerifyConnectedToDevice()
            self.PrintDeviceInfo()
            if(self.connectedToDevice):
                print("Successfully connected to device.")
        else:
            print("ERROR: An attempt was made to connect to a device, but no connection has been made with SNI.")
    
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
            if HexHelper.hexToInt(address) < HexHelper.hexToInt("F50000") and checkRomRead:
                if "NO_ROM_READ" in self.deviceInfo:
                    print(f"ERROR: An attempt was made to read from ROM, but this operation is not supported for device of type '{self.deviceInfo[0]}'.")
                    return None
            jsonReadDataFromAddressCommand = {
                "Opcode" : "GetAddress",
                "Space"  : "SNES",
                "Operands" : [address, HexHelper.intToHex(numBytes)]
            }
            self.webSocket.send(json.dumps(jsonReadDataFromAddressCommand))
            result = self.webSocket.recv()
            result = HexHelper.dataToHex(result)
            print(f"Read from address {address} was successful.")
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
            if HexHelper.hexToInt(address) < HexHelper.hexToInt("F50000") and checkRomWrite:
                if "NO_ROM_WRITE" in self.deviceInfo:
                    print(f"ERROR: An attempt was made to write to ROM, but this operation is not supported for device of type '{self.deviceInfo[0]}'.")
                    return None
            # Send Put Data Opcode
            numBytes = len(hexData) // 2
            jsonReadDataFromAddressCommand = {
                "Opcode" : "PutAddress",
                "Space"  : "SNES",
                "Operands" : [address, HexHelper.intToHex(numBytes)]
            }
            self.webSocket.send(json.dumps(jsonReadDataFromAddressCommand))
            # Send Data
            self.webSocket.send(HexHelper.hexToData(hexData))
            print(f"Write to address {address} was successful.")
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
            print(f"CAUTION: Value of '{itemName}' has not updated by the time it could be checked - it is possible the CPU hasn't had time to change it, or the game state may have changed.")
            return
        if bigToSmall and currentValue < lastValue:
            print(f"WARNING: Value of '{itemName}' has overflowed because it became too big. This may be due to very large values being used for this item's reward amount. Setting its value to the maximum possible...")
            self.SetData("FF" * numBytes, address)
        elif not bigToSmall and currentValue > lastValue:
            print(f"WARNING: Value of '{itemName}' has overflowed because it became too small. This may be due to negative values being used for this item's reward amount. Setting its value to 0...")
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
            try:
                self.queuedEvents.append((self.__ReceiveItemInternal, [itemName, sender, showMessage], {}))
                if self.inGameInvokeEventThread is None or not self.inGameInvokeEventThread.is_alive():
                    self.inGameInvokeEventThread = threading.Thread(target = self.__InvokeInGameEvents)
                    self.inGameInvokeEventThread.start()
            finally:
                self.lock.release()
        else:
            print(f"ERROR: Super Metroid player was sent item '{itemName}', which is not known to be a valid Super Metroid item.")
    
    def __InvokeInGameEvents(self):
        self.lock.acquire()
        try:
            while len(self.queuedEvents) > 0:
                if self.IsPlayerReadyForEvent():
                    print("Player is ready for event, sending now...")
                    currentEvent = self.queuedEvents.pop(0)
                    (currentEvent[0])(*currentEvent[1])
                else:
                    print("Player is not ready for event, waiting 300 milliseconds...")
                    time.sleep(0.3)
        finally:
            self.lock.release()
    
    # The part that actually does the thing.
    # Only called from event manager, will assume that state is permissible when run.
    # Always called from within a lock.
    def __ReceiveItemInternal(self, itemName, sender, showMessage = True):
        # Use the in-game event system to send a player their item.
        if showMessage:
            # Set message ID appropriately.
            # Needs to be a valid item ID (though not necessarily the message ID of the item the player received.)
            self.SetData("F51C1F", "1000")
            
            # Set the function to be called.
            # TODO: Verify this is correct
            self.SetData("F6FF72", "65AD")
            
            # Set the "Item Picked Up" word to 1.
            # Tells the game that the next item it gets will be from multi.
            self.SetData("F6FF74", "0100")
            # Give item data needed to complete pickup.
            
            # Header/footer.
            # This is a standard item, so give the pointer to
            # An empty header/footer of correct width.
            # TODO: Import these dynamically from patcher.
            width = "Small"
            if itemName in self.itemMessageWidths:
                width = self.itemMessageWidths[itemName]
            if width == "Small":
                self.SetData("F6FF76", "4080")
            elif width == "Large":
                self.SetData("F6FF76", "0080")
            
            # Content.
            # Different for each item - main message for an item pickup.
            # TODO: Import these dynamically from patcher.
            self.SetData("F6FF78", HexHelper.reverseEndianness(self.itemMessageAddresses[itemName]))
            
            # Message box size, in bytes.
            # Dictates height.
            size = "4000"
            if itemName in self.itemMessageNonstandardSizes:
                size = HexHelper.reverseEndianness(self.itemMessageNonstandardSizes[itemName])
            self.SetData("F6FF7A", size)
            
            # Message ID. Should be accurate if it can be helped.
            # Also set to Wave Beam.
            self.SetData("F6FF7C", HexHelper.reverseEndianness(self.itemMessageIDs[itemName]))
            
            # Get the original routine address and save it to jump to later.
            originalJumpDestination = self.GetData("F50A42", 2)
            
            self.SetData("F6FF80", originalJumpDestination)
            
            # Item Collection Routine.
            # What we actually call on pickup.
            self.SetData("F6FF7E", self.itemRoutineDict[itemName])
            
            # Overwrite an instruction pointer in the game's RAM.
            # This is what actually causes our code to execute.
            self.SetData("F50A42", "F0FF")
            
        # Otherwise, directly add the item to their inventory.
        else:
            if itemName in self.toggleItemList:
                self.GiveToggleItem(itemName)
            elif itemName in self.ammoItemList:
                # TODO: Change this part so that this is passed as an argument actually
                self.IncrementItem(itemName, self.ammoItemToQuantity[itemName])
            pass
    # For displaying an arbitrary message
    # TODO: Figure out how to do this.
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
    # TODO: Test to see if this introduces errors in HUD graphics.
    def IncrementItem(self, itemName, incrementAmount, maxAmountOnly = False):
        if itemName in self.ammoItemList:
            currentAmmoAddress = self.ammoItemAddresses[itemName]
            maxAmmoAddress = HexHelper.intToHex(HexHelper.hexToInt(currentAmmoAddress) + 2)
            currentAmmo = HexHelper.reverseEndianness(self.GetData(currentAmmoAddress, 2))
            maxAmmo     = HexHelper.reverseEndianness(self.GetData(maxAmmoAddress, 2))
            if maxAmountOnly:
                newCurrentAmmo = HexHelper.reverseEndianness(currentAmmo)
            else:
                newCurrentAmmo = HexHelper.reverseEndianness(HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(currentAmmo) + incrementAmount), 4))
            newMaxAmmo = HexHelper.reverseEndianness(HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(maxAmmo) + incrementAmount), 4))
            self.SetData(currentAmmoAddress, newCurrentAmmo)
            self.SetData(maxAmmoAddress, newMaxAmmo)
        else:
            if itemName in self.toggleItemList:
                print(f"ERROR: IncrementItem cannot be called with item '{itemName}', as this item is not represented by an integer.")
            else:
                print(f"ERROR: Super Metroid player had item '{itemName}' incremented, but this item is not a valid Super Metroid item.")
    
    # Give a player a bitflag-type item.
    # This will also equip it.
    def GiveToggleItem(self, itemName):
        if itemName in self.toggleItemList:
            itemOffset = self.toggleItemBitflagOffsets[itemName]
            equippedByteAddress = HexHelper.intToHex(HexHelper.hexToInt(self.toggleItemBaseAddress) + itemOffset[0])
            obtainedByteAddress = HexHelper.intToHex(HexHelper.hexToInt(equippedByteAddress) + 2)
            equippedByte = self.GetData(equippedByteAddress, 1)
            obtainedByte = self.GetData(obtainedByteAddress, 1)
            bitflag = 1 << itemOffset[1]
            newEquippedByte = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(equippedByte) | bitflag), 2)
            newObtainedByte = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(obtainedByte) | bitflag), 2)
            self.SetData(equippedByteAddress, newEquippedByte)
            self.SetData(obtainedByteAddress, newObtainedByte)
        else:
            if itemName in self.ammoItemList:
                print(f"ERROR: TakeAwayItem cannot be called with item '{itemName}', as this item is represented by an integer and not a bitflag.")
            else:
                print(f"ERROR: Super Metroid player had item '{itemName}' taken away, but this item is not a valid Super Metroid item.")
    
    # Take away a player's bitflag-type item if they have it.
    # This will also unequip it.
    def TakeAwayToggleItem(self, itemName):
        if itemName in self.toggleItemList:
            itemOffset = self.toggleItemBitflagOffsets[itemName]
            equippedByteAddress = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(self.toggleItemBaseAddress) + itemOffset[0]), 2)
            obtainedByteAddress = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(equippedByteAddress) + 2), 2)
            equippedByte = self.GetData(equippedByteAddress, 1)
            obtainedByte = self.GetData(obtainedByteAddress, 1)
            bitflag = 1 << itemOffset[1]
            # Do bitwise and with all ones (except the bitflag we want to turn off)
            newEquippedByte = HexHelper.intToHex(HexHelper.hexToInt(equippedByte) & (255 - bitflag))
            newObtainedByte = HexHelper.intToHex(HexHelper.hexToInt(obtainedByte) & (255 - bitflag))
            self.SetData(equippedByteAddress, newEquippedByte)
            self.SetData(obtainedByteAddress, newObtainedByte)
        else:
            if itemName in self.ammoItemList:
                print(f"ERROR: TakeAwayItem cannot be called with item '{itemName}', as this item is represented by an integer and not a bitflag.")
            else:
                print(f"ERROR: Super Metroid player had item '{itemName}' taken away, but this item is not a valid Super Metroid item.")
    
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
                self.webSocket.send(json.dumps(jsonGetDeviceInfoCommand))
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
            print("ERROR: Cannot verify that device has been connected, as the connection to SNI has not been initialized. Attempting to reestablish connection...")
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
                #print("CAUTION: Could not determine current game. This could be because the device connected is an SNES Classic, or because the interface hasn't exposed this information.")
                self.inSuperMetroid = True
                return True
            if gameType == "Super Metroid":
                self.inSuperMetroid = True
                return True
            else:
                print(f"ERROR: Could not verify game being played as Super Metroid. According to SNI, this device is currently running {gameType}.")
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
            functionSlot = self.GetData("F50A42", 2)
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
    def VerifyGameLoaded(self):
        self.VerifyCorrectGame()
        if self.inSuperMetroid:
            gameState = self.GetGameState()
            # We could technically give players items while pausing,
            # But this causes the pickup box to show up on a pitch black screen once
            # The player unpauses.
            # This may be confusing as players will not be able to see it.
            validGameStates = ["In Game", "In Room Transition"]
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
            status = HexHelper.hexToInt(self.GetData("F50998", 1))
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
                ammoItemCurrentCount.append(HexHelper.hexToInt(HexHelper.reverseEndianness(currentAmmo)))
                maxAmmoAddress = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(address) + 2), 6)
                maximumAmmo = self.GetData(maxAmmoAddress, 2)
                ammoItemMaximumCount.append(HexHelper.hexToInt(HexHelper.reverseEndianness(maximumAmmo)))
                # Reserve energy is backwards, for some reason.
                if itemName == "Reserve Tank":
                    index = len(ammoItemCurrentCount) - 1
                    ammoItemCurrentCount[index], ammoItemMaximumCount[index] = ammoItemMaximumCount[index], ammoItemCurrentCount[index]
            for i in range(len(ammoItemList)):
                print(f"Samus has {str(ammoItemCurrentCount[i])} {self.itemNameToQuantityName[(ammoItemList[i])]} out of {str(ammoItemMaximumCount[i])}.")
            self.ammoItemsHeldList         = ammoItemList
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
                obtainedVal  = HexHelper.hexToInt(obtainedByte)
                equippedVal  = HexHelper.hexToInt(equippedByte)
                bitToCheck   = 1 << byteBitOffsetPair[1]
                if (obtainedVal & bitToCheck) != 0:
                    obtainedItems.append(itemName)
                if (equippedVal & bitToCheck) != 0:
                    equippedItems.append(itemName)
                    if itemName not in obtainedItems:
                        print(f"WARNING: Player has equipped item '{itemName}', but they haven't obtained it yet.")
            self.obtainedToggleItems = obtainedItems
            self.equippedToggleItems = equippedItems
            for itemName in obtainedItems:
                displayString = f"Samus has obtained {itemName}"
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
    # TODO: Make more observations about data format
    def GetMapCompletion(self):
        pass
    
    # Check if player has automap enabled.
    def GetAutomapEnabled(self):
        pass
    
    # Used to take away X-Ray Scope and Grapple Beam.
    # 7E:09D2 - 7E:09D3 : Currently selected status bar item
    # TODO: Check whether this is necessary.
    # def __SetStatusBarSelection(self):
    #     pass
    
    # I don't know if this is strictly necessary, but it can't possibly hurt.
    def CloseConnection(self):
        if self.connectionInitialized:
            self.webSocket.close()
        else:
            print("WARNING: Connection cannot be closed, as no connection was initialized. Ignoring request...")
    
    # This method handles making sure requests don't overlap, and that requests wait for one another to finish.
    # Not all requests need to be handled this way, such as those which only read from memory.
    def HandleRequestQueue(self):
        pass

if __name__ == "__main__":
    if os.path.isfile(os.getcwd() + "\\romfilepath.txt"):
        f = open(os.getcwd() + "\\romfilepath.txt", 'r')
        patchFilePath = f.readline().rstrip()
        patchFilePath = patchFilePath[-len(patchFilePath):-4]
        patchFilePath += "_PatcherData.json"
        f.close()
    else:
        print("Enter the path to the PatchData file that was generated when you patched your ROM.")
        patchFilePath = input()
    interface = SuperMetroidInterface(patchFilePath)
    menu  = "C: Initialize Connection\n"
    menu += "D: Attach to a Device\n"
    menu += "I: Query Inventory\n"
    menu += "S: Query Gamestate\n"
    menu += "R: Query If Player is Ready for an Item\n"
    menu += "W: Send Wave Beam\n"
    menu += "G: Force Give Screw Attack\n"
    menu += "T: Force Take Screw Attack\n"
    menu += "M: Force Give 5 Missiles\n"
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
                print(f"Current State: {state}")
        elif lastInput == "R":
            print("\nQuerying whether Samus is ready for an item...")
            readiness = interface.IsPlayerReadyForItem()
            if   readiness == True:
                print("Samus is ready to receive an item.")
            elif readiness == False:
                print("Samus isn't ready to receive an item.")
        elif lastInput == "W":
            print("Trying to send Wave Beam...")
            interface.ReceiveItem("Wave Beam", "Galactic Federation HQ")
        elif lastInput == "G":
            print("Manually Giving Screw Attack...")
            interface.GiveToggleItem("Screw Attack")
        elif lastInput == "T":
            print("Manually Taking Screw Attack...")
            interface.TakeAwayToggleItem("Screw Attack")
        elif lastInput == "M":
            print("Manually Giving 5 Missiles...")
            interface.IncrementItem("Missile Expansion", 5)
        elif lastInput == "Q":
            print("\nQuitting...")
            interface.CloseConnection()
        else:
            print(f"\nERROR: Input '{str(lastInput)}' not recognized")